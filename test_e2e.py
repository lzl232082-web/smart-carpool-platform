"""端到端业务流程自测（幂等版，可重复运行）：发布→推荐→接单→加入→行程→互评→统计"""
import datetime
import time

import auth
import carpool_ops as ops
import notify

ok_all = True
suffix = str(int(time.time()))[-6:]  # 每次运行生成新账号，保证幂等
S1, S2, D1 = f'9{suffix[:5]}1', f'9{suffix[:5]}2', f'DRV{suffix}'
PWD = '123456'


def check(name, cond, extra=''):
    global ok_all
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        ok_all = False


# 1. 注册/登录
check('学生1注册', auth.register_student(S1, '张三', '13800000001', PWD)[0])
check('学生2注册', auth.register_student(S2, '李四', '13800000002', PWD)[0])
check('司机注册', auth.register_driver(D1, '王师傅', '13900000001', PWD)[0])
ok, msg, stu1 = auth.login_student(S1, PWD)
check('学生1登录', ok)
ok, msg, stu2 = auth.login_student(S2, PWD)
check('学生2登录', ok)
ok, msg, drv = auth.login_driver(D1, PWD)
check('司机登录', ok)
check('错误密码被拒绝', not auth.login_student(S1, 'wrong')[0])

# 2. 车辆登记
check('车辆登记', ops.add_vehicle(D1, f'苏T{suffix[-5:]}', '比亚迪秦', 4)[0])
check('车辆查询', len(ops.get_driver_vehicles(D1)) == 1)

# 3. 发布拼车（费用预估）
now = datetime.datetime.now() + datetime.timedelta(hours=1)
t = now.strftime("%Y-%m-%d %H:%M")
ok, msg = ops.create_carpool_request(S1, '宿舍区1栋', '东门', t, 2, '有大件行李')
check('学生1发布拼车', ok, msg)
ok, msg = ops.create_carpool_request(S2, '宿舍区9栋', '东门', t, 1, '')
check('学生2发布拼车', ok, msg)
open_reqs = ops.get_open_carpool_requests()
req1 = [r for r in open_reqs if str(r.student_number) == S1][0]
check('费用已预估', req1.estimated_fare is not None, f'fare={req1.estimated_fare}')

# 4. K-Means 推荐 + 重叠度
recs = ops.recommend_for_student(S1, '宿舍区1栋', '东门', now)
check('推荐非空', len(recs) >= 1)
if recs:
    check('重叠度>0', recs[0]['overlap'] > 0, f"overlap={recs[0]['overlap']:.2f}")

# 5. 司机接单
vid = ops.get_driver_vehicles(D1)[0].id
ok, msg = ops.accept_carpool_request(req1.request_id, D1, vid)
check('司机接单', ok, msg)
check('重复接单被拒绝', not ops.accept_carpool_request(req1.request_id, D1, vid)[0])

# 6. 加入拼车
ok, msg = ops.join_carpool(req1.request_id, S2, 1)
check('学生2加入拼车', ok, msg)
check('重复加入被拒绝', not ops.join_carpool(req1.request_id, S2, 1)[0])

# 7. 行程管理
ok, msg = ops.start_trip(req1.request_id, D1)
check('开始行程', ok, msg)
ok, msg = ops.complete_trip(req1.request_id, D1)
check('完成行程', ok, msg)

# 8. 互评
can, target = ops.can_review(req1.request_id, 'student', S1)
check('学生可评司机', can and target == D1)
check('学生提交评价', ops.submit_review(req1.request_id, 'student', S1, 'driver', D1, 5, '师傅很准时')[0])
can, target = ops.can_review(req1.request_id, 'driver', D1)
check('司机可评学生', can and target == S1)
check('司机提交评价', ops.submit_review(req1.request_id, 'driver', D1, 'student', S1, 4, '守时')[0])
check('评价后不可重复评', not ops.can_review(req1.request_id, 'student', S1)[0])
rep = ops.get_reputation('driver', D1)
check('司机信誉=5.0', rep == 5.0, f'rep={rep}')

# 9. 通知
notes = notify.get_notifications('student', S1)
check('学生1收到通知', len(notes) >= 2, f'n={len(notes)}')
types = {n.n_type for n in notes}
check('含接单/加入通知', 'accept' in types and 'join' in types, types)
notify.mark_all_read('student', S1)
check('全部已读', notify.unread_count('student', S1) == 0)

# 10. 编辑/取消
ok, msg = ops.create_carpool_request(S1, '校门口', '体育馆', t, 1, '')
open_reqs2 = ops.get_open_carpool_requests()
req2 = [r for r in open_reqs2 if str(r.student_number) == S1][0]
ok, msg = ops.update_request(req2.request_id, S1, seats=3, remark='改行李')
check('编辑订单', ok, msg)
s = __import__('db').SessionLocal()
from models import CarpoolRequestModel
r2 = s.query(CarpoolRequestModel).get(req2.request_id)
check('编辑已生效', r2.seats_needed == 3 and r2.remark == '改行李')
s.close()
ok, msg = ops.cancel_request(req2.request_id, student_number=S1)
check('取消订单', ok, msg)

# 11. 相似度 & 统计
sims = ops.similar_students(S1)
check('相似度计算不报错', isinstance(sims, list))
days, pub, act = ops.stats_daily_publish()
check('每日统计非空', len(days) >= 1)
check('时段热度非空', len(ops.stats_hour_heat()) >= 1)
check('状态分布非空', len(ops.stats_status_dist()) >= 1)
ov = ops.stats_overview()
check('总览完成数>=1', ov['completed'] >= 1, ov)

# 12. 设置与密码
check('保存设置', auth.save_settings('student', S1, theme='dark', language='en', notify_system=0)[0])
p = auth.get_settings('student', S1)
check('设置保存读取', p.theme == 'dark' and p.language == 'en')
check('修改密码', auth.change_password('student', S1, PWD, 'abc123')[0])
check('新密码可登录', auth.login_student(S1, 'abc123')[0])
check('旧密码被拒绝', not auth.login_student(S1, PWD)[0])
check('改回密码', auth.change_password('student', S1, 'abc123', PWD)[0])

print('\n===== 全部测试', '通过' if ok_all else '存在失败', '=====')
