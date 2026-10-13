"""智慧出行校园共享拼车平台 —— Streamlit 主界面（全 Python 实现）

学生端：拼车推荐(K-Means聚类+重叠度) / 发布拼车(动态定价) / 我的拼车(编辑·取消·退出)
        路线导航(Dijkstra动态权重) / 消息中心 / 数据大屏(真实统计) / 个人中心 / 系统设置
司机端：接单大厅(按距离排序) / 我的订单(开始·完成·互评) / 车辆管理 / 其余同上
"""
import datetime

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

import auth
import carpool_ops as ops
import notify
from algorithms import get_node_pos

st.set_page_config(page_title="智慧出行校园共享拼车平台", page_icon="🚗", layout="wide")

CAMPUS_CENTER = [32.0628, 118.7885]
STATUS_CN = ops.STATUS_CN

# ==================== 多语言（系统设置模块） ====================
I18N = {
    'zh': {'rec': '🏠 拼车推荐', 'publish': '🚗 发布拼车', 'mine': '📋 我的拼车',
           'map': '🗺️ 路线导航', 'msg': '🔔 消息中心', 'stats': '📊 数据大屏',
           'me': '👤 个人中心', 'set': '⚙️ 系统设置',
           'hall': '📋 接单大厅', 'orders': '🚙 我的订单'},
    'en': {'rec': '🏠 Recommendations', 'publish': '🚗 Publish', 'mine': '📋 My Carpools',
           'map': '🗺️ Navigation', 'msg': '🔔 Messages', 'stats': '📊 Dashboard',
           'me': '👤 Profile', 'set': '⚙️ Settings',
           'hall': '📋 Order Hall', 'orders': '🚙 My Trips'},
}


def t(key):
    lang = st.session_state.get('lang', 'zh')
    return I18N.get(lang, I18N['zh']).get(key, key)


def apply_theme():
    """主题模式设置：明亮 / 暗黑（系统设置模块）"""
    theme = st.session_state.get('theme', 'light')
    if theme == 'dark':
        st.markdown("""
        <style>
        .stApp, [data-testid="stSidebar"] {background-color:#1a1d29;color:#e8e8e8;}
        .stApp * {color:#e8e8e8 !important;}
        [data-testid="stHeader"] {background-color:rgba(26,29,41,0);}
        div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input {
            background-color:#2a2d3a;color:#e8e8e8;}
        .stTabs [data-baseweb="tab-list"] {background-color:#1a1d29;}
        </style>""", unsafe_allow_html=True)


# ==================== Session 初始化 ====================
for k, v in {'logged_in': False, 'user_role': None, 'user_info': None,
             'lang': 'zh', 'theme': 'light'}.items():
    if k not in st.session_state:
        st.session_state[k] = v

apply_theme()


def fmt_dt(dt):
    return dt.strftime('%m-%d %H:%M') if dt else '-'


def draw_route_map(path_names=None, highlight_pair=None):
    """校园地图 + Dijkstra 最短路径折线"""
    pos = get_node_pos()
    m = folium.Map(location=CAMPUS_CENTER, zoom_start=15)
    for name, (lat, lng) in pos.items():
        folium.Marker([lat, lng], popup=name, tooltip=name,
                      icon=folium.Icon(color='blue', icon='university')).add_to(m)
    if path_names and len(path_names) > 1:
        pts = [pos[n] for n in path_names if n in pos]
        folium.PolyLine(pts, color='red', weight=4, opacity=0.8,
                        tooltip='Dijkstra 最优路径').add_to(m)
        for n in (path_names[0], path_names[-1]):
            if n in pos:
                folium.Marker(pos[n], popup=n, tooltip=n,
                              icon=folium.Icon(color='red', icon='flag')).add_to(m)
    if highlight_pair:
        for n in highlight_pair:
            if n in pos:
                folium.CircleMarker(pos[n], radius=10, color='green',
                                    fill=True, popup=f'行程节点:{n}').add_to(m)
    return m


