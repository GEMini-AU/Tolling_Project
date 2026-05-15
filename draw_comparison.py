#对比分析对照实验
#车密度和车速对比


import pandas as pd
import matplotlib.pyplot as plt

# 设置中文字体（根据你的系统可能需要微调，Windows默认黑体）
plt.rcParams['font.sans-serif'] = ['SimHei'] 
plt.rcParams['axes.unicode_minus'] = False

print("正在生成 A/B 测试对比图表...")

try:
    df_base = pd.read_csv("baseline_report.csv")
    df_toll = pd.read_csv("weihai_analysis_report.csv")

    plt.figure(figsize=(14, 10))

    # --- 图 1：全城平均车速对比 ---
    plt.subplot(2, 1, 1)
    plt.plot(df_base['Time_Step'], df_base['Average_Speed_mps'] * 3.6, label='基线组 (不收费)', color='#e74c3c', linewidth=2, linestyle='--')
    plt.plot(df_toll['Time_Step'], df_toll['Average_Speed_mps'] * 3.6, label='实验组 (动态收费)', color='#2ecc71', linewidth=2)
    plt.title('全城平均车速对比 (km/h)', fontsize=16)
    plt.xlabel('仿真时间 (秒)', fontsize=12)
    plt.ylabel('平均车速 (km/h)', fontsize=12)
    plt.legend(fontsize=12)
    plt.grid(True, alpha=0.3)

    # --- 图 2：CBD 核心区拥堵程度对比 ---
    plt.subplot(2, 1, 2)
    plt.plot(df_base['Time_Step'], df_base['Vehicles_in_CBD'], label='基线组 (不收费)', color='#e74c3c', linewidth=2, linestyle='--')
    plt.plot(df_toll['Time_Step'], df_toll['Vehicles_in_CBD'], label='实验组 (动态收费)', color='#3498db', linewidth=2)
    plt.title('CBD 核心区车辆密度对比 (拥堵程度)', fontsize=16)
    plt.xlabel('仿真时间 (秒)', fontsize=12)
    plt.ylabel('区域内车辆数 (辆)', fontsize=12)
    plt.axhline(y=40, color='orange', linestyle=':', label='Logistic 拥堵预警拐点 (40辆)')
    plt.legend(fontsize=12)
    plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('baseline_vs_tolling_comparison.png', dpi=300)
    print("生成成功！请查看当前目录下的 baseline_vs_tolling_comparison.png")
    plt.show()

except FileNotFoundError:
    print("找不到 CSV 文件，请确保 baseline_report.csv 和 weihai_analysis_report.csv 存在。")