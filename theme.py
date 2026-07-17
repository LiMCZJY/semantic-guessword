# -*- coding: utf-8 -*-
"""多主题系统（移植自 guessword 的 17 主题思路，改为 PyQt QSS 实现）。

- 浅色系：默认绿 / 暖白 / 冷白 / 淡蓝 / 淡粉 / 淡紫
- 直播高对比（供 OBS 窗口捕获）：直播黑 / 直播蓝 / 直播紫 / 直播红 / 直播绿

默认主题「默认绿」视觉与原版完全一致，其余为可切换选项。
ASSOC_BAR_STYLE / GIFT_BAR_STYLE 改为可变全局，apply_theme 时刷新，
widgets 在每次 fill() 时读取最新值，实现榜单进度条随主题变色。
"""

import json
import os


def _default_palette():
    """原版「默认绿」调色板（保持视觉不变）。"""
    return {
        "bg_top": "#e8f8ee", "bg_bottom": "#d6f0e0",
        "text": "#1f3d2b",
        "card_bg": "#ffffff", "card_border": "#c7e9d4",
        "primary_top": "#4cc585", "primary_bottom": "#2faa63",
        "primary_hover": "#3bbd74", "primary_press": "#268a50",
        "ghost_text": "#176d3c", "ghost_border": "#46c07a",
        "scroll_bg": "#dff1e6", "scroll_handle": "#8fcfac",
        "scroll_handle_hover": "#5fb98c",
        "answer_color": "#0b5e30", "answer_bg": "#ffffff", "answer_border": "#46c07a",
        "title": "#176d3c", "section": "#176d3c",
        "bar_assoc": ("#7fe0a6", "#2faa63"), "bar_gift": ("#bfe9f5", "#6fc4e0"),
        "accent": "#2faa63", "soft": "47,170,99", "danmaku": "#2faa63",
    }