# ==================== 未登录：登录与注册 ====================
if not st.session_state.logged_in:
    st.sidebar.title("请选择您的身份通道")
    role_choice = st.sidebar.radio("身份通道", ["学生端", "司机端"],
                                   label_visibility="collapsed")
    st.title("🚗 智慧出行校园共享拼车平台")
    st.caption("K-Means 智能拼单 · Dijkstra 动态权重路径规划 · 皮尔逊用户相似度推荐 · 分时段动态定价")
    tab_login, tab_register = st.tabs(["🔑 账号登录", "📝 账号注册"])

    if role_choice == "学生端":
        with tab_login:
            st.subheader("学生用户登录")
            with st.form("stu_login_form"):
                num = st.text_input("学号", key="stu_login_num")
                pwd = st.text_input("密码", type="password", key="stu_login_pwd")
                if st.form_submit_button("学生登录", type="primary"):
                    ok, msg, user = auth.login_student(num, pwd)
                    if ok:
                        pref = auth.get_settings('student', user.student_number)
                        st.session_state.update(logged_in=True, user_role='student',
                                                user_info=user, lang=pref.language,
                                                theme=pref.theme)
                        st.rerun()
                    else:
                        st.error(msg)
        with tab_register:
            st.subheader("学生用户注册")
            rn = st.text_input("学号（数字）", key="stu_reg_num")
            rname = st.text_input("真实姓名", key="stu_reg_name")
            rphone = st.text_input("手机号", key="stu_reg_phone")
            rpwd = st.text_input("设置密码（≥6位）", type="password", key="stu_reg_pwd")
            if st.button("立即注册学生账号"):
                ok, msg = auth.register_student(rn, rname, rphone, rpwd)
                st.success(msg) if ok else st.error(msg)
    else:
        with tab_login:
            st.subheader("司机用户登录")
            with st.form("drv_login_form"):
                lic = st.text_input("驾照号 / 账号", key="drv_login_license")
                pwd = st.text_input("密码", type="password", key="drv_login_pwd")
                if st.form_submit_button("司机登录", type="primary"):
                    ok, msg, user = auth.login_driver(lic, pwd)
                    if ok:
                        pref = auth.get_settings('driver', user.driver_license)
                        st.session_state.update(logged_in=True, user_role='driver',
                                                user_info=user, lang=pref.language,
                                                theme=pref.theme)
                        st.rerun()
                    else:
                        st.error(msg)
        with tab_register:
            st.subheader("司机用户注册")
            dlic = st.text_input("驾驶证号", key="drv_reg_license")
            dname = st.text_input("真实姓名", key="drv_reg_name")
            dphone = st.text_input("手机号", key="drv_reg_phone")
            dpwd = st.text_input("设置密码（≥6位）", type="password", key="drv_reg_pwd")
            if st.button("立即注册司机账号"):
                ok, msg = auth.register_driver(dlic, dname, dphone, dpwd)
                st.success(msg) if ok else st.error(msg)
    st.stop()

# ==================== 已登录：主控台 ====================
user = st.session_state.user_info
role = st.session_state.user_role
role_key = user.student_number if role == 'student' else user.driver_license
ukey = str(role_key)

st.sidebar.title("👤 用户控制面板")
if role == 'student':
    st.sidebar.markdown(f"**身份**：学生端")
    st.sidebar.markdown(f"**姓名**：{user.name}")
    st.sidebar.markdown(f"**学号**：{user.student_number}")
    rep = ops.get_reputation('student', ukey)
    st.sidebar.markdown(f"**信誉评分**：{'⭐ ' + str(rep) if rep else '暂无评价'}")
else:
    st.sidebar.markdown(f"**身份**：司机端")
    st.sidebar.markdown(f"**姓名**：{user.real_name}")
    st.sidebar.markdown(f"**驾照号**：{user.driver_license}")
    rep = ops.get_reputation('driver', ukey)
    st.sidebar.markdown(f"**信誉评分**：{'⭐ ' + str(rep) if rep else '暂无评价'}")
unread = notify.unread_count(role, ukey)
if unread:
    st.sidebar.warning(f"📬 {unread} 条未读消息")
if st.sidebar.button("退出登录"):
    st.session_state.update(logged_in=False, user_role=None, user_info=None)
    st.rerun()

