@echo off
chcp 65001 >nul
echo [1/2] 安装打包依赖（PyQt6 + sentence-transformers + PyInstaller）...
python -m pip install PyQt6 sentence-transformers pyinstaller

echo [2/2] PyInstaller 打包（单文件 / 无控制台 / 内含 bge 语义模型，永不降级余弦）...
taskkill /f /im 语义猜词.exe >nul 2>&1
python -m PyInstaller --onefile --windowed --name 语义猜词 --noconfirm --add-data "models/bge;models/bge" main.py
echo 完成：dist\语义猜词.exe （约 330MB+，含 bge 模型，离线可用）
pause
