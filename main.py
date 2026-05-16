import os, sys, csv, random
import traci
import sqlite3

from config import (
    SIM_STEPS, INITIAL_BALANCE, NET_FILE, ROUTE_FILE, PARK_FILE,
    CBD_X_MIN, CBD_X_MAX, CBD_Y_MIN, CBD_Y_MAX,
    CHARGE_INTERVAL_METERS, TOLL_THRESHOLD_HIGH,
    VOT_MIN, VOT_MAX, DETOUR_TIME_MIN, DETOUR_TIME_MAX,
    EXPECTED_CBD_DISTANCE_KM, TOLL_TO_TIME_FACTOR, get_toll_fee_per_km,
)

if 'SUMO_HOME' not in os.environ:
    sys.exit("环境变量中未声明 'SUMO_HOME'，请配置后重试。")
tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
sys.path.append(tools)


def init_database(cursor):
    cursor.execute("CREATE TABLE IF NOT EXISTS Wallet (veh_id TEXT PRIMARY KEY, balance REAL)")
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS Logs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, veh_id TEXT, "
        "amount REAL, step INTEGER, remark TEXT DEFAULT 'PAID')"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS Trips ("
        "trip_id INTEGER PRIMARY KEY AUTOINCREMENT, veh_id TEXT, "
        "enter_step INTEGER, exit_step INTEGER, "
        "enter_edge TEXT, exit_edge TEXT, "
        "travel_time REAL, route_distance REAL, "
        "toll_paid REAL, detoured INTEGER DEFAULT 0, "
        "avg_speed REAL)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS DetourLog ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, veh_id TEXT, "
        "step INTEGER, edge_id TEXT, "
        "action TEXT, current_fee REAL)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_veh ON Trips(veh_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_detoured ON Trips(detoured)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_step ON Logs(step)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_detour_veh ON DetourLog(veh_id)")


def identify_cbd_edges():
    """扫描全网边, 找出位于 CBD 内的边"""
    cbd_edges = set()
    for edge_id in traci.edge.getIDList():
        lanes = traci.edge.getLaneNumber(edge_id)
        if lanes == 0:
            continue
        shape = traci.lane.getShape(f"{edge_id}_0")
        if not shape:
            continue
        # 检查车道中点是否在 CBD 内
        mid_idx = len(shape) // 2
        mx, my = shape[mid_idx][0], shape[mid_idx][1]
        if CBD_X_MIN <= mx <= CBD_X_MAX and CBD_Y_MIN <= my <= CBD_Y_MAX:
            cbd_edges.add(edge_id)
    return cbd_edges


def update_cbd_edge_efforts(cbd_edges, current_fee_per_km, current_step):
    """
    用 adaptTraveltime 给 CBD 边设置惩罚后的总行程时间。

    [关键] adaptTraveltime 需要传入的是"总行程时间"(actual + penalty),
    而不是"额外惩罚量"。若只传惩罚量(如10秒), 但边正常需要48秒,
    SUMO 会认为 CBD 边只需10秒, 反而吸引更多车流!

    正确做法: 先读取边的实际通行时间, 再加上货币换算的惩罚秒数。
    """
    if current_fee_per_km <= 0:
        return
    extra_seconds_per_km = current_fee_per_km * TOLL_TO_TIME_FACTOR

    for edge_id in cbd_edges:
        if traci.edge.getLaneNumber(edge_id) <= 0:
            continue
        edge_len_m = traci.lane.getLength(f"{edge_id}_0")
        if edge_len_m <= 0:
            continue
        # 读取当前实际平均速度 (m/s), 至少 1 m/s 防除零
        mean_speed = max(traci.edge.getLastStepMeanSpeed(edge_id), 1.0)
        # 实际通行时间 (秒)
        actual_tt = edge_len_m / mean_speed
        # 货币成本换算的惩罚秒数
        penalty_seconds = extra_seconds_per_km * (edge_len_m / 1000.0)
        # 传入 actual + penalty, 让 SUMO 路由器看到正确的总耗时
        traci.edge.adaptTraveltime(edge_id, actual_tt + penalty_seconds,
                                   current_step, SIM_STEPS)


