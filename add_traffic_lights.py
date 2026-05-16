"""
给 CBD 网格路网内的所有路口安装红绿灯
CBD 范围: x=800~2800, y=800~2800 (junction C2 到 H7)
"""
import xml.etree.ElementTree as ET
from config import CBD_X_MIN, CBD_X_MAX, CBD_Y_MIN, CBD_Y_MAX

tree = ET.parse('cbd_grid.net.xml')
root = tree.getroot()

count = 0
for junction in root.findall('junction'):
    jtype = junction.get('type', '')
    if jtype == 'internal':
        continue
    x = float(junction.get('x', 0))
    y = float(junction.get('y', 0))
    jid = junction.get('id', '')

    if CBD_X_MIN <= x <= CBD_X_MAX and CBD_Y_MIN <= y <= CBD_Y_MAX:
        old_type = junction.get('type')
        junction.set('type', 'traffic_light')
        count += 1
        print(f"  [{count:2d}] {jid} ({x:.0f},{y:.0f}): {old_type} → traffic_light")

tree.write('cbd_grid.net.xml', encoding='UTF-8', xml_declaration=True)
print(f"\n已安装 {count} 个红绿灯 (CBD 范围: {CBD_X_MIN}~{CBD_X_MAX}, {CBD_Y_MIN}~{CBD_Y_MAX})")