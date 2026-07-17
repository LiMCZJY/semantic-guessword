# -*- coding: utf-8 -*-
"""直播弹幕条（呼应 guessword 的 LiveDanmaku.jsx）。

把每次提交的猜词以「飞过」的弹幕形式在直播大屏顶部滚动展示，强化「弹幕猜词」的
直播感。颜色随主题（theme.current()['danmaku']）变化。无显示屏/offscreen 环境下
构造与 push 不崩溃，仅在有显示器时真正绘制移动。
"""

import random

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QWidget

import theme


class DanmakuStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setObjectName("card")
        self._items = []          # [{label, x, y, speed}]
        self._max = 14
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def push(self, text, gift=False):
        if not text:
            return
        th = theme.current()
        color = "#ffd36f" if gift else th["danmaku"]
        lab = QLabel(text, self)
        lab.setStyleSheet(
            f"color:{color}; font-weight:bold; font-size:14px; "
            f"background:transparent; padding:0 6px;")
        lab.adjustSize()
        y = random.randint(2, max(2, self.height() - lab.height() - 2))
        lab.move(self.width(), y)
        lab.show()
        self._items.append({"label": lab, "x": self.width(),
                            "y": y, "speed": random.uniform(1.6, 3.6)})
        # 超出上限移除最旧
        while len(self._items) > self._max:
            old = self._items.pop(0)
            old["label"].deleteLater()
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self):
        if not self._items:
            self._timer.stop()
            return
        w = self.width()
        alive = []
        for it in self._items:
            it["x"] -= it["speed"]
            it["label"].move(int(it["x"]), it["y"])
            if it["x"] > -it["label"].width():
                alive.append(it)
            else:
                it["label"].deleteLater()
        self._items = alive
