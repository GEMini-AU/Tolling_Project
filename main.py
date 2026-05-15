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

    # 基础乘数 1，最高乘数 10
    # 拐点为 25，斜率 0.20
    congestion_multiplier = 1 + 9 / (1 + math.exp(-0.20 * (vehicle_count - 25)))
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



# 将原有的 run_simulation() 改为带参数的函数
def run_simulation(enable_tolling=True, output_csv="weihai_analysis_report.csv", db_path="weihai_toll_system.db"):
    """
    核心仿真主函数
    :param enable_tolling: 是否开启动态收费与绕行博弈（True为实验组，False为基线组）
    :param output_csv: 数据报表导出路径
    """
    traci.start(sumo_cmd)
    
    #无论是否收费，都连接对应的数据库，基线组也要记录 Trips
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")  # 开启 WAL 提升并发性能
    cursor = conn.cursor()
    
    # 钱包表
    cursor.execute("CREATE TABLE IF NOT EXISTS Wallet (veh_id TEXT PRIMARY KEY, balance REAL)")
    # 日志表，增加 remark 字段，用于标记欠费
    cursor.execute("CREATE TABLE IF NOT EXISTS Logs (id INTEGER PRIMARY KEY AUTOINCREMENT, veh_id TEXT, amount REAL, step INTEGER, remark TEXT DEFAULT 'PAID')")
    
    # 行程表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Trips (
            trip_id INTEGER PRIMARY KEY AUTOINCREMENT,
            veh_id TEXT,
            enter_step INTEGER,
            exit_step INTEGER,
            enter_edge TEXT,
            exit_edge TEXT,
            travel_time REAL,
            route_distance REAL,
            toll_paid REAL,
            detoured INTEGER DEFAULT 0,
            avg_speed REAL
        )
    """)
    
    # 为高频查询字段建立索引，速度提升百倍
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_veh ON Trips(veh_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_detoured ON Trips(detoured)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_step ON Logs(step)")


    csv_file = open(output_csv, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["Time_Step", "Vehicles_in_CBD", "Current_Toll_Fee", "Average_Speed_mps", "Total_Revenue", "Detoured_Vehicles"])

    step = 0
    total_revenue = 0.0
    total_detoured = 0
    detoured_vehicles_set = set()
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
        # 用于追踪当前在 CBD 内的车辆行程状态
        active_trips = {}
        while step < SIM_STEPS:
            traci.simulationStep()
            all_vehs = traci.vehicle.getIDList()
            vehs_in_cbd = []
            total_speed = 0.0
            
            # ==========================================
            # 扫描全网车辆，确定谁在 CBD 内
            # ==========================================
            for v_id in all_vehs:
                x, y = traci.vehicle.getPosition(v_id)
                speed = traci.vehicle.getSpeed(v_id)
                total_speed += speed
                if CBD_X_MIN <= x <= CBD_X_MAX and CBD_Y_MIN <= y <= CBD_Y_MAX:
                    vehs_in_cbd.append((v_id, speed))

            curr_vehs_in_zone = [v[0] for v in vehs_in_cbd]
            cbd_count = len(vehs_in_cbd)
            avg_speed = (total_speed / len(all_vehs)) if all_vehs else 0.0
            
            # 获取当前实时的 元/公里 费率
            current_fee_per_km = get_toll_fee_per_km(cbd_count) if enable_tolling else 0.0

            # ==========================================
            # 行程审计逻辑：入场与出场
            # ==========================================
            # A. 检测新进入 CBD 的车辆（入场记录）
            for v_id, speed in vehs_in_cbd:
                if v_id not in active_trips:
                    active_trips[v_id] = {
                        "enter_step": step,
                        "enter_edge": traci.vehicle.getRoadID(v_id),
                        "initial_distance": traci.vehicle.getDistance(v_id),
                        "toll_paid": 0.0,
                        "detoured": 0
                    }

            # B. 检测离开 CBD 或消失的车辆（离场结算）
            exited_vehs = [v_id for v_id in active_trips if v_id not in curr_vehs_in_zone]
            for v_id in exited_vehs:
                trip = active_trips[v_id]
                exit_step = step
                exit_edge = traci.vehicle.getRoadID(v_id) if v_id in all_vehs else "EXITED"
                
                travel_time = exit_step - trip["enter_step"]
                final_dist = traci.vehicle.getDistance(v_id) if v_id in all_vehs else trip["initial_distance"] + 2000
                route_distance = max(0, final_dist - trip["initial_distance"])
                avg_speed_trip = (route_distance / travel_time) if travel_time > 0 else 0
                

                cursor.execute("""
                    INSERT INTO Trips (veh_id, enter_step, exit_step, enter_edge, exit_edge, travel_time, route_distance, toll_paid, detoured, avg_speed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (v_id, trip["enter_step"], exit_step, trip["enter_edge"], exit_edge, travel_time, route_distance, trip["toll_paid"], trip["detoured"], avg_speed_trip))
                
                del active_trips[v_id]

            # ==========================================
            # 核心业务逻辑：里程计费与绕行博弈
            # ==========================================
            if enable_tolling:
                for v_id, speed in vehs_in_cbd:
                    if v_id not in veh_distance_tracker:
                        veh_distance_tracker[v_id] = 0.0
                    veh_distance_tracker[v_id] += speed
                    
                    if veh_distance_tracker[v_id] >= CHARGE_INTERVAL_METERS:
                        charge_amount = current_fee_per_km * (CHARGE_INTERVAL_METERS / 1000.0)
                        try:
                            #使用 with conn 上下文管理器
                            # Python 会在此处自动开启事务。
                            # 如果块内代码全部成功，自动执行 COMMIT；如果触发任何异常，自动执行 ROLLBACK。
                            with conn:
                                cursor.execute("INSERT OR IGNORE INTO Wallet VALUES (?, ?)", (v_id, INITIAL_BALANCE))
                                # 包含防刷钱约束的扣款
                                cursor.execute("UPDATE Wallet SET balance = balance - ? WHERE veh_id = ? AND balance >= ?", (charge_amount, v_id, charge_amount))
                                
                                if cursor.rowcount > 0:
                                    cursor.execute("INSERT INTO Logs (veh_id, amount, step, remark) VALUES (?, ?, ?, 'PAID')", (v_id, charge_amount, step))
                                    total_revenue += charge_amount
                                    if v_id in active_trips:
                                        active_trips[v_id]["toll_paid"] += charge_amount
                                else:
                                    cursor.execute("INSERT INTO Logs (veh_id, amount, step, remark) VALUES (?, ?, ?, 'DEBT_VIOLATION')", (v_id, charge_amount, step))
                                    
                        except Exception as e:
                            # 拒绝静默吞没异常，一旦回滚，立刻在终端高亮打印死因！
                            print(f"🚨 [ACID 事务回滚] 车辆: {v_id}, 仿真步: {step}, 错误详情: {e}")
                            
                        
                        veh_distance_tracker[v_id] -= CHARGE_INTERVAL_METERS 
                        
                        # 绕行动作判定
                        # 基于时间价值 (VOT) 的理性绕行博弈模型
                        if current_fee_per_km >= TOLL_THRESHOLD_HIGH:
                            # 估算预期拥堵费 (假设平均需要再开 1.5 公里穿越 CBD)
                            expected_toll_savings = current_fee_per_km * 1.5
                            
                            # 为当前司机生成随机的时间价值 (元/秒) 和预估绕行时间
                            # 假设时间价值在 0.02 到 0.08 元/秒之间 (折合时薪 72~288 元)
                            driver_value_of_time = random.uniform(0.02, 0.08) 
                            # 预估绕开收费区需要多花 180 ~ 420 秒 (3~7分钟)
                            detour_extra_seconds = random.uniform(180, 420)
                            
                            #理性经济决策：如果省下的钱，值得上多花的时间，就绕行！
                            if expected_toll_savings > (detour_extra_seconds * driver_value_of_time):
                                traci.vehicle.rerouteTraveltime(v_id) 
                                detoured_vehicles_set.add(v_id) # 加入去重集合
                                traci.vehicle.setColor(v_id, (0, 100, 255)) # 绕行变蓝
                                
                                if v_id in active_trips:
                                    active_trips[v_id]["detoured"] = 1
                            else:
                                # 嫌绕路太费时间，咬牙硬交钱死磕
                                traci.vehicle.setColor(v_id, (255, 0, 0))
                        else:
                            # 费率不高时，默认不绕行
                            traci.vehicle.setColor(v_id, (255, 0, 0))
                            
            else:
                # 基线模式全变绿
                for v_id, _ in vehs_in_cbd:
                    traci.vehicle.setColor(v_id, (0, 255, 0))

            # ==========================================
            # 数据落盘
            # ==========================================
            if step % 10 == 0:
                csv_writer.writerow([step, cbd_count, round(current_fee_per_km, 2), round(avg_speed, 2), round(total_revenue, 2), total_detoured])
                
                if step % 1000 == 0:
                    if enable_tolling:
                        print(f"进度: {step}/{SIM_STEPS}s | CBD拥堵: {cbd_count}辆 | 动态费率: ¥{current_fee_per_km:.2f}/km | 财政总计: ¥{total_revenue:.2f}")
                    else:
                        print(f"进度: {step}/{SIM_STEPS}s | CBD拥堵: {cbd_count}辆 | [无收费基线测试中...]")
            
            step += 1

    except Exception as e:
        print(f"\n[错误] 仿真异常: {e}")
    finally:
        # ==========================================
        # 终极资源释放：无论是否收费，无论是否报错，强制清场
        # ==========================================
        if 'csv_file' in locals() and not csv_file.closed:
            csv_file.close()
            
        if 'conn' in locals():
            conn.close()  # ✅ 移除 if enable_tolling 限制，双模式全部安全关库
            
        traci.close()

# ==========================================
# 自动化执行两组对照实验
# ==========================================
if __name__ == "__main__":
    print(">>> 开始执行基线对照实验 (Baseline Experiment) <<<")
    # 给基线组分配独立的 baseline.db
    run_simulation(enable_tolling=False, output_csv="baseline_report.csv", db_path="baseline.db")
    
    print("\n>>> 开始执行动态收费实验 (Tolling Experiment) <<<")
    # 实验组继续使用主数据库
    run_simulation(enable_tolling=True, output_csv="weihai_analysis_report.csv", db_path="weihai_toll_system.db")