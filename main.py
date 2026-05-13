import os
import sys
import traci
import sqlite3
import csv
import random

# 1. 环境检查：确保能找到 SUMO 工具
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请先配置 SUMO_HOME 环境变量")

# 2. 数据库初始化 (满足 ACID 事务要求)
def init_database():
    conn = sqlite3.connect('weihai_tolling.db')
    cursor = conn.cursor()
    # 记录钱包余额
    cursor.execute('CREATE TABLE IF NOT EXISTS Wallet (veh_id TEXT PRIMARY KEY, balance REAL)')
    # 记录每一笔交易流水 (Transaction Log)
    cursor.execute('CREATE TABLE IF NOT EXISTS Logs (id INTEGER PRIMARY KEY AUTOINCREMENT, veh_id TEXT, amount REAL, step INTEGER)')
    conn.commit()
    return conn

# 3. 动态定价算法 (根据 CBD 拥堵数阶梯收费)
def get_toll_fee(vehicle_count):
    if vehicle_count < 30: return 1.0   # 畅通：1元
    elif vehicle_count < 80: return 2.5 # 拥挤：2.5元
    else: return 5.0                   # 极度拥堵：5元

def run_simulation():
    # --- 配置区：威高商圈电子围栏坐标 (Geofencing) ---
    # 请在运行 sumo-gui 后，鼠标悬停在威高广场区域，读取左下和右上坐标填在这里
    CBD_X_MIN, CBD_X_MAX = 97.71, 700.81
    CBD_Y_MIN, CBD_Y_MAX = -510.29, 310.81

    # 启动仿真 (关联威海地图和新生成的 4000 辆车)
    sumo_cmd = ["sumo-gui", "-n", "weihai_cbd.net.xml", "-r", "routes.rou.xml","-a", "parks.add.xml", "--start"]
    traci.start(sumo_cmd)
    
    conn = init_database()
    cursor = conn.cursor()

    # 开启 CSV 书记员：自动生成实验报表
    log_file = open('weihai_analysis_report.csv', 'w', newline='', encoding='utf-8')
    csv_writer = csv.writer(log_file)
    csv_writer.writerow(['秒数', 'CBD内车辆数', '实时电费', '全城平均时速', '政府总收入', '累计绕行人数'])

    step = 0
    total_revenue = 0
    total_detoured = 0

    print("--- 威海市威高商圈动态计费系统：全线启动 ---")
    try:
        traci.polygon.add(
            polygonID="CBD_ZONE", 
            # 👇 重点在这里：我们加了第5个点，让它连回起点，彻底闭合框框！
            shape=[
                (CBD_X_MIN, CBD_Y_MIN), # 1. 起点：左下角
                (CBD_X_MAX, CBD_Y_MIN), # 2. 连线到：右下角
                (CBD_X_MAX, CBD_Y_MAX), # 3. 连线到：右上角
                (CBD_X_MIN, CBD_Y_MAX), # 4. 连线到：左上角
                (CBD_X_MIN, CBD_Y_MIN)  # 5. 终点：连回左下角（补齐左边界！）
            ], 
            color=(255, 0, 0, 150), 
            fill=False, 
            lineWidth=8 
        )
    except:
        pass
    # 👇 终极修复：增加一个“已收费名单”，防止重复处理
    processed_vehs = set() 

    # 【视觉特效】在你的新地图上画出红色的收费结界
    try:
        traci.polygon.add(
            polygonID="CBD_ZONE", 
            shape=[(CBD_X_MIN, CBD_Y_MIN), (CBD_X_MAX, CBD_Y_MIN), (CBD_X_MAX, CBD_Y_MAX), (CBD_X_MIN, CBD_Y_MAX), (CBD_X_MIN, CBD_Y_MIN)], 
            color=(255, 0, 0, 150), 
            fill=False, 
            lineWidth=8 
        )
    except:
        pass 

    while step < 10800:  
        traci.simulationStep()
        
        all_vehs = traci.vehicle.getIDList()
        vehs_in_cbd = []
        total_speed = 0

        # 判断小车是否踏入收费区
        for v_id in all_vehs:
            x, y = traci.vehicle.getPosition(v_id)
            speed = traci.vehicle.getSpeed(v_id)
            total_speed += speed
            
            if CBD_X_MIN <= x <= CBD_X_MAX and CBD_Y_MIN <= y <= CBD_Y_MAX:
                vehs_in_cbd.append(v_id)

        cbd_count = len(vehs_in_cbd)
        current_fee = get_toll_fee(cbd_count)
        avg_speed = (total_speed / len(all_vehs)) if all_vehs else 0

        # --- 数据库扣款与绕行博弈 (只执行一次) ---
        for v_id in vehs_in_cbd:
            # 👇 核心逻辑：如果这辆车没被处理过，才进去处理
            if v_id not in processed_vehs:
                processed_vehs.add(v_id) # 盖个章：已收费！

                try:
                    conn.execute("BEGIN TRANSACTION")
                    cursor.execute("INSERT OR IGNORE INTO Wallet VALUES (?, 100.0)", (v_id,))
                    cursor.execute("UPDATE Wallet SET balance = balance - ? WHERE veh_id = ?", (current_fee, v_id))
                    cursor.execute("INSERT INTO Logs (veh_id, amount, step) VALUES (?, ?, ?)", (v_id, current_fee, step))
                    total_revenue += current_fee

                    # 绕行判定：一经决定，永不更改
                    if current_fee >= 2.5 and random.random() < 0.7:
                        traci.vehicle.rerouteTraveltime(v_id) # 重新规划路线
                        total_detoured += 1
                        traci.vehicle.setColor(v_id, (0, 100, 255)) # 变成蓝色绕行车
                    else:
                        traci.vehicle.setColor(v_id, (255, 0, 0)) # 变成红色土豪车
                    
                    conn.commit() 
                except Exception as e:
                    conn.rollback() 
                    print(f"事务失败: {e}")

        # 每 10 秒记录一次数据
        if step % 10 == 0:
            csv_writer.writerow([step, cbd_count, current_fee, avg_speed, total_revenue, total_detoured])
            if step % 1000 == 0:
                print(f"进度: {step}/10800s | CBD人数: {cbd_count} | 累计收入: ¥{total_revenue:.2f}")

        step += 1

    log_file.close()
    conn.close()
    traci.close()
    print("--- 实验结束！请查看 weihai_analysis_report.csv 获取分析数据 ---")

if __name__ == "__main__":
    run_simulation()