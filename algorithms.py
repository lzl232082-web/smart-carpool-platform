"""核心算法模块（与策划书第四章算法设计一一对应）：

1. Dijkstra 最短路径（堆优化）—— 动态权重 = 距离 × (1 + 拥堵系数)
2. 路径重叠度计算 —— 共同经过的路段总长度 / 用户 A 路径总长度
3. K-Means 聚类拼单 —— 对开放中订单按起终点经纬度聚类分组推荐
4. 用户相似度（皮尔逊相关系数）—— 基于历史出行目的地的画像向量
5. 分时段动态定价 —— 基础价 + 距离费 × 时段系数（高峰上浮）
"""
import heapq
import math
from datetime import datetime

import numpy as np

# ==================== 1. Dijkstra 最短路径 ====================

def dijkstra(edges: dict, src: int, dst: int):
    """堆优化 Dijkstra。

    :param edges: {node_id: [(neighbor_id, distance米, congestion), ...]}
    :param src: 源节点id  :param dst: 目标节点id
    :return: (动态权重总成本, 实际总距离米, 路径节点id列表)；不可达返回 (inf, inf, [])
    权重 = 距离 × (1 + 拥堵系数)，即策划书 4.1 的动态权重优化。
    """
    if src == dst:
        return 0.0, 0.0, [src]
    dist = {src: 0.0}          # 动态权重累计
    real = {src: 0.0}          # 真实距离累计(米)
    prev = {}
    visited = set()
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u == dst:
            break
        for v, w_dist, cong in edges.get(u, []):
            w = w_dist * (1 + cong)
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                real[v] = real[u] + w_dist
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if dst not in visited and dst not in dist:
        return math.inf, math.inf, []
    path, cur = [dst], dst
    while cur != src:
        cur = prev[cur]
        path.append(cur)
    return dist[dst], real[dst], path[::-1]


def build_graph(edge_rows):
    """把 node_distances 查询结果构建成邻接表。

    :param edge_rows: 可迭代对象，元素需含 from_node/to_node/distance/congestion
    """
    g = {}
    for e in edge_rows:
        g.setdefault(e.from_node, []).append((e.to_node, e.distance, e.congestion or 0))
    return g


def route_overlap(path_a: list, path_b: list, edge_len: dict) -> float:
    """路径重叠度 = 共同经过的路段总长度 / 用户A路径总长度（策划书 4.1 优化②）。

    :param path_a: 用户A路径节点序列  :param path_b: 待比较路径节点序列
    :param edge_len: {(u,v): 距离} 无向边长度表
    """
    if len(path_a) < 2:
        return 0.0
    edges_a = {tuple(sorted((path_a[i], path_a[i + 1])))
               for i in range(len(path_a) - 1)}
    edges_b = {tuple(sorted((path_b[i], path_b[i + 1])))
               for i in range(len(path_b) - 1)}
    common = edges_a & edges_b
    total_a = sum(edge_len.get(e, 0) for e in edges_a)
    if total_a == 0:
        return 0.0
    return sum(edge_len.get(e, 0) for e in common) / total_a


# ==================== 2. K-Means 聚类拼单 ====================

def kmeans_cluster_orders(orders, my_point=None, k_max=3, random_state=42):
    """对开放中的拼车订单做 K-Means 聚类，用于"拼单推荐"。

    特征向量 = [出发地纬度, 出发地经度, 目的地纬度, 目的地经度]。
    k 值结合业务先验确定：最多 k_max 组（对应校园区域划分），订单不足时降级。
    :param orders: 订单列表，每个订单需有 departure/destination 属性（节点名称）
    :param my_point: 可选，把"我的需求"也作为一个样本参与聚类（键 'me'）
    :return: {request_id或'me': 簇编号}
    """
    node_pos = get_node_pos()
    pts, keys = [], []
    if my_point is not None:
        pts.append(list(my_point))
        keys.append('me')
    for o in orders:
        dep, dst = node_pos.get(o.departure), node_pos.get(o.destination)
        if dep and dst:
            pts.append([dep[0], dep[1], dst[0], dst[1]])
            keys.append(getattr(o, 'request_id', None) or id(o))
    if not pts:
        return {}
    X = np.array(pts)
    k = max(1, min(k_max, len(X)))
    labels = _simple_kmeans(X, k, random_state)
    return dict(zip(keys, labels.tolist()))