def detour_decision(current_fee_per_km):
    if current_fee_per_km <= 0:
        return False
    expected_savings = current_fee_per_km * EXPECTED_CBD_DISTANCE_KM
    driver_vot = random.uniform(VOT_MIN, VOT_MAX)
    detour_extra_seconds = random.uniform(DETOUR_TIME_MIN, DETOUR_TIME_MAX)

    if expected_savings > (detour_extra_seconds * driver_vot):
        return True
    elif current_fee_per_km >= TOLL_THRESHOLD_HIGH:
        return random.random() < 0.4
    else:
        return random.random() < 0.05


def run_simulation(enable_tolling=True, output_csv="weihai_analysis_report.csv",
                   db_path="weihai_toll_system.db"):
    cmd = ["sumo", "-n", NET_FILE, "-r", ROUTE_FILE, "-a", PARK_FILE]
    traci.start(cmd)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    init_database(cursor)

    # 预计算 CBD 边
    cbd_edges = identify_cbd_edges()
    print(f"CBD 收费边: {len(cbd_edges)} 条")

    csv_file = open(output_csv, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        "Time_Step", "Vehicles_in_CBD", "Current_Toll_Fee",
        "CBD_Avg_Speed_mps", "Global_Avg_Speed_mps",
        "Total_Revenue", "Detoured_Vehicles"
    ])

    step = 0
    total_revenue = 0.0
    detoured_vehicles = set()
    veh_distance_tracker = {}
    active_trips = {}

    # 预警区: CBD 外扩 300 米, 模拟司机看到"前方收费"提示牌
    APPROACH_MARGIN = 300.0
    APP_X_MIN = CBD_X_MIN - APPROACH_MARGIN
    APP_X_MAX = CBD_X_MAX + APPROACH_MARGIN
    APP_Y_MIN = CBD_Y_MIN - APPROACH_MARGIN
    APP_Y_MAX = CBD_Y_MAX + APPROACH_MARGIN

    try:
        traci.polygon.add(
            polygonID="CBD_ZONE",
            shape=[
                (CBD_X_MIN, CBD_Y_MIN), (CBD_X_MAX, CBD_Y_MIN),
                (CBD_X_MAX, CBD_Y_MAX), (CBD_X_MIN, CBD_Y_MAX),
                (CBD_X_MIN, CBD_Y_MIN)
            ],
            color=(255, 0, 0, 150), fill=False, lineWidth=8
        )
        traci.polygon.add(
            polygonID="APPROACH_ZONE",
            shape=[
                (APP_X_MIN, APP_Y_MIN), (APP_X_MAX, APP_Y_MIN),
                (APP_X_MAX, APP_Y_MAX), (APP_X_MIN, APP_Y_MAX),
                (APP_X_MIN, APP_Y_MIN)
            ],
            color=(255, 165, 0, 50), fill=True, lineWidth=2
        )
    except Exception:
        pass

    warned_vehicles = set()  # 已在预警区完成决策的车

    mode_name = "【动态收费模式】" if enable_tolling else "【无收费基线模式】"
    print(f"\n--- 仿真启动: {mode_name} ---")
    print(f"路网: {NET_FILE} | CBD: ({CBD_X_MIN},{CBD_Y_MIN})→({CBD_X_MAX},{CBD_Y_MAX})")

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

            curr_vehs_in_zone = [v[0] for v in vehs_in_cbd]
            cbd_count = len(vehs_in_cbd)
            cbd_speed = sum(v[1] for v in vehs_in_cbd) / cbd_count if cbd_count > 0 else 0.0
            global_avg_speed = (total_speed / len(all_vehs)) if all_vehs else 0.0
            current_fee_per_km = get_toll_fee_per_km(cbd_count) if enable_tolling else 0.0

            # ==========================================
            # CBD 边路权惩罚 (每 30 步更新)
            # ==========================================
            if enable_tolling and step % 30 == 0:
                update_cbd_edge_efforts(cbd_edges, current_fee_per_km, step)

            # ==========================================
            # 预警区绕行决策 — 车还没进 CBD, 提前 reroute
            # ==========================================
            if enable_tolling and step % 5 == 0:
                for v_id in all_vehs:
                    if v_id in detoured_vehicles or v_id in warned_vehicles:
                        continue
                    if v_id in curr_vehs_in_zone:
                        continue
                    x, y = traci.vehicle.getPosition(v_id)
                    if APP_X_MIN <= x <= APP_X_MAX and APP_Y_MIN <= y <= APP_Y_MAX:
                        warned_vehicles.add(v_id)
                        if detour_decision(current_fee_per_km):
                            traci.vehicle.rerouteTraveltime(v_id)
                            detoured_vehicles.add(v_id)
                            traci.vehicle.setColor(v_id, (0, 100, 255))
                        else:
                            traci.vehicle.setColor(v_id, (255, 200, 0))

            # ==========================================
            # 行程审计
            # ==========================================
            for v_id, speed in vehs_in_cbd:
                if v_id not in active_trips:
                    active_trips[v_id] = {
                        "enter_step": step,
                        "enter_edge": traci.vehicle.getRoadID(v_id),
                        "initial_distance": traci.vehicle.getDistance(v_id),
                        "toll_paid": 0.0,
                        "detoured": 0,
                    }

            exited_vehs = [v for v in active_trips if v not in curr_vehs_in_zone]
            for v_id in exited_vehs:
                trip = active_trips[v_id]
                exit_step = step
                exit_edge = (
                    traci.vehicle.getRoadID(v_id) if v_id in all_vehs else "EXITED"
                )
                travel_time = exit_step - trip["enter_step"]
                final_dist = (
                    traci.vehicle.getDistance(v_id)
                    if v_id in all_vehs
                    else trip["initial_distance"] + 2000
                )
                route_distance = max(0, final_dist - trip["initial_distance"])
                avg_speed_trip = (route_distance / travel_time) if travel_time > 0 else 0

                cursor.execute(
                    "INSERT INTO Trips (veh_id, enter_step, exit_step, enter_edge, "
                    "exit_edge, travel_time, route_distance, toll_paid, detoured, avg_speed) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (v_id, trip["enter_step"], exit_step, trip["enter_edge"],
                     exit_edge, travel_time, route_distance,
                     trip["toll_paid"], trip["detoured"], avg_speed_trip),
                )
                del active_trips[v_id]

            # ==========================================
            # 里程计费 (GPS 电子围栏)
            # ==========================================
            if enable_tolling:
                for v_id, speed in vehs_in_cbd:
                    if v_id not in veh_distance_tracker:
                        veh_distance_tracker[v_id] = 0.0
                    veh_distance_tracker[v_id] += speed

                    if veh_distance_tracker[v_id] >= CHARGE_INTERVAL_METERS:
                        charge_amount = current_fee_per_km * (CHARGE_INTERVAL_METERS / 1000.0)
                        try:
                            with conn:
                                cursor.execute(
                                    "INSERT OR IGNORE INTO Wallet VALUES (?, ?)",
                                    (v_id, INITIAL_BALANCE),
                                )
                                cursor.execute(
                                    "UPDATE Wallet SET balance = balance - ? "
                                    "WHERE veh_id = ? AND balance >= ?",
                                    (charge_amount, v_id, charge_amount),
                                )
                                if cursor.rowcount > 0:
                                    cursor.execute(
                                        "INSERT INTO Logs (veh_id, amount, step, remark) "
                                        "VALUES (?, ?, ?, 'PAID')",
                                        (v_id, charge_amount, step),
                                    )
                                    total_revenue += charge_amount
                                    if v_id in active_trips:
                                        active_trips[v_id]["toll_paid"] += charge_amount
                                else:
                                    cursor.execute(
                                        "INSERT INTO Logs (veh_id, amount, step, remark) "
                                        "VALUES (?, ?, ?, 'DEBT_VIOLATION')",
                                        (v_id, charge_amount, step),
                                    )
                        except Exception as e:
                            print(f"[ACID 事务回滚] {v_id}, step {step}: {e}")

                        veh_distance_tracker[v_id] -= CHARGE_INTERVAL_METERS

                        # 绕行决策 → rerouteTraveltime 现在会感知 CBD 边的高代价
                        if v_id not in detoured_vehicles and detour_decision(current_fee_per_km):
                            traci.vehicle.rerouteTraveltime(v_id)
                            detoured_vehicles.add(v_id)
                            traci.vehicle.setColor(v_id, (0, 100, 255))
                            if v_id in active_trips:
                                active_trips[v_id]["detoured"] = 1
                        else:
                            traci.vehicle.setColor(v_id, (255, 0, 0))
            else:
                for v_id, _ in vehs_in_cbd:
                    traci.vehicle.setColor(v_id, (0, 255, 0))

            # ==========================================
            # 数据落盘
            # ==========================================
            if step % 10 == 0:
                total_det = len(detoured_vehicles)
                csv_writer.writerow([
                    step, cbd_count, round(current_fee_per_km, 2),
                    round(cbd_speed, 2), round(global_avg_speed, 2),
                    round(total_revenue, 2), total_det,
                ])
                if step % 1000 == 0:
                    if enable_tolling:
                        print(
                            f"进度: {step}/{SIM_STEPS}s | CBD车: {cbd_count} | "
                            f"费率: ¥{current_fee_per_km:.2f}/km | "
                            f"CBD车速: {cbd_speed*3.6:.1f}km/h | "
                            f"收入: ¥{total_revenue:.2f} | 绕行: {total_det}"
                        )
                    else:
                        print(
                            f"进度: {step}/{SIM_STEPS}s | CBD车: {cbd_count} | "
                            f"CBD车速: {cbd_speed*3.6:.1f}km/h | [基线]"
                        )

            step += 1

    except Exception as e:
        print(f"\n[错误] 仿真异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 仿真结束后, 记录仍在 CBD 内的车辆 (末班车)
        for v_id, trip in list(active_trips.items()):
            travel_time = step - trip["enter_step"]
            rd = max(0, traci.vehicle.getDistance(v_id) - trip["initial_distance"]) if v_id in traci.vehicle.getIDList() else 2000
            cursor.execute(
                "INSERT INTO Trips (veh_id, enter_step, exit_step, enter_edge, "
                "exit_edge, travel_time, route_distance, toll_paid, detoured, avg_speed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (v_id, trip["enter_step"], step, trip["enter_edge"],
                 "SIM_END", travel_time, rd,
                 trip["toll_paid"], trip["detoured"],
                 rd / travel_time if travel_time > 0 else 0),
            )

        # 确保末班车数据提交
        conn.commit()
        trip_count = cursor.execute("SELECT COUNT(*) FROM Trips").fetchone()[0]
        print(f"[数据库] Trips 表总记录: {trip_count} 趟")

        if not csv_file.closed:
            csv_file.close()
        conn.close()
        traci.close()

    return total_revenue, len(detoured_vehicles)


if __name__ == "__main__":
    print(">>> 开始执行基线对照实验 (Baseline) <<<")
    run_simulation(enable_tolling=False, output_csv="baseline_report.csv", db_path="baseline.db")

    print("\n>>> 开始执行动态收费实验 (Tolling) <<<")
    rev, det = run_simulation(
        enable_tolling=True,
        output_csv="weihai_analysis_report.csv",
        db_path="weihai_toll_system.db",
    )
    print(f"\n仿真完成。总收入: ¥{rev:.2f}, 绕行车辆: {det}")