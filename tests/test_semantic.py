# -*- coding: utf-8 -*-
"""semantic 单测：模型缺失优雅降级 + 10 维数学（假嵌入 monkeypatch 打穿）。

真 bge 模型本机需联网/大文件，按「外部依赖无法实测就用假实现打穿」的约定，
用 monkeypatch 注入确定性嵌入，验证维度基向量点积 → 0~100 的映射正确。
"""

import os

os.environ["FORCE_FALLBACK"] = "1"

import semantic


def setup_function(_):
    semantic._DIM_LOADED = False
    semantic._DIM_BASIS = []
    semantic._PROFILE_CACHE.clear()


def test_profile_none_without_model():
    semantic.ensure_dims()
    assert semantic._DIM_LOADED is False
    assert semantic.profile("苹果") is None


def test_dim_math_with_fake_model(monkeypatch):
    # 10 个互相正交的单位基向量 e0..e9（维度=10）
    dim = 10
    semantic._DIM_BASIS = [
        [1.0 if j == i else 0.0 for j in range(dim)] for i in range(dim)
    ]
    semantic._DIM_LOADED = True

    def fake_encode(text):
        idx = ord(text[-1]) - ord("0")
        v = [0.0] * dim
        if 0 <= idx < dim:
            v[idx] = 1.0
        return v

    monkeypatch.setattr(semantic, "_encode", fake_encode)

    prof = semantic.profile("词5")
    assert prof is not None
    assert len(prof) == 10
    assert prof[5] == 100.0
    assert prof[0] == 0.0
    assert max(prof) == 100.0
    # 非匹配维度应为 0（max(0, 点积)）
    assert all(p == 0.0 for i, p in enumerate(prof) if i != 5)

    # 缓存命中
    again = semantic.profile("词5")
    assert again is prof


def test_dim_names_count():
    names = semantic.dim_names()
    assert len(names) == 10
    assert "食物" in names and "生活" in names
