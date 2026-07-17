# -*- coding: utf-8 -*-
"""下载 bge 语义模型到 models/bge（首次运行项目前执行一次）。

模型：BAAI/bge-small-zh-v1.5（约 95MB）。
需联网；默认走 HuggingFace 官方源，如需国内镜像可先设环境变量：
    HF_ENDPOINT=https://hf-mirror.com
"""

import os
import sys

from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "bge")


def main():
    os.makedirs(TARGET, exist_ok=True)
    print(f"下载模型 {MODEL_NAME} -> {TARGET}")
    model = SentenceTransformer(MODEL_NAME)
    model.save(TARGET)
    print("完成。可运行：python main.py")


if __name__ == "__main__":
    sys.exit(main())
