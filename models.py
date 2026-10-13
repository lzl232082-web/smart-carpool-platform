"""SQLAlchemy ORM 模型：与 MySQL campus_carpool 库实际表结构对齐。

核心 8 张表（与策划书数据库物理模型一致）：
students / drivers / vehicles / carpool_requests / carpool_joins /
driver_offers / node_locations / node_distances
扩展 3 张表（支撑消息通知、互评信誉、系统设置功能）：
notifications / reviews / user_settings
"""
import datetime

from sqlalchemy import (BigInteger, Column, DateTime, Double, Integer,
                        SmallInteger, String, Text)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ==================== 1. 学生表 ====================
class StudentModel(Base):
    __tablename__ = 'students'
    student_id = Column(Integer, primary_key=True, autoincrement=True)
    student_number = Column(Integer, unique=True, nullable=False, comment='学号')
    name = Column(String(50), nullable=False, comment='姓名')
    phone = Column(String(20), comment='手机号')
    password_hash = Column(String(255), nullable=False, comment='密码')
    created_at = Column(DateTime, default=datetime.datetime.now, comment='创建时间')


# ==================== 2. 司机表 ====================
class DriverModel(Base):
    __tablename__ = 'drivers'
    driver_id = Column(Integer, primary_key=True, autoincrement=True)
    driver_license = Column(String(50), unique=True, nullable=False, comment='驾照号')
    real_name = Column(String(50), nullable=False, comment='姓名')
    phone = Column(String(20), nullable=False, comment='手机号')
    driver_password = Column(String(255), nullable=False, comment='密码')
    is_approved = Column(SmallInteger, default=0, comment='是否通过认证(0未审核/1已认证)')
    created_at = Column(DateTime, default=datetime.datetime.now, comment='创建时间')


# ==================== 3. 车辆表 ====================
class VehicleModel(Base):
    __tablename__ = 'vehicles'
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    driver_license = Column(String(50), nullable=False, comment='驾照号')
    plate_number = Column(String(20), nullable=False, comment='车牌号')
    brand = Column(String(50), comment='车品牌/车型')
    seat_capacity = Column(Integer, nullable=False, comment='座位数')


# ==================== 4. 发布拼车表 ====================
class CarpoolRequestModel(Base):
    __tablename__ = 'carpool_requests'
    request_id = Column(Integer, primary_key=True, autoincrement=True)
    student_number = Column(Integer, nullable=False, comment='学号')
    departure = Column(String(100), nullable=False, comment='出发地(节点名称)')
    destination = Column(String(100), nullable=False, comment='目的地(节点名称)')
    departure_time = Column(DateTime, nullable=False, comment='出发时间')
    seats_needed = Column(Integer, nullable=False, comment='所需座位数')
    status = Column(String(20), default='open',
                    comment='open待接单/accepted已接单/in_progress行程中/completed已完成/cancelled已取消')
    remark = Column(String(255), comment='备注(行李/吸烟等特殊要求)')
    estimated_fare = Column(Double, comment='预估费用(元)')
    created_at = Column(DateTime, default=datetime.datetime.now, comment='创建时间')


# ==================== 5. 加入拼车表 ====================
class CarpoolJoinModel(Base):
    __tablename__ = 'carpool_joins'
    booking_id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, nullable=False, comment='发布id')
    student_number = Column(Integer, nullable=False, comment='学号')
    seats = Column(Integer, nullable=False, comment='座位数')
    booked_at = Column(DateTime, default=datetime.datetime.now, comment='加入时间')
    status = Column(String(20), default='joined', comment='joined已加入/left已退出')


# ==================== 6. 司机接单表 ====================
class DriverOfferModel(Base):
    __tablename__ = 'driver_offers'
    offer_id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, nullable=False, comment='发布id')
    driver_license = Column(String(50), nullable=False, comment='驾照号')
    vehicle_id = Column(BigInteger, nullable=False, comment='车辆id')
    offer_time = Column(DateTime, default=datetime.datetime.now, comment='接单时间')
    status = Column(String(20), default='accepted',
                    comment='accepted已接单/in_progress行程中/completed已完成/cancelled已取消')
    remaining_seats = Column(Integer, comment='剩余座位')


# ==================== 7. 节点位置表 ====================
class NodeLocationModel(Base):
    __tablename__ = 'node_locations'
    node_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment='节点名称')
    latitude = Column(Double, nullable=False, comment='纬度')
    longitude = Column(Double, nullable=False, comment='经度')


# ==================== 8. 路径距离表 ====================
class NodeDistanceModel(Base):
    __tablename__ = 'node_distances'
    edge_id = Column(Integer, primary_key=True, autoincrement=True)
    from_node = Column(Integer, nullable=False, comment='起点节点id')
    to_node = Column(Integer, nullable=False, comment='终点节点id')
    distance = Column(Double, nullable=False, comment='距离(米)')
    congestion = Column(Double, default=0.2, comment='拥堵系数(0~1)')


# ==================== 9. 消息通知表(扩展) ====================
class NotificationModel(Base):
    __tablename__ = 'notifications'
    notify_id = Column(Integer, primary_key=True, autoincrement=True)
    target_role = Column(String(20), nullable=False, comment='student/driver')
    target_key = Column(String(50), nullable=False, comment='学号或驾照号')
    title = Column(String(100), nullable=False, comment='标题')
    content = Column(String(500), nullable=False, comment='内容')
    n_type = Column(String(20), default='system', comment='accept接单/join加入/system系统')
    is_read = Column(SmallInteger, default=0, comment='0未读/1已读')
    created_at = Column(DateTime, default=datetime.datetime.now, comment='时间')


# ==================== 10. 互评表(扩展) ====================
class ReviewModel(Base):
    __tablename__ = 'reviews'
    review_id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, nullable=False, comment='订单id')
    reviewer_role = Column(String(20), nullable=False, comment='评价人角色student/driver')
    reviewer_key = Column(String(50), nullable=False, comment='评价人(学号/驾照号)')
    reviewee_role = Column(String(20), nullable=False, comment='被评价人角色')
    reviewee_key = Column(String(50), nullable=False, comment='被评价人(驾照号/学号)')
    rating = Column(Integer, nullable=False, comment='评分1~5')
    comment = Column(String(255), comment='评语')
    created_at = Column(DateTime, default=datetime.datetime.now, comment='时间')


# ==================== 11. 用户设置表(扩展) ====================
class UserSettingModel(Base):
    __tablename__ = 'user_settings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(20), nullable=False, comment='student/driver')
    user_key = Column(String(50), nullable=False, comment='学号或驾照号')
    language = Column(String(10), default='zh', comment='zh中文/en英语')
    theme = Column(String(10), default='light', comment='light明亮/dark暗黑')
    notify_activity = Column(SmallInteger, default=1, comment='活动通知')
    notify_system = Column(SmallInteger, default=1, comment='系统通知')
    notify_carpool = Column(SmallInteger, default=1, comment='拼车提醒')
    emergency_contact = Column(String(100), comment='紧急联系人')