# ------------------- 公共页面（学生/司机共用） -------------------

def page_map():
    st.subheader("校园及周边地图导航（Dijkstra 动态权重路径规划）")
    nodes = ops.get_node_names()
    c1, c2, c3 = st.columns(3)
    dep = c1.selectbox("出发地", nodes, key="map_dep")
    dst = c2.selectbox("目的地", nodes, index=min(1, len(nodes) - 1), key="map_dst")
    btn = c3.button("🧭 规划最优路线", type="primary")
    if btn:
        route = ops.estimate_route(dep, dst)
        if route is None or route[0] == float('inf'):
            st.error("两地之间暂无可达道路！")
        else:
            dist, cost, names, fare = route
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("实际距离", f"{dist:.0f} 米")
            m2.metric("动态权重成本", f"{cost:.0f}")
            m3.metric("预估费用", f"{fare} 元")
            m4.metric("途经节点数", len(names))
            st.caption("路径：" + " → ".join(names))
            st.caption("权重 = 距离 × (1 + 拥堵系数)，高峰时段费用自动上浮")
    st_folium(draw_route_map(), width=900, height=480)


def page_messages():
    st.subheader("消息中心（接单通知 / 拼车加入通知 / 系统维护通知）")
    rows = notify.get_notifications(role, ukey)
    if st.button("全部标记已读"):
        notify.mark_all_read(role, ukey)
        st.rerun()
    if not rows:
        st.info("暂无消息。")
    for n in rows[:30]:
        icon = {'accept': '🚕', 'join': '👥', 'system': '📢'}.get(n.n_type, '📨')
        with st.container(border=True):
            head = f"{icon} **{n.title}**　<small style='color:gray'>{fmt_dt(n.created_at)}</small>"
            if not n.is_read:
                if st.button("标记已读", key=f"read_{n.notify_id}"):
                    notify.mark_read(n.notify_id)
                    st.rerun()
            st.markdown(head, unsafe_allow_html=True)
            st.write(n.content)


def page_stats():
    st.subheader("数据统计大屏（基于真实库表聚合）")
    ov = ops.stats_overview()
    m = st.columns(6)
    m[0].metric("学生数", ov['students'])
    m[1].metric("司机数", ov['drivers'])
    m[2].metric("车辆数", ov['vehicles'])
    m[3].metric("拼车订单", ov['requests'])
    m[4].metric("待接单", ov['open'])
    m[5].metric("已完成", ov['completed'])
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        days, pub, act = ops.stats_daily_publish()
        if days:
            df = pd.DataFrame({'日期': days, '发布量': pub, '活跃量(加入)': act})
            fig = px.line(df, x='日期', y=['发布量', '活跃量(加入)'], markers=True,
                          title='每日拼车发布量与活跃量')
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("暂无订单数据。")
        heat = ops.stats_hour_heat()
        if heat:
            df = pd.DataFrame({'时段': [f"{h:02d}:00" for h in sorted(heat)],
                               '需求热度': [heat[h] for h in sorted(heat)]})
            st.plotly_chart(px.bar(df, x='时段', y='需求热度',
                                   title='各时段拼车需求热度（按出发时间）'),
                            width='stretch')
    with c2:
        dist = ops.stats_status_dist()
        if dist:
            st.plotly_chart(px.pie(names=list(dist), values=list(dist),
                                   title='订单状态分布'), width='stretch')
        if role == 'student':
            st.caption("与你相似的同学（皮尔逊相关系数）")
            sims = ops.similar_students(user.student_number)
            if sims:
                for sn, name, sim in sims:
                    st.write(f"**{name}**（{sn}）　相似度：{'🧡' if sim > 0 else '💙'} {sim}")
            else:
                st.info("暂无其他同学数据可比较。")


