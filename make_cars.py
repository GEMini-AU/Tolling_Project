import subprocess
import os
import sys

print("🔍 启动物理级造车引擎...")

map_file = "weihai_cbd.net.xml"
sumo_home = os.environ.get('SUMO_HOME')
script_path = os.path.join(sumo_home, 'tools', 'randomTrips.py')

# 使用 sys.executable 获取当前运行这段代码的“真·Python”绝对路径
# 把所有命令拆成一个列表，完全避开 Windows 终端的引号、空格和假代号
cmd_list = [
    sys.executable,  
    script_path,
    "-n", map_file,
    "-r", "routes.rou.xml",
    "-e", "10800",
    "-p", "2.7"
]

print(f"🚗 正在威海地图上强行注入 4000 辆车...")

try:
    # 抛弃 shell=True，直接让底层操作系统执行列表里的物理文件
    result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
    print("\n✅ 奇迹发生！威海市 4000 辆车早高峰生成完毕！")
    print("👉 现在，请毫不犹豫地去运行你的 main.py！")
    
except subprocess.CalledProcessError as e:
    print("\n❌ 引擎报错（这次绝对逃不掉）：")
    print(e.stderr if e.stderr else "依然是空...")
except Exception as e:
    print("\n❌ 发生极其底层的未知错误：", str(e))