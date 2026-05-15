#对比分析对照实验
#车密度和车速对比


import pandas as pd
import matplotlib.pyplot as plt

def draw_comprehensive_charts():
    # 设置图表样式与中文字体 
    plt.style.use('seaborn-v0_8-whitegrid')
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS'] 
    plt.rcParams['axes.unicode_minus'] = False

    try:
        print("正在读取仿真报告...")
        df_base = pd.read_csv("baseline_report.csv")
        df_toll = pd.read_csv("weihai_analysis_report.csv")

        # 创建 3 行 1 列的大型三联图表，共享 X 轴 (时间)
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 14), sharex=True)

        # ==========================================
        # 平均车速对比 (Average Speed)
        # ==========================================
        ax1.plot(df_base['Time_Step'], df_base['Average_Speed_mps'] * 3.6, label='无收费基线模式', color='gray', linestyle='--')
        ax1.plot(df_toll['Time_Step'], df_toll['Average_Speed_mps'] * 3.6, label='动态收费干预模式', color='royalblue', linewidth=2)
        ax1.set_ylabel('CBD 平均车速 (km/h)', fontsize=12)
        ax1.set_title('图 1: 威海 CBD 拥堵早高峰车速恢复对比', fontsize=14, fontweight='bold')
        ax1.legend(loc='lower right')

        # ==========================================
        # 车辆密度分流对比 (Traffic Density)
        # ==========================================
        ax2.plot(df_base['Time_Step'], df_base['Vehicles_in_CBD'], label='无收费基线车辆数', color='gray', linestyle='--')
        ax2.plot(df_toll['Time_Step'], df_toll['Vehicles_in_CBD'], label='动态收费驻留车辆数', color='crimson', linewidth=2)
        ax2.axhline(y=50, color='orange', linestyle=':', label='Logistic 拥堵预警拐点')
        ax2.set_ylabel('区域驻留车辆数', fontsize=12)
        ax2.set_title('图 2: 动态定价驱离分流效果评估', fontsize=14, fontweight='bold')
        ax2.legend(loc='upper right')

        # ==========================================
        # 收入 vs 车速 
        # ==========================================
        color_rev = 'darkgreen'
        ax3.plot(df_toll['Time_Step'], df_toll['Total_Revenue'], label='累计拥堵费收入 (¥)', color=color_rev, linewidth=2.5)
        ax3.set_xlabel('仿真时间 (秒)', fontsize=12)
        ax3.set_ylabel('财政总收入 (¥)', color=color_rev, fontsize=12)
        ax3.tick_params(axis='y', labelcolor=color_rev)
        
        # 创建共用 X 轴的副 Y 轴，用于同框展示车速
        ax3_twin = ax3.twinx()
        color_speed = 'royalblue'
        ax3_twin.plot(df_toll['Time_Step'], df_toll['Average_Speed_mps'] * 3.6, label='实时车速', color=color_speed, alpha=0.6, linestyle='-.')
        ax3_twin.set_ylabel('实时车速 (km/h)', color=color_speed, fontsize=12)
        ax3_twin.tick_params(axis='y', labelcolor=color_speed)
        
        ax3.set_title('每小时收益增长与车速恢复关联视图', fontsize=14, fontweight='bold')

        # 调整布局并保存
        fig.tight_layout()
        output_file = "weihai_toll_evaluation_charts.png"
        plt.savefig(output_file, dpi=300)
        print(f"三维高阶评价图表生成成功，已保存至: {output_file}")

    except Exception as e:
        print(f"绘图失败: {e}")

if __name__ == "__main__":
    draw_comprehensive_charts()