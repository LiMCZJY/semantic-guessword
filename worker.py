# -*- coding: utf-8 -*-
"""打分线程 worker：大礼物批量打分 / bge 推理放线程，避免卡 UI。

UI 通过 ScoreWorker(user, words, is_gift) 启动，finished_sig 回传 engine.submit_batch 结果。
"""

from PyQt6.QtCore import QThread, pyqtSignal

import engine


class ScoreWorker(QThread):
    finished_sig = pyqtSignal(dict)

    def __init__(self, user, words, is_gift=False):
        super().__init__()
        self.user = user
        self.words = list(words)
        self.is_gift = is_gift

    def run(self):
        try:
            res = engine.submit_batch(self.user, self.words, self.is_gift)
        except Exception as e:
            # 防止线程因打分异常静默崩溃；返回零结果，UI 不写入榜单
            res = {"submitted": 0, "best": 0.0, "added": 0, "error": str(e)}
        self.finished_sig.emit(res)
