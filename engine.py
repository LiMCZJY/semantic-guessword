# -*- coding: utf-8 -*-
"""语义猜词 游戏引擎（纯 Python，无 HTTP）。

从原网页版 app.py 移植：状态 / 语义打分 / 礼物 / 回合 / 词库。
所有写操作加 threading.Lock。默认 FORCE_FALLBACK=1 走字符级余弦，免模型开箱即玩。
"""

import os
import sys
import re
import math
import time
import random
import threading
from collections import defaultdict

from wordbank import WORD_BANK

# ---------- 语义引擎配置 ----------
EMBED_OK = False
_MODEL = None
_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
SCORE_MODE = "cos"   # "cos" 或 "shift"

# ---------- 计分 / 礼物常量 ----------
RATE_LIMIT = 3          # 同一用户 N 秒内只处理 1 条；0=不限
LIVE_BONUS = 50         # 直播模式猜中额外奖励分
GIFT_SUBMIT_CAP = 60    # 单次送礼最多写入榜单条数
GIFT_SCORE_CAP = 90.0   # 礼物关联度封顶（绝不猜中）
GUESS_KEEP = 60         # 关联度榜最多保留条数（见 _truncate_guesses）
GIFT_WORD_COUNT = {"点赞": 1, "小心心": 50, "关注": 50, "大啤酒": 100, "鲜花": 500}

# ---------- 接近度提示阈值（bge 余弦口径，0~100） ----------
# 移植自 guessword 的「接近了 / 就差一点」反馈，按 bge 分值重新标定。
PROX_NEAR = 55.0        # ≥ 此值：💡 接近了！
PROX_VERYNEAR = 75.0    # ≥ 此值：🔥 就差一点！

# ---------- 拼音渐进提示（可选 pypinyin；缺失则整体降级为空） ----------
PY_HINT_T1 = 0.4        # 经过 hint_time 的 40% 揭示首字拼音首字母
PY_HINT_T2 = 0.7        # 经过 hint_time 的 70% 揭示全部拼音首字母（完整提示解锁前）

# 词库内所有两字词（礼物批量生成池）
ALL_TWOCHAR = [w["word"] for cat in WORD_BANK.values() for w in cat if len(w["word"]) == 2]

# ---------- 状态 ----------
state = {
    "round_id": 0,
    "answer": "",            # 当前谜底
    "pos": "",               # 词性
    "duration": 240,         # 单局总时长（秒）
    "hint_time": 120,        # 多少秒后解锁提示
    "hint": "",              # 提示文本
    "start_ts": 0,           # 本局开始时间戳
    "solved": False,         # 是否已有人猜中
    "winner": "",            # 猜中者
    "last_winner": "",       # 上局猜中者（开新局时从 winner 结转）
    "guesses": [],           # 本局猜词记录 [{user, word, score, pts, gift?}]
    "scores": {},            # user -> 累计积分
    "live": False,           # 直播沉浸模式
}

_lock = threading.Lock()
_last_submit = {}          # user -> 上次提交时间戳（限流用）
_RATE_LOCK = threading.Lock()

_SIM_CACHE = {}           # (norm_a, norm_b) -> 余弦
_SIM_CACHE_MAX = 8000


# ---------- 模型加载（可选 bge） ----------
def load_model():
    """加载 bge 本地模型；FORCE_FALLBACK=1 时跳过（仅供单测）。
    加载失败：单测逃生口才允许字符余弦降级；否则直接抛错，绝不静默降级。"""
    global EMBED_OK, _MODEL
    if os.environ.get("FORCE_FALLBACK") == "1":
        EMBED_OK = False
        _MODEL = None
        return
    try:
        from sentence_transformers import SentenceTransformer
        candidates = []
        # 1) 源码 / 项目目录下的 models/bge
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "bge"))
        # 2) PyInstaller 打包后的 models/bge
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "models", "bge"))
        local = next((p for p in candidates if os.path.isdir(p)), None)
        if local:
            _MODEL = SentenceTransformer(local)
        else:
            _MODEL = SentenceTransformer(_MODEL_NAME)  # 联网下载
        EMBED_OK = True
    except Exception as e:
        if os.environ.get("FORCE_FALLBACK") == "1":
            EMBED_OK = False
            _MODEL = None
            return
        raise RuntimeError("BGE 语义模型加载失败，已禁用余弦降级：" + repr(e)) from e


