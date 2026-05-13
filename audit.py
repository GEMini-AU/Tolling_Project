import sqlite3
import pandas as pd



# 1. 连接数据库
db_path = "weihai_toll_system.db"
conn = sqlite3.connect(db_path)

try:
    # 查询 Wallet 表：找出“被扣费最多”的 5 辆车（账户余额最低的）
    print("="*50)
    print("【电子钱包账户抽查】 - 扣费最多的前 5 辆车")
    print("="*50)
    # 用 SQL 语句按余额升序排列，取前 5 行
    wallet_query = "SELECT veh_id AS '车辆牌照(ID)', balance AS '账户余额(元)' FROM Wallet ORDER BY balance ASC LIMIT 5"
    wallet_df = pd.read_sql_query(wallet_query, conn)
    print(wallet_df.to_string(index=False))
    print("\n")

    # 查询 Logs 表：查看最近发生的 5 笔交易流水
    print("="*50)
    print("【路网扣费交易流水】 - 最新 5 笔抓拍记录")
    print("="*50)
    # 用 SQL 语句按时间步倒序排列，取前 5 行
    logs_query = "SELECT veh_id AS '车辆牌照(ID)', amount AS '扣费金额(元)', step AS '发生时间(秒)' FROM Logs ORDER BY step DESC LIMIT 5"
    logs_df = pd.read_sql_query(logs_query, conn)
    print(logs_df.to_string(index=False))
    print("\n")

    # 让数据库自己算总账
    print("="*50)
    print("【财务总账核对】")
    print("="*50)
    total_revenue_query = "SELECT SUM(amount) FROM Logs"
    cursor = conn.cursor()
    cursor.execute(total_revenue_query)
    total_db_revenue = cursor.fetchone()[0]
    print(f"数据库底层汇总的总财政收入为: ¥{total_db_revenue:.2f}")
    

except Exception as e:
    print(f"读取数据库失败，请确认文件名正确且已生成数据。错误信息: {e}")
finally:
    conn.close()
    print("数据库连接已安全关闭。")