import sqlite3

print("--- 🏦 开始建造虚拟银行 ---")

# 建立/连接数据库（如果没有这个文件，它会自动帮你建一个）
# 我们给这个银行起名叫 tolling_system.db
conn = sqlite3.connect('tolling_system.db')

# 建立一个游标，由他来执行 SQL 命令
cursor = conn.cursor()

# 3. 建一张名为 Wallet（钱包）的表格
# 表格有两列：vehicle_id (车牌号，作为唯一主键)，balance (账户余额)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS Wallet (
        vehicle_id TEXT PRIMARY KEY,
        balance REAL
    )
''')

# 4. 盖章确认（保存更改）并关门下班
conn.commit()
conn.close()

print("--- ✅ 虚拟钱包表格 (Wallet Schema) 创建成功！ ---")