# -*- coding: utf-8 -*-
"""主播台窗口（MainWindow）。

含全部控件：出题 / 猜词 / 礼物 / 随机抽题 / 直播开关 / 重置。
关联度榜与积分榜调用 widgets.py 的可复用控件，1 秒轮询增量刷新。
"""

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QProgressBar, QDialog, QFormLayout,
    QMessageBox, QCheckBox, QApplication,
)

import engine
import worker
import theme
from widgets import AssociationBoard, ScoreBoard
from wordbank import WORD_BANK


class _PuzzleDialog(QDialog):
    """手动录入谜底。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("手动出题")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.answer = QLineEdit()
        self.pos = QLineEdit()
        self.duration = QLineEdit("240")
        self.hint_time = QLineEdit("120")
        self.hint = QLineEdit()
        form.addRow("谜底 *", self.answer)
        form.addRow("词性", self.pos)
        form.addRow("单局时长(秒)", self.duration)
        form.addRow("提示解锁(秒)", self.hint_time)
        form.addRow("提示文本", self.hint)
        btns = QHBoxLayout()
        ok = QPushButton("确定出题")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        form.addRow(btns)

    def data(self):
        return {
            "answer": self.answer.text().strip(),
            "pos": self.pos.text().strip(),
            "duration": int(self.duration.text() or 240),
            "hint_time": int(self.hint_time.text() or 120),
            "hint": self.hint.text().strip(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("语义猜词 · 主播台")
        self.resize(1100, 720)
        self._gift_worker = None

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        # ---------- 顶部栏 ----------
        top = QFrame()
        top.setObjectName("card")
        tl = QVBoxLayout(top)
        tl.setContentsMargins(12, 10, 12, 10)
        tl.setSpacing(6)

        title_row = QHBoxLayout()
        title = QLabel("🎯 抖音直播间 AI 语义猜词")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.live_toggle = QCheckBox("直播沉浸模式")
        self.live_toggle.stateChanged.connect(self._on_live)
        title_row.addWidget(self.live_toggle)

        title_row.addSpacing(12)
        title_row.addWidget(QLabel("主题"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(theme.get_names())
        self.theme_combo.setCurrentText(theme.current_name())
        self.theme_combo.currentTextChanged.connect(self._on_theme)
        title_row.addWidget(self.theme_combo)
        tl.addLayout(title_row)

        info = QHBoxLayout()
        ans_label = QLabel("当前谜底：")
        self.answer = QLabel("（未出题）")
        self.answer.setObjectName("answer")
        self.pos_label = QLabel("")
        self.last_winner = QLabel("")
        self.last_winner.setStyleSheet("color:#b8860b; font-weight:bold;")
        info.addWidget(ans_label)
        info.addWidget(self.answer)
        info.addWidget(self.pos_label)
        info.addStretch(1)
        info.addWidget(self.last_winner)
        tl.addLayout(info)

        timer_row = QHBoxLayout()
        self.timer_bar = QProgressBar()
        self.timer_bar.setRange(0, 100)
        self.timer_bar.setTextVisible(False)
        self.timer_bar.setFixedHeight(14)
        self.remaining = QLabel("—")
        self.remaining.setStyleSheet("font-weight:bold; color:#176d3c;")
        timer_row.addWidget(self.timer_bar, 1)
        timer_row.addWidget(self.remaining)
        tl.addLayout(timer_row)

        self.hint_label = QLabel("提示：未出题")
        self.hint_label.setWordWrap(True)
        tl.addWidget(self.hint_label)

        v.addWidget(top)

        # ---------- 中部：关联度榜 + 积分榜 ----------
        mid = QHBoxLayout()
        mid.setSpacing(12)

        left = QVBoxLayout()
        la = QLabel("🔗 关联度猜词榜（显示全部，可滚动）")
        la.setObjectName("section")
        left.addWidget(la)
        self.assoc = AssociationBoard()
        left.addWidget(self.assoc, 1)

        right = QVBoxLayout()
        ra = QLabel("🏆 积分排行榜")
        ra.setObjectName("section")
        right.addWidget(ra)
        self.score = ScoreBoard()
        right.addWidget(self.score, 1)

        mid.addLayout(left, 3)
        mid.addLayout(right, 2)
        v.addLayout(mid, 1)

        # ---------- 底部操作区 ----------
        bottom = QFrame()
        bottom.setObjectName("card")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(8)

        # 第一行：猜词
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("昵称"))
        self.nick = QLineEdit("我")
        self.nick.setFixedWidth(110)
        r1.addWidget(self.nick)
        r1.addWidget(QLabel("猜词"))
        self.guess = QLineEdit()
        self.guess.setPlaceholderText("输入一个词，回车提交")
        self.guess.returnPressed.connect(self._submit_guess)
        r1.addWidget(self.guess, 1)
        send = QPushButton("发送")
        send.clicked.connect(self._submit_guess)
        r1.addWidget(send)
        bl.addLayout(r1)

        # 第二行：礼物 + 抽题 + 出题 + 重置
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("礼物"))
        self.gift_combo = QComboBox()
        self.gift_combo.addItems(list(engine.GIFT_WORD_COUNT.keys()))
        r2.addWidget(self.gift_combo)
        gift_btn = QPushButton("送出")
        gift_btn.clicked.connect(self._send_gift)
        r2.addWidget(gift_btn)

        r2.addSpacing(16)
        r2.addWidget(QLabel("分类"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItem("全部", "")
        for c in WORD_BANK.keys():
            self.cat_combo.addItem(c, c)
        r2.addWidget(self.cat_combo)
        r2.addWidget(QLabel("难度"))
        self.diff_combo = QComboBox()
        self.diff_combo.addItem("全部", "")
        self.diff_combo.addItem("简单", "简单")
        self.diff_combo.addItem("中等", "中等")
        self.diff_combo.addItem("困难", "困难")
        self.diff_combo.addItem("偏难", "偏难")
        r2.addWidget(self.diff_combo)
        draw_btn = QPushButton("随机抽题")
        draw_btn.clicked.connect(self._draw)
        r2.addWidget(draw_btn)

        r2.addSpacing(16)
        manual_btn = QPushButton("手动出题")
        manual_btn.setObjectName("ghost")
        manual_btn.clicked.connect(self._manual)
        r2.addWidget(manual_btn)

        r2.addSpacing(16)
        reset_keep = QPushButton("保留积分重置")
        reset_keep.setObjectName("ghost")
        reset_keep.clicked.connect(lambda: self._reset(True))
        r2.addWidget(reset_keep)
        reset_clear = QPushButton("清空积分重置")
        reset_clear.setObjectName("ghost")
        reset_clear.clicked.connect(lambda: self._reset(False))
        r2.addWidget(reset_clear)
        r2.addStretch(1)
        bl.addLayout(r2)

        self.status = QLabel("就绪")
        self.status.setStyleSheet("color:#666;")
        bl.addWidget(self.status)

        v.addWidget(bottom)

        # 轮询
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()
        self._refresh()

    # ---------- 操作 ----------
    def _submit_guess(self):
        user = self.nick.text().strip() or "我"
        word = self.guess.text().strip()
        if not word:
            return
        res = engine.submit_guess(user, word)
        if res.get("rated"):
            self.status.setText(f"⏳ {user} 提交过快，请稍候（限流 {engine.RATE_LIMIT}s/条）")
        elif res.get("submitted"):
            self.status.setText(f"✅ {user} 猜「{word}」关联度 {res['best']:.1f}%")
        else:
            self.status.setText("⚠️ 当前无进行中的题目或本局已结束")
        self.guess.clear()
        self._refresh()

    def _send_gift(self):
        user = self.nick.text().strip() or "我"
        gtype = self.gift_combo.currentText()
        words = engine.gen_gift_words(gtype)
        if not words:
            self.status.setText(f"⚠️ 未知礼物类型：{gtype}")
            return
        # 送礼放 worker 线程，避免大礼物批量打分阻塞 UI
        if self._gift_worker and self._gift_worker.isRunning():
            self.status.setText("⏳ 上一批礼物还在处理中…")
            return
        self._gift_worker = worker.ScoreWorker(user, words, True)
        self._gift_worker.finished_sig.connect(self._on_gift_done)
        self.status.setText(f"🎁 正在送出「{gtype}」（{len(words)} 词）…")
        self._gift_worker.start()

    def _on_gift_done(self, res):
        if res.get("rated"):
            self.status.setText("⏳ 提交过快，礼物被限流，请稍候")
        else:
            self.status.setText(
                f"🎁 {self.gift_combo.currentText()} 已送出：{res['submitted']} 词，"
                f"最佳关联度 {res['best']:.1f}%（封顶 90，绝不猜中）")
        self._refresh()

    def _draw(self):
        cat = self.cat_combo.currentData()
        diff = self.diff_combo.currentData()
        pick = engine.draw_from_bank(cat, diff)
        if not pick:
            self.status.setText("⚠️ 当前筛选无可用题目")
            return
        engine.new_round(pick["word"], pick.get("pos", ""), 240, 120, pick.get("hint", ""))
        self.status.setText(f"🎲 已抽题：{pick['word']}（{pick.get('difficulty','')}）")
        self._refresh()

    def _manual(self):
        dlg = _PuzzleDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.data()
            if not data["answer"]:
                QMessageBox.warning(self, "提示", "谜底不能为空")
                return
            engine.new_round(data["answer"], data["pos"], data["duration"],
                             data["hint_time"], data["hint"])
            self.status.setText(f"✍️ 已出题：{data['answer']}")
            self._refresh()

    def _on_live(self, state):
        on = (state == Qt.CheckState.Checked.value)
        engine.set_live(on)
        self.status.setText(f"直播模式：{'开' if on else '关'}")
        self._refresh()

    def _on_theme(self, name):
        app = QApplication.instance()
        theme.apply_theme(app, name)
        self.status.setText(f"🎨 主题：{name}")
        live = getattr(self, "live_win", None)
        if live is not None and live.theme_combo.currentText() != name:
            live.theme_combo.setCurrentText(name)

    def _reset(self, keep):
        msg = "保留" if keep else "清空"
        if QMessageBox.question(self, "确认重置",
                                f"确定{msg}积分榜并结束本局？") != QMessageBox.StandardButton.Yes:
            return
        engine.reset(keep_scores=keep)
        self.status.setText(f"🔄 已重置（{msg}积分）")
        self._refresh()

    # ---------- 刷新 ----------
    def _refresh(self):
        s = engine.get_state()
        # 顶部
        if s["answer"]:
            self.answer.setText(s["answer"])
            self.pos_label.setText(f"（{s['pos']}）" if s["pos"] else "")
            if s["duration"] > 0:
                pct = int(min(100, s["elapsed"] / s["duration"] * 100))
            else:
                pct = 0
            self.timer_bar.setValue(pct)
            if s["ended"]:
                self.remaining.setText("本局结束")
            else:
                self.remaining.setText(f"剩余 {int(s['remaining'])}s")
            if s["hint_unlocked"]:
                self.hint_label.setText(f"💡 提示：{s['hint'] or '（无）'}")
            else:
                self.hint_label.setText(f"🔒 提示：{int(max(0, s['hint_time'] - s['elapsed']))} 秒后解锁")
        else:
            self.answer.setText("（未出题）")
            self.pos_label.setText("")
            self.timer_bar.setValue(0)
            self.remaining.setText("—")
            self.hint_label.setText("提示：未出题")

        if s["last_winner"]:
            self.last_winner.setText(f"👑 上局猜中：{s['last_winner']}")
        else:
            self.last_winner.setText("")

        # 榜单
        self.assoc.update(engine.group_guesses(s["guesses"]))
        self.score.update(s["leaderboard"])