# ---------- 语义打分 ----------
def _norm(t):
    return re.sub(r"\s+", "", (t or "").strip().lower())


def _fallback_vec(t):
    v = defaultdict(float)
    for ch in t:
        if not ch.isspace():
            v[ch] += 1.0
    return v


def _cosine(a, b):
    common = set(a) & set(b)
    if not common:
        return 0.0
    num = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(x * x for x in a.values()))
    nb = math.sqrt(sum(x * x for x in b.values()))
    return 0.0 if (na == 0 or nb == 0) else num / (na * nb)


def similarity(a, b):
    """返回 [-1,1] 余弦；完全一致（归一化后相等）直接 1.0。带 FIFO 缓存。
    仅当 FORCE_FALLBACK=1（单测）才允许字符余弦降级；生产永远走 bge，绝不降级。"""
    if _norm(a) == _norm(b):
        return 1.0
    ka, kb = _norm(a), _norm(b)
    key = (ka, kb) if ka <= kb else (kb, ka)
    if key in _SIM_CACHE:
        return _SIM_CACHE[key]
    if EMBED_OK and _MODEL is not None:
        va = _MODEL.encode([a], normalize_embeddings=True)[0]
        vb = _MODEL.encode([b], normalize_embeddings=True)[0]
        c = float(va @ vb)
    elif os.environ.get("FORCE_FALLBACK") == "1":
        # 仅单测逃生口：字符余弦降级
        c = _cosine(_fallback_vec(a), _fallback_vec(b))
    else:
        raise RuntimeError("BGE 模型未加载，已禁用余弦降级（similarity 不应被调用）")
    _SIM_CACHE[key] = c
    if len(_SIM_CACHE) > _SIM_CACHE_MAX:
        _SIM_CACHE.pop(next(iter(_SIM_CACHE)))
    return c


def score_of(a, b):
    """返回 0~100，保留一位小数。"""
    c = similarity(a, b)
    if SCORE_MODE == "shift":
        return round(max(0.0, min(100.0, (c + 1) / 2 * 100)), 1)
    return round(max(0.0, min(100.0, c * 100)), 1)


# ---------- 拼音渐进提示（铁律之外的新增线索机制，可降级） ----------
def _pinyin_initials(word):
    """返回每个字拼音首字母（大写）；无 pypinyin 或异常返回 None。"""
    try:
        from pypinyin import lazy_pinyin, Style
    except Exception:
        return None
    try:
        res = lazy_pinyin(word or "", style=Style.INITIALS, strict=False)
        out = []
        for s in res:
            if not s:
                out.append("")
                continue
            ch = s[0].upper()
            out.append(ch if ch.isalpha() else "")
        return out
    except Exception:
        return None


def pinyin_hint(answer, elapsed, hint_time):
    """按 elapsed 占 hint_time 的比例渐进揭示拼音首字母；完整提示解锁后返回空。

    返回形如「拼音提示：P_ ?_」/「拼音提示：P_ G_」；无 pypinyin 或无需揭示时返回空串。
    """
    inits = _pinyin_initials(answer)
    if not inits:
        return ""
    if hint_time and elapsed >= hint_time:
        return ""  # 完整文本提示已解锁，拼音提示不再单独显示
    show_all = bool(hint_time and elapsed >= hint_time * PY_HINT_T2)
    show_first = bool(hint_time and elapsed >= hint_time * PY_HINT_T1)
    if not show_all and not show_first:
        return ""  # 未到首字揭示阈值前完全不显示（避免开局就暴露字数）
    revealed = []
    for i, ini in enumerate(inits):
        token = (ini + "_") if ini else "_"
        if show_all:
            revealed.append(token)
        elif i == 0 and show_first:
            revealed.append(token)
        else:
            revealed.append("?_")
    return "拼音提示：" + " ".join(revealed)


# ---------- 限流 ----------
def _rate_ok(user):
    if RATE_LIMIT <= 0:
        return True
    now = time.time()
    with _RATE_LOCK:
        last = _last_submit.get(user, 0)
        if now - last < RATE_LIMIT:
            return False
        _last_submit[user] = now
    return True


