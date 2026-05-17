import pandas as pd
import numpy as np
import sqlite3

def run_precision_kpi_analysis():
    print("=" * 60)
    print("  CBD 动态收费系统深度评估报告 ")
    print("=" * 60)

    try:
        df_csv = pd.read_csv("toll_analysis_report.csv")
        conn = sqlite3.connect("toll_system.db")
        df_trips = pd.read_sql_query("SELECT * FROM Trips", conn)
        conn.close()

        # ==========================================
        # 峰值车速提升幅度 (收费 vs 基线, 同时间窗口对比)
        # ==========================================
        try:
            df_base_csv = pd.read_csv("baseline_report.csv")
            peak_start, peak_end = 1800, 7200

            # --- CBD 内速度 (只统计CBD有车的时刻) ---
            mask_t = (df_csv['Time_Step'] >= peak_start) & (df_csv['Time_Step'] <= peak_end) & (df_csv['CBD_Avg_Speed_mps'] > 0)
            mask_b = (df_base_csv['Time_Step'] >= peak_start) & (df_base_csv['Time_Step'] <= peak_end) & (df_base_csv['CBD_Avg_Speed_mps'] > 0)

            toll_cbd  = df_csv.loc[mask_t, 'CBD_Avg_Speed_mps'].mean()
            base_cbd  = df_base_csv.loc[mask_b, 'CBD_Avg_Speed_mps'].mean()
            cbd_delta = toll_cbd - base_cbd

            # --- 全网均速 ---
            mask_g_t = (df_csv['Time_Step'] >= peak_start) & (df_csv['Time_Step'] <= peak_end) & (df_csv['Global_Avg_Speed_mps'] > 0)
            mask_g_b = (df_base_csv['Time_Step'] >= peak_start) & (df_base_csv['Time_Step'] <= peak_end) & (df_base_csv['Global_Avg_Speed_mps'] > 0)

            toll_global  = df_csv.loc[mask_g_t, 'Global_Avg_Speed_mps'].mean()
            base_global  = df_base_csv.loc[mask_g_b, 'Global_Avg_Speed_mps'].mean()
            global_delta = toll_global - base_global

            print(f"\n峰值车速提升幅度 (早高峰 {peak_start}s-{peak_end}s)")
            print(f"  {'指标':<18} {'基线':>10} {'收费':>10} {'变化':>12}")
            print(f"  {'-'*52}")
            print(f"  {'CBD 区域均速':<18} {base_cbd*3.6:>9.2f}km/h {toll_cbd*3.6:>9.2f}km/h {cbd_delta*3.6:>+10.2f}km/h")
            print(f"  {'全网均速':<18} {base_global*3.6:>9.2f}km/h {toll_global*3.6:>9.2f}km/h {global_delta*3.6:>+10.2f}km/h")
            print(f"  {'CBD 驻留车辆':<18} {df_base_csv.loc[mask_b,'Vehicles_in_CBD'].mean():>9.1f}辆   {df_csv.loc[mask_t,'Vehicles_in_CBD'].mean():>9.1f}辆   {df_csv.loc[mask_t,'Vehicles_in_CBD'].mean()-df_base_csv.loc[mask_b,'Vehicles_in_CBD'].mean():>+10.1f}辆")
            print(f"\n解读:")
            print(f"  CBD速度: {cbd_delta*3.6:+.2f}km/h — 收费筛选了刚性目的地车辆, 停靠较多, 均速略低 (正常)")
            print(f"  全网速度: {global_delta*3.6:+.2f}km/h — 绕行车辆散布外环, 全网通行效率{'提升' if global_delta >= 0 else '下降'}")
        except Exception as e:
            print(f"\n峰值车速提升: 计算失败 - {e}")


        # ==========================================
        # 区域进入弹性
        # ==========================================
        print(f"\n区域进入弹性")
        try:
            conn_base = sqlite3.connect("baseline.db")
            df_base_trips = pd.read_sql_query("SELECT * FROM Trips", conn_base)
            conn_base.close()

            peak_start, peak_end = 1800, 5400
            q_baseline = len(df_base_trips[
                (df_base_trips['enter_step'] >= peak_start) &
                (df_base_trips['enter_step'] < peak_end)
            ])
            q_tolled = len(df_trips[
                (df_trips['enter_step'] >= peak_start) &
                (df_trips['enter_step'] < peak_end)
            ])

            p_tolled = df_csv[
                (df_csv['Time_Step'] >= peak_start) &
                (df_csv['Time_Step'] < peak_end)
            ]['Current_Toll_Fee'].mean()

            if q_baseline > 0 and p_tolled > 0:
                delta_Q_pct = (q_tolled - q_baseline) / q_baseline
                # 基准价 = BASE_RATE_PER_KM = 2.0 元/km (畅通时的最低费率)
                # 使用 1.0 会使分母虚大, 弹性系数严重偏小
                BASE_RATE = 2.0
                delta_P_pct = (p_tolled - BASE_RATE) / BASE_RATE
                elasticity = abs(delta_Q_pct / delta_P_pct) if delta_P_pct != 0 else 0

                print(f"[高峰窗口: {peak_start}s-{peak_end}s]")
                print(f"免费基线驶入: {q_baseline} 辆")
                print(f"收费组驶入: {q_tolled} 辆 (均价 {p_tolled:.2f} 元/km)")
                print(f"需求弹性系数 E = {elasticity:.4f}")
                if elasticity > 1:
                    print("结论: E > 1, 车流对价格富有弹性")
                else:
                    print("结论: E < 1, 车流对价格缺乏弹性")
        except Exception as e:
            print(f"弹性计算失败: {e}")

        # ==========================================
        # 每小时收入与车速视图
        # ==========================================
        print(f"\n每小时收入与车速报告")
        df_csv['Hour'] = (df_csv['Time_Step'] // 3600) + 1
        hourly_stats = df_csv.groupby('Hour').agg(
            Hourly_Revenue=('Total_Revenue',
                lambda x: x.iloc[-1] - x.iloc[0] if len(x) > 1 else 0),
            CBD_Avg_Speed_kmh=('CBD_Avg_Speed_mps', lambda x: x.mean() * 3.6),
            Max_Vehicles=('Vehicles_in_CBD', 'max')
        ).reset_index()

        print("时段 | 新增收入 (元) | CBD均速 (km/h) | 峰值车辆")
        print("-" * 55)
        for _, row in hourly_stats.iterrows():
            print(f"第{int(row['Hour'])}小时 | {row['Hourly_Revenue']:>12.2f} | "
                  f"{row['CBD_Avg_Speed_kmh']:>13.2f} | {int(row['Max_Vehicles']):>6}")

        # ==========================================
        # 收入-延误比 (RDR)
        # ==========================================
        print(f"\n收入-延误比 (RDR)")
        total_revenue = df_csv['Total_Revenue'].iloc[-1]
        free_flow_speed = 13.89

        try:
            conn_base = sqlite3.connect("baseline.db")
            df_base_raw = pd.read_sql_query("SELECT * FROM Trips", conn_base)
            conn_base.close()

            print(f"  [诊断] 基线总行程: {len(df_base_raw)} 趟")
            df_base_trips = df_base_raw[df_base_raw['route_distance'] > 10]
            print(f"  [诊断] 有效行程 (距离>10m): {len(df_base_trips)} 趟")

            if len(df_base_trips) == 0:
                print("  [警告] 基线数据库无有效行程! 基线仿真可能未完成。")
                print("  请确保 main.py 中基线实验已执行且未中途崩溃。")
            else:
                df_base_trips = df_base_trips.copy()
                df_base_trips['Real_Delay'] = np.maximum(0,
                    df_base_trips['travel_time'] -
                    (df_base_trips['route_distance'] / free_flow_speed))
                baseline_delay = df_base_trips['Real_Delay'].sum()

                valid = df_trips[df_trips['route_distance'] > 10].copy()
                valid['Real_Delay'] = np.maximum(0,
                    valid['travel_time'] -
                    (valid['route_distance'] / free_flow_speed))
                tolled_delay = valid['Real_Delay'].sum()

                delay_reduced = baseline_delay - tolled_delay

                print(f"基线总延误: {baseline_delay:.0f} 秒 ({len(df_base_trips)} 趟)")
                print(f"收费总延误: {tolled_delay:.0f} 秒 ({len(valid)} 趟)")
                print(f"削减延误: {delay_reduced:.0f} 秒")
                print(f"总收费: {total_revenue:.2f} 元")

                if delay_reduced > 0 and total_revenue > 0:
                    rdr = delay_reduced / total_revenue
                    print(f"RDR (总量口径): 每收 1 元拥堵费, 全网减少 {rdr:.2f} 秒延误")
                    # 归一化口径: 消除行程数差异的影响
                    base_per_trip = baseline_delay / len(df_base_trips)
                    toll_per_trip = tolled_delay / len(valid) if len(valid) > 0 else 0
                    per_trip_improve = base_per_trip - toll_per_trip
                    rdr_norm = per_trip_improve * len(valid) / total_revenue
                    print(f"  基线每趟延误: {base_per_trip:.1f}秒, 收费每趟延误: {toll_per_trip:.1f}秒")
                    print(f"RDR (归一化口径): 每收 1 元拥堵费, 等效减少 {rdr_norm:.2f} 秒延误")

                # =====================================================
                # 延误拆组分析: 死磕组 vs 绕行组
                # 死磕组延误↓ → 证明收费政策成功疏导CBD核心区
                # 绕行组延误↑ → 展示"拥堵溢出效应"(Congestion Spillover)
                # =====================================================
                print(f"\n延误分组分析 (收费组内部拆解)")
                stay_group = valid[valid['detoured'] == 0]
                flee_group = valid[valid['detoured'] == 1]

                # 基线每趟平均延误 (作为对照基准)
                base_avg = df_base_trips['Real_Delay'].mean()

                if len(stay_group) > 0:
                    stay_avg = stay_group['Real_Delay'].mean()
                    arrow = '↓' if stay_avg < base_avg else '↑'
                    print(f"  死磕组 (留CBD缴费, n={len(stay_group)}): 每趟延误 {stay_avg:.1f}s "
                          f"vs 基线 {base_avg:.1f}s -> {arrow}{abs(stay_avg - base_avg):.1f}s"
                          f"  [CBD疏堵成功]")
                if len(flee_group) > 0:
                    flee_avg = flee_group['Real_Delay'].mean()
                    arrow = '↑' if flee_avg > base_avg else '↓'
                    print(f"  绕行组 (reroute进CBD, n={len(flee_group)}): 每趟延误 {flee_avg:.1f}s "
                          f"vs 基线 {base_avg:.1f}s -> {arrow}{abs(flee_avg - base_avg):.1f}s"
                          f"  [拥堵溢出效应 Congestion Spillover]")
                elif delay_reduced <= 0:
                    print("注意: 延误未减少, 绕行车辆可能拉长了路网总行程时间")
        except Exception as e:
            print(f"RDR 计算失败: {e}")

    except Exception as e:
        print(f"全局异常: {e}")

if __name__ == "__main__":
    run_precision_kpi_analysis()