def page_profile():
    st.subheader("个人中心")
    if role == 'student':
        st.markdown(f"**姓名**：{user.name}　**学号**：{user.student_number}　**手机号**：{user.phone}")
    else:
        st.markdown(f"**姓名**：{user.real_name}　**驾照号**：{user.driver_license}　**手机号**：{user.phone}")
    rep = ops.get_reputation(role, ukey)
    st.metric("信誉评分", f"⭐ {rep}" if rep else "暂无评价（完成行程互评后生成）")
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 编辑基本资料")
        new_name = st.text_input("姓名", value=user.name if role == 'student' else user.real_name)
        new_phone = st.text_input("手机号", value=user.phone or '')
        if st.button("保存资料"):
            ok, msg = auth.update_profile(role, ukey, name=new_name, phone=new_phone)
            st.success(msg) if ok else st.error(msg)
        st.markdown("#### 紧急联系人")
        pref = auth.get_settings(role, ukey)
        ec = st.text_input("紧急联系人及电话", value=pref.emergency_contact or '',
                           help="行程出现紧急情况时，平台将优先联系该联系人")
        if st.button("保存紧急联系人"):
            ok, msg = auth.save_settings(role, ukey, emergency_contact=ec)
            st.success(msg) if ok else st.error(msg)
    with c2:
        st.markdown("#### 修改密码")
        old = st.text_input("原密码", type="password", key="old_pwd")
        new = st.text_input("新密码（≥6位）", type="password", key="new_pwd")
        new2 = st.text_input("确认新密码", type="password", key="new_pwd2")
        if st.button("确认修改密码"):
            if new != new2:
                st.error("两次输入的新密码不一致！")
            else:
                ok, msg = auth.change_password(role, ukey, old, new)
                st.success(msg) if ok else st.error(msg)
    if role == 'driver':
        st.divider()
        st.markdown("#### 🚙 车辆信息管理")
        vehs = ops.get_driver_vehicles(user.driver_license)
        for v in vehs:
            st.write(f"🚘 {v.brand or '-'}　车牌：**{v.plate_number}**　座位数：{v.seat_capacity}")
        with st.expander("＋ 登记新车辆"):
            vp = st.text_input("车牌号", key="v_plate")
            vb = st.text_input("品牌/车型", key="v_brand")
            vs = st.number_input("座位数", 2, 20, 4, key="v_seats")
            if st.button("提交车辆登记"):
                ok, msg = ops.add_vehicle(user.driver_license, vp, vb, vs)
                st.success(msg) if ok else st.error(msg)


def page_settings():
    st.subheader("系统设置")
    pref = auth.get_settings(role, ukey)
    c1, c2 = st.columns(2)
    lang = c1.selectbox("语言 Language", ['zh', 'en'],
                        index=0 if pref.language == 'zh' else 1,
                        format_func=lambda x: '简体中文' if x == 'zh' else 'English')
    theme = c2.radio("主题模式", ['light', 'dark'],
                     index=0 if pref.theme == 'light' else 1,
                     format_func=lambda x: '明亮模式' if x == 'light' else '暗黑模式')
    st.markdown("#### 通知偏好")
    n1 = st.checkbox("活动通知（平台优惠、社群活动）", value=bool(pref.notify_activity))
    n2 = st.checkbox("系统消息（规则更新、功能升级、维护公告）", value=bool(pref.notify_system))
    n3 = st.checkbox("拼车提醒（接单、加入、行程临近）", value=bool(pref.notify_carpool))
    if st.button("保存全部设置"):
        ok, msg = auth.save_settings(role, ukey, language=lang, theme=theme,
                                     notify_activity=1 if n1 else 0,
                                     notify_system=1 if n2 else 0,
                                     notify_carpool=1 if n3 else 0)
        if ok:
            st.session_state.lang, st.session_state.theme = lang, theme
        st.success(msg) if ok else st.error(msg)
    st.divider()
    st.markdown("#### 关于我们")
    st.info("智慧出行校园共享拼车平台 —— 面向校园师生的共享出行服务系统，"
            "整合校园闲置运力，提供智能拼单、路径规划与分时段动态定价。")


