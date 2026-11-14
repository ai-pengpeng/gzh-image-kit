# -*- coding: utf-8 -*-
"""必填字段体检（check_required）的回归测试。

守的是 2026-11-14 第三轮外部实测撞出来的那个崩溃：
`r1` 少写 `tag`，渲染时直接 `KeyError: 'tag'` —— 一屏英文栈、指向源码行号，
用户只看到「程序崩了」，看不出「第几张、缺哪个字段、这款版式为什么非要它」。

三条规则，都是「不测就会退回去」的：

1. 必填字段缺了必须在**渲染前**报出来，不能等到渲染时才崩。
2. 缺几个就报几个，一次报全 —— 不让用户改一处、跑一次、再崩一次。
3. `tag` 只对「表里打 ✓」的版式必填（`r5`–`r8` 本来就不显示题签，不能要求它）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("render_riso", ROOT / "render_riso.py")
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)


def test_missing_tag_on_cover_is_caught():
    """r1 是封面，题签是版式的一部分；缺了原来会 KeyError 崩掉。"""
    errs = rr.check_required([{"v": "r1", "head": "标题", "hero": "巨字"}])
    assert errs, "缺 tag 居然没报错——这条就是原来的崩溃点"
    assert "tag" in errs[0] and "r1" in errs[0], errs


def test_every_missing_field_is_reported_at_once():
    """一次报全，不是改一个跑一次。"""
    errs = rr.check_required([
        {"v": "r1", "hero": "缺 tag 和 head"},
        {"v": "r2", "tag": "有", "head": "缺 hero"},
        {"v": "r9", "tag": "有", "hero": "缺 head"},
    ])
    assert len(errs) == 3, "应该三张各一条，实际：%r" % (errs,)
    joined = "\n".join(errs)
    for need in ("tag", "head", "hero"):
        assert need in joined, "缺的字段没报全：\n" + joined


def test_layouts_that_do_not_show_tag_do_not_require_it():
    """r5–r8 表里 tag 是 ·，就不能拿 tag 卡人——卡了就是把「不显示」当成「必填」。"""
    for v in ("r5", "r6", "r7", "r8"):
        errs = rr.check_required([{"v": v, "head": "标题", "hero": "巨字"}])
        assert errs == [], "%s 本来就不显示 tag，却报错了：%r" % (v, errs)


def test_default_variant_follows_rotation():
    """不写 v 时第一张就是 r1，所以一样要 tag；第 5 张是 r5，不该要。"""
    assert rr.check_required([{"head": "a", "hero": "b"}]), "第一张不写 v 就是 r1，必须要求 tag"
    cards = [{"head": "a", "hero": "b"} for _ in range(5)]
    errs = rr.check_required(cards)
    assert len(errs) == 4, "前四张是 r1–r4（都要 tag），第五张是 r5（不要）：%r" % (errs,)


def test_blank_string_counts_as_missing():
    """`"tag": ""` 和没写是一回事——渲染出来那行是空的。"""
    errs = rr.check_required([{"v": "r1", "tag": "   ", "head": "标题", "hero": "巨字"}])
    assert errs, "空白 tag 被当成有值了"


def test_good_spec_is_completely_clean():
    ok = [{"v": "r1", "tag": "题签", "head": "标题", "hero": "巨字"}]
    assert rr.check_required(ok) == []


if __name__ == "__main__":
    raise SystemExit("用 pytest 跑：python -m pytest tests/ -q")
