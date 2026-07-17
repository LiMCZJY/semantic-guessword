# -*- coding: utf-8 -*-
"""Headless 冒烟测试：用 offscreen 平台构建两窗口，验证构造/刷新/榜单/猜中/续局无异常。

不是 pytest 用例（需要 QApplication 事件循环 + 显示器），以脚本方式运行：
    QT_QPA_PLATFORM=offscreen python tests/smoke_ui.py
"""

import os
import sys

os.environ["FORCE_FALLBACK"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# 让脚本能 import 项目根目录的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine
from ui_main import MainWindow
from ui_live import LiveWindow


def main():
    engine.RATE_LIMIT = 0   # 冒烟测试确定性：关闭限流
    # 准备数据：40 个真实猜词（验证关联度榜无截断、铁律 7）+ 5 个积分者（验证前三固定+滚屏）
    engine.reset(keep_scores=False)
    engine.new_round("西瓜", "名词", 240, 120, "夏天冰镇红瓤")
    for i in range(40):
        engine.submit_guess(f"观众{i}", f"词{i}")          # 40 个不同词，均进入关联度榜
    engine.submit_batch("送礼者", engine.gen_gift_words("鲜花"), is_gift=True)

    # 直接设定 5 个积分者，覆盖段位与「第 4 名起滚屏」
    engine.state["scores"] = {
        "王者A": 320, "黄金B": 160, "白银C": 80, "青铜D": 40, "萌新E": 5
    }

    app = None
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication(sys.argv)
    except Exception as e:
        print("SKIP: 无法创建 QApplication（无显示器环境）：", e)
        return 0

    mw = MainWindow()
    lw = LiveWindow()
    mw.show()
    lw.show()

    # 多次刷新（含一次尺寸变化以触发滚屏逻辑）
    for _ in range(3):
        mw._refresh()
        lw._refresh()

    # 断言：关联度榜显示全部真实猜词（无 slice 截断，铁律 7），且礼物词也同待遇入榜（铁律 4）
    assoc_rows = len(mw.assoc.rows)
    for i in range(40):
        assert f"词{i}" in mw.assoc.rows, f"真实猜词 词{i} 未显示（铁律 7）"
    assert assoc_rows > 15, f"关联度榜不得有 15 条硬截断，实际 {assoc_rows} 条（铁律 7）"

    # 断言：积分榜前三固定区有 3 张卡，第 4 名起滚动区有 2 行
    top_visible = sum(1 for c in mw.score.top_cards if c.isVisible())
    assert top_visible == 3, f"前三固定区应显示 3 张卡，实际 {top_visible}（铁律 8）"
    assert len(mw.score._rows) == 2, f"第4名起应有 2 行，实际 {len(mw.score._rows)}"

    # 模拟猜中 -> 直播大屏恭喜遮罩 + 自动续局
    engine.set_live(True)
    engine.submit_guess("观众0", "西瓜")     # 猜中
    assert engine.state["solved"] is True
    lw._refresh()                            # 触发恭喜遮罩
    assert lw.congrats.isVisible(), "猜中后恭喜遮罩应显示"
    lw._auto_next()                          # 直接调用续局逻辑
    st = engine.get_state()
    assert st["round_id"] >= 2, "直播模式应自动续局"
    assert st["last_winner"] == "观众0", "上局猜中者结转"
    assert st["solved"] is False, "新局未猜中"
    lw._refresh()                            # 新局刷新，隐藏遮罩

    print("SMOKE OK: 关联度榜=%d 条, 前三卡=%d, 滚屏行=%d, 续局 round_id=%d"
          % (assoc_rows, top_visible, len(mw.score._rows), st["round_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
