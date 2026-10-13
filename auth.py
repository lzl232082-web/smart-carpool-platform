"""用户认证与个人中心模块（策划书第五章-1 登录注册、第五章-2 个人信息管理）：

- 学生/司机注册与登录（SHA256 密码哈希）
- 个人资料查看/编辑、密码修改、紧急联系人
- 用户设置（主题/语言/通知偏好）读写
"""
import hashlib

from db import SessionLocal
from models import DriverModel, StudentModel, UserSettingModel, VehicleModel


def hash_password(password: str) -> str:
    """使用 SHA256 对密码进行哈希加密"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


# ==================== 学生端方法 ====================
def register_student(student_number: str, name: str, phone: str, password: str):
    """学生注册"""
    s = SessionLocal()
    try:
        if not student_number.isdigit():
            return False, "学号必须为数字！"
        if len(password) < 6:
            return False, "密码至少 6 位！"
        if s.query(StudentModel).filter_by(student_number=int(student_number)).first():
            return False, "该学号已被注册！"
        s.add(StudentModel(student_number=int(student_number), name=name,
                           phone=phone, password_hash=hash_password(password)))
        s.commit()
        return True, "学生账号注册成功！请前往登录。"
    except Exception as e:
        s.rollback()
        return False, f"注册失败: {e}"
    finally:
        s.close()


def login_student(student_number: str, password: str):
    """学生登录"""
    s = SessionLocal()
    try:
        student = s.query(StudentModel).filter_by(student_number=int(student_number)).first()
        if not student:
            return False, "学号不存在！", None
        if student.password_hash != hash_password(password):
            return False, "密码错误！", None
        return True, "登录成功！", student
    except ValueError:
        return False, "学号必须为数字！", None
    except Exception as e:
        return False, f"登录异常: {e}", None
    finally:
        s.close()


# ==================== 司机端方法 ====================
def register_driver(driver_license: str, real_name: str, phone: str, password: str):
    """司机注册（默认直接通过认证）"""
    s = SessionLocal()
    try:
        if not driver_license.strip():
            return False, "请输入驾照号！"
        if len(password) < 6:
            return False, "密码至少 6 位！"
        if s.query(DriverModel).filter_by(driver_license=driver_license).first():
            return False, "该驾照号已被注册！"
        s.add(DriverModel(driver_license=driver_license, real_name=real_name,
                          phone=phone, driver_password=hash_password(password),
                          is_approved=1))
        s.commit()
        return True, "司机账号注册成功！请前往登录。"
    except Exception as e:
        s.rollback()
        return False, f"注册失败: {e}"
    finally:
        s.close()


def login_driver(driver_license: str, password: str):
    """司机登录（登录后可登录并接单）"""
    s = SessionLocal()
    try:
        driver = s.query(DriverModel).filter_by(driver_license=driver_license).first()
        if not driver:
            return False, "驾照号不存在！", None
        if driver.driver_password != hash_password(password):
            return False, "密码错误！", None
        return True, "登录成功！", driver
    except Exception as e:
        return False, f"登录异常: {e}", None
    finally:
        s.close()


# ==================== 个人中心 ====================
def update_profile(role: str, user_key, name=None, phone=None):
    """修改姓名/手机号等基本资料"""
    s = SessionLocal()
    try:
        if role == 'student':
            obj = s.query(StudentModel).filter_by(student_number=int(user_key)).first()
        else:
            obj = s.query(DriverModel).filter_by(driver_license=user_key).first()
        if not obj:
            return False, "用户不存在！"
        if name:
            obj.name = name
        if phone:
            obj.phone = phone
        s.commit()
        return True, "个人资料修改成功！"
    except Exception as e:
        s.rollback()
        return False, f"修改失败: {e}"
    finally:
        s.close()


def change_password(role: str, user_key, old_pwd: str, new_pwd: str):
    """修改密码（需验证旧密码）"""
    s = SessionLocal()
    try:
        if role == 'student':
            obj = s.query(StudentModel).filter_by(student_number=int(user_key)).first()
        else:
            obj = s.query(DriverModel).filter_by(driver_license=user_key).first()
        if not obj:
            return False, "用户不存在！"
        current_hash = obj.password_hash if role == 'student' else obj.driver_password
        if current_hash != hash_password(old_pwd):
            return False, "原密码错误！"
        if len(new_pwd) < 6:
            return False, "新密码至少 6 位！"
        if current_hash == hash_password(new_pwd):
            return False, "新密码不能与原密码相同！"
        if role == 'student':
            obj.password_hash = hash_password(new_pwd)
        else:
            obj.driver_password = hash_password(new_pwd)
        s.commit()
        return True, "密码修改成功！请牢记新密码。"
    except ValueError:
        return False, "账号格式错误！"
    except Exception as e:
        s.rollback()
        return False, f"修改失败: {e}"
    finally:
        s.close()


# ==================== 用户设置 ====================
def get_settings(role: str, user_key):
    """读取用户设置，不存在则自动创建默认设置"""
    s = SessionLocal()
    try:
        pref = s.query(UserSettingModel).filter_by(role=role,
                                                   user_key=str(user_key)).first()
        if not pref:
            pref = UserSettingModel(role=role, user_key=str(user_key))
            s.add(pref)
            s.commit()
            s.refresh(pref)
        return pref
    finally:
        s.close()


def save_settings(role: str, user_key, **kwargs):
    """保存设置项：language/theme/notify_activity/notify_system/notify_carpool/emergency_contact"""
    s = SessionLocal()
    try:
        pref = s.query(UserSettingModel).filter_by(role=role,
                                                   user_key=str(user_key)).first()
        if not pref:
            pref = UserSettingModel(role=role, user_key=str(user_key))
            s.add(pref)
        for k, v in kwargs.items():
            if hasattr(pref, k) and v is not None:
                setattr(pref, k, v)
        s.commit()
        return True, "设置已保存！"
    except Exception as e:
        s.rollback()
        return False, f"保存失败: {e}"
    finally:
        s.close()