# ---------- 礼物词生成（铁律 1：剔除当前谜底） ----------
def gen_gift_words(gtype):
    n = GIFT_WORD_COUNT.get(gtype)
    if not n:
        return []
    ans = state.get("answer", "")
    pool = [w for w in ALL_TWOCHAR if w != ans] or ALL_TWOCHAR
    return random.choices(pool, k=n)


# ---------- 段位 ----------
def tier_of(score):
    if score >= 300:
        return "王者"
    if score >= 150:
        return "黄金"
    if score >= 50:
        return "白银"
    if score >= 1:
        return "青铜"
    return "萌新"


# ---------- 关联度榜截断（铁律 5：真实词只增不减） ----------
def _truncate_guesses():
    real = [g for g in state["guesses"] if not g.get("gift")]
    gift = sorted((g for g in state["guesses"] if g.get("gift")),
                  key=lambda g: g["score"], reverse=True)
    keep = real + gift[:max(0, GUESS_KEEP - len(real))]
    keep.sort(key=lambda g: g["score"], reverse=True)
    state["guesses"] = keep


# ---------- 单条手动猜词 ----------
def submit_guess(user, word):
    if not word or not word.strip():
        return {"best": 0, "submitted": 0, "ended": bool(state["answer"])}
    if not _rate_ok(user):
        return {"best": 0, "submitted": 0, "ended": False, "rated": True}
    sc = score_of(state["answer"], word)
    with _lock:
        ended = bool(state["answer"]) and (
            (time.time() - state["start_ts"] >= state["duration"]) or state["solved"])
        if not state["answer"] or ended:
            return {"best": 0, "submitted": 0, "ended": bool(state["answer"])}
        pts = 0
        if sc >= 100:
            if not state["solved"]:
                state["solved"] = True
                state["winner"] = user
                pts = 100 + (LIVE_BONUS if state["live"] else 0)
        elif sc >= (70 if SCORE_MODE == "shift" else 50) and not state["solved"]:
            base = 70 if SCORE_MODE == "shift" else 50
            pts = max(1, int((sc - base) // 10))
        state["guesses"].append(
            {"user": user, "word": word, "score": sc, "pts": pts, "gift": False})
        state["scores"][user] = state["scores"].get(user, 0) + pts
        _truncate_guesses()
        return {"best": sc, "submitted": 1, "ended": False}


# ---------- 批量提交（手动 / 礼物共用） ----------
def submit_batch(user, words, is_gift=False):
    if not words:
        return {"best": 0, "submitted": 0, "ended": bool(state["answer"])}
    if not _rate_ok(user):
        return {"best": 0, "submitted": 0, "ended": False, "rated": True}
    words = words[:GIFT_SUBMIT_CAP]
    # 打分在锁外算（bge 推理不阻塞写锁）
    scored = [(w, score_of(state["answer"], w)) for w in words]
    with _lock:
        ended = bool(state["answer"]) and (
            (time.time() - state["start_ts"] >= state["duration"]) or state["solved"])
        if not state["answer"] or ended:
            return {"best": 0, "submitted": 0, "ended": bool(state["answer"])}
        best = 0
        for w, sc in scored:
            if is_gift:
                sc = min(sc, GIFT_SCORE_CAP)          # 铁律 2：礼物封顶 90，绝不猜中
            pts = 0
            if not is_gift and sc >= 100:
                if not state["solved"]:
                    state["solved"] = True
                    state["winner"] = user
                    pts = 100 + (LIVE_BONUS if state["live"] else 0)
            elif sc >= (70 if SCORE_MODE == "shift" else 50) and not state["solved"]:
                base = 70 if SCORE_MODE == "shift" else 50
                pts = max(1, int((sc - base) // 10))
            # 铁律 3：积分计入送礼者本人昵称（无后缀）
            state["guesses"].append(
                {"user": user, "word": w, "score": sc, "pts": pts, "gift": is_gift})
            state["scores"][user] = state["scores"].get(user, 0) + pts
            best = max(best, sc)
        _truncate_guesses()
        return {"best": best, "submitted": len(scored), "ended": False}


# ---------- 关联度榜分组（同词合并，count 累加，score 取最高） ----------
def group_guesses(guesses):
    groups = {}
    for g in guesses:
        w = g["word"]
        if w not in groups:
            groups[w] = {"user": g["user"], "word": w,
                         "score": g["score"], "count": 0, "gift": g.get("gift", False)}
        groups[w]["count"] += 1
        if g["score"] > groups[w]["score"]:
            groups[w]["score"] = g["score"]
            groups[w]["user"] = g["user"]
    out = list(groups.values())
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


# ---------- 回合管理 ----------
def new_round(answer, pos="", duration=240, hint_time=120, hint=""):
    global state
    with _lock:
        state["round_id"] += 1
        state["answer"] = answer
        state["pos"] = pos
        state["duration"] = duration
        state["hint_time"] = hint_time
        state["hint"] = hint
        state["start_ts"] = time.time()
        state["solved"] = False
        if state["winner"]:
            state["last_winner"] = state["winner"]
        state["winner"] = ""
        state["guesses"] = []


def draw_from_bank(category="", difficulty=""):
    """category 空=全库；difficulty='偏难'=中等+困难，否则精确匹配。返回一条 dict 或 None。"""
    if category:
        cats = [category] if category in WORD_BANK else []
    else:
        cats = list(WORD_BANK.keys())
    pool = []
    for c in cats:
        for w in WORD_BANK.get(c, []):
            if difficulty == "偏难":
                if w["difficulty"] in ("中等", "困难"):
                    pool.append(w)
            elif difficulty:
                if w["difficulty"] == difficulty:
                    pool.append(w)
            else:
                pool.append(w)
    if not pool:
        return None
    return random.choice(pool)


def set_live(on):
    global state
    with _lock:
        state["live"] = bool(on)


def reset(keep_scores=True):
    global state
    with _lock:
        scores = dict(state["scores"]) if keep_scores else {}
        last_winner = state["last_winner"] if keep_scores else ""
        state = {
            "round_id": state["round_id"],
            "answer": "",
            "pos": "",
            "duration": state["duration"],
            "hint_time": state["hint_time"],
            "hint": "",
            "start_ts": 0,
            "solved": False,
            "winner": "",
            "last_winner": last_winner,
            "guesses": [],
            "scores": scores,
            "live": state["live"],
        }


# ---------- 状态快照（对应原 public_state，去 HTTP） ----------
def get_state():
    with _lock:
        now = time.time()
        dur = state["duration"]
        start = state["start_ts"]
        elapsed = max(0.0, now - start) if start else 0.0
        remaining = max(0.0, dur - elapsed) if start else float(dur)
        hint_unlocked = bool(state["answer"]) and (elapsed >= state["hint_time"])
        ended = bool(state["answer"]) and (remaining <= 0 or state["solved"])
        lb = sorted(state["scores"].items(), key=lambda kv: kv[1], reverse=True)[:30]
        leaderboard = [{"user": u, "score": sc, "tier": tier_of(sc)} for u, sc in lb]

        # 接近度 / 弹幕统计 / 拼音渐进提示（供前端反馈与雷达图）
        real_guesses = [g for g in state["guesses"] if not g.get("gift")]
        if real_guesses:
            best_g = max(real_guesses, key=lambda g: g["score"])
            best_score = best_g["score"]
            best_word = best_g["word"]
        else:
            best_score = 0.0
            best_word = ""
        guess_count = len(real_guesses)
        ph = pinyin_hint(state["answer"], elapsed, state["hint_time"]) if state["answer"] else ""

        return {
            "embed": EMBED_OK,
            "round_id": state["round_id"],
            "answer": state["answer"],
            "pos": state["pos"],
            "duration": dur,
            "hint_time": state["hint_time"],
            "hint": state["hint"],
            "start_ts": start,
            "remaining": remaining,
            "elapsed": elapsed,
            "hint_unlocked": hint_unlocked,
            "solved": state["solved"],
            "winner": state["winner"],
            "last_winner": state["last_winner"],
            "ended": ended,
            "live": state["live"],
            "guesses": [dict(g) for g in state["guesses"]],
            "leaderboard": leaderboard,
            "best_score": best_score,
            "best_word": best_word,
            "guess_count": guess_count,
            "pinyin_hint": ph,
        }
