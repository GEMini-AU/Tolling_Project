import subprocess
import os
import sys

print(" 初始化交通流生成引擎 (Grid CBD Traffic Demand)...")

net_file = "cbd_grid.net.xml"
sumo_home = os.environ.get('SUMO_HOME')

if not sumo_home:
    sys.exit(" 未找到 SUMO_HOME 环境变量，请检查系统配置。")

script_path = os.path.join(sumo_home, 'tools', 'randomTrips.py')

# 核心发车参数
# period=2.7 → 约 4000 辆车
# fringe-factor=10 → 大部分车从路网边缘出发/到达, 路线必然穿越 CBD
cmd_list = [
    sys.executable,
    script_path,
    "-n", net_file,
    "-r", "routes.rou.xml",
    "-b", "0",
    "-e", "10800",               # 3小时早高峰
    "-p", "2.7",                 # 每2.7秒发一辆 → 10800/2.7 ≈ 4000辆, 符合题目规模
    "--vclass", "passenger",
    "--fringe-factor", "10",     # 边缘发车权重10倍 → 制造CBD穿越车流
]

approx_count = int(10800 / 2.7)
print(f"路网: {net_file} | 预计发车 ~{approx_count} 辆 (10800s / 2.7s)")

try:
    result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
    print("\n CBD 3小时早高峰车流生成完毕")
    if result.stdout:
        # randomTrips.py 会输出统计信息
        for line in result.stdout.strip().split('\n'):
            if 'trip' in line.lower() or 'vehicle' in line.lower() or 'total' in line.lower():
                print(f"  {line}")
except subprocess.CalledProcessError as e:
    print("\n 引擎报错:")
    print(e.stderr if e.stderr else "空错误输出")
except Exception as e:
    print(f"\n未知错误: {e}")