def _simple_kmeans(X, k, random_state=42, iters=50):
    """K-Means 主体（欧氏距离，公式 4-1/4-2），不依赖 sklearn，便于教学演示。"""
    rng = np.random.RandomState(random_state)
    centers = X[rng.choice(len(X), k, replace=False)]
    labels = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        # 分配：就近分组 D(xi, zj) = min{...}
        d = np.linalg.norm(X[:, None, :] - centers[None, :, :], axis=2)
        new_labels = d.argmin(axis=1)
        if np.array_equal(new_labels, labels) and _ > 0:
            break
        labels = new_labels
        # 更新：重新计算簇中心（平方误差最小化）
        for j in range(k):
            if (labels == j).any():
                centers[j] = X[labels == j].mean(axis=0)
    return labels


# ==================== 3. 用户相似度（皮尔逊相关系数）====================

def pearson(u: dict, v: dict) -> float:
    """皮尔逊相关系数（策划书公式 4-3）：基于两个用户的偏好向量。

    :param u/v: {目的地或物品: 偏好强度}
    """
    common = set(u) & set(v)
    n = len(common)
    if n < 2:
        return 0.0
    uu = np.array([u[i] for i in common], dtype=float)
    vv = np.array([v[i] for i in common], dtype=float)
    du, dv = uu - uu.mean(), vv - vv.mean()
    denom = math.sqrt((du ** 2).sum()) * math.sqrt((dv ** 2).sum())
    if denom == 0:
        return 0.0
    return float((du * dv).sum() / denom)


def user_preference_vectors(history_rows):
    """由历史订单构建每个用户的偏好向量 {目的地: 出行次数权重}。

    :param history_rows: 含 student_number 与 destination 的记录
    """
    pref = {}
    for r in history_rows:
        pref.setdefault(str(r.student_number), {})
        pref[str(r.student_number)][r.destination] = \
            pref[str(r.student_number)].get(r.destination, 0) + 1
    return pref


# ==================== 4. 分时段动态定价 ====================

BASE_FARE = 3.0        # 起步价(元)
RATE_PER_KM = 1.2      # 每公里单价(元)


def dynamic_fare(distance_m: float, when: datetime = None) -> float:
    """费用预估 = 起步价 + 公里数 × 单价 × 时段系数（四舍五入到角）。

    高峰(7-9,17-19)上浮30%，深夜(22-6)上浮20%，平峰不变。
    """
    when = when or datetime.now()
    h = when.hour
    if 7 <= h < 9 or 17 <= h < 19:
        factor = 1.3
    elif h >= 22 or h < 6:
        factor = 1.2
    else:
        factor = 1.0
    fare = BASE_FARE + (distance_m / 1000) * RATE_PER_KM * factor
    return round(fare, 1)


# ---------- 小工具：节点坐标表（带缓存）----------
_NODE_POS_CACHE = None


def get_node_pos():
    """{节点名称: (纬度, 经度)}，首次查询后缓存。"""
    global _NODE_POS_CACHE
    if _NODE_POS_CACHE is None:
        from db import SessionLocal
        from models import NodeLocationModel
        s = SessionLocal()
        try:
            _NODE_POS_CACHE = {n.name: (float(n.latitude), float(n.longitude))
                               for n in s.query(NodeLocationModel).all()}
        finally:
            s.close()
    return _NODE_POS_CACHE


_NAME2ID_CACHE = None


def get_name2id():
    """{节点名称: 真实node_id}，与路网邻接表中的节点id一致。"""
    global _NAME2ID_CACHE
    if _NAME2ID_CACHE is None:
        from db import SessionLocal
        from models import NodeLocationModel
        s = SessionLocal()
        try:
            _NAME2ID_CACHE = {n.name: n.node_id
                              for n in s.query(NodeLocationModel).all()}
        finally:
            s.close()
    return _NAME2ID_CACHE


def get_graph_and_edge_len():
    """返回 (邻接表, 无向边长度表)，供 Dijkstra 与重叠度计算共用。"""
    from db import SessionLocal
    from models import NodeDistanceModel
    s = SessionLocal()
    try:
        rows = s.query(NodeDistanceModel).all()
        g = build_graph(rows)
        el = {(min(e.from_node, e.to_node), max(e.from_node, e.to_node)): e.distance
              for e in rows}
        return g, el
    finally:
        s.close()
