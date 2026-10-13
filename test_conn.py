"""数据库连接自检：验证 db.py 配置可正常连通 campus_carpool"""
from sqlalchemy import text

from db import engine

try:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION();")).scalar()
        print(f"数据库连接成功！MySQL 版本号是: {version}")
        tables = conn.execute(text("SHOW TABLES;")).scalars().all()
        print(f"campus_carpool 当前数据表（{len(tables)} 张）: {tables}")
except Exception as e:
    print(f"连接失败，错误原因是: {e}")
