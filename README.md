# 抖音直播间 AI 语义猜词 · 桌面应用

PyQt6 桌面应用（替代原网页版），彻底修复原网页版「关联度榜缩水 / 不滚动 / 每秒闪烁」三大 bug：
榜单用原生 `QScrollArea` / `ScoreBoard` 渲染，原生滚动天然可用、增量刷新不闪、不丢位移。

语义打分用 **bge 本地模型**（`BAAI/bge-small-zh-v1.5`），离线可跑，**永不降级字符余弦**。
玩法为「直播猜词」：主播在抖音直播，观众发两字中文弹幕参与；系统实时把观众发的词和目标词做
**语义相似度**计算（0~100），单人猜中即本局结束，直播模式自动续局。

> 本项目是在开源项目 `guessword`（Java+React 网页版）思路上的桌面化重写与增强，详见文末「对照 guessword」。

## 目录结构

```
语义猜词/
├── main.py              # 入口：加载模型、双窗口、持久化主题
├── engine.py            # 游戏主逻辑（回合制 / 礼物 / 段位 / 积分榜 / 接近度阈值）
├── wordbank.py          # 词库
├── worker.py            # 后台评分线程
├── semantic.py          # 10 维语义画像（bge 重做 guessword 的 VectorService 维度分解）
├── theme.py             # 多主题系统（11 套，含直播高对比）
├── radar.py             # 语义雷达图（目标词水印 + 猜词描边）
├── danmaku.py           # 直播弹幕条
├── widgets.py           # 关联度榜 / 积分榜控件
├── ui_main.py           # 主播台窗口
├── ui_live.py           # 直播大屏窗口（OBS 窗口捕获用）
├── tests/               # 引擎单测 + 双窗口冒烟 + 雷达绘制回归
├── build.bat            # 一键打包成 exe
├── download_model.py    # 首次运行前下载 bge 模型
└── requirements.txt
```

## 环境要求

- Python 3.11+
- PyQt6、torch、sentence-transformers
- 语义模型 `BAAI/bge-small-zh-v1.5`（**不随仓库提供**，见下方「获取模型」）

## 快速开始（源码运行）

```bash
pip install -r requirements.txt
python download_model.py     # 首次：下载 bge 模型到 models/bge
python main.py
```

默认即 **bge 语义打分**（`models/bge/` 已就位时加载即用，离线可跑），**永不降级字符余弦**。
`FORCE_FALLBACK=1` 仅用于引擎单测（免模型跑 `tests/`），生产 / 打包后从不启用。

## 获取模型（二选一）

**方式 A（推荐，脚本自动下载）**

```bash
python download_model.py
# 国内网络慢可先设镜像：
#   HF_ENDPOINT=https://hf-mirror.com python download_model.py
```

**方式 B（手动放置）**
从 HuggingFace 下载 [`BAAI/bge-small-zh-v1.5`](https://huggingface.co/BAAI/bge-small-zh-v1.5)，
把整个目录内容解压 / 复制到本项目的 `models/bge/` 下（需含 `model.safetensors`、`config.json`、
`tokenizer.json` 等）。

> 模型约 95MB，`models/` 目录已在 `.gitignore` 中排除，不会进入 git 仓库。

## 双窗口

- **主播台**（MainWindow）：出题（手动 / 随机抽题）、猜词、礼物、直播开关、重置、关联度榜、积分榜、主题切换。
- **直播大屏**（LiveWindow）：可全屏 / 无边框，供 OBS「窗口捕获」推流；谜底遮罩直到猜中揭晓；
  猜中全屏恭喜 + 自动续局（直播模式）。

## 关键不变量（铁律）

1. 礼物词生成剔除当前谜底，礼物永不亮出 / 猜中答案。
2. 礼物关联度封顶 90，绝不触发猜中 / 获胜。
3. 礼物积分计入送礼者本人昵称（无后缀）。
4. 礼物词与手动词同待遇进入关联度榜（带 gift 标记）。
5. 关联度榜截断保留全部真实猜词，礼物词只补满到 60；真实词只增不减。
6. 关联度始终显示一位小数。
7. 关联度榜显示全部条目，禁止硬截断，且必须可滚动。
8. 积分榜前三名固定（金色高亮），第 4 名起人数多时自动循环滚屏。
9. 任何刷新 / 重渲染都不得重建整个列表导致闪烁 / 位移跳变。

## 对照 guessword 移植 / 增强的特性

在 guessword（Java+React 网页版）思路基础上，桌面版额外补齐了以下能力，
均保持「永不降级 bge」与上文 9 条铁律不变：

- **10 维语义画像（雷达图）**：`semantic.py` 用 bge 把 guessword 的 `VectorService` 维度分解思路重做
  （10 维锚点词→维度基向量→点积）。直播大屏右侧雷达图以「目标词淡色水印 + 最新猜词亮色描边」展示语义方向。
- **多主题 + 直播高对比主题**：`theme.py` 提供 11 套主题（6 浅色 + 5 直播高对比 黑/蓝/紫/红/绿），
  主播台与大屏均可实时切换并持久化（`theme.json`），榜单进度条随主题变色，专为 OBS 窗口捕获优化。
- **接近度横幅**：关联度越过 `PROX_NEAR=55` 弹「💡 接近了！」、越过 `PROX_VERYNEAR=75` 弹「🔥 就差一点！」
  （阈值在 `engine.py`，按 bge 分值标定）。
- **弹幕条**：每次提交的猜词在直播大屏顶部飞过，强化「弹幕猜词」直播感。
- **拼音渐进提示（可选）**：安装 `pypinyin` 后，按 `elapsed` 比例渐进揭示谜底拼音首字母
  （40% 揭示首字、70% 揭示全部；完整提示解锁后收回），未装则整体降级为空。

## 测试

```bash
pip install pytest
pytest tests/test_engine.py tests/test_semantic.py tests/test_engine_extra.py -q
# 双窗口构造/刷新/榜单/猜中/续局（需 PyQt6，offscreen 无显示器也可）
QT_QPA_PLATFORM=offscreen FORCE_FALLBACK=1 python tests/smoke_ui.py
# 雷达绘制回归（验证 QPainter 不抛类型异常，需 PyQt6）
QT_QPA_PLATFORM=offscreen FORCE_FALLBACK=1 python tests/smoke_radar.py
```

## 打包（生成 exe）

```bash
build.bat
```

生成 `dist\语义猜词.exe`（单文件、双击即运行、无需装 Python）：
- **内含 bge 语义模型**（`models/bge/` 由 `build.bat` 打进 exe），离线可用、语义打分、**永不降级余弦**。
- 体积约 330MB（torch + 模型权重），属正常。
- 轻量版（不含模型、走字符余弦，约 36MB）不推荐；如确需，给 `PyInstaller` 加 `--exclude-module` torch 等
  并设 `FORCE_FALLBACK=1`（与「永不余弦」需求相悖，仅作记录）。

## 许可证

本项目暂未包含 LICENSE 文件。若计划开源，建议补充许可证（如 MIT）后再发布。
