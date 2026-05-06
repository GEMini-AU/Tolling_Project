import os
import sys
import traci

# --- 设定动态路费的规则 ---
def calculate_toll(current_vehicle_count):
    """
    根据区域内的车辆数量，动态计算拥堵费
    """
    base_fee = 1.0  # 基础费率：1元
    
    if current_vehicle_count < 10:
        # 畅通状态
        return base_fee
    elif 10 <= current_vehicle_count <= 20:
        # 轻度拥堵状态：基础费率 x 2.5
        return base_fee * 2.5
    else:
        # 严重拥堵状态：基础费率 x 5.0
        return base_fee * 5.0

# --- 基础环境配置 ---
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请配置 SUMO_HOME 环境变量")

sumoCmd = ["sumo", "-c", "sim.sumocfg"] 
traci.start(sumoCmd)
print("--- 🚀 仿真开始连接，动态定价引擎已启动 ---")

# ---  开启循环 ---
step = 0
while step < 100:  
    traci.simulationStep() 
    
    # 获取路网实时车辆数 (X变量)
    active_vehicles = traci.vehicle.getIDList()
    vehicle_count = len(active_vehicles)
    
    # 【核心新增】将车辆数扔进我们的大脑，计算出当前应该收多少钱 (Y结果)
    current_toll_fee = calculate_toll(vehicle_count)
    
    # 打印结果，看看算法是否生效
    print(f"第 {step} 秒 | 路网车辆数: {vehicle_count} 辆 | 实时动态过路费: ¥ {current_toll_fee}")
    
    step += 1

traci.close()
print("--- 🛑 仿真结束 ---")