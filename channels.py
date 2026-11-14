#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""channels.py —— 渠道口径的唯一真身。

为什么单独一个文件
------------------
「这个渠道能不能用代码渲染图」这条判断，原本散在 gen_diagram.py 里写了一份，
gen_cards.py 里没有——于是同一个用户按直觉「gen_cards 出贴图 → check --channel
greenbook 验收」，必然白跑一轮（产出 20–47KB，被体积闸判 FAIL）。

渠道别名同理：用户在命令行敲的可能是 `greenbook`、`贴图`、`小绿书`，
三个词指的是同一个渠道。别名表写两处，就一定会有一处漏更新。
"""
from __future__ import annotations

# greenbook（小绿书）渠道：贴图必须是生图模型出的插画，
# 代码渲染的卡片图在这个渠道是**规格不允许**，不是「不够好看」。
GREENBOOK_ALIASES = {"greenbook", "贴图", "小绿书", "tie"}

GREENBOOK_REJECT_HINT = (
    "   该渠道的贴图必须是生图模型出的 AI 插画："
    "奶油暖白 #FAF7F2 + 薄荷绿 #4ECDC4，3:4 竖版。\n"
    "   代码渲染的卡片图体积通常只有 20–60KB，会被 check.py 的体积闸判 FAIL。\n"
    "   本脚本产出的图适用于：公众号长文正文配图 / 图卡，不适用于该渠道。"
)


def is_greenbook(channel: str) -> bool:
    """渠道标识是否指向 greenbook（含中文别名）。空串不算。"""
    return bool(channel) and channel.strip().lower() in GREENBOOK_ALIASES


def reject_greenbook(channel: str, tool: str) -> bool:
    """渠道是 greenbook 时打印拒绝说明并返回 True，调用方据此 sys.exit(2)。

    返回布尔值而不是直接退出，是为了让调用方决定退出码，也便于测试。
    """
    if not is_greenbook(channel):
        return False
    print("❌ %s 不能在 greenbook（贴图 / 小绿书）渠道使用。" % tool)
    print(GREENBOOK_REJECT_HINT)
    print("   如果你要的是长文配图，去掉 --channel 参数即可。")
    return True
