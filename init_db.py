"""数据库初始化脚本：
1. 自动创建 campus_carpool 数据库
2. 按模型创建全部核心表与扩展表（已存在的表不重建）
3. 对旧表缺失的列自动补齐（无损迁移）
4. 写入校园路网种子数据（节点 + 带拥堵系数的道路），供 Dijkstra 路径规划使用
"""
from sqlalchemy import create_engine, inspect, text

from db import DB_PASSWORD, DB_URL, engine
from models import Base

# ---------- 1. 创建数据库 ----------
engine_temp = create_engine(
    f"mysql+pymysql://root:{DB_PASSWORD}@localhost:3306/?charset=utf8mb4")
with engine_temp.connect() as conn:
    conn.execute(text(
        "CREATE DATABASE IF NOT EXISTS campus_carpool "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"))
print("数据库 'campus_carpool' 创建成功（或已存在）！")

# ---------- 2. 建表（核心 8 张 + 扩展 3 张）----------
Base.metadata.create_all(engine)
print("全部数据表创建成功（已存在的表自动跳过）！")

# ---------- 3. 旧表缺列自动补齐 ----------
MIGRATE_COLUMNS = [
    ("carpool_requests", "remark", "ALTER TABLE carpool_requests ADD COLUMN remark VARCHAR(255) COMMENT '备注'"),
    ("carpool_requests", "estimated_fare", "ALTER TABLE carpool_requests ADD COLUMN estimated_fare DOUBLE COMMENT '预估费用'"),
    ("node_distances", "congestion", "ALTER TABLE node_distances ADD COLUMN congestion DOUBLE DEFAULT 0.2 COMMENT '拥堵系数'"),
]
insp = inspect(engine)
with engine.begin() as conn:
    for table, col, ddl in MIGRATE_COLUMNS:
        if table in insp.get_table_names() and col not in [
                c["name"] for c in insp.get_columns(table)]:
            conn.execute(text(ddl))
            print(f"表 {table} 补齐列 {col} 完成")

# ---------- 4. 校园路网种子数据 ----------
CAMPUS_NODES = [
    # (名称, 纬度, 经度)
    ("校门口", 32.0652, 118.7861),
    ("图书馆", 32.0628, 118.7885),
    ("第一教学楼", 32.0641, 118.7902),
    ("实验楼", 32.0615, 118.7920),
    ("大学生活动中心", 32.0602, 118.7879),
    ("第一食堂", 32.0634, 118.7862),
    ("体育馆", 32.0589, 118.7898),
    ("宿舍区1栋", 32.0596, 118.7855),
    ("宿舍区9栋", 32.0581, 118.7868),
    ("行政楼", 32.0648, 118.7919),
    ("校医院", 32.0611, 118.7941),
    ("东门", 32.0608, 118.7962),
]
CAMPUS_EDGES = [
    # (起点名称, 终点名称, 距离米, 拥堵系数)
    ("校门口", "图书馆", 320, 0.5),
    ("图书馆", "第一教学楼", 210, 0.4),
    ("第一教学楼", "实验楼", 260, 0.2),
    ("图书馆", "第一食堂", 340, 0.6),
    ("校门口", "第一食堂", 280, 0.5),
    ("第一食堂", "宿舍区1栋", 300, 0.3),
    ("宿舍区1栋", "宿舍区9栋", 260, 0.2),
    ("宿舍区9栋", "体育馆", 350, 0.3),
    ("体育馆", "大学生活动中心", 240, 0.2),
    ("大学生活动中心", "宿舍区1栋", 330, 0.3),
    ("第一教学楼", "行政楼", 180, 0.2),
    ("行政楼", "实验楼", 220, 0.2),
    ("实验楼", "校医院", 300, 0.2),
    ("校医院", "东门", 380, 0.3),
    ("体育馆", "东门", 420, 0.4),
    ("图书馆", "行政楼", 250, 0.3),
    ("大学生活动中心", "第一食堂", 310, 0.4),
    ("实验楼", "图书馆", 300, 0.3),
]

from models import NodeDistanceModel, NodeLocationModel  # noqa: E402
from db import SessionLocal  # noqa: E402

s = SessionLocal()
try:
    if s.query(NodeLocationModel).count() == 0:
        name2id = {}
        for name, lat, lng in CAMPUS_NODES:
            node = NodeLocationModel(name=name, latitude=lat, longitude=lng)
            s.add(node)
            s.flush()
            name2id[name] = node.node_id
        for a, b, dist, cong in CAMPUS_EDGES:
            s.add(NodeDistanceModel(from_node=name2id[a], to_node=name2id[b],
                                    distance=dist, congestion=cong))
            s.add(NodeDistanceModel(from_node=name2id[b], to_node=name2id[a],
                                    distance=dist, congestion=cong))
        s.commit()
        print(f"路网种子数据写入完成：{len(CAMPUS_NODES)} 个节点，"
              f"{len(CAMPUS_EDGES)} 条双向道路。")
    else:
        print("路网种子数据已存在，跳过。")
finally:
    s.close()

print("数据库初始化全部完成！")
