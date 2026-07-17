# -*- coding: utf-8 -*-
"""语义雷达图（移植自 guessword 的 RadarChart.jsx 思路，改用 QPainter 实现）。

- 10 个轴 = semantic.dim_names()（食物/学习/…/生活）；
- 目标词画像作淡色填充「背景水印」（对应 guessword 把目标维度画像铺底）；
- 最新一条猜词画像作亮色描边叠加，直观看出「猜的词朝哪个语义方向偏」；
- 模型未加载（profile 返回 None）时显示占位文字，不崩溃。
"""

import math

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

import semantic
import theme


class RadarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dims = semantic.dim_names()
        self._target = None     # list[float] 0~100 | None
        self._guess = None      # list[float] 0~100 | None
        self.setMinimumHeight(220)

    def set_data(self, target, guess):
        self._target = target
        self._guess = guess
        self.update()

    def _geometry(self):
        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2 + 6
        r = min(w, h) / 2 - 26
        return cx, cy, max(10.0, r)

    def _point(self, cx, cy, r, i, value):
        n = len(self._dims)
        ang = -math.pi / 2 + i * (2 * math.pi / n)
        rr = (max(0.0, min(100.0, value)) / 100.0) * r
        return QPointF(cx + rr * math.cos(ang), cy + rr * math.sin(ang))

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            self._paint(p)
        except Exception:
            # 绘制异常绝不能拖垮进程（打包成 exe 后未处理异常会导致闪退）
            pass
        finally:
            p.end()

    def _paint(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = self._geometry()
        n = len(self._dims)

        # 网格环
        grid = QPen(QColor(150, 150, 150, 60), 1)
        for ring in (0.25, 0.5, 0.75, 1.0):
            pts = [self._point(cx, cy, r, i, ring * 100) for i in range(n)]
            p.setPen(grid)
            p.drawPolygon(pts)

        # 轴线 + 标签
        label_pen = QPen(QColor(120, 120, 120, 180), 1)
        p.setPen(label_pen)
        p.setFont(QFont("Microsoft YaHei", 10))
        th = theme.current()
        accent = QColor(th["danmaku"])
        for i, name in enumerate(self._dims):
            outer = self._point(cx, cy, r, i, 100)
            p.drawLine(QPointF(cx, cy), outer)
            lp = self._point(cx, cy, r + 14, i, 100)
            p.setPen(accent)
            p.drawText(QPointF(lp.x() - 16, lp.y() + 4), name)
            p.setPen(label_pen)

        # 目标词画像：淡色填充水印
        if self._target:
            tpts = [self._point(cx, cy, r, i, self._target[i]) for i in range(n)]
            soft = th["soft"].split(",")
            fill = QColor(int(soft[0]), int(soft[1]), int(soft[2]), 70)
            p.setBrush(fill)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(tpts)
            p.setBrush(Qt.BrushStyle.NoBrush)

        # 最新猜词画像：亮色描边
        if self._guess:
            gpts = [self._point(cx, cy, r, i, self._guess[i]) for i in range(n)]
            p.setPen(QPen(accent, 2.5))
            p.drawPolygon(gpts)
            p.setPen(QPen(accent, 3))
            for pt in gpts:
                p.drawEllipse(pt, 2.5, 2.5)

        # 占位
        if not self._target and not self._guess:
            p.setPen(QColor(150, 150, 150))
            p.setFont(QFont("Microsoft YaHei", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "语义模型未加载\n（bge 就绪后显示画像）")
