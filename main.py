import os
import sys
import traci
import sqlite3
import csv
import random
import math

# ==========================================
#               仿真全局配置参数 
# ==========================================
SIM_STEPS = 10800              # 仿真总时长 (3小时 = 10800 秒)
DETOUR_PROBABILITY = 0.7       # 绕行概率阈值 (70% 的车辆会因为拥堵费绕路)
INITIAL_BALANCE = 100.0        # 账户初始余额 (元)

# 基于距离的收费参数
BASE_RATE_PER_KM = 2.0         # 基础费率：畅通时每公里 2.0 元
CHARGE_INTERVAL_METERS = 500.0 # 虚拟收费门架：每累计行驶 500 米（0.5公里）触发一次账单结算
TOLL_THRESHOLD_HIGH = 5.0      # 触发绕行博弈的敏感费率（元/公里）

# CBD 核心区地理围栏坐标
CBD_X_MIN, CBD_X_MAX = 99.26, 701.14
CBD_Y_MIN, CBD_Y_MAX = -510.77, 312.23

def get_toll_fee_per_km(vehicle_count):
    """
    连续型 Logistic 动态定价机制
    替代原有的阶梯式跳变费率。
    确保价格随拥堵度平滑上升，更符合真实的交通经济学模型。
    """

    # 基础乘数 1，最高乘数 10，拐点在 40 辆车
    congestion_multiplier = 1 + 9 / (1 + math.exp(-0.08 * (vehicle_count - 40)))
    return BASE_RATE_PER_KM * congestion_multiplier

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

# 将原有的 run_simulation() 改为带参数的函数
def run_simulation(enable_tolling=True, output_csv="weihai_analysis_report.csv"):
    """
    核心仿真主函数
    :param enable_tolling: 是否开启动态收费与绕行博弈（True为实验组，False为基线组）
    :param output_csv: 数据报表导出路径
    """
    traci.start(sumo_cmd)
    
    # 只有开启收费时，才连接数据库
    if enable_tolling:
        conn = sqlite3.connect("weihai_toll_system.db", isolation_level=None)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS Wallet (veh_id TEXT PRIMARY KEY, balance REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS Logs (id INTEGER PRIMARY KEY AUTOINCREMENT, veh_id TEXT, amount REAL, step INTEGER)")
        # 注意：后续可以按建议新增 Trips 表

    csv_file = open(output_csv, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["Time_Step", "Vehicles_in_CBD", "Current_Toll_Fee", "Average_Speed_mps", "Total_Revenue", "Detoured_Vehicles"])

    step = 0
    total_revenue = 0.0
    total_detoured = 0
    veh_distance_tracker = {}  

    # 绘制 CBD 电子围栏

    try:

        traci.polygon.add(

            polygonID="CBD_ZONE",

            shape=[(CBD_X_MIN, CBD_Y_MIN), (CBD_X_MAX, CBD_Y_MIN), (CBD_X_MAX, CBD_Y_MAX), (CBD_X_MIN, CBD_Y_MAX), (CBD_X_MIN, CBD_Y_MIN)],

            color=(255, 0, 0, 150), fill=False, lineWidth=8

        )

    except:

        pass 

    mode_name = "【动态收费模式】" if enable_tolling else "【无收费基线模式】"
    print(f"\n--- 仿真启动，当前执行: {mode_name} ---")

    try:
        while step < SIM_STEPS:
            traci.simulationStep()
            all_vehs = traci.vehicle.getIDList()
            vehs_in_cbd = []
            total_speed = 0.0

            for v_id in all_vehs:
                x, y = traci.vehicle.getPosition(v_id)
                speed = traci.vehicle.getSpeed(v_id)
                total_speed += speed
                if CBD_X_MIN <= x <= CBD_X_MAX and CBD_Y_MIN <= y <= CBD_Y_MAX:
                    vehs_in_cbd.append((v_id, speed))

            cbd_count = len(vehs_in_cbd)
            avg_speed = (total_speed / len(all_vehs)) if all_vehs else 0.0
            
            # 【关键区别】：如果不收费，费率强制为 0
            current_fee_per_km = get_toll_fee_per_km(cbd_count) if enable_tolling else 0.0

            # --- 核心业务逻辑 ---
            if enable_tolling:
                for v_id, speed in vehs_in_cbd:
                    if v_id not in veh_distance_tracker:
                        veh_distance_tracker[v_id] = 0.0
                    veh_distance_tracker[v_id] += speed
                    
                    if veh_distance_tracker[v_id] >= CHARGE_INTERVAL_METERS:
                        charge_amount = current_fee_per_km * (CHARGE_INTERVAL_METERS / 1000.0)
                        try:
                            conn.execute("BEGIN TRANSACTION")
                            cursor.execute("INSERT OR IGNORE INTO Wallet VALUES (?, ?)", (v_id, INITIAL_BALANCE))
                            cursor.execute("UPDATE Wallet SET balance = balance - ? WHERE veh_id = ?", (charge_amount, v_id))
                            cursor.execute("INSERT INTO Logs (veh_id, amount, step) VALUES (?, ?, ?)", (v_id, charge_amount, step))
                            total_revenue += charge_amount
                            veh_distance_tracker[v_id] -= CHARGE_INTERVAL_METERS 

                            if current_fee_per_km >= TOLL_THRESHOLD_HIGH and random.random() < DETOUR_PROBABILITY:
                                traci.vehicle.rerouteTraveltime(v_id) 
                                total_detoured += 1
                                traci.vehicle.setColor(v_id, (0, 100, 255))
                            else:
                                traci.vehicle.setColor(v_id, (255, 0, 0))
                            conn.execute("COMMIT") 
                        except Exception as e:
                            conn.execute("ROLLBACK") 
            else:
                # 【基线模式】：仅观察，不干预，全城亮绿色
                for v_id, _ in vehs_in_cbd:
                    traci.vehicle.setColor(v_id, (0, 255, 0))

            if step % 10 == 0:
                csv_writer.writerow([step, cbd_count, round(current_fee_per_km, 2), round(avg_speed, 2), round(total_revenue, 2), total_detoured])
                
                #在控制台打印实时数据
                if step % 1000 == 0:
                    if enable_tolling:
                        print(f"进度: {step}/{SIM_STEPS}s | CBD拥堵: {cbd_count}辆 | 动态费率: ¥{current_fee_per_km:.2f}/km | 财政总计: ¥{total_revenue:.2f}")
                    else:
                        print(f"进度: {step}/{SIM_STEPS}s | CBD拥堵: {cbd_count}辆 | [无收费基线测试中...]")
            step += 1

    except Exception as e:
        print(f"\n[错误] 仿真异常: {e}")
    finally:
        csv_file.close()
        if enable_tolling:
            conn.close()
        traci.close()
        print(f"--- {mode_name} 运行完毕，数据已保存至 {output_csv} ---")

# ==========================================
# 自动化执行两组对照实验
# ==========================================
if __name__ == "__main__":
    print(">>> 开始执行基线对照实验 (Baseline Experiment) <<<")
    
    # 1. 跑第一遍：无收费对照组
    run_simulation(enable_tolling=False, output_csv="baseline_report.csv")
    
    # 2. 跑第二遍：动态收费实验组
    run_simulation(enable_tolling=True, output_csv="weihai_analysis_report.csv")