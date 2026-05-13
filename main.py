import os
import sys
import traci
import sqlite3
import csv
import random

# ==========================================
#               仿真全局配置参数 
# ==========================================
SIM_STEPS = 10800              # 仿真总时长 (3小时 = 10800 秒)
DETOUR_PROBABILITY = 0.7       # 绕行概率阈值 (70% 的车辆会因为拥堵费绕路)
TOLL_THRESHOLD_HIGH = 2.5      # 触发绕行博弈的拥堵费阈值 (元)
INITIAL_BALANCE = 100.0        # 账户初始余额 (元)

# CBD 核心区地理围栏坐标
CBD_X_MIN, CBD_X_MAX = 99.26, 701.14
CBD_Y_MIN, CBD_Y_MAX = -510.77, 312.23

# ==========================================
#               环境与工具初始化
# ==========================================
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("环境变量中未声明 'SUMO_HOME'，请配置后重试。")

# 启动命令配置 (包含路网、路由、绿地附加文件)

sumo_cmd = [
    "sumo-gui",
    "-n", "weihai_cbd.net.xml",
    "-r", "routes.rou.xml",
    "-a", "parks.add.xml",
    "--start"
]

def get_toll_fee(vehicle_count):
    """
    动态定价机制
    根据 CBD 区域内实时车辆密度，动态调整拥堵费费率。
    """
    if vehicle_count < 20:
        return 1.0  # 畅通状态，基础费率
    elif vehicle_count < 50:
        return 2.5  # 轻度拥堵，提高费率
    else:
        return 5.0  # 严重拥堵，惩罚性费率

def run_simulation():
    """核心仿真主函数"""
    traci.start(sumo_cmd)
    
    # --- 数据库持久化配置  ---
    conn = sqlite3.connect("weihai_toll_system.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS Wallet (veh_id TEXT PRIMARY KEY, balance REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS Logs (id INTEGER PRIMARY KEY AUTOINCREMENT, veh_id TEXT, amount REAL, step INTEGER)")
    conn.commit()

    # --- 数据报表输出配置  ---
    csv_file = open("weihai_analysis_report.csv", "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    
    csv_writer.writerow(["Time_Step", "Vehicles_in_CBD", "Current_Toll_Fee", "Average_Speed_mps", "Total_Revenue", "Detoured_Vehicles"])

    # 仿真状态变量
    step = 0
    total_revenue = 0.0
    total_detoured = 0
    processed_vehs = set()  # 已处理车辆集合，防止重复扣费

    # 绘制 CBD 电子围栏
    try:
        traci.polygon.add(
            polygonID="CBD_ZONE",
            shape=[(CBD_X_MIN, CBD_Y_MIN), (CBD_X_MAX, CBD_Y_MIN), (CBD_X_MAX, CBD_Y_MAX), (CBD_X_MIN, CBD_Y_MAX), (CBD_X_MIN, CBD_Y_MIN)],
            color=(255, 0, 0, 150), fill=False, lineWidth=8
        )
    except:
        pass 

    print("--- 仿真系统启动，开始执行动态收费模型 ---")

    try:
        # 主仿真循环
        while step < SIM_STEPS:
            traci.simulationStep()
            
            all_vehs = traci.vehicle.getIDList()
            vehs_in_cbd = []
            total_speed = 0.0

            # 检测车辆位置状态
            for v_id in all_vehs:
                x, y = traci.vehicle.getPosition(v_id)
                speed = traci.vehicle.getSpeed(v_id)
                total_speed += speed
                
                # 触发地理围栏判定
                if CBD_X_MIN <= x <= CBD_X_MAX and CBD_Y_MIN <= y <= CBD_Y_MAX:
                    vehs_in_cbd.append(v_id)

            # 计算当前时刻的交通指标
            cbd_count = len(vehs_in_cbd)
            current_fee = get_toll_fee(cbd_count)
            avg_speed = (total_speed / len(all_vehs)) if all_vehs else 0.0

            # --- 核心业务逻辑：金融事务处理与绕行博弈 ---
            for v_id in vehs_in_cbd:
                if v_id not in processed_vehs:
                    processed_vehs.add(v_id) 

                    try:
                        # 开启数据库事务，保证数据强一致性
                        conn.execute("BEGIN TRANSACTION")
                        
                        cursor.execute("INSERT OR IGNORE INTO Wallet VALUES (?, ?)", (v_id, INITIAL_BALANCE))
                        cursor.execute("UPDATE Wallet SET balance = balance - ? WHERE veh_id = ?", (current_fee, v_id))
                        cursor.execute("INSERT INTO Logs (veh_id, amount, step) VALUES (?, ?, ?)", (v_id, current_fee, step))
                        
                        total_revenue += current_fee

                        # 驾驶员行为决策模型 
                        if current_fee >= TOLL_THRESHOLD_HIGH and random.random() < DETOUR_PROBABILITY:
                            traci.vehicle.rerouteTraveltime(v_id) # 触发重新路由
                            total_detoured += 1
                            traci.vehicle.setColor(v_id, (0, 100, 255)) # 蓝色: 绕行车
                        else:
                            traci.vehicle.setColor(v_id, (255, 0, 0)) # 红色: 付费车
                        
                        conn.commit() # 提交事务
                    except Exception as e:
                        conn.rollback() # 异常回滚
                        print(f"[{step}s] 车辆 {v_id} 交易事务失败: {e}")

            # 数据采样与持久化 (每 10 秒记录一次)
            if step % 10 == 0:
                csv_writer.writerow([step, cbd_count, current_fee, avg_speed, total_revenue, total_detoured])
                
                # 终端输出
                if step % 1000 == 0:
                    print(f"进度: {step}/{SIM_STEPS}s | CBD拥堵度: {cbd_count}辆 | 动态费率: ¥{current_fee} | 累计财政收入: ¥{total_revenue:.2f}")

            step += 1

    except Exception as e:
        print(f"\n[致命错误] 仿真运行中发生异常: {e}")
    finally:
        # 防御性编程：无论程序如何终止，绝对保证资源安全释放
        print("\n--- 仿真结束，正在执行资源清理与数据落盘 ---")
        csv_file.close()
        conn.close()
        traci.close()
        print("--- 清理完成！请查看 weihai_analysis_report.csv 获取评估指标 ---")

if __name__ == "__main__":
    run_simulation()