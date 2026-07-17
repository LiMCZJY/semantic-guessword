# -*- coding: utf-8 -*-
"""直播大屏窗口（LiveWindow）。

独立窗口，可全屏/无边框（方便 OBS 窗口捕获）。隐藏谜底直到猜中揭晓。
关联度榜 + 积分榜同主播台。猜中瞬间全屏恭喜动画 + 显示答案；
直播模式猜中自动 draw_from_bank + new_round 续局。无后台控件。

新增（移植自 guessword 的好思路）：
- 语义雷达图：目标词 10 维画像作淡色水印，最新猜词叠加亮色描边；
- 弹幕条：每次提交的猜词飞过顶部，强化「弹幕猜词」直播感；
- 接近度横幅：关联度越过高阈值时弹出「接近了 / 就差一点」；
- 主题切换：与主播台共享 QApplication 样式，可选直播高对比主题。
"""

import time

from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtProperty
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QProgressBar, QPushButton, QApplication, QComboBox,
)

import engine
import theme
import semantic
from widgets import AssociationBoard, ScoreBoard
from radar import RadarChart
from danmaku import DanmakuStrip


class _Congrats(QWidget):
    """猜中全屏恭喜遮罩（淡入 + 轻微缩放）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._opacity = 0.0
        self.winner = ""
        self.answer = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

    def setData(self, winner, answer):
        self.winner = winner
        self.answer = answer

    def _get_opacity(self):
        return self._opacity

    def _set_opacity(self, v):
        self._opacity = v
        self.update()

    opacity = pyqtProperty(float, _get_opacity, _set_opacity)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(theme.current()["accent"])
        # 半透明底色
        p.fillRect(self.rect(), QColor(0, 60, 30, int(150 * self._opacity)))
        # 中央面板
        cx, cy = self.rect().width() / 2, self.rect().height() / 2
        scale = 0.8 + 0.2 * self._opacity
        w, h = 720 * scale, 300 * scale
        r = QRectF(cx - w / 2, cy - h / 2, w, h)
        p.setBrush(QColor(255, 255, 255, int(235 * self._opacity)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 24, 24)
        p.setPen(accent)
        p.setOpacity(self._opacity)
        font = QFont("Microsoft YaHei", int(40 * scale), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(r, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   f"🎉 恭喜 {self.winner} 猜中！")
        font2 = QFont("Microsoft YaHei", int(72 * scale), QFont.Weight.Bold)
        p.setFont(font2)
        p.setPen(accent)
        p.drawText(r.adjusted(0, h * 0.42, 0, 0),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   f"答案是：{self.answer}")


class LiveWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("语义猜词 · 直播大屏")
        self.resize(960, 680)
        self._prev_solved = False
        self._prev_round_id = -1
        self._auto_next_timer = None

        # 接近度横幅状态
        self._prev_best = 0.0
        self._prox_timer = None
        # 弹幕去重（每局重置）
        self._danmaku_sent = set()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        # 顶部：答案遮罩 + 大号计时 + 提示
        top = QFrame()
        top.setObjectName("card")
        tl = QVBoxLayout(top)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.setSpacing(8)

        head = QHBoxLayout()
        self.answer = QLabel("？？")
        self.answer.setObjectName("answer")
        self.answer.setStyleSheet(
            "font-size:40px; font-weight:bold; color:#0b5e30; background:#fff; "
            "border:3px solid #46c07a; border-radius:12px; padding:6px 20px;")
        self.live_tag = QLabel("🔴 LIVE")
        self.live_tag.setStyleSheet("color:#e23b3b; font-weight:bold; font-size:16px;")
        self.live_tag.hide()
        head.addWidget(QLabel("谜底"))
        head.addWidget(self.answer)
        head.addStretch(1)
        head.addWidget(self.live_tag)
        tl.addLayout(head)

        timer_row = QHBoxLayout()
        self.timer_bar = QProgressBar()
        self.timer_bar.setRange(0, 100)
        self.timer_bar.setTextVisible(False)
        self.timer_bar.setFixedHeight(18)
        self.timer_bar.setStyleSheet(theme.ASSOC_BAR_STYLE)
        self.remaining = QLabel("—")
        self.remaining.setStyleSheet("font-size:30px; font-weight:bold; color:#176d3c;")
        timer_row.addWidget(self.timer_bar, 1)
        timer_row.addWidget(self.remaining)
        tl.addLayout(timer_row)

        self.hint = QLabel("提示：未出题")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("font-size:16px;")
        tl.addWidget(self.hint)

        self.pinyin = QLabel("")
        self.pinyin.setStyleSheet("font-size:14px; color:#b8860b; font-weight:bold;")
        tl.addWidget(self.pinyin)

        v.addWidget(top)

        # 弹幕条
        self.danmaku = DanmakuStrip()
        v.addWidget(self.danmaku)

        # 中部：关联度榜 + (雷达 + 积分榜)
        mid = QHBoxLayout()
        mid.setSpacing(12)
        left = QVBoxLayout()
        la = QLabel("🔗 关联度猜词榜")
        la.setObjectName("section")
        left.addWidget(la)
        self.assoc = AssociationBoard()
        left.addWidget(self.assoc, 1)
        mid.addLayout(left, 3)

        right = QVBoxLayout()
        # 雷达图卡片
        rc = QFrame()
        rc.setObjectName("card")
        rcl = QVBoxLayout(rc)
        rcl.setContentsMargins(10, 8, 10, 8)
        rcl.setSpacing(4)
        rtitle = QLabel("🕸 语义雷达（目标词→水印 / 最新猜词→描边）")
        rtitle.setObjectName("section")
        rcl.addWidget(rtitle)
        self.radar = RadarChart()
        rcl.addWidget(self.radar, 1)
        right.addWidget(rc)

        ra = QLabel("🏆 积分排行榜")
        ra.setObjectName("section")
        right.addWidget(ra)
        self.score = ScoreBoard()
        right.addWidget(self.score, 1)
        mid.addLayout(right, 2)
        v.addLayout(mid, 1)

        # 底部工具条：全屏 / 无边框 / 主题
        bar = QHBoxLayout()
        bar.addStretch(1)
        fs = QPushButton("全屏")
        fs.setObjectName("ghost")
        fs.clicked.connect(self._toggle_fullscreen)
        bar.addWidget(fs)
        border = QPushButton("无边框")
        border.setObjectName("ghost")
        border.clicked.connect(self._toggle_borderless)
        bar.addWidget(border)
        bar.addSpacing(12)
        bar.addWidget(QLabel("主题"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(theme.get_names())
        self.theme_combo.setCurrentText(theme.current_name())
        self.theme_combo.currentTextChanged.connect(self._on_theme)
        bar.addWidget(self.theme_combo)
        v.addLayout(bar)

        # 恭喜遮罩
        self.congrats = _Congrats(self.centralWidget())
        self.congrats.setGeometry(self.centralWidget().rect())

        # 接近度横幅（叠加层）
        self.prox = QLabel("", self.centralWidget())
        self.prox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prox.setStyleSheet(
            "font-size:34px; font-weight:bold; color:#fff; "
            "background:rgba(20,20,20,0.78); border-radius:14px; padding:10px 28px;")
        self.prox.hide()
        self._place_prox()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

        # 遮罩淡入动画定时器
        self._anim = QTimer(self)
        self._anim.setInterval(30)
        self._anim.timeout.connect(self._anim_step)
        self._anim_val = 0.0

    def _place_prox(self):
        cw = self.centralWidget()
        if not cw:
            return
        w, h = 420, 64
        self.prox.setGeometry((cw.width() - w) // 2, 92, w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "congrats"):
            self.congrats.setGeometry(self.centralWidget().rect())
        if hasattr(self, "prox"):
            self._place_prox()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _toggle_borderless(self):
        if self.windowFlags() & Qt.WindowType.FramelessWindowHint:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.FramelessWindowHint)
        else:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.show()

    def _on_theme(self, name):
        app = QApplication.instance()
        theme.apply_theme(app, name)
        main = getattr(self, "main_win", None)
        if main is not None and main.theme_combo.currentText() != name:
            main.theme_combo.setCurrentText(name)

    def _refresh(self):
        s = engine.get_state()

        # 新局：重置接近度/弹幕去重
        if s["round_id"] != self._prev_round_id:
            self._prev_best = 0.0
            self._danmaku_sent = set()

        # 答案遮罩
        if s["solved"] and s["answer"]:
            self.answer.setText(s["answer"])
            self.answer.setStyleSheet(
                "font-size:40px; font-weight:bold; color:#fff; background:#2faa63; "
                "border:3px solid #1d7d49; border-radius:12px; padding:6px 20px;")
        else:
            self.answer.setText("？？")
            self.answer.setStyleSheet(
                "font-size:40px; font-weight:bold; color:#0b5e30; background:#fff; "
                "border:3px solid #46c07a; border-radius:12px; padding:6px 20px;")

        if s["live"]:
            self.live_tag.show()
        else:
            self.live_tag.hide()

        # 计时（进度条随主题变色）
        self.timer_bar.setStyleSheet(theme.ASSOC_BAR_STYLE)
        if s["answer"]:
            if s["duration"] > 0:
                pct = int(min(100, s["elapsed"] / s["duration"] * 100))
            else:
                pct = 0
            self.timer_bar.setValue(pct)
            if s["ended"]:
                self.remaining.setText("本局结束")
            else:
                self.remaining.setText(f"{int(s['remaining'])}s")
            if s["hint_unlocked"]:
                self.hint.setText(f"💡 {s['hint'] or '（无）'}")
            else:
                self.hint.setText(f"🔒 {int(max(0, s['hint_time'] - s['elapsed']))} 秒后解锁")
            self.pinyin.setText(s["pinyin_hint"] or "")
        else:
            self.timer_bar.setValue(0)
            self.remaining.setText("—")
            self.hint.setText("提示：未出题")
            self.pinyin.setText("")

        # 语义雷达：目标词作水印，最新猜词叠加
        target = semantic.profile(s["answer"]) if s["answer"] else None
        guess = semantic.profile(s["best_word"]) if s.get("best_word") else None
        self.radar.set_data(target, guess)

        # 弹幕条：本局新出现的词各飞一次
        for g in s["guesses"]:
            if g["word"] not in self._danmaku_sent:
                self._danmaku_sent.add(g["word"])
                self.danmaku.push(g["word"], gift=g.get("gift", False))

        # 榜单
        self.assoc.update(engine.group_guesses(s["guesses"]))
        self.score.update(s["leaderboard"])

        # 接近度横幅
        if not s["solved"]:
            best = s["best_score"]
            if best > self._prev_best + 0.01:
                if best >= engine.PROX_VERYNEAR:
                    self._show_prox("🔥 就差一点！")
                elif best >= engine.PROX_NEAR:
                    self._show_prox("💡 接近了！")
            self._prev_best = best

        # 猜中恭喜 + 续局
        if s["solved"] and not self._prev_solved and s["winner"]:
            self._show_congrats(s["winner"], s["answer"])
            if s["live"]:
                self._schedule_auto_next()
        if s["round_id"] != self._prev_round_id and not s["solved"]:
            self._hide_congrats()
        self._prev_solved = s["solved"]
        self._prev_round_id = s["round_id"]

    def _show_prox(self, text):
        self.prox.setText(text)
        self.prox.show()
        if self._prox_timer and self._prox_timer.isActive():
            self._prox_timer.stop()
        self._prox_timer = QTimer(self)
        self._prox_timer.setSingleShot(True)
        self._prox_timer.timeout.connect(self.prox.hide)
        self._prox_timer.start(2600)

    def _show_congrats(self, winner, answer):
        self.congrats.setData(winner, answer)
        self.congrats.show()
        self._anim_val = 0.0
        self.congrats.opacity = 0.0
        self._anim.start()

    def _hide_congrats(self):
        self._anim.stop()
        self.congrats.hide()
        self.congrats.opacity = 0.0

    def _anim_step(self):
        self._anim_val = min(1.0, self._anim_val + 0.08)
        self.congrats.opacity = self._anim_val
        if self._anim_val >= 1.0:
            self._anim.stop()

    def _schedule_auto_next(self):
        if self._auto_next_timer and self._auto_next_timer.isActive():
            return
        self._auto_next_timer = QTimer(self)
        self._auto_next_timer.setSingleShot(True)
        self._auto_next_timer.timeout.connect(self._auto_next)
        self._auto_next_timer.start(4000)   # 恭喜展示 4 秒后自动续局

    def _auto_next(self):
        pick = engine.draw_from_bank()
        if pick:
            engine.new_round(pick["word"], pick.get("pos", ""), 240, 120, pick.get("hint", ""))
        # 隐藏遮罩（新局）
        self._hide_congrats()
