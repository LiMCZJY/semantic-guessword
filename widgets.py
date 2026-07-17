# -*- coding: utf-8 -*-
"""可复用榜单控件。

- AssociationBoard：关联度猜词榜。原生可滚动、显示全部、增量更新不重建整个列表（铁律 7、9）。
- ScoreBoard：积分榜。前三名固定金色区，第 4 名起循环滚屏；内容未溢出则不滚（铁律 8）。
"""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QFrame, QProgressBar,
)

import theme


# ============================================================
# 关联度猜词榜
# ============================================================
class _AssocRow(QFrame):
    """单行：昵称(×次数) | 词 | 进度条 | 关联度%"""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setFixedHeight(34)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 2, 8, 2)
        h.setSpacing(8)

        self.nick = QLabel()
        self.nick.setFixedWidth(110)
        self.nick.setStyleSheet("color:#176d3c; font-weight:bold;")

        self.word = QLabel()
        self.word.setFixedWidth(70)
        self.word.setStyleSheet("font-size:15px; font-weight:bold; color:#0b5e30;")

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(16)

        self.pct = QLabel()
        self.pct.setFixedWidth(58)
        self.pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pct.setStyleSheet("font-weight:bold; color:#176d3c;")

        h.addWidget(self.nick)
        h.addWidget(self.word)
        h.addWidget(self.bar, 1)
        h.addWidget(self.pct)

    def fill(self, g):
        count = g.get("count", 1)
        nick_text = g["user"]
        if count > 1:
            nick_text = f"{g['user']} ×{count}"
        if g.get("gift"):
            nick_text = "🎁 " + nick_text
        self.nick.setText(nick_text)
        self.word.setText(g["word"])
        sc = g["score"]
        self.bar.setValue(int(round(sc)))
        self.bar.setStyleSheet(theme.GIFT_BAR_STYLE if g.get("gift") else theme.ASSOC_BAR_STYLE)
        self.pct.setText(f"{sc:.1f}%")   # 铁律 6：一位小数


class AssociationBoard(QWidget):
    """关联度榜：显示全部、可滚动、增量更新不闪。"""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner_lay = QVBoxLayout(self.inner)
        self.inner_lay.setContentsMargins(6, 6, 6, 6)
        self.inner_lay.setSpacing(4)
        self.inner_lay.addStretch(1)   # 底部占位，内容少时不顶到头
        self.scroll.setWidget(self.inner)
        lay.addWidget(self.scroll)

        self.rows = {}        # word -> _AssocRow
        self._order = []      # 当前排序（word 列表）

    def update(self, grouped):
        """grouped: list of {user, word, score, count, gift}，已按 score 降序。"""
        current = {g["word"] for g in grouped}

        # 1) 删除已不存在的词
        for w in list(self.rows.keys()):
            if w not in current:
                row = self.rows.pop(w)
                self.inner_lay.removeWidget(row)
                row.deleteLater()

        # 2) 新建 / 就地更新（不重建，不闪）
        for g in grouped:
            if g["word"] not in self.rows:
                self.rows[g["word"]] = _AssocRow()
            self.rows[g["word"]].fill(g)

        # 3) 仅在排序变化时才重排（保持滚动位置稳定）
        new_order = [g["word"] for g in grouped]
        if new_order != self._order:
            self._reorder(new_order)
            self._order = new_order

    def _reorder(self, order):
        lay = self.inner_lay
        # 先把所有行移出布局（不删除），再按新顺序加回，stretch 始终在末尾
        for w in order:
            lay.removeWidget(self.rows[w])
        for w in order:
            lay.insertWidget(lay.count() - 1, self.rows[w])


# ============================================================
# 积分榜
# ============================================================
REST_ROW_H = 34
TOP_CARD_H = 60


class _TopCard(QFrame):
    """前三名固定金色卡片。"""

    MEDALS = ["①", "②", "③"]

    def __init__(self, rank):
        super().__init__()
        self.setObjectName("card")
        self.setFixedHeight(TOP_CARD_H)
        self.setStyleSheet(
            "QFrame#card { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 #fff3cf, stop:1 #ffe39a); border:1px solid #e8c25a; }")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 2, 10, 2)
        self.rank = QLabel(self.MEDALS[rank])
        self.rank.setStyleSheet("font-size:22px; color:#b8860b;")
        self.user = QLabel()
        self.user.setStyleSheet("font-size:16px; font-weight:bold; color:#7a5b00;")
        self.score = QLabel()
        self.score.setStyleSheet("font-size:16px; font-weight:bold; color:#7a5b00;")
        self.tier = QLabel()
        self.tier.setStyleSheet("color:#9a7400; font-size:12px;")
        h.addWidget(self.rank)
        h.addWidget(self.user, 1)
        h.addWidget(self.tier)
        h.addWidget(self.score)

    def fill(self, item):
        self.user.setText(item["user"])
        self.score.setText(f'{item["score"]}分')
        self.tier.setText(item["tier"])


