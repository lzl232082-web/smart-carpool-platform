"""拼车业务操作层（策划书第五章-3 拼车功能模块 + 第五章-2 个人信息管理）：

学生：发布/编辑/取消拼车、浏览聚类推荐、加入/退出拼车、互评
司机：按距离排序接单、管理车辆、开始/完成行程、互评
数据统计：真实库表聚合（每日发布量、时段热度、状态分布、信誉评分）
"""
import datetime

from sqlalchemy import func

from algorithms import (dijkstra, dynamic_fare, get_graph_and_edge_len,
                        get_name2id, get_node_pos, kmeans_cluster_orders,
                        pearson, route_overlap, user_preference_vectors)
from db import SessionLocal
from models import (CarpoolJoinModel, CarpoolRequestModel, DriverOfferModel,
                    DriverModel, NodeLocationModel, ReviewModel, StudentModel,
                    VehicleModel)
from notify import push

STATUS_CN = {'open': '待接单', 'accepted': '已接单', 'in_progress': '行程中',
             'completed': '已完成', 'cancelled': '已取消'}


# ==================== 节点与费用 ====================

def get_node_names():
    s = SessionLocal()
    try:
        return [n.name for n in s.query(NodeLocationModel).order_by(NodeLocationModel.node_id).all()]
    finally:
        s.close()


def estimate_route(departure: str, destination: str, when: datetime.datetime = None):
    """Dijkstra 计算路线：返回 (实际距离米, 动态权重成本, 路径节点名列表, 预估费用)。"""
    g, el = get_graph_and_edge_len()
    name2id = get_name2id()
    if departure not in name2id or destination not in name2id:
        return None
    id2name = {v: k for k, v in name2id.items()}
    cost, dist, path_ids = dijkstra(g, name2id[departure], name2id[destination])
    names = [id2name[i] for i in path_ids if i in id2name] if path_ids else []
    fare = dynamic_fare(dist, when) if dist != float('inf') else None
    return dist, cost, names, fare


# ==================== 学生端：发布 / 编辑 / 取消 ====================

def create_carpool_request(student_number: int, departure: str, destination: str,
                           departure_time: str, seats: int, remark: str = ''):
    """学生发布拼车需求（自动计算距离与动态费用）。"""
    s = SessionLocal()
    try:
        dt = datetime.datetime.strptime(departure_time, "%Y-%m-%d %H:%M")
        route = estimate_route(departure, destination, dt)
        if route is None:
            return False, "出发地或目的地不在校园路网中！"
        dist, _, _, fare = route
        if dist == float('inf'):
            return False, "两地之间暂无可达道路！"
        req = CarpoolRequestModel(
            student_number=int(student_number), departure=departure,
            destination=destination, departure_time=dt, seats_needed=int(seats),
            status='open', remark=remark or '', estimated_fare=fare)
        s.add(req)
        s.commit()
        return True, (f"拼车需求发布成功！全程约 {dist:.0f} 米，"
                      f"预估费用 {fare} 元/人，已进入推荐池。")
    except ValueError:
        return False, "出发时间格式应为 2026-01-01 08:30"
    except Exception as e:
        s.rollback()
        return False, f"发布失败: {e}"
    finally:
        s.close()


def update_request(request_id: int, student_number: int, departure=None,
                   destination=None, departure_time=None, seats=None, remark=None):
    """学生编辑自己尚在待接单状态的订单。"""
    s = SessionLocal()
    try:
        req = s.query(CarpoolRequestModel).filter_by(request_id=request_id,
                                                     student_number=int(student_number)).first()
        if not req:
            return False, "订单不存在！"
        if req.status != 'open':
            return False, "仅待接单状态的订单可以编辑！"
        if departure:
            req.departure = departure
        if destination:
            req.destination = destination
        if departure_time:
            req.departure_time = datetime.datetime.strptime(departure_time, "%Y-%m-%d %H:%M")
            route = estimate_route(req.departure, req.destination, req.departure_time)
            if route and route[0] != float('inf'):
                req.estimated_fare = route[3]
        if seats:
            req.seats_needed = int(seats)
        if remark is not None:
            req.remark = remark
        s.commit()
        return True, "订单修改成功！"
    except ValueError:
        return False, "出发时间格式应为 2026-01-01 08:30"
    except Exception as e:
        s.rollback()
        return False, f"修改失败: {e}"
    finally:
        s.close()


