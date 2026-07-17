# -*- coding: utf-8 -*-
"""engine 新增字段单测（best_score / best_word / guess_count / pinyin_hint）。

守住铁律不变的前提下，验证 guessword 移植来的「接近度统计」与「拼音渐进提示」。
"""

import os

os.environ["FORCE_FALLBACK"] = "1"

import engine
from engine import (
    new_round, submit_guess, submit_batch, gen_gift_words, reset, get_state,
)


def setup_function(_):
    engine.RATE_LIMIT = 0
    reset(keep_scores=False)
    engine._last_submit.clear()


def test_get_state_new_fields():
    new_round("篮球", "名词", 240, 120, "投篮")
    submit_guess("a", "篮球")  # 猜中 100
    st = get_state()
    for k in ("best_score", "best_word", "guess_count", "pinyin_hint"):
        assert k in st, f"get_state 缺少字段 {k}"
    assert st["best_score"] == 100.0
    assert st["best_word"] == "篮球"
    assert st["guess_count"] == 1


def test_best_score_ignores_gifts():
    new_round("西瓜", "名词", 240, 120, "夏天")
    submit_guess("甲", "冬瓜")                 # 真实词（与「西瓜」共享「瓜」，字符余弦 50）
    submit_batch("送礼", gen_gift_words("鲜花"), is_gift=True)  # 礼物封顶 90
    st = get_state()
    # guess_count 只计真实词
    assert st["guess_count"] == 1
    # best_score / best_word 来自真实词，礼物不污染
    assert st["best_word"] == "冬瓜"
    assert st["best_score"] > 0


def test_guess_count_excludes_gifts():
    new_round("西瓜", "名词", 240, 120, "夏天")
    submit_batch("送礼", gen_gift_words("鲜花"), is_gift=True)
    st = get_state()
    assert st["guess_count"] == 0, "礼物词不计入 guess_count"


def test_pinyin_hint_progressive(monkeypatch):
    # 本环境未必有 pypinyin，用假首字母打穿渐进揭示逻辑
    monkeypatch.setattr(engine, "_pinyin_initials", lambda w: ["X", "G"])

    # 刚出题（elapsed≈0）：不揭示
    assert engine.pinyin_hint("西瓜", 0, 120) == ""
    # 经过 50% 提示时间（T1=0.4 ~ T2=0.7 之间）：仅首字
    ph = engine.pinyin_hint("西瓜", 60, 120)
    assert "X_" in ph and "?_" in ph
    # 经过 83% 提示时间（> T2）：全部揭示
    ph2 = engine.pinyin_hint("西瓜", 100, 120)
    assert "X_" in ph2 and "G_" in ph2
    # 完整提示已解锁（elapsed >= hint_time）：拼音提示清空，由文本提示接管
    assert engine.pinyin_hint("西瓜", 120, 120) == ""

    # 无 pypinyin（initials=None）：任何阶段都返回空（优雅降级）
    monkeypatch.setattr(engine, "_pinyin_initials", lambda w: None)
    assert engine.pinyin_hint("西瓜", 60, 120) == ""
