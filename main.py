import os
import sys
import traci
import sqlite3

# --- 设定动态路费的规则 ---
def calculate_toll(current_vehicle_count):
    base_fee = 1.0  
    if current_vehicle_count < 10:   #车辆数量小于10的时候保持一块钱
        return base_fee
    elif 10 <= current_vehicle_count <= 20:   #车辆数量10-20的时候保持2.5
        return base_fee * 2.5
    else:                                  #大于20的时候收费5块
        return base_fee * 5.0

# --- 基础环境配置 ---
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请配置 SUMO_HOME 环境变量")

# 运行时自动打开sumo界面
sumoCmd = ["sumo-gui", "-c", "sim.sumocfg"] 
traci.start(sumoCmd)

conn = sqlite3.connect('tolling_system.db')
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS Wallet (
        vehicle_id TEXT PRIMARY KEY,
        balance REAL
    )
''')

print("---  动态定价、ETC扣费与自动绕行系统已全面启动 ---")

step = 0
while step < 100:  
    traci.simulationStep() 
    
    active_vehicles = traci.vehicle.getIDList()
    vehicle_count = len(active_vehicles)
    current_toll_fee = calculate_toll(vehicle_count)
    
    # 打印实时路况
    print(f"第 {step} 秒 | 路网车辆: {vehicle_count} 辆 | 过路费: ¥ {current_toll_fee}")
    
    # 逐辆车扫描
    for veh_id in active_vehicles:
        cursor.execute("SELECT balance FROM Wallet WHERE vehicle_id = ?", (veh_id,))
        result = cursor.fetchone()
        
        if result is None:
            # 新车入网，先扣费
            new_balance = 100.0 - current_toll_fee
            cursor.execute("INSERT INTO Wallet (vehicle_id, balance) VALUES (?, ?)", (veh_id, new_balance))
            
            # 
            # 如果当前过路费已经涨到了 2.5 元（轻度拥堵）或更高
            if current_toll_fee >= 2.5:
                # 强行让小车改道绕路
                traci.vehicle.setRouteID(veh_id, "route_bypass")
                print(f"   -> 新车 {veh_id} 扣款 ¥{current_toll_fee} | 嫌贵/太堵，已强制绕行小路！")
            else:
                print(f"   -> 新车 {veh_id} 扣款 ¥{current_toll_fee} | 畅通无阻，继续走主路。")

    conn.commit()
    step += 1

conn.close()
traci.close()