def cancel_request(request_id: int, student_number: int = None,
                   driver_license: str = None):
    """取消订单（学生取消自己发布的；司机可取消自己的接单记录）。"""
    s = SessionLocal()
    try:
        req = s.query(CarpoolRequestModel).filter_by(request_id=request_id).first()
        if not req:
            return False, "订单不存在！"
        if student_number is not None and req.student_number != int(student_number):
            return False, "只能取消自己发布的订单！"
        if req.status in ('completed', 'cancelled'):
            return False, "该订单已结束，无法取消。"
        req.status = 'cancelled'
        s.query(DriverOfferModel).filter_by(request_id=request_id).update(
            {DriverOfferModel.status: 'cancelled'}, synchronize_session=False)
        s.query(CarpoolJoinModel).filter_by(request_id=request_id).update(
            {CarpoolJoinModel.status: 'left'}, synchronize_session=False)
        s.commit()
        push('student', req.student_number, '订单已取消',
             f"行程 #{request_id}（{req.departure}→{req.destination}）已取消。")
        return True, "订单已取消。"
    except Exception as e:
        s.rollback()
        return False, f"取消失败: {e}"
    finally:
        s.close()


# ==================== 订单查询 ====================

def get_open_carpool_requests(exclude_student: int = None):
    """所有待接单订单（排除自己发布的）。"""
    s = SessionLocal()
    try:
        q = s.query(CarpoolRequestModel).filter_by(status='open')
        if exclude_student is not None:
            q = q.filter(CarpoolRequestModel.student_number != int(exclude_student))
        return q.order_by(CarpoolRequestModel.departure_time).all()
    finally:
        s.close()


def get_my_published(student_number: int):
    """我发布的订单（附接单司机、已加入人数）。"""
    s = SessionLocal()
    try:
        reqs = s.query(CarpoolRequestModel).filter(
            CarpoolRequestModel.student_number == int(student_number),
            CarpoolRequestModel.status != 'cancelled'
        ).order_by(CarpoolRequestModel.request_id.desc()).all()
        result = []
        for r in reqs:
            offer = s.query(DriverOfferModel).filter(
                DriverOfferModel.request_id == r.request_id,
                DriverOfferModel.status != 'cancelled').first()
            joins = s.query(CarpoolJoinModel).filter_by(
                request_id=r.request_id, status='joined').all()
            driver_name, plate = None, None
            if offer:
                d = s.query(DriverModel).filter_by(driver_license=offer.driver_license).first()
                v = s.query(VehicleModel).filter_by(id=offer.vehicle_id).first()
                driver_name = d.real_name if d else offer.driver_license
                plate = v.plate_number if v else None
            result.append({'req': r, 'offer': offer, 'joins': joins,
                           'driver_name': driver_name, 'plate': plate,
                           'joined_seats': sum(j.seats for j in joins)})
        return result
    finally:
        s.close()


def get_my_joined(student_number: int):
    """我加入的订单。"""
    s = SessionLocal()
    try:
        rows = s.query(CarpoolJoinModel, CarpoolRequestModel).join(
            CarpoolRequestModel,
            CarpoolJoinModel.request_id == CarpoolRequestModel.request_id
        ).filter(CarpoolJoinModel.student_number == int(student_number),
                 CarpoolJoinModel.status == 'joined'
                 ).order_by(CarpoolJoinModel.booking_id.desc()).all()
        result = []
        for join, req in rows:
            offer = s.query(DriverOfferModel).filter(
                DriverOfferModel.request_id == req.request_id,
                DriverOfferModel.status != 'cancelled').first()
            driver_name, plate, phone = None, None, None
            if offer:
                d = s.query(DriverModel).filter_by(driver_license=offer.driver_license).first()
                v = s.query(VehicleModel).filter_by(id=offer.vehicle_id).first()
                driver_name = d.real_name if d else offer.driver_license
                phone = d.phone if d else None
                plate = v.plate_number if v else None
            result.append({'join': join, 'req': req, 'driver_name': driver_name,
                           'plate': plate, 'driver_phone': phone})
        return result
    finally:
        s.close()


