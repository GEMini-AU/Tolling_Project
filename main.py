import os
import sys
import traci
import sqlite3   #导入数据库
import random    #导入随机函数

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

cursor.execute("DROP TABLE IF EXISTS Wallet")  #每次运行删掉以前的表，保证每次仿真是零起点

cursor.execute('''
    CREATE TABLE IF NOT EXISTS Wallet (
        vehicle_id TEXT PRIMARY KEY,
        balance REAL
    )
''')

print("---  动态定价、ETC扣费与自动绕行系统已全面启动 ---")


step = 0
while step < 400:  
    traci.simulationStep() 
    
    # 获取全网所有车辆
    active_vehicles = traci.vehicle.getIDList()
    
    # 站长只数“收费主路(road_toll)”上有多少辆车
    cars_on_toll_road = traci.edge.getLastStepVehicleIDs("road_toll")
    toll_road_count = len(cars_on_toll_road)
    
    # 算价格
    current_toll_fee = calculate_toll(toll_road_count)
    
    print(f"第 {step} 秒 | 主路拥堵: {toll_road_count} 辆 | 过路费: ¥ {current_toll_fee}")
    

    
    
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
            # 【终极优化：模拟真实人类的选择概率】
            if current_toll_fee >= 2.5:
                # 掷骰子：生成一个 0 到 1 之间的随机数。如果小于 0.7（即70%的概率）
                if random.random() < 0.70:
                    # 这 70% 的人嫌贵，强制绕路
                    traci.vehicle.setRouteID(veh_id, "route_bypass")
                    print(f"   -> 💳 新车 {veh_id} 扣款 ¥{current_toll_fee} | 嫌贵绕行！(价格敏感型)")
                else:
                    # 剩下 30% 的人是土豪或赶时间，硬着头皮走主路
                    print(f"   -> 💳 新车 {veh_id} 扣款 ¥{current_toll_fee} | 哪怕涨价也要走主路！(土豪/赶时间)")
            else:
                print(f"   -> 💳 新车 {veh_id} 扣款 ¥{current_toll_fee} | 畅通无阻，继续走主路。")

    conn.commit()
    step += 1

conn.close()
traci.close()