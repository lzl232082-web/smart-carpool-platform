"""统一数据库连接配置（全项目唯一的 DB_URL，各业务模块均从本文件导入）"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "20050720lzl"
DB_NAME = "campus_carpool"

DB_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# expire_on_commit=False 保证 commit 后对象属性仍可访问
engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    """获取一个数据库会话（用完记得 close）"""
    return SessionLocal()
