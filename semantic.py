# -*- coding: utf-8 -*-
"""10 维语义画像（移植自 guessword 的 VectorService 思路，改用 bge 重实现）。

guessword 用腾讯词向量 + 6 个锚点词/维 取均值得到「维度基向量」，任意词与该基向量
的点积即该语义维度得分。这里用 bge 本地嵌入完全复刻同一思路：

  - 10 个语义维度，每维 6 个中文锚点词；
  - 启动时把锚点词编码后按维取均值 → 维度基向量（一次性，_DIM_BASIS）；
  - profile(word) = [max(0, word·basis_i) * 100 for i in 10 维]  ∈ [0,100]。

模型未加载（EMBED_OK=False）时 profile() 返回 None，UI 优雅降级（雷达图显示占位）。
不引入任何额外硬依赖：bge 走 engine._MODEL，纯 Python 做点积，无需 numpy。
"""

import re

import engine

# ---------- 10 个语义维度 + 每维 6 个中文锚点词 ----------
DIMENSIONS = [
    ("食物", ["米饭", "面包", "水果", "蔬菜", "牛肉", "蛋糕"]),
    ("学习", ["书本", "学校", "老师", "考试", "知识", "笔记"]),
    ("游戏", ["玩具", "电子", "关卡", "玩家", "冒险", "棋牌"]),
    ("科技", ["电脑", "手机", "网络", "芯片", "软件", "智能"]),
    ("艺术", ["绘画", "音乐", "舞蹈", "雕塑", "电影", "文学"]),
    ("自然", ["山川", "河流", "森林", "星空", "海洋", "花草"]),
    ("情感", ["快乐", "悲伤", "爱情", "愤怒", "思念", "温暖"]),
    ("运动", ["跑步", "足球", "篮球", "游泳", "健身", "比赛"]),
    ("动物", ["猫咪", "狗狗", "老虎", "小鸟", "鱼类", "熊猫"]),
    ("生活", ["家庭", "工作", "睡眠", "购物", "旅行", "厨房"]),
]

_DIM_LOADED = False
_DIM_BASIS = []          # list[list[float]]，长度 = 嵌入维度
_PROFILE_CACHE = {}      # word -> [10 floats] | None
_PROFILE_CACHE_MAX = 4000


def dim_names():
    """返回 10 个维度名（供 UI 雷达图标签）。"""
    return [d[0] for d in DIMENSIONS]


def _norm(t):
    return re.sub(r"\s+", "", (t or "").strip().lower())


def _encode(text):
    """用 engine 的 bge 模型编码单个文本为 list[float]；无模型返回 None。"""
    if not engine.EMBED_OK or engine._MODEL is None:
        return None
    try:
        v = engine._MODEL.encode([text], normalize_embeddings=True)[0]
        return list(v)
    except Exception:
        return None


def ensure_dims(force=False):
    """加载 10 维基向量；模型缺失则 _DIM_LOADED=False（优雅降级）。"""
    global _DIM_LOADED, _DIM_BASIS
    if _DIM_LOADED and not force:
        return _DIM_LOADED
    if not engine.EMBED_OK or engine._MODEL is None:
        _DIM_LOADED = False
        return False
    basis = []
    for _name, anchors in DIMENSIONS:
        av = [v for v in (_encode(a) for a in anchors) if v]
        if not av:
            basis.append(None)
            continue
        dim = len(av[0])
        mean = [sum(v[i] for v in av) / len(av) for i in range(dim)]
        basis.append(mean)
    _DIM_BASIS = basis
    _DIM_LOADED = True
    return True


def profile(word):
    """返回该词的 10 维语义画像（0~100，list[float]）。模型未就绪返回 None。"""
    if not _DIM_LOADED or not _DIM_BASIS:
        return None
    w = _norm(word)
    if not w:
        return None
    if w in _PROFILE_CACHE:
        return _PROFILE_CACHE[w]
    v = _encode(word)
    if not v:
        _PROFILE_CACHE[w] = None
        return None
    out = []
    for basis in _DIM_BASIS:
        if not basis or len(basis) != len(v):
            out.append(0.0)
            continue
        s = max(0.0, sum(v[i] * basis[i] for i in range(len(v))))
        out.append(round(min(100.0, s * 100), 1))
    _PROFILE_CACHE[w] = out
    if len(_PROFILE_CACHE) > _PROFILE_CACHE_MAX:
        _PROFILE_CACHE.pop(next(iter(_PROFILE_CACHE)))
    return out