# ==================== 推荐与匹配 ====================

def recommend_for_student(student_number: int, departure: str, destination: str,
                          when: datetime.datetime):
    """K-Means 聚类拼单推荐：
    ① 同簇订单优先；② 路径重叠度高优先；③ 出发时间 ±30 分钟内优先。
    返回 [(订单, 重叠度, 时间差分钟, 是否同簇, 剩余可加入座位)]。
    """
    s = SessionLocal()
    try:
        open_reqs = s.query(CarpoolRequestModel).filter(
            CarpoolRequestModel.status == 'open',
            CarpoolRequestModel.student_number != int(student_number)).all()
    finally:
        s.close()
    if not open_reqs:
        return []

    g, el = get_graph_and_edge_len()
    name2id = get_name2id()
    pos = get_node_pos()
    src, dst = name2id.get(departure), name2id.get(destination)
    if src is None or dst is None:
        return []
    _, _, my_path = dijkstra(g, src, dst)

    # 把"我的需求"也作为一个点参与聚类，从而判断哪些订单与我同簇
    my_pt = None
    if departure in pos and destination in pos:
        d0, d1 = pos[departure], pos[destination]
        my_pt = [d0[0], d0[1], d1[0], d1[1]]
    cluster = kmeans_cluster_orders(open_reqs, my_point=my_pt)
    recs = []
    for r in open_reqs:
        rs, rd = name2id.get(r.departure), name2id.get(r.destination)
        if rs is None or rd is None:
            continue
        _, _, r_path = dijkstra(g, rs, rd)
        overlap = route_overlap(my_path, r_path, el)
        tdiff = abs((r.departure_time - when).total_seconds()) / 60
        same_cluster = (cluster.get(r.request_id) is not None
                        and cluster.get(r.request_id) == cluster.get('me'))
        # 计算剩余可加入座位
        joined = s.query(func.coalesce(func.sum(CarpoolJoinModel.seats), 0)).filter(
            CarpoolJoinModel.request_id == r.request_id,
            CarpoolJoinModel.status == 'joined').scalar()
        offer = s.query(DriverOfferModel).filter(
            DriverOfferModel.request_id == r.request_id,
            DriverOfferModel.status != 'cancelled').first()
        remain = (offer.remaining_seats - joined) if offer else None
        recs.append({'req': r, 'overlap': overlap, 'tdiff': tdiff,
                     'same_cluster': same_cluster, 'remain_seats': remain})
    # 排序：同簇 > 重叠度 > 时间接近
    recs.sort(key=lambda x: (not x['same_cluster'], -x['overlap'], x['tdiff']))
    return recs


def similar_students(student_number: int, top_n=5):
    """皮尔逊相似度：返回 [(学号, 姓名, 相似度)]，按相似度降序。"""
    s = SessionLocal()
    try:
        rows = s.query(CarpoolRequestModel).filter(
            CarpoolRequestModel.status.in_(['open', 'accepted', 'in_progress', 'completed'])).all()
        students = s.query(StudentModel).all()
    finally:
        s.close()
    pref = user_preference_vectors(rows)
    me = pref.get(str(student_number), {})
    result = []
    for stu in students:
        if int(stu.student_number) == int(student_number):
            continue
        other = pref.get(str(stu.student_number), {})
        sim = pearson(me, other)
        result.append((stu.student_number, stu.name, round(sim, 3)))
    result.sort(key=lambda x: -x[2])
    return result[:top_n]


# ==================== 司机端：接单 / 行程 / 车辆 ====================

def get_driver_vehicles(driver_license: str):
    s = SessionLocal()
    try:
        return s.query(VehicleModel).filter_by(driver_license=driver_license).all()
    finally:
        s.close()


def add_vehicle(driver_license: str, plate_number: str, brand: str, seat_capacity: int):
    s = SessionLocal()
    try:
        if s.query(VehicleModel).filter_by(driver_license=driver_license,
                                           plate_number=plate_number).first():
            return False, "该车牌号已登记！"
        s.add(VehicleModel(driver_license=driver_license, plate_number=plate_number,
                           brand=brand, seat_capacity=int(seat_capacity)))
        s.commit()
        return True, "车辆登记成功！"
    except Exception as e:
        s.rollback()
        return False, f"登记失败: {e}"
    finally:
        s.close()


