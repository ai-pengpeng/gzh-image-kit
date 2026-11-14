# -*- coding: utf-8 -*-
"""封面正文分行的回归测试。

守的是 2026-11-14 外部审美复评指出的最后一处硬伤：封面左栏 35 字的正文，
CSS 自动折行后末行只剩「间。」两个字，挂在封面第一眼阅读动线的末尾。

更值得记的是**这条防线本来就存在，只是没铺到这条管线上**：
`cover_head()` 早就有「先缩字号、再平衡折行」的防孤字逻辑，正文却直接交给
浏览器折。所以这里测的不只是「会不会出孤行」，还有「分行器有没有真的接管」。

跑：`python -m pytest tests/ -q`
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

# 那份出过事故的原文（封面第 1 张的 caption）
COVER = "同一件事，贴图版从第一张就得把结论端出来——滑动的人不给你铺垫的时间。"


def _lines(text: str, width: float = 11.2) -> list[str]:
    return rr.cap_lines(text, width).split("<br>")


def _em(s: str) -> float:
    return sum(rr._em_width(c) for c in s)


def test_cover_caption_has_no_orphan_line():
    """事故原文：末行不许是「间。」这种只剩一两个字。"""
    lines = _lines(COVER)
    assert len(lines) >= 2, "这段话不该只有一行，测试前提失效"
    assert _em(lines[-1]) >= 3.0, "末行太短（孤行）：%r" % lines[-1]


def test_no_line_starts_with_closing_punctuation():
    """标点顶行首是中文排版硬禁则。"""
    for text in (COVER, "先看结论，再往下翻；别急着跳。", "第一点、第二点：都要写清。"):
        for line in _lines(text):
            assert line and line[0] not in rr._NO_LINE_START, (
                "行首出现了禁则字符：%r（全文 %r）" % (line, text))


def test_no_line_ends_with_opening_punctuation():
    """开引号/开括号不许挂行尾——下一行开头会是光秃秃的引号。"""
    text = "他说「这事儿得先看清楚再动手」，然后就走了，留下我一个人在那儿琢磨"
    for line in _lines(text):
        assert line[-1] not in rr._NO_LINE_END, \
            "行尾出现了开引号：%r" % line


def test_short_text_passes_through():
    assert rr.cap_lines("短句。", 11.2) == "短句。"
    assert rr.cap_lines("", 11.2) == ""
    assert rr.cap_lines(None, 11.2) == ""


def test_no_punctuation_long_run_still_breaks():
    """没有标点的长句必须照样断行，不能因为「找不到体面的断点」就整段塞一行。"""
    text = "这是一句没有任何标点而且非常长的中文句子用来测试分行器在无标点情况下是否会把末行压到两个字"
    lines = _lines(text)
    assert len(lines) >= 3, "长句没被断开：%r" % lines
    assert all(_em(l) <= 12.2 for l in lines), "某一行明显超宽：%r" % [round(_em(l), 1) for l in lines]


def test_mixed_latin_lines_stay_within_budget():
    """混了西文的行按「全角当量」算也不许明显超宽（按字数算会算错这一条）。"""
    text = "谷歌 11 月 12 日发的 Gemini 4 Hydrogen，AI Studio 与 API 的免费档都能调。"
    for line in _lines(text):
        # 允许禁则造成的 1 个字溢出，再多就是估算错了
        assert _em(line) <= 12.2, "行超宽：%r → %.1f" % (line, _em(line))


def test_renderer_actually_uses_the_splitter():
    """测「有没有接上」：封面模板必须走 cap_lines，而不是把正文丢回 CSS 折行。

    这条是防止「修好了函数但没接到管线」——本次事故的成因就是保护函数存在、
    却没被调用，所以只测函数行为是不够的。
    """
    card = {"v": "r1", "tag": "标签", "head": "标题", "hero": "竖排巨字",
            "caption": COVER}
    html = rr.r1_cover(card)
    assert "<br>" in html, "封面正文没有走分行器（HTML 里没有 <br>）"
    body = html.split('class="r1-cap">')[1].split("</div>")[0]
    assert _em(body.split("<br>")[-1]) >= 3.0, "接上了，但末行仍是孤行"