# ------------------- 学生端 -------------------
if role == 'student':
    st.title(f"🎓 学生端主控台 —— 欢迎您，{user.name}同学")
    tabs = st.tabs([t('rec'), t('publish'), t('mine'), t('map'), t('msg'),
                    t('stats'), t('me'), t('set')])
    tb_rec, tb_pub, tb_mine, tb_map, tb_msg, tb_stat, tb_me, tb_set = tabs

    with tb_rec:
        st.subheader("智能拼单推荐（K-Means 聚类 + 路径重叠度 + 时间窗口 ±30 分钟）")
        nodes = ops.get_node_names()
        with st.form("rec_form"):
            c1, c2, c3 = st.columns(3)
            r_dep = c1.selectbox("我的出发地", nodes, key="rec_dep")
            r_dst = c2.selectbox("我的目的地", nodes, index=min(1, len(nodes) - 1), key="rec_dst")
            r_time = c3.text_input("预计出发时间", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
            run_rec = st.form_submit_button("🔍 获取推荐", type="primary")
        if run_rec:
            try:
                when = datetime.datetime.strptime(r_time, "%Y-%m-%d %H:%M")
                recs = ops.recommend_for_student(user.student_number, r_dep, r_dst, when)
                if not recs:
                    st.info("暂无可推荐的拼车订单，您可以去【发布拼车】先发布需求。")
                for rec in recs:
                    r = rec['req']
                    badge = "🟢 同簇推荐" if rec['same_cluster'] else "⚪ 其他簇"
                    with st.container(border=True):
                        cc1, cc2 = st.columns([4, 1])
                        cc1.markdown(
                            f"行程 **#{r.request_id}**　{r.departure} ➔ **{r.destination}**"
                            f"　出发：{fmt_dt(r.departure_time)}　"
                            f"已拼 {rec['remain_seats'] if rec['remain_seats'] is not None else r.seats_needed} 座"
                            f"　费用 {r.estimated_fare or '-'} 元")
                        cc1.caption(
                            f"{badge}｜路径重叠度 {rec['overlap'] * 100:.0f}%｜"
                            f"时间差 {rec['tdiff']:.0f} 分钟"
                            + (f"｜备注：{r.remark}" if r.remark else ""))
                        if cc2.button("一键加入", key=f"join_{r.request_id}",
                                      disabled=rec['remain_seats'] == 0):
                            ok, msg = ops.join_carpool(r.request_id, user.student_number)
                            st.success(msg) if ok else st.error(msg)
            except ValueError:
                st.error("时间格式应为 2026-01-01 08:30")

    with tb_pub:
        st.subheader("发起新的拼车需求（自动预估费用，支持分时段动态定价）")
        nodes = ops.get_node_names()
        with st.form("pub_form"):
            col1, col2 = st.columns(2)
            p_dep = col1.selectbox("出发地", nodes, key="pub_dep")
            p_dst = col2.selectbox("目的地", nodes, index=min(2, len(nodes) - 1), key="pub_dst")
            col3, col4 = st.columns(2)
            p_time = col3.text_input("出发时间（可预约未来出行）",
                                     datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
            p_seats = col4.number_input("同行人数", 1, 6, 1)
            p_remark = st.text_input("备注（如携带大件行李、不允许吸烟等）")
            e1, e2 = st.columns([1, 3])
            est_fare = e1.form_submit_button("💰 预估费用")
            pub_go = e2.form_submit_button("📤 提交拼车发布", type="primary")
        if est_fare:
            route = ops.estimate_route(p_dep, p_dst)
            if route and route[0] != float('inf'):
                st.success(f"距离约 {route[0]:.0f} 米，预估费用 {route[3]} 元/人")
            else:
                st.error("两地之间暂无可达道路！")
        if pub_go:
            ok, msg = ops.create_carpool_request(user.student_number, p_dep, p_dst,
                                                 p_time, p_seats, p_remark)
            st.success(msg) if ok else st.error(msg)
        st.divider()
        st.subheader("📋 全部待接单订单")
        for r in ops.get_open_carpool_requests(user.student_number):
            st.info(f"行程 #{r.request_id} | {r.departure} ➔ {r.destination} | "
                    f"出发 {fmt_dt(r.departure_time)} | 招募 {r.seats_needed} 人 | "
                    f"费用 {r.estimated_fare or '-'} 元 | 待接单")

    with tb_mine:
        st.subheader("我发布的拼车")
        for item in ops.get_my_published(user.student_number):
            r, offer = item['req'], item['offer']
            with st.container(border=True):
                st.markdown(
                    f"**#{r.request_id}** {r.departure} ➔ {r.destination}　"
                    f"{fmt_dt(r.departure_time)}　{r.seats_needed} 人　"
                    f"`{STATUS_CN.get(r.status, r.status)}`　"
                    f"已加入 {item['joined_seats']} 人")
                if item['driver_name']:
                    st.caption(f"接单司机：{item['driver_name']}"
                               + (f"（车牌 {item['plate']}）" if item['plate'] else '')
                               + f"　费用 {r.estimated_fare or '-'} 元/人"
                               + (f"　备注：{r.remark}" if r.remark else ""))
                b1, b2 = st.columns(2)
                if r.status == 'open' and b1.button("✏️ 编辑", key=f"edit_{r.request_id}"):
                    st.session_state['editing'] = r.request_id
                if r.status in ('open', 'accepted') and b2.button("🗑️ 取消订单",
                                                                  key=f"cancel_{r.request_id}"):
                    ok, msg = ops.cancel_request(r.request_id, student_number=user.student_number)
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()
                if r.status == 'completed':
                    can, _ = ops.can_review(r.request_id, 'student', ukey)
                    if can:
                        with st.expander(f"⭐ 评价司机（行程 #{r.request_id}）"):
                            rate = st.slider("服务评分", 1, 5, 5, key=f"rate_{r.request_id}")
                            cmt = st.text_input("评语", key=f"cmt_{r.request_id}")
                            if st.button("提交评价", key=f"sub_{r.request_id}"):
                                offer2 = item['offer']
                                ok, msg = ops.submit_review(
                                    r.request_id, 'student', ukey, 'driver',
                                    offer2.driver_license, rate, cmt)
                                st.success(msg) if ok else st.error(msg)
            if st.session_state.get('editing') == r.request_id:
                with st.container(border=True):
                    st.markdown("修改后重新发布：")
                    nodes2 = ops.get_node_names()
                    ed = st.selectbox("出发地", nodes2,
                                      index=nodes2.index(r.departure) if r.departure in nodes2 else 0,
                                      key=f"ed_dep_{r.request_id}")
                    ed2 = st.selectbox("目的地", nodes2,
                                       index=nodes2.index(r.destination) if r.destination in nodes2 else 0,
                                       key=f"ed_dst_{r.request_id}")
                    edt = st.text_input("出发时间", r.departure_time.strftime("%Y-%m-%d %H:%M"))
                    eds = st.number_input("人数", 1, 6, r.seats_needed)
                    if st.button("保存修改", key=f"ed_save_{r.request_id}"):
                        ok, msg = ops.update_request(r.request_id, user.student_number,
                                                     departure=ed, destination=ed2,
                                                     departure_time=edt, seats=eds)
                        if ok:
                            st.session_state.pop('editing', None)
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()
        st.divider()
        st.subheader("我加入的拼车")
        for item in ops.get_my_joined(user.student_number):
            j, r = item['join'], item['req']
            with st.container(border=True):
                st.markdown(f"**#{r.request_id}** {r.departure} ➔ {r.destination}　"
                            f"{fmt_dt(r.departure_time)}　`{STATUS_CN.get(r.status, r.status)}`　"
                            f"占用 {j.seats} 座")
                if item['driver_name']:
                    st.caption(f"司机：{item['driver_name']}"
                               + (f"　📞 {item['driver_phone']}" if item['driver_phone'] else '')
                               + (f"　车牌 {item['plate']}" if item['plate'] else ''))
                if r.status in ('open', 'accepted'):
                    if st.button("退出拼车", key=f"leave_{j.booking_id}"):
                        ok, msg = ops.leave_carpool(j.booking_id, user.student_number)
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()

    with tb_map:
        page_map()
    with tb_msg:
        page_messages()
    with tb_stat:
        page_stats()
    with tb_me:
        page_profile()
    with tb_set:
        page_settings()

# ------------------- 司机端 -------------------
else:
    st.title(f"🚘 司机端主控台 —— 欢迎您，{user.real_name}师傅")
    tabs = st.tabs([t('hall'), t('orders'), t('map'), t('msg'), t('stats'),
                    t('me'), t('set')])
    tb_hall, tb_orders, tb_map, tb_msg, tb_stat, tb_me, tb_set = tabs

    with tb_hall:
        st.subheader("当前可接单的校园拼车请求（按距离当前位置由近到远排序）")
        vehs = ops.get_driver_vehicles(user.driver_license)
        if not vehs:
            st.warning("您尚未登记车辆，请先到【个人中心】完成车辆登记后再接单！")
        reqs = ops.get_open_requests_sorted_for_driver()
        if not reqs:
            st.info("暂无待接单请求。学生发布行程后，订单将实时显示在这里。")
        for req in reqs:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"📍 **{req.departure} ➔ {req.destination}**　"
                            f"出发 {fmt_dt(req.departure_time)}　"
                            f"需 {req.seats_needed} 座　预估 {req.estimated_fare or '-'} 元/人")
                c1.caption(f"订单编号 #{req.request_id}"
                           + (f"　备注：{req.remark}" if req.remark else ""))
                if vehs:
                    choice = c2.selectbox("选车辆", vehs,
                                          format_func=lambda v: f"{v.plate_number}({v.seat_capacity}座)",
                                          key=f"veh_{req.request_id}")
                    if c2.button("立即接单", key=f"accept_{req.request_id}", type="primary"):
                        ok, msg = ops.accept_carpool_request(req.request_id,
                                                             user.driver_license, choice.id)
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()

    with tb_orders:
        st.subheader("我的接单与行程管理")
        orders = ops.get_driver_orders(user.driver_license)
        if not orders:
            st.info("暂无接单记录，去【接单大厅】看看吧！")
        for it in orders:
            offer, req = it['offer'], it['req']
            with st.container(border=True):
                st.markdown(
                    f"**#{req.request_id}** {req.departure} ➔ {req.destination}　"
                    f"{fmt_dt(req.departure_time)}　`{STATUS_CN.get(req.status, req.status)}`　"
                    f"乘客 {it['student_name']}（{req.student_number}）")
                st.caption(f"车辆：{it['vehicle'].plate_number if it['vehicle'] else '-'}　"
                           f"乘客电话：{it['student_phone'] or '-'}　"
                           f"已加入 {it['joined_seats']} 人　"
                           f"费用 {req.estimated_fare or '-'} 元/人"
                           + (f"　备注：{req.remark}" if req.remark else ""))
                b1, b2, b3 = st.columns(3)
                if offer.status == 'accepted' and b1.button("▶️ 开始行程",
                                                            key=f"start_{req.request_id}"):
                    ok, msg = ops.start_trip(req.request_id, user.driver_license)
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()
                if offer.status == 'in_progress' and b2.button("🏁 确认完成",
                                                               key=f"done_{req.request_id}"):
                    ok, msg = ops.complete_trip(req.request_id, user.driver_license)
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()
                if req.status in ('open', 'accepted') and b3.button("❌ 取消接单",
                                                                    key=f"dc_{req.request_id}"):
                    ok, msg = ops.cancel_request(req.request_id, driver_license=user.driver_license)
                    st.success(msg) if ok else st.error(msg)
                    st.rerun()
                if req.status == 'completed':
                    can, target = ops.can_review(req.request_id, 'driver', ukey)
                    if can:
                        with st.expander(f"⭐ 评价学生（行程 #{req.request_id}）"):
                            rate = st.slider("乘车行为评分", 1, 5, 5, key=f"drate_{req.request_id}")
                            cmt = st.text_input("评语", key=f"dcmt_{req.request_id}")
                            if st.button("提交评价", key=f"dsub_{req.request_id}"):
                                ok, msg = ops.submit_review(
                                    req.request_id, 'driver', ukey, 'student',
                                    str(req.student_number), rate, cmt)
                                st.success(msg) if ok else st.error(msg)

    with tb_map:
        page_map()
    with tb_msg:
        page_messages()
    with tb_stat:
        page_stats()
    with tb_me:
        page_profile()
    with tb_set:
        page_settings()
