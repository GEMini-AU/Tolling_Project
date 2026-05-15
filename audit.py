import sqlite3
import pandas as pd

def run_traffic_audit(db_path="weihai_toll_system.db"):
    """
    对仿真生成的 Trips 行程数据进行多维度的专业交通审计
    """
    print("="*60)
    print("威海 CBD 动态收费系统深度行程审计报告 ")
    print("="*60)

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        
        # 验证表是否存在且有数据
        test_df = pd.read_sql_query("SELECT COUNT(*) as cnt FROM Trips", conn)
        if test_df['cnt'][0] == 0:
            print("Trips 表为空！请先运行开启动态收费的 main.py 完成一次仿真。")
            conn.close()
            return

        # ---------------------------------------------------------
        # 宏观路网效能分析 (Macro-Level Efficiency)
        # ---------------------------------------------------------
        print("\n第一部分：宏观路网效能")
        macro_sql = """
            SELECT 
                COUNT(*) as Total_Trips,
                ROUND(AVG(travel_time), 2) as Avg_Travel_Time_sec,
                ROUND(AVG(route_distance), 2) as Avg_Distance_m,
                -- 仅计算合理速度下的平均值，过滤掉时速超 120km/h (33.3m/s) 的异常幽灵数据
                ROUND(AVG(CASE WHEN avg_speed < 33.3 THEN avg_speed ELSE NULL END) * 3.6, 2) as Avg_Speed_kmh,
                ROUND(SUM(toll_paid), 2) as Total_Revenue
            FROM Trips
        """
        macro_df = pd.read_sql_query(macro_sql, conn)
        
        print(f"总计记录行程: {macro_df['Total_Trips'][0]} 趟")
        print(f"车辆平均耗时: {macro_df['Avg_Travel_Time_sec'][0]} 秒/趟")
        print(f"车辆平均行驶: {macro_df['Avg_Distance_m'][0]} 米/趟")
        print(f"CBD 内平均车速: {macro_df['Avg_Speed_kmh'][0]} km/h")
        print(f"财政总计收入: ¥ {macro_df['Total_Revenue'][0]}")

        # ---------------------------------------------------------
        # 2. 绕行博弈深度评估 (Diversion Analysis)
        # ---------------------------------------------------------
        print("\n第二部分：价格杠杆与绕行博弈评估")
        detour_sql = """
            SELECT 
                detoured,
                COUNT(*) as count,
                ROUND(AVG(travel_time), 2) as avg_time,
                ROUND(AVG(route_distance), 2) as avg_dist,
                ROUND(AVG(toll_paid), 2) as avg_toll
            FROM Trips
            GROUP BY detoured
        """
        detour_df = pd.read_sql_query(detour_sql, conn)
        
        # 数据重组以方便展示
        stay_data = detour_df[detour_df['detoured'] == 0]
        flee_data = detour_df[detour_df['detoured'] == 1]
        
        stay_cnt = stay_data['count'].values[0] if not stay_data.empty else 0
        flee_cnt = flee_data['count'].values[0] if not flee_data.empty else 0
        total = stay_cnt + flee_cnt
        flee_rate = (flee_cnt / total * 100) if total > 0 else 0

        print(f"价格驱动分流率: {flee_rate:.2f}% (共 {flee_cnt} 辆车因高昂费率选择绕行)")
        
        if not stay_data.empty and not flee_data.empty:
            print("\n  [行为对比矩阵]")
            print(f"  - 死磕路线 (硬交钱): 平均耗时 {stay_data['avg_time'].values[0]}s | 平均过路费 ¥{stay_data['avg_toll'].values[0]}")
            print(f"  - 绕行路线 (省点钱): 平均耗时 {flee_data['avg_time'].values[0]}s | 平均过路费 ¥{flee_data['avg_toll'].values[0]}")
            
            time_diff = flee_data['avg_time'].values[0] - stay_data['avg_time'].values[0]
            print(f"  * 结论: 绕行车辆平均多花了 {time_diff:.2f} 秒的时间成本，来躲避极端的拥堵费。")

        # ---------------------------------------------------------
        # 微观极端异常追踪 (Micro-Level Anomaly Tracking)
        # ---------------------------------------------------------
        print("\n第三部分：极端异常行程曝光台")
        
        # 选出被坑得最惨的“大冤种”（交钱最多）
        max_toll_sql = """
            SELECT veh_id, travel_time, route_distance, ROUND(toll_paid, 2) as toll, exit_step
            FROM Trips 
            ORDER BY toll_paid DESC LIMIT 3
        """
        top_toll_df = pd.read_sql_query(max_toll_sql, conn)
        print("拥堵费缴纳 TOP 3 车辆 (谁在里面堵得最久、交得最多):")
        print(top_toll_df.to_string(index=False))

        # 选出跑得最慢的车
        min_speed_sql = """
            SELECT veh_id, travel_time, route_distance, ROUND(avg_speed * 3.6, 2) as speed_kmh
            FROM Trips 
            WHERE travel_time > 60 -- 过滤掉那些刚进来几秒钟就退出的边缘数据
            ORDER BY avg_speed ASC LIMIT 3
        """
        slow_df = pd.read_sql_query(min_speed_sql, conn)
        print("\n▶ 最慢TOP 3 车辆:")
        print(slow_df.to_string(index=False))

        conn.close()
        print("\n" + "="*60)
        print("审计完成！所有核心 KPI 均已从 Trips 数据池提取完毕。")

    except Exception as e:
        print(f"审计脚本执行失败: {e}")

if __name__ == "__main__":
    run_traffic_audit()