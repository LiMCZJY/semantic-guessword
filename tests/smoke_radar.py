# -*- coding: utf-8 -*-
"""Headless 冒烟测试：强制渲染语义雷达图，回归验证 QPainter 绘制不抛异常。

背景：radar.py 曾把 QPointF.x()/y()（float）直接传给 drawText(x:int, y:int, str)，
PyQt6 类型检查严格会抛 TypeError。源码环境下 PyQt6 只打印不中断，看似正常；
但打包成 windowed exe 后，paintEvent 的未处理异常会导致进程闪退。

本测试直接调用 RadarChart._paint(painter)（绘制主体，未被 paintEvent 的兜底 try 吞掉），
覆盖「有目标+猜词数据」这条正是当年崩溃的绘制路径。任何绘制类型错误都会让本测试失败。

以脚本方式运行（需系统 Python 的 PyQt6）：
    QT_QPA_PLATFORM=offscreen FORCE_FALLBACK=1 python tests/smoke_radar.py
"""

import os
import sys

os.environ.setdefault("FORCE_FALLBACK", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

import radar


def _render(widget):
    """用真实 QPainter 在离屏 QPixmap 上执行绘制主体；异常会向上抛出。"""
    pm = QPixmap(320, 280)
    pm.fill()
    p = QPainter(pm)
    try:
        widget._paint(p)
    finally:
        p.end()


def main():
    app = QApplication(sys.argv)
    w = radar.RadarChart()
    w.resize(320, 280)

    # 1) 无数据：占位分支
    _render(w)
    print("  [1/3] 占位绘制 OK")

    # 2) 仅目标词画像（水印填充多边形 + 轴标签 drawText，正是崩溃路径）
    target = [50.0, 70.0, 20.0, 90.0, 10.0, 60.0, 40.0, 80.0, 15.0, 55.0]
    w.set_data(target, None)
    _render(w)
    print("  [2/3] 目标画像 + 轴标签 drawText OK")

    # 3) 目标 + 最新猜词（描边多边形 + 顶点圆点 drawEllipse）
    guess = [30.0, 45.0, 65.0, 25.0, 85.0, 35.0, 75.0, 20.0, 50.0, 40.0]
    w.set_data(target, guess)
    _render(w)
    print("  [3/3] 猜词描边 + 顶点圆点 OK")

    print("SMOKE_RADAR_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