# 其余主题：仅列出与本调色板不同的键，缺失项从默认补齐。
_THEMES_RAW = {
    "暖白": {
        "bg_top": "#fbf6ec", "bg_bottom": "#f3ebd9", "text": "#3d3320",
        "card_bg": "#fffdf8", "card_border": "#e8d9b8",
        "primary_top": "#e0a64c", "primary_bottom": "#c4882f",
        "primary_hover": "#d4963f", "primary_press": "#a06d24",
        "ghost_text": "#8a6a2f", "ghost_border": "#d9b86a",
        "scroll_bg": "#f3ecdb", "scroll_handle": "#d9b86a", "scroll_handle_hover": "#c8a14f",
        "answer_color": "#8a5a1f", "answer_bg": "#fffdf8", "answer_border": "#d9b86a",
        "title": "#8a6a2f", "section": "#8a6a2f",
        "bar_assoc": ("#f0c878", "#c4882f"), "bar_gift": ("#bfe9f5", "#6fc4e0"),
        "accent": "#c4882f", "soft": "196,136,47", "danmaku": "#c4882f",
    },
    "冷白": {
        "bg_top": "#eef3fb", "bg_bottom": "#e0e9f5", "text": "#1f2d3d",
        "card_bg": "#ffffff", "card_border": "#c7d7ea",
        "primary_top": "#5a8fd0", "primary_bottom": "#3a6fb0",
        "primary_hover": "#4f82c4", "primary_press": "#2f5896",
        "ghost_text": "#2f5a8a", "ghost_border": "#6f9fd0",
        "scroll_bg": "#e6eef7", "scroll_handle": "#8fb0d8", "scroll_handle_hover": "#6f9fd0",
        "answer_color": "#1f4a7a", "answer_bg": "#ffffff", "answer_border": "#6f9fd0",
        "title": "#2f5a8a", "section": "#2f5a8a",
        "bar_assoc": ("#8fb8e8", "#3a6fb0"), "bar_gift": ("#bfe9f5", "#6fc4e0"),
        "accent": "#3a6fb0", "soft": "58,111,176", "danmaku": "#3a6fb0",
    },
    "淡蓝": {
        "bg_top": "#e6f3fb", "bg_bottom": "#d6eaf6", "text": "#1f3a4d",
        "card_bg": "#ffffff", "card_border": "#bfe0f0",
        "primary_top": "#4ca6d0", "primary_bottom": "#2f88b0",
        "primary_hover": "#3f9bc4", "primary_press": "#247096",
        "ghost_text": "#1f6a8a", "ghost_border": "#6fc0e0",
        "scroll_bg": "#e0eef7", "scroll_handle": "#8fc8e0", "scroll_handle_hover": "#6fb0d0",
        "answer_color": "#0f5a7a", "answer_bg": "#ffffff", "answer_border": "#6fc0e0",
        "title": "#1f6a8a", "section": "#1f6a8a",
        "bar_assoc": ("#8fd0e8", "#2f88b0"), "bar_gift": ("#bfe9f5", "#6fc4e0"),
        "accent": "#2f88b0", "soft": "47,136,176", "danmaku": "#2f88b0",
    },
    "淡粉": {
        "bg_top": "#fbe9f1", "bg_bottom": "#f6dbe8", "text": "#4d1f33",
        "card_bg": "#ffffff", "card_border": "#f0bfd6",
        "primary_top": "#e06ca0", "primary_bottom": "#c04884",
        "primary_hover": "#d45f95", "primary_press": "#a03a6c",
        "ghost_text": "#a03a6c", "ghost_border": "#e08fc0",
        "scroll_bg": "#f7e6ef", "scroll_handle": "#e0a8c8", "scroll_handle_hover": "#d08fb8",
        "answer_color": "#a02f64", "answer_bg": "#ffffff", "answer_border": "#e08fc0",
        "title": "#a03a6c", "section": "#a03a6c",
        "bar_assoc": ("#f0a8c8", "#c04884"), "bar_gift": ("#bfe9f5", "#6fc4e0"),
        "accent": "#c04884", "soft": "192,72,132", "danmaku": "#c04884",
    },
    "淡紫": {
        "bg_top": "#f1e9fb", "bg_bottom": "#e8dcf6", "text": "#3a1f4d",
        "card_bg": "#ffffff", "card_border": "#d6c0f0",
        "primary_top": "#906cd0", "primary_bottom": "#6f48b0",
        "primary_hover": "#8560c4", "primary_press": "#5a3a96",
        "ghost_text": "#5a3a8a", "ghost_border": "#a88fe0",
        "scroll_bg": "#ece6f7", "scroll_handle": "#c0a8e0", "scroll_handle_hover": "#a88fd0",
        "answer_color": "#4a2f7a", "answer_bg": "#ffffff", "answer_border": "#a88fe0",
        "title": "#5a3a8a", "section": "#5a3a8a",
        "bar_assoc": ("#c0a8ec", "#6f48b0"), "bar_gift": ("#bfe9f5", "#6fc4e0"),
        "accent": "#6f48b0", "soft": "111,72,176", "danmaku": "#6f48b0",
    },
    "直播黑": {
        "bg_top": "#0e1411", "bg_bottom": "#060a08", "text": "#e8f5ec",
        "card_bg": "#14201a", "card_border": "#244634",
        "primary_top": "#3fcf86", "primary_bottom": "#1f9e5e",
        "primary_hover": "#2fbf76", "primary_press": "#177a48",
        "ghost_text": "#8fe9bd", "ghost_border": "#2f9e6a",
        "scroll_bg": "#14201a", "scroll_handle": "#2f9e6a", "scroll_handle_hover": "#46c07a",
        "answer_color": "#7cffb0", "answer_bg": "#0b1a12", "answer_border": "#2f9e6a",
        "title": "#7cffb0", "section": "#5fe0a0",
        "bar_assoc": ("#3fcf86", "#1f9e5e"), "bar_gift": ("#4fb8e0", "#2f8ec0"),
        "accent": "#2fcf86", "soft": "47,207,134", "danmaku": "#7cffb0",
    },
    "直播蓝": {
        "bg_top": "#0a0f1a", "bg_bottom": "#05080f", "text": "#e6eefc",
        "card_bg": "#0f1726", "card_border": "#233a5c",
        "primary_top": "#3aa0ff", "primary_bottom": "#1f6fd0",
        "primary_hover": "#2f8fe6", "primary_press": "#1859a8",
        "ghost_text": "#8fd0ff", "ghost_border": "#2f6fd0",
        "scroll_bg": "#0f1726", "scroll_handle": "#2f6fd0", "scroll_handle_hover": "#4f8fe6",
        "answer_color": "#8fd0ff", "answer_bg": "#0a1422", "answer_border": "#2f6fd0",
        "title": "#8fd0ff", "section": "#5aa0e0",
        "bar_assoc": ("#5ab8ff", "#1f6fd0"), "bar_gift": ("#7fe0d8", "#3fb0a8"),
        "accent": "#3aa0ff", "soft": "58,160,255", "danmaku": "#8fd0ff",
    },
    "直播紫": {
        "bg_top": "#140a1a", "bg_bottom": "#0a050f", "text": "#f0e6fc",
        "card_bg": "#1c0f26", "card_border": "#3a235c",
        "primary_top": "#b06cff", "primary_bottom": "#7a3fd0",
        "primary_hover": "#9a5af0", "primary_press": "#5e2fa8",
        "ghost_text": "#d9a8ff", "ghost_border": "#7a3fd0",
        "scroll_bg": "#1c0f26", "scroll_handle": "#7a3fd0", "scroll_handle_hover": "#9a5af0",
        "answer_color": "#d9a8ff", "answer_bg": "#160a22", "answer_border": "#7a3fd0",
        "title": "#d9a8ff", "section": "#b06cff",
        "bar_assoc": ("#b06cff", "#7a3fd0"), "bar_gift": ("#ff8fd0", "#d05fa8"),
        "accent": "#b06cff", "soft": "176,108,255", "danmaku": "#d9a8ff",
    },
    "直播红": {
        "bg_top": "#1a0a0a", "bg_bottom": "#0f0505", "text": "#fce6e6",
        "card_bg": "#260f0f", "card_border": "#5c2323",
        "primary_top": "#ff6b5a", "primary_bottom": "#e03b2f",
        "primary_hover": "#f05545", "primary_press": "#b82a20",
        "ghost_text": "#ffb0a0", "ghost_border": "#e03b2f",
        "scroll_bg": "#260f0f", "scroll_handle": "#e03b2f", "scroll_handle_hover": "#f05545",
        "answer_color": "#ffb0a0", "answer_bg": "#220a0a", "answer_border": "#e03b2f",
        "title": "#ffb0a0", "section": "#ff8a7a",
        "bar_assoc": ("#ff7a5a", "#e03b2f"), "bar_gift": ("#ffd08f", "#e0a02f"),
        "accent": "#ff5a4a", "soft": "255,90,74", "danmaku": "#ffb0a0",
    },
    "直播绿": {
        "bg_top": "#06140a", "bg_bottom": "#030a05", "text": "#e6fff0",
        "card_bg": "#0a1f14", "card_border": "#235c3a",
        "primary_top": "#4cff9e", "primary_bottom": "#1fd07a",
        "primary_hover": "#3af090", "primary_press": "#17a862",
        "ghost_text": "#8effc0", "ghost_border": "#1fd07a",
        "scroll_bg": "#0a1f14", "scroll_handle": "#1fd07a", "scroll_handle_hover": "#3af090",
        "answer_color": "#8effc0", "answer_bg": "#04140a", "answer_border": "#1fd07a",
        "title": "#8effc0", "section": "#5affa6",
        "bar_assoc": ("#5affa6", "#1fd07a"), "bar_gift": ("#8fe0ff", "#3fb0e0"),
        "accent": "#4cff9e", "soft": "76,255,158", "danmaku": "#8effc0",
    },
}

