import os
import sys
tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
os.system(f'python "{tools}/randomTrips.py" -n weihai_cbd.net.xml -r routes.rou.xml -e 10800 -p 2.7')
print("✅ 威海市 4000 辆车早高峰生成完毕！")