# -*- coding: utf-8 -*-
"""引擎单测（纯 Python，FORCE_FALLBACK=1 保证确定性）。覆盖文档第 12.1 节。"""

import os
import random

os.environ["FORCE_FALLBACK"] = "1"

import engine
from engine import (
    submit_guess, submit_batch, gen_gift_words, new_round, draw_from_bank,
    get_state, group_guesses, reset, set_live,
)


def setup_function(_):
    # 每测之间彻底重置，使用不同随机种子
    random.seed()
    engine.RATE_LIMIT = 0   # 测试确定性：关闭限流
    reset(keep_scores=False)
    engine._last_submit.clear()


def _real_guesses():
    return [g for g in engine.state["guesses"] if not g.get("gift")]


def _gift_guesses():
    return [g for g in engine.state["guesses"] if g.get("gift")]


# ---------------- 铁律 1/2：礼物封顶 90、不出现谜底、不猜中 ----------------
def test_gift_flower_capped_and_safe():
    new_round("苹果", "名词", 240, 120, "水果之王")
    res = submit_batch("观众A", gen_gift_words("鲜花"), is_gift=True)
    assert res["best"] <= 90, "礼物最佳关联度必须 <= 90（铁律 2）"
    assert res["best"] >= 0
    assert all(g.get("gift") for g in _gift_guesses()), "礼物词必须带 gift:True"
    assert "苹果" not in gen_gift_words("鲜花"), "礼物词不得包含当前谜底（铁律 1）"
    assert engine.state["solved"] is False, "礼物绝不能猜中（铁律 2）"
    assert engine.state["solved"] is False


# ---------------- 铁律 5：真实词只增不减，礼物补满到 60 ----------------
def test_real_guesses_only_increase():
    new_round("西瓜", "名词", 240, 120, "夏天的水果")
    # 30 个真实猜词（不同昵称，互不相同词避免合并）
    for i in range(30):
        submit_guess(f"观众{i}", f"词{i}")
    assert len(_real_guesses()) == 30, f"真实词应为 30，实际 {len(_real_guesses())}"

    # 送鲜花（500 词 -> 截断到 GIFT_SUBMIT_CAP=60）
    submit_batch("送礼人", gen_gift_words("鲜花"), is_gift=True)
    total_after_gift = len(engine.state["guesses"])
    # 真实 30 + 礼物补满到 60 => 总数 60，礼物 30
    assert len(_real_guesses()) == 30, "礼物不得挤掉真实词（铁律 5）"
    assert total_after_gift == 60, f"总数应补满到 60，实际 {total_after_gift}"

    # 再加 10 个真实词 -> 真实 40，礼物被挤到 20，总数仍 60
    for i in range(30, 40):
        submit_guess(f"观众{i}", f"词{i}")
    assert len(_real_guesses()) == 40, f"真实词应增到 40，实际 {len(_real_guesses())}"
    assert len(engine.state["guesses"]) == 60, "总数保持 60 上限"
    assert len(_gift_guesses()) == 20, f"礼物被挤到 20，实际 {len(_gift_guesses())}"


# ---------------- 手动猜中：积分 + 直播奖励 ----------------
def test_manual_solve_and_live_bonus():
    new_round("篮球", "名词", 240, 120, "投篮")
    res = submit_guess("观众B", "篮球")
    assert res["best"] == 100.0
    assert engine.state["solved"] is True
    assert engine.state["winner"] == "观众B"
    assert engine.state["scores"]["观众B"] == 100

    # 直播模式 +50
    reset(keep_scores=False)
    set_live(True)
    new_round("篮球", "名词", 240, 120, "投篮")
    submit_guess("观众C", "篮球")
    assert engine.state["scores"]["观众C"] == 150, "直播模式猜中应 +50"
    set_live(False)


# ---------------- 铁律 6：关联度一位小数 ----------------
def test_score_one_decimal():
    sc = engine.score_of("苹果", "水果")
    assert isinstance(sc, float)
    assert round(sc, 1) == sc, "关联度必须保留一位小数（铁律 6）"
    # 完全一致应 100.0
    assert engine.score_of("苹果", "苹果") == 100.0


# ---------------- 铁律 3：礼物积分计本人（无后缀） ----------------
def test_gift_scores_self():
    # 用确定会得分的礼物词：耳机 vs 手机 共享「机」-> 余弦 0.5 -> 50.0% -> 部分分 1
    new_round("手机", "名词", 240, 120, "掌中小方块")
    submit_batch("送礼者", ["耳机"], is_gift=True)
    assert engine.state["scores"].get("送礼者", 0) > 0, "礼物积分应计入本人"
    assert "送礼者·礼物" not in engine.state["scores"], "积分 key 不得加后缀（铁律 3）"


# ---------------- 铁律 8：直播续局 ----------------
def test_live_auto_next_round():
    set_live(True)
    new_round("西瓜", "名词", 240, 120, "夏天")
    submit_guess("观众X", "西瓜")          # 猜中
    rid = engine.state["round_id"]
    pick = draw_from_bank()                 # 模拟自动续局
    assert pick is not None
    new_round(pick["word"], pick.get("pos", ""), 240, 120, pick.get("hint", ""))
    assert engine.state["round_id"] == rid + 1, "应开启下一题"
    assert engine.state["last_winner"] == "观众X", "上局猜中者结转"
    set_live(False)


# ---------------- 关联度榜分组：同词合并、count 累加、score 取最高 ----------------
def test_group_guesses_merge():
    new_round("西瓜", "名词", 240, 120, "夏天")
    submit_guess("甲", "水果")
    submit_guess("乙", "水果")
    submit_guess("丙", "甜")
    grouped = group_guesses(engine.state["guesses"])
    by_word = {g["word"]: g for g in grouped}
    assert by_word["水果"]["count"] == 2, "同词应合并计数"
    assert by_word["水果"]["user"] in ("甲", "乙")
    assert len(grouped) == 2, "两种不同词 => 两行"


# ---------------- 关联度榜显示全部、无 slice 截断（铁律 7） ----------------
def test_assoc_board_no_truncation():
    new_round("西瓜", "名词", 240, 120, "夏天")
    for i in range(40):
        submit_guess(f"观众{i}", f"不同词{i}")   # 40 个不同词
    st = get_state()
    grouped = group_guesses(st["guesses"])
    assert len(grouped) == 40, "关联度榜应显示全部 40 条，不得截断（铁律 7）"
    assert st["ended"] is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