DEFAULT_THEME = "默认绿"
THEME_LIB = {"默认绿": _default_palette()}
for _n, _over in _THEMES_RAW.items():
    _p = _default_palette()
    _p.update(_over)
    THEME_LIB[_n] = _p


def _build_qss(p):
    return f"""
QWidget {{
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {p['text']};
}}

QMainWindow, QWidget#root {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['bg_top']}, stop:1 {p['bg_bottom']});
}}

QLabel#title {{
    font-size: 20px;
    font-weight: bold;
    color: {p['title']};
}}

QLabel#section {{
    font-size: 15px;
    font-weight: bold;
    color: {p['section']};
    padding: 2px 0;
}}

QLabel#answer {{
    font-size: 22px;
    font-weight: bold;
    color: {p['answer_color']};
    background: {p['answer_bg']};
    border: 2px solid {p['answer_border']};
    border-radius: 8px;
    padding: 4px 12px;
}}

QLineEdit, QComboBox {{
    background: {p['card_bg']};
    border: 1px solid {p['card_border']};
    border-radius: 6px;
    padding: 5px 8px;
    color: {p['text']};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {p['primary_bottom']};
}}

QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['primary_top']}, stop:1 {p['primary_bottom']});
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: bold;
}}

QPushButton:hover {{ background: {p['primary_hover']}; }}
QPushButton:pressed {{ background: {p['primary_press']}; }}
QPushButton:disabled {{ background: {p['scroll_handle']}; color: {p['card_bg']}; }}

QPushButton#ghost {{
    background: {p['card_bg']};
    color: {p['ghost_text']};
    border: 1px solid {p['ghost_border']};
}}

QProgressBar {{
    border: 1px solid {p['card_border']};
    border-radius: 5px;
    background: {p['card_bg']};
    text-align: center;
    height: 16px;
}}

QProgressBar::chunk {{
    border-radius: 4px;
}}

QFrame#card {{
    background: {p['card_bg']};
    border: 1px solid {p['card_border']};
    border-radius: 10px;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: {p['scroll_bg']};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {p['scroll_handle']};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {p['scroll_handle_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def _build_bar(stops):
    s0, s1 = stops
    return (f"QProgressBar::chunk {{ background: qlineargradient("
            f"x1:0,y1:0,x2:1,y2:0, stop:0 {s0}, stop:1 {s1}); }}")


# 预生成每个主题的 QSS 与进度条样式
for _name, _p in THEME_LIB.items():
    _p["_qss"] = _build_qss(_p)
    _p["_assoc"] = _build_bar(_p["bar_assoc"])
    _p["_gift"] = _build_bar(_p["bar_gift"])

_CURRENT = DEFAULT_THEME
THEME = THEME_LIB[DEFAULT_THEME]["_qss"]            # 向后兼容别名
ASSOC_BAR_STYLE = THEME_LIB[DEFAULT_THEME]["_assoc"]
GIFT_BAR_STYLE = THEME_LIB[DEFAULT_THEME]["_gift"]


# ---------- 运行时切换 / 持久化 ----------
def get_names():
    return list(THEME_LIB.keys())


def current_name():
    return _CURRENT


def current():
    """返回当前主题的完整字典（含 accent / soft / danmaku，供雷达图与弹幕条取色）。"""
    return THEME_LIB[_CURRENT]


def apply_theme(app, name):
    """切换主题：刷新全局 QSS 与进度条样式，重设应用样式表，并持久化。"""
    global _CURRENT, THEME, ASSOC_BAR_STYLE, GIFT_BAR_STYLE
    if name not in THEME_LIB:
        name = DEFAULT_THEME
    p = THEME_LIB[name]
    _CURRENT = name
    THEME = p["_qss"]
    ASSOC_BAR_STYLE = p["_assoc"]
    GIFT_BAR_STYLE = p["_gift"]
    if app is not None:
        app.setStyleSheet(THEME)
    _persist(name)
    return name


def _persist_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme.json")


def _persist(name):
    try:
        with open(_persist_path(), "w", encoding="utf-8") as f:
            json.dump({"theme": name}, f, ensure_ascii=False)
    except Exception:
        pass


def load_persisted():
    try:
        with open(_persist_path(), encoding="utf-8") as f:
            d = json.load(f)
        n = d.get("theme")
        if n in THEME_LIB:
            return n
    except Exception:
        pass
    return DEFAULT_THEME
