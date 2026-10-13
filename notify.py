"""消息通知模块（策划书第五章-5 消息通知模块）：

三类通知：
- accept 接单通知：司机接单后推送给发布者与已加入的同学
- join   加入通知：有同学加入拼车时推送给司机与发布者
- system 系统维护通知：平台公告

通知持久化到 notifications 表，用户可在"消息中心"查看并标记已读；
读取时会按 user_settings 中的通知偏好过滤。
"""
from db import SessionLocal
from models import NotificationModel, UserSettingModel


def push(target_role: str, target_key: str, title: str, content: str, n_type: str = 'system'):
    """写入一条通知。target_role: student/driver；target_key: 学号或驾照号。"""
    s = SessionLocal()
    try:
        s.add(NotificationModel(target_role=target_role, target_key=str(target_key),
                                title=title, content=content, n_type=n_type))
        s.commit()
        return True
    except Exception:
        s.rollback()
        return False
    finally:
        s.close()


def get_notifications(target_role: str, target_key: str, only_unread=False):
    """拉取某用户的通知（按 user_settings 偏好过滤类型，最新在前）。"""
    s = SessionLocal()
    try:
        q = s.query(NotificationModel).filter(
            NotificationModel.target_role == target_role,
            NotificationModel.target_key == str(target_key))
        if only_unread:
            q = q.filter(NotificationModel.is_read == 0)
        rows = q.order_by(NotificationModel.notify_id.desc()).all()
        # 读取偏好设置，过滤不需要的通知类型
        pref = s.query(UserSettingModel).filter_by(
            role=target_role, user_key=str(target_key)).first()
        if pref:
            allow = {'accept': bool(pref.notify_carpool), 'join': bool(pref.notify_carpool),
                     'system': bool(pref.notify_system)}
            rows = [r for r in rows if allow.get(r.n_type, True)]
        return rows
    finally:
        s.close()


def unread_count(target_role: str, target_key: str) -> int:
    return len(get_notifications(target_role, target_key, only_unread=True))


def mark_read(notify_id: int):
    s = SessionLocal()
    try:
        n = s.query(NotificationModel).get(notify_id)
        if n:
            n.is_read = 1
            s.commit()
    finally:
        s.close()


def mark_all_read(target_role: str, target_key: str):
    s = SessionLocal()
    try:
        s.query(NotificationModel).filter(
            NotificationModel.target_role == target_role,
            NotificationModel.target_key == str(target_key),
            NotificationModel.is_read == 0).update(
            {NotificationModel.is_read: 1}, synchronize_session=False)
        s.commit()
    finally:
        s.close()


def broadcast_system(title: str, content: str):
    """向全体用户发布系统维护公告。"""
    s = SessionLocal()
    try:
        from models import DriverModel, StudentModel
        for stu in s.query(StudentModel).all():
            s.add(NotificationModel(target_role='student', target_key=str(stu.student_number),
                                    title=title, content=content, n_type='system'))
        for drv in s.query(DriverModel).all():
            s.add(NotificationModel(target_role='driver', target_key=drv.driver_license,
                                    title=title, content=content, n_type='system'))
        s.commit()
    except Exception:
        s.rollback()
    finally:
        s.close()