def get_open_requests_sorted_for_driver(driver_lat=32.0628, driver_lng=118.7885):
    """待接单大厅：按距离司机当前位置（图书馆默认）由近到远排序。"""
    open_reqs = get_open_carpool_requests()
    pos = get_node_pos()
    def dist(o):
        p = pos.get(o.departure, (0, 0))
        return ((p[0] - driver_lat) ** 2 + (p[1] - driver_lng) ** 2) ** 0.5
    return sorted(open_reqs, key=dist)


def accept_carpool_request(request_id: int, driver_license: str, vehicle_id: int):
    """司机接单：写 driver_offers 表，订单状态改为 accepted，并推送接单通知。"""
    s = SessionLocal()
    try:
        req = s.query(CarpoolRequestModel).filter_by(request_id=request_id).first()
        if not req or req.status != 'open':
            return False, "该订单已被接单或不存在。"
        if s.query(DriverOfferModel).filter(
                DriverOfferModel.request_id == request_id,
                DriverOfferModel.status != 'cancelled').first():
            return False, "该订单已被其他司机接单。"
        veh = s.query(VehicleModel).filter_by(id=vehicle_id,
                                              driver_license=driver_license).first()
        if not veh:
            return False, "车辆信息不存在！"
        if veh.seat_capacity < req.seats_needed:
            return False, f"车辆座位数({veh.seat_capacity})不足该订单需求({req.seats_needed})。"
        s.add(DriverOfferModel(request_id=request_id, driver_license=driver_license,
                               vehicle_id=vehicle_id, status='accepted',
                               remaining_seats=veh.seat_capacity))
        req.status = 'accepted'
        s.commit()
        v_info = f"{veh.brand or ''} {veh.plate_number}"
        push('student', req.student_number, '接单通知',
             f"您发布的行程 #{request_id}（{req.departure}→{req.destination}）已被接单！"
             f"车辆：{v_info.strip()}，请按时到达 {req.departure} 上车。", 'accept')
        return True, "接单成功！已通知发布者，可在'我的订单'中开始行程。"
    except Exception as e:
        s.rollback()
        return False, f"接单异常: {e}"
    finally:
        s.close()


def get_driver_orders(driver_license: str):
    """司机的接单记录（附订单与学生信息）。"""
    s = SessionLocal()
    try:
        rows = s.query(DriverOfferModel, CarpoolRequestModel).join(
            CarpoolRequestModel,
            DriverOfferModel.request_id == CarpoolRequestModel.request_id
        ).filter(DriverOfferModel.driver_license == driver_license,
                 DriverOfferModel.status != 'cancelled'
                 ).order_by(DriverOfferModel.offer_id.desc()).all()
        result = []
        for offer, req in rows:
            stu = s.query(StudentModel).filter_by(student_number=req.student_number).first()
            joins = s.query(CarpoolJoinModel).filter_by(request_id=req.request_id,
                                                        status='joined').all()
            veh = s.query(VehicleModel).filter_by(id=offer.vehicle_id).first()
            result.append({'offer': offer, 'req': req,
                           'student_name': stu.name if stu else str(req.student_number),
                           'student_phone': stu.phone if stu else '',
                           'joins': joins, 'vehicle': veh,
                           'joined_seats': sum(j.seats for j in joins)})
        return result
    finally:
        s.close()


def start_trip(request_id: int, driver_license: str):
    """司机开始行程：accepted → in_progress。"""
    s = SessionLocal()
    try:
        offer = s.query(DriverOfferModel).filter_by(request_id=request_id,
                                                    driver_license=driver_license).first()
        req = s.query(CarpoolRequestModel).filter_by(request_id=request_id).first()
        if not offer or offer.status != 'accepted':
            return False, "仅已接单状态可开始行程！"
        offer.status = 'in_progress'
        req.status = 'in_progress'
        s.commit()
        push('student', req.student_number, '行程开始',
             f"行程 #{request_id} 已开始，车辆正向 {req.departure} 驶来，请注意上车。", 'accept')
        return True, "行程已开始！"
    except Exception as e:
        s.rollback()
        return False, f"操作失败: {e}"
    finally:
        s.close()


