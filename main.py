# -*- coding: utf-8 -*-
"""入口：创建 QApplication + MainWindow + LiveWindow，加载语义模型。"""

import os
import sys
import datetime
import traceback
import faulthandler

# 语义打分永远用 bge 本地模型（models/bge/，已随项目提供），绝不降级字符余弦。
# FORCE_FALLBACK=1 仅供引擎单测使用，生产/打包后永不启用。

# ---- 崩溃捕获：打包成 windowed exe 后无控制台，任何未处理异常/段错误写入 crash.log ----
_BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
    else os.path.dirname(os.path.abspath(__file__))
_CRASH_LOG = os.path.join(_BASE_DIR, "crash.log")
try:
    _crash_fp = open(_CRASH_LOG, "a", encoding="utf-8")
    faulthandler.enable(_crash_fp)
except Exception:
    _crash_fp = None


def _excepthook(exc_type, exc_value, exc_tb):
    try:
        with open(_CRASH_LOG, "a", encoding="utf-8") as fp:
            fp.write("\n===== %s 未处理异常 =====\n" % datetime.datetime.now().isoformat())
            traceback.print_exception(exc_type, exc_value, exc_tb, file=fp)
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook

from PyQt6.QtWidgets import QApplication

import engine
import theme
import semantic
from ui_main import MainWindow
from ui_live import LiveWindow


def main():
    try:
        engine.load_model()
    except RuntimeError as e:
        sys.exit(str(e))
    if not engine.EMBED_OK and os.environ.get("FORCE_FALLBACK") != "1":
        sys.exit("BGE 模型未加载，已禁用余弦降级。请检查 models/bge 是否存在。")

    app = QApplication(sys.argv)
    # 应用上次选择的主题（持久化在 theme.json）
    theme.apply_theme(app, theme.load_persisted())

    # 加载 10 维语义基向量（模型就绪才有效；失败仅影响雷达图，不阻塞启动）
    try:
        semantic.ensure_dims()
    except Exception as e:
        print("语义维度加载跳过：", e)

    main_win = MainWindow()
    live_win = LiveWindow()
    # 双窗口互引，便于主题切换互相同步
    main_win.live_win = live_win
    live_win.main_win = main_win
    main_win.show()
    live_win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
