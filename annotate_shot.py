#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
annotate_shot.py —— 截图人工标注（红框 / 箭头 / 圆圈 / 文字 / 序号）

为什么要这个：公众号配图里，官方图谁都能拿，带标注的实拍截图才是「我真的用过」。
            标注要克制、手写感强，别做成电商促销图。

用法：
  python annotate_shot.py --in shot.png --out out.png --spec spec.json
  python annotate_shot.py --in shot.png --out out.png \
      --items '[{"type":"rect","box":[120,260,500,320]},
                {"type":"arrow","frm":[600,300],"to":[510,300]},
                {"type":"label","text":"这行是关键","at":[610,290]}]'

标注类型：
  rect    {"box":[x1,y1,x2,y2], "color":"#E23B2E", "width":6, "radius":8}
  ellipse {"box":[x1,y1,x2,y2], "color":..., "width":...}
  arrow   {"frm":[x,y], "to":[x,y], "color":..., "width":..., "head":24}
  label   {"text":"...", "at":[x,y], "size":34, "color":..., "bg":"white"|"red"|null, "anchor":"la"}
  number  {"n":1, "at":[x,y], "r":26, "color":...}

坐标：默认图片像素；写成 "10%" 这种百分数字符串则按图片宽/高换算。
线宽与字号不填时按图片尺寸自适应。
"""
from __future__ import annotations

import argparse
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

from fontkit import resolve_font

RED = "#E23B2E"


def load_font(size: int):
    # 字体由 fontkit 统一解析；找不到可用字体时它会抛异常，绝不静默退回默认字体。
    return ImageFont.truetype(resolve_font(True), size)


def _num(v, total, base):
    """'10%' -> 像素；数字原样返回。base 用于按比例的自适应量。"""
    if isinstance(v, str) and v.endswith("%"):
        return base * float(v[:-1]) / 100.0
    return float(v)


def _pt(seq, w, h):
    return (_num(seq[0], w, w), _num(seq[1], h, h))


def _box(seq, w, h):
    return (_num(seq[0], w, w), _num(seq[1], h, h),
            _num(seq[2], w, w), _num(seq[3], h, h))


def draw_arrow(d: ImageDraw.ImageDraw, p1, p2, color, width, head):
    d.line([p1, p2], fill=color, width=int(width))
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    left = (p2[0] - head * math.cos(ang - math.pi / 7),
            p2[1] - head * math.sin(ang - math.pi / 7))
    right = (p2[0] - head * math.cos(ang + math.pi / 7),
             p2[1] - head * math.sin(ang + math.pi / 7))
    d.polygon([p2, left, right], fill=color)


def annotate(src: str, dst: str, items: list, scale: float = 1.0) -> str:
    im = Image.open(src).convert("RGB")
    w, h = im.size
    if scale and abs(scale - 1.0) > 1e-6:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = im.size

    d = ImageDraw.Draw(im)
    base = min(w, h)
    default_width = max(3, round(base / 170))
    default_size = max(18, round(base / 26))
    default_head = max(12, round(base / 34))

    for it in items:
        t = (it.get("type") or "").lower()
        color = it.get("color") or RED
        lw = it.get("width") or default_width

        if t == "rect":
            x1, y1, x2, y2 = _box(it["box"], w, h)
            r = it.get("radius")
            if r:
                d.rounded_rectangle([x1, y1, x2, y2], radius=r, outline=color, width=int(lw))
            else:
                d.rectangle([x1, y1, x2, y2], outline=color, width=int(lw))

        elif t == "ellipse":
            x1, y1, x2, y2 = _box(it["box"], w, h)
            d.ellipse([x1, y1, x2, y2], outline=color, width=int(lw))

        elif t == "arrow":
            p1 = _pt(it["frm"], w, h)
            p2 = _pt(it["to"], w, h)
            draw_arrow(d, p1, p2, color, lw, it.get("head") or default_head)

        elif t == "label":
            size = int(it.get("size") or default_size)
            font = load_font(size)
            text = it["text"]
            x, y = _pt(it["at"], w, h)
            anchor = it.get("anchor") or "la"
            bg = it.get("bg")
            if bg:
                pad = max(6, size // 3)
                tb = d.textbbox((x, y), text, font=font, anchor=anchor,
                                stroke_width=0)
                d.rounded_rectangle([tb[0] - pad, tb[1] - pad, tb[2] + pad, tb[3] + pad],
                                    radius=pad, fill=("#FFFFFF" if bg == "white" else color))
                fg = color if bg == "white" else "#FFFFFF"
                d.text((x, y), text, font=font, fill=fg, anchor=anchor)
            else:
                d.text((x, y), text, font=font, fill=color, anchor=anchor,
                       stroke_width=max(2, size // 12), stroke_fill="#FFFFFF")

        elif t == "number":
            r = float(it.get("r") or base / 28)
            cx, cy = _pt(it["at"], w, h)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
            font = load_font(int(r * 1.25))
            d.text((cx, cy), str(it["n"]), font=font, fill="#FFFFFF", anchor="mm")

        else:
            raise ValueError(f"未知标注类型: {t}")

    out_dir = os.path.dirname(os.path.abspath(dst))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    im.save(dst, quality=95)
    return dst


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--spec", help="标注 JSON 文件路径")
    ap.add_argument("--items", help="标注 JSON 字符串（与 --spec 二选一）")
    ap.add_argument("--scale", type=float, default=1.0, help="先缩放再标注，如 0.6")
    a = ap.parse_args()

    if a.spec:
        with open(a.spec, encoding="utf-8") as f:
            items = json.load(f)
    elif a.items:
        items = json.loads(a.items)
    else:
        raise SystemExit("需要 --spec 或 --items")
    if isinstance(items, dict):
        items = items.get("items", [])

    p = annotate(a.src, a.dst, items, a.scale)
    print(p)


if __name__ == "__main__":
    main()