def complete_trip(request_id: int, driver_license: str):
    """司机确认完成：in_progress → completed，自动核算费用并通知互评。"""
    s = SessionLocal()
    try:
        offer = s.query(DriverOfferModel).filter_by(request_id=request_id,
                                                    driver_license=driver_license).first()
        req = s.query(CarpoolRequestModel).filter_by(request_id=request_id).first()
        if not offer or offer.status != 'in_progress':
            return False, "仅行程中状态可确认完成！"
        offer.status = 'completed'
        req.status = 'completed'
        s.commit()
        joins = s.query(CarpoolJoinModel).filter_by(request_id=request_id,
                                                    status='joined').all()
        fare = req.estimated_fare or 0
        per_head = round(fare / (1 + len(joins)), 1) if joins else fare
        push('student', req.student_number, '行程完成',
             f"行程 #{request_id} 已完成，费用 {per_head} 元/人已按分摊规则结算，"
             f"请对本次服务进行评价。", 'accept')
        for j in joins:
            push('student', j.student_number, '行程完成',
                 f"您加入的行程 #{request_id} 已完成，费用 {per_head} 元/人，"
                 f"欢迎评价本次拼车体验。", 'accept')
        push('driver', driver_license, '行程完成',
             f"行程 #{request_id} 结算完成，请对学生的乘车行为进行评价。", 'accept')
        return True, f"行程完成！费用 {per_head} 元/人已结算。"
    except Exception as e:
        s.rollback()
        return False, f"操作失败: {e}"
    finally:
        s.close()


# ==================== 加入 / 退出拼车 ====================

def join_carpool(request_id: int, student_number: int, seats: int = 1):
    """学生加入已被接单（或待接单）的拼车订单，占用剩余座位。"""
    s = SessionLocal()
    try:
        req = s.query(CarpoolRequestModel).filter_by(request_id=request_id).first()
        if not req or req.status not in ('open', 'accepted'):
            return False, "该订单当前不可加入。"
        if req.student_number == int(student_number):
            return False, "不能加入自己发布的订单！"
        if s.query(CarpoolJoinModel).filter_by(request_id=request_id,
                                               student_number=int(student_number),
                                               status='joined').first():
            return False, "您已加入过该订单！"
        offer = s.query(DriverOfferModel).filter(
            DriverOfferModel.request_id == request_id,
            DriverOfferModel.status != 'cancelled').first()
        joined = s.query(func.coalesce(func.sum(CarpoolJoinModel.seats), 0)).filter(
            CarpoolJoinModel.request_id == request_id,
            CarpoolJoinModel.status == 'joined').scalar()
        if offer:
            if joined + seats > offer.remaining_seats:
                return False, f"剩余座位不足！当前仅剩 {offer.remaining_seats - joined} 座。"
        elif joined + seats > req.seats_needed:
            return False, f"该订单仅招募 {req.seats_needed} 人，已满。"
        s.add(CarpoolJoinModel(request_id=request_id,
                               student_number=int(student_number), seats=int(seats)))
        s.commit()
        push('student', req.student_number, '拼车加入通知',
             f"{student_number} 号同学加入了您的行程 #{request_id}"
             f"（{req.departure}→{req.destination}，+{seats} 座）。", 'join')
        if offer:
            push('driver', offer.driver_license, '拼车加入通知',
                 f"行程 #{request_id} 新增 1 位拼车同学（学号 {student_number}，"
                 f"需 {seats} 座），出发时间 {req.departure_time:%m-%d %H:%M}。"
                 f"{('备注：' + req.remark) if req.remark else ''}", 'join')
        return True, "加入成功！出发前请留意消息通知。"
    except Exception as e:
        s.rollback()
        return False, f"加入失败: {e}"
    finally:
        s.close()


