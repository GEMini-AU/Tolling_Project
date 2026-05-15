import subprocess
import os
import sys

print(" 初始化交通流生成引擎 (Traffic Demand Generation)...")

map_file = "weihai_cbd.net.xml"
sumo_home = os.environ.get('SUMO_HOME')

if not sumo_home:
    sys.exit(" 未找到 SUMO_HOME 环境变量，请检查系统配置。")

script_path = os.path.join(sumo_home, 'tools', 'randomTrips.py')


# 核心发车参数配置 

cmd_list = [
    sys.executable,  
    script_path,
    "-n", map_file,
    "-r", "routes.rou.xml",
    "-b", "0",                  # 绝对零点启动，确保从第 0 秒开始生成
    "-e", "10800",              # 终止时间：第 10800 秒 (3小时)
    "-p", "2.7",                # 泊松分布发车间隔
    "--vclass", "passenger",    # 强制要求所有生成的车辆模型均为轿车
    "--fringe-factor", "10"     # 边缘发车权重设为10，强制让大部分车从路网边缘进入CBD
]

print("威海路网注入轿车")

try:
    
    result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
    print("\n 威海 CBD 3小时早高峰车流生成完毕")
    
    
except subprocess.CalledProcessError as e:
    print("\n 引擎报错")
    print(e.stderr if e.stderr else "依然是空...")
except Exception as e:
    print("\n未知错误：", str(e))