import os
import sys
import traci
import sqlite3  # 导入数据库模块

# --- 设定动态路费的规则 ---
def calculate_toll(current_vehicle_count):
    base_fee = 1.0  
    if current_vehicle_count < 10:
        return base_fee
    elif 10 <= current_vehicle_count <= 20:
        return base_fee * 2.5
    else:
        return base_fee * 5.0

# --- 基础环境配置 ---
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请配置 SUMO_HOME 环境变量")

sumoCmd = ["sumo", "-c", "sim.sumocfg"] 
traci.start(sumoCmd)

# 连接到我们刚才建好的虚拟银行
conn = sqlite3.connect('tolling_system.db')
cursor = conn.cursor()

print("---  仿真开始连接,动态定价与【ETC扣费系统】已启动 ---")

# ---  开启循环 ---
step = 0
while step < 100:  
    traci.simulationStep() 
    
    # 查车数
    active_vehicles = traci.vehicle.getIDList()
    vehicle_count = len(active_vehicles)
    
    # 算价格
    current_toll_fee = calculate_toll(vehicle_count)
    
    print(f"第 {step} 秒 | 路网车辆数: {vehicle_count} 辆 | 实时动态过路费: ¥ {current_toll_fee}")
    
    # 开始逐辆车扫描扣款！
    for veh_id in active_vehicles:
        # 查一下这辆车有没有在银行里开过户
        cursor.execute("SELECT balance FROM Wallet WHERE vehicle_id = ?", (veh_id,))
        result = cursor.fetchone()
        
        if result is None:
            # 如果没查到，说明是一辆刚上路的新车！
            # 计算扣费后的余额 (送100块，减去当前过路费)
            new_balance = 100.0 - current_toll_fee
            
            # 记录进数据库
            cursor.execute("INSERT INTO Wallet (vehicle_id, balance) VALUES (?, ?)", (veh_id, new_balance))
            
            print(f"新车入网: {veh_id} | 扣费: ¥{current_toll_fee} | 钱包余额: ¥{new_balance}")
        
        # 如果 result 不是 None，说明是老车，已经在路上跑了，进场费已经交过，不需要重复扣。

    # 盖章确认，把这1秒钟内所有的交易写死在硬盘上
    conn.commit()
    
    step += 1

# 
conn.close()
traci.close()
print("--- 🛑 仿真结束 ---")