class _ScoreRow(QFrame):
    """第 4 名起的滚动行。"""

    def __init__(self, rank):
        super().__init__()
        self.setObjectName("card")
        self.setFixedHeight(REST_ROW_H)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 1, 8, 1)
        self.rank = QLabel(str(rank))
        self.rank.setFixedWidth(28)
        self.rank.setStyleSheet("color:#888; font-weight:bold;")
        self.user = QLabel()
        self.user.setStyleSheet("font-weight:bold; color:#1f3d2b;")
        self.tier = QLabel()
        self.tier.setStyleSheet("color:#b8902f; font-size:12px;")
        self.score = QLabel()
        self.score.setStyleSheet("font-weight:bold; color:#176d3c;")
        h.addWidget(self.rank)
        h.addWidget(self.user, 1)
        h.addWidget(self.tier)
        h.addWidget(self.score)

    def fill(self, item, rank):
        self.rank.setText(str(rank))
        self.user.setText(item["user"])
        self.tier.setText(item["tier"])
        self.score.setText(f'{item["score"]}分')


class ScoreBoard(QWidget):
    """积分榜：前三固定 + 第4名起循环滚屏（铁律 8）。"""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # 前三固定区
        self.top_frame = QFrame()
        self.top_frame.setObjectName("card")
        self.top_lay = QVBoxLayout(self.top_frame)
        self.top_lay.setContentsMargins(6, 6, 6, 6)
        self.top_lay.setSpacing(6)
        self.top_cards = [_TopCard(i) for i in range(3)]
        for c in self.top_cards:
            self.top_lay.addWidget(c)
        lay.addWidget(self.top_frame)

        # 第4名起滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner_lay = QVBoxLayout(self.inner)
        self.inner_lay.setContentsMargins(0, 0, 0, 0)
        self.inner_lay.setSpacing(4)
        self.scroll.setWidget(self.inner)
        lay.addWidget(self.scroll, 1)

        self._rest = []          # 当前第4名起的原始数据
        self._rest_sig = None    # 重排签名
        self._rows = []          # 第一份行控件（高度计算用）
        self.offset = 0.0
        self.speed = 0.5
        self.single_h = 0
        self._scrolling = False

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)

    def update(self, leaderboard):
        # 前三
        for i in range(3):
            if i < len(leaderboard):
                self.top_cards[i].show()
                self.top_cards[i].fill(leaderboard[i])
            else:
                self.top_cards[i].hide()

        # 第4名起
        rest = leaderboard[3:]
        sig = [(it["user"], it["score"]) for it in rest]
        if sig != self._rest_sig:
            self._rebuild_rest(rest)
            self._rest_sig = sig

        # 是否滚动：内容超出视口高度才滚
        viewport_h = self.scroll.viewport().height()
        if self.single_h > 0 and self.single_h > viewport_h:
            if not self._scrolling:
                self._scrolling = True
                self.timer.start()
        else:
            self._scrolling = False
            if self.timer.isActive():
                self.timer.stop()
            self.offset = 0.0
            self.scroll.verticalScrollBar().setValue(0)

    def _rebuild_rest(self, rest):
        # 清空
        while self.inner_lay.count():
            item = self.inner_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows = []

        for idx, it in enumerate(rest):
            row = _ScoreRow(4 + idx)
            row.fill(it, 4 + idx)
            self.inner_lay.addWidget(row)
            self._rows.append(row)
        # 复制第二份用于无缝循环
        for idx, it in enumerate(rest):
            row = _ScoreRow(4 + idx)
            row.fill(it, 4 + idx)
            self.inner_lay.addWidget(row)

        n = len(rest)
        self.single_h = n * (REST_ROW_H + 4)
        # 重建后保持 offset 不越界
        if self.single_h > 0:
            self.offset = min(self.offset, float(self.single_h))
        else:
            self.offset = 0.0

    def _tick(self):
        if not self._scrolling or self.single_h <= 0:
            return
        self.offset += self.speed
        if self.offset >= self.single_h:
            self.offset -= self.single_h
        self.scroll.verticalScrollBar().setValue(int(self.offset))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 视口高度变化后重新评估是否滚动
        viewport_h = self.scroll.viewport().height()
        if self.single_h > 0 and self.single_h > viewport_h:
            if not self._scrolling:
                self._scrolling = True
                self.timer.start()
        else:
            self._scrolling = False
            if self.timer.isActive():
                self.timer.stop()
            self.offset = 0.0
            self.scroll.verticalScrollBar().setValue(0)
