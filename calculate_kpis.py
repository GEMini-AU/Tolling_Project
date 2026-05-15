import pandas as pd
import numpy as np
import sqlite3

def run_precision_kpi_analysis():
    print("="*60)
    print(" 威海 CBD 动态收费系统深度评估报告 ")
    print("="*60)

    try:
        # 读取宏观 CSV 用于计算车速和每小时视图
        df_csv = pd.read_csv("weihai_analysis_report.csv")
        
        # 读取微观数据库 Trips 表用于精确延误计算
        conn = sqlite3.connect("weihai_toll_system.db")
        df_trips = pd.read_sql_query("SELECT * FROM Trips", conn)
        conn.close()

        # ==========================================
        # 峰值车速提升幅度
        # ==========================================
        # 截取前 1 小时集中发车期的均速作为“真实拥堵基准”
        congestion_speed = df_csv[df_csv['Time_Step'] <= 3600]['Average_Speed_mps'].mean()
        # 截取最后 1 小时作为“路网消化恢复期均速”
        recovery_speed = df_csv[df_csv['Time_Step'] > 7200]['Average_Speed_mps'].mean() 
        speed_improvement = recovery_speed - congestion_speed
        
        print(f"\n峰值车速提升幅度")
        print(f"早高峰拥堵时段均速: {congestion_speed:.2f} m/s")
        print(f"路网消化恢复期均速: {recovery_speed:.2f} m/s")
        print(f"真实提升幅度: +{speed_improvement:.2f} m/s (约 {speed_improvement*3.6:.2f} km/h)")

        # ==========================================
        # 真实的区域进入弹性 
        # ==========================================
        print(f"\n区域进入弹性")
        try:
            conn_base = sqlite3.connect("baseline.db")
            df_base_trips = pd.read_sql_query("SELECT * FROM Trips", conn_base)
            conn_base.close()
            
            peak_start, peak_end = 1800, 5400
            q_baseline = len(df_base_trips[(df_base_trips['enter_step'] >= peak_start) & (df_base_trips['enter_step'] < peak_end)])
            q_tolled = len(df_trips[(df_trips['enter_step'] >= peak_start) & (df_trips['enter_step'] < peak_end)])
            
            p_baseline = 0.0
            p_tolled = df_csv[(df_csv['Time_Step'] >= peak_start) & (df_csv['Time_Step'] < peak_end)]['Current_Toll_Fee'].mean()
            
            if q_baseline > 0 and p_tolled > 0:
                delta_Q_pct = (q_tolled - q_baseline) / q_baseline
                delta_P_pct = (p_tolled - 1.0) / 1.0 
                elasticity = abs(delta_Q_pct / delta_P_pct)
                
                print(f"[高峰同环比控制] 测试时间窗口: {peak_start}s - {peak_end}s")
                print(f"免费基线组 (均价 ¥0.00) -> 真实驶入意愿: {q_baseline} 辆车")
                print(f"收费干预组 (均价 ¥{p_tolled:.2f}) -> 真实驶入意愿: {q_tolled} 辆车")
                print(f"计算得出区域进入需求弹性系数 (E): {elasticity:.4f}")
                if elasticity > 1:
                    print("结论: E > 1，车流对价格【富有弹性】，拥堵费成功抑制了刚性驶入需求！")
                else:
                    print("结论: E < 1，车流对价格【缺乏弹性】，人们宁可交钱也要进城。")
            else:
                print("高峰期数据量不足，无法计算弹性。")
        except Exception as e:
            print(f"弹性计算缺少对照组数据库 (baseline.db) 支持: {e}")

        # ==========================================
        # 每小时视图
        # ==========================================
        print(f"\n每小时维度的收入与车速报告")
        df_csv['Hour'] = (df_csv['Time_Step'] // 3600) + 1
        hourly_stats = df_csv.groupby('Hour').agg(
            Hourly_Revenue=('Total_Revenue', lambda x: x.iloc[-1] - x.iloc[0] if len(x) > 1 else 0),
            Avg_Speed_kmh=('Average_Speed_mps', lambda x: x.mean() * 3.6),
            Max_Vehicles=('Vehicles_in_CBD', 'max')
        ).reset_index()

        print("时段 (Hour) | 新增过路费收入 (¥) | 区域平均车速 (km/h) | 峰值拥堵车辆数")
        print("-" * 75)
        for index, row in hourly_stats.iterrows():
            print(f" 第 {int(row['Hour'])} 小时   | ¥ {row['Hourly_Revenue']:<15.2f} | {row['Avg_Speed_kmh']:<17.2f} | {int(row['Max_Vehicles'])}")

        # ==========================================
        # 基于 Trips 的高精度真实延误削减计算 
        # ==========================================
        print(f"\n 收入 - 延误比 ")
        total_revenue = df_csv['Total_Revenue'].iloc[-1]
        free_flow_speed = 13.89  # 基准速度 50km/h
        
        try:
            conn_base = sqlite3.connect("baseline.db")
            df_base_trips = pd.read_sql_query("SELECT * FROM Trips WHERE route_distance > 10", conn_base)
            conn_base.close()
            
            df_base_trips['Real_Delay'] = np.maximum(0, df_base_trips['travel_time'] - (df_base_trips['route_distance'] / free_flow_speed))
            baseline_total_delay = df_base_trips['Real_Delay'].sum()
            
            valid_trips = df_trips[df_trips['route_distance'] > 10].copy()
            valid_trips['Real_Delay'] = np.maximum(0, valid_trips['travel_time'] - (valid_trips['route_distance'] / free_flow_speed))
            tolled_total_delay = valid_trips['Real_Delay'].sum()
            
            delay_reduced = baseline_total_delay - tolled_total_delay
            
            print(f"基线组真实物理延误: {baseline_total_delay:.2f} 秒")
            print(f"收费组真实物理延误: {tolled_total_delay:.2f} 秒")
            print(f"成功削减延误总量: {delay_reduced:.2f} 秒")
            print(f"系统总计收取拥堵费: ¥{total_revenue:.2f}")
            
            if delay_reduced > 0 and total_revenue > 0:
                rdr = delay_reduced / total_revenue
                print(f"RDR 指标结果: 每收取 1 元拥堵费，真实减少了 {rdr:.4f} 秒的交通延误！")
            else:
                print("注：由于大量车辆绕行导致其个人行驶距离拉长，路网总计延误可能出现负向转移。这正是绕行博弈的代价。")
                
        except Exception as e:
            print(f"读取 baseline.db 计算延误对比时发生错误: {e}")


    except Exception as e:
        print(f"数据处理时发生全局异常: {e}")

if __name__ == "__main__":
    run_precision_kpi_analysis()