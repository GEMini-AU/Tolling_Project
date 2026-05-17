"""
一键运行: 清理旧数据 → 仿真 → 审计 → KPI → 图表
用法: python run_all.py
"""
import os
import sys
import subprocess

PYTHON = sys.executable
STEPS = [
    ("清理旧数据", [PYTHON, "-c", "import os; [os.remove(f) for f in ['baseline.db','toll_system.db','baseline_report.csv','toll_analysis_report.csv'] if os.path.exists(f)]; print('已清理')"]),
    ("运行仿真 (约5-10分钟)", [PYTHON, "main.py"]),
    ("行程审计", [PYTHON, "audit.py"]),
    ("KPI 分析", [PYTHON, "calculate_kpis.py"]),
    ("生成图表", [PYTHON, "draw_comparison.py"]),
]

for name, cmd in STEPS:
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0 and name != "清理旧数据":
        print(f"[警告] {name} 返回码: {result.returncode}")

print(f"\n{'='*50}")
print("  全部完成! 查看 toll_evaluation_charts.png")
print(f"{'='*50}")