import pandas as pd
import matplotlib.pyplot as plt

def draw_comprehensive_charts():
    plt.style.use('seaborn-v0_8-whitegrid')
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False

    try:
        print("读取仿真报告...")
        df_base = pd.read_csv("baseline_report.csv")
        df_toll = pd.read_csv("toll_analysis_report.csv")

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 14), sharex=True)

        # ==========================================
        # 图1: CBD 车速 + 全网均速 (双Y轴)
        # ==========================================
        color_cbd_base  = 'silver'
        color_cbd_toll  = 'royalblue'
        color_glob_base = 'sandybrown'
        color_glob_toll = 'darkorange'

        ax1.plot(df_base['Time_Step'], df_base['CBD_Avg_Speed_mps'] * 3.6,
                 label='CBD 基线均速', color=color_cbd_base, linestyle='--', linewidth=1.5)
        ax1.plot(df_toll['Time_Step'], df_toll['CBD_Avg_Speed_mps'] * 3.6,
                 label='CBD 收费均速', color=color_cbd_toll, linewidth=2)
        ax1.set_ylabel('CBD 平均车速 (km/h)', fontsize=11, color=color_cbd_toll)
        ax1.tick_params(axis='y', labelcolor=color_cbd_toll)
        ax1.set_ylim(bottom=0)

        ax1_twin = ax1.twinx()
        ax1_twin.plot(df_base['Time_Step'], df_base['Global_Avg_Speed_mps'] * 3.6,
                      label='全网 基线均速', color=color_glob_base, linestyle=':', linewidth=1.5)
        ax1_twin.plot(df_toll['Time_Step'], df_toll['Global_Avg_Speed_mps'] * 3.6,
                      label='全网 收费均速', color=color_glob_toll, linewidth=2, linestyle='-.')
        ax1_twin.set_ylabel('全网平均车速 (km/h)', fontsize=11, color=color_glob_toll)
        ax1_twin.tick_params(axis='y', labelcolor=color_glob_toll)
        ax1_twin.set_ylim(bottom=0)

        ax1.set_title('图 1: 峰值车速对比 — CBD 区域 vs 全网均速', fontsize=14, fontweight='bold')
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax1_twin.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='lower right', fontsize=9)

        # ==========================================
        # 图2: CBD 车辆密度 + 费率
        # ==========================================
        ax2.plot(df_base['Time_Step'], df_base['Vehicles_in_CBD'],
                 label='无收费基线车辆数', color='gray', linestyle='--')
        ax2.plot(df_toll['Time_Step'], df_toll['Vehicles_in_CBD'],
                 label='动态收费驻留车辆数', color='crimson', linewidth=2)
        ax2.axhline(y=25, color='orange', linestyle=':', label='Logistic 拥堵拐点 (25辆)')
        ax2.set_ylabel('CBD 驻留车辆数', fontsize=12)
        ax2.set_title('图 2: 动态定价驱离分流效果', fontsize=14, fontweight='bold')
        ax2.legend(loc='upper right')

        # ==========================================
        # 图3: 收入 vs 车速 (双Y轴)
        # ==========================================
        color_rev = 'darkgreen'
        ax3.plot(df_toll['Time_Step'], df_toll['Total_Revenue'],
                 label='累计拥堵费收入', color=color_rev, linewidth=2.5)
        ax3.set_xlabel('仿真时间 (秒)', fontsize=12)
        ax3.set_ylabel('累计收入 (元)', color=color_rev, fontsize=12)
        ax3.tick_params(axis='y', labelcolor=color_rev)

        ax3_twin = ax3.twinx()
        color_speed = 'royalblue'
        ax3_twin.plot(df_toll['Time_Step'], df_toll['CBD_Avg_Speed_mps'] * 3.6,
                      label='CBD实时车速', color=color_speed, alpha=0.6, linestyle='-.')
        ax3_twin.set_ylabel('CBD 实时车速 (km/h)', color=color_speed, fontsize=12)
        ax3_twin.tick_params(axis='y', labelcolor=color_speed)

        ax3.set_title('图 3: 收入增长与 CBD 车速关联视图', fontsize=14, fontweight='bold')
        # 合并双Y轴的图例（必须手动合并，否则只显示主轴的图例）
        lines1, labels1 = ax3.get_legend_handles_labels()
        lines2, labels2 = ax3_twin.get_legend_handles_labels()
        ax3.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        fig.tight_layout()
        output_file = "toll_evaluation_charts.png"
        plt.savefig(output_file, dpi=300)
        print(f"图表已保存: {output_file}")

    except Exception as e:
        print(f"绘图失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    draw_comprehensive_charts()