def leave_carpool(booking_id: int, student_number: int):
    s = SessionLocal()
    try:
        j = s.query(CarpoolJoinModel).filter_by(booking_id=booking_id,
                                                student_number=int(student_number)).first()
        if not j or j.status != 'joined':
            return False, "未找到有效的加入记录！"
        j.status = 'left'
        s.commit()
        return True, "已退出该拼车。"
    except Exception as e:
        s.rollback()
        return False, f"退出失败: {e}"
    finally:
        s.close()


# ==================== 互评与信誉 ====================

def can_review(request_id: int, role: str, key: str):
    """行程完成后双方可互评；返回 (是否可评, 被评价对象key)。"""
    s = SessionLocal()
    try:
        req = s.query(CarpoolRequestModel).filter_by(request_id=request_id).first()
        if not req or req.status != 'completed':
            return False, None
        already = s.query(ReviewModel).filter_by(request_id=request_id,
                                                 reviewer_role=role,
                                                 reviewer_key=str(key)).first()
        if already:
            return False, None
        if role == 'student':
            offer = s.query(DriverOfferModel).filter(
                DriverOfferModel.request_id == request_id,
                DriverOfferModel.status != 'cancelled').first()
            return (offer is not None, offer.driver_license if offer else None)
        else:
            return True, str(req.student_number)
    finally:
        s.close()


def submit_review(request_id: int, reviewer_role: str, reviewer_key: str,
                  reviewee_role: str, reviewee_key: str, rating: int, comment: str = ''):
    s = SessionLocal()
    try:
        s.add(ReviewModel(request_id=request_id, reviewer_role=reviewer_role,
                          reviewer_key=str(reviewer_key), reviewee_role=reviewee_role,
                          reviewee_key=str(reviewee_key), rating=int(rating),
                          comment=comment or ''))
        s.commit()
        return True, "评价提交成功，感谢您的反馈！"
    except Exception as e:
        s.rollback()
        return False, f"评价失败: {e}"
    finally:
        s.close()


def get_reputation(role: str, key: str):
    """信誉评分 = 所收评价的平均分(1~5)。"""
    s = SessionLocal()
    try:
        avg = s.query(func.avg(ReviewModel.rating)).filter_by(
            reviewee_role=role, reviewee_key=str(key)).scalar()
        return round(float(avg), 1) if avg else None
    finally:
        s.close()


# ==================== 数据统计（真实库表聚合）====================

def stats_daily_publish():
    """每日拼车发布量与活跃（发布+加入）量。"""
    s = SessionLocal()
    try:
        pub = s.query(func.date(CarpoolRequestModel.created_at).label('d'),
                      func.count('*')).group_by('d').order_by('d').all()
        act = s.query(func.date(CarpoolJoinModel.booked_at).label('d'),
                      func.count('*')).group_by('d').order_by('d').all()
        days = sorted({str(d) for d, _ in pub} | {str(d) for d, _ in act})
        pub_map = {str(d): c for d, c in pub}
        act_map = {str(d): c for d, c in act}
        return days, [pub_map.get(d, 0) for d in days], [act_map.get(d, 0) for d in days]
    finally:
        s.close()


def stats_hour_heat():
    """各时段（按出发时间）拼车需求热度。"""
    s = SessionLocal()
    try:
        rows = s.query(func.hour(CarpoolRequestModel.departure_time).label('h'),
                       func.count('*')).group_by('h').order_by('h').all()
        return {int(h): c for h, c in rows}
    finally:
        s.close()


def stats_status_dist():
    s = SessionLocal()
    try:
        rows = s.query(CarpoolRequestModel.status,
                       func.count('*')).group_by(CarpoolRequestModel.status).all()
        return {STATUS_CN.get(k, k): v for k, v in rows}
    finally:
        s.close()


def stats_overview():
    s = SessionLocal()
    try:
        return {
            'students': s.query(StudentModel).count(),
            'drivers': s.query(DriverModel).count(),
            'vehicles': s.query(VehicleModel).count(),
            'requests': s.query(CarpoolRequestModel).count(),
            'open': s.query(CarpoolRequestModel).filter_by(status='open').count(),
            'completed': s.query(CarpoolRequestModel).filter_by(status='completed').count(),
            'joins': s.query(CarpoolJoinModel).filter_by(status='joined').count(),
        }
    finally:
        s.close()
