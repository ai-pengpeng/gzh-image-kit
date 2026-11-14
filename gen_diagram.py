#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_diagram.py —— 公众号正文「自绘配图」通用生成器

用途：把文章里的流程 / 对比 / 清单 / 阶段做成干净好看的卡片式配图。
     对标公众号阅读体验：拉停留时长、给收藏理由、避免照搬他人配图。

四种版式：
  steps    竖排流程卡（序号圆 + 标题 + 说明）
  compare  左右对比卡（A vs B，常用于「能/不能」「坑/对策」）
  list     网格清单卡（N 列，常用于「几条结论」「优先级」）
  stages   横向阶段条（带箭头推进，常用于「阶段/演进」）

用法：
  python gen_diagram.py --mode steps --title "两步配好凭据" --out a.png \
    --data '{"items":[{"n":"1","t":"启用配置","d":"点生成，管理员扫码"}]}'

  python gen_diagram.py --mode compare --title "个人号边界" --out b.png \
    --data '{"left":{"t":"能做","items":["建草稿","上传素材"]},"right":{"t":"不能","items":["直接群发"],"bad":true}}'

  python gen_diagram.py --mode list --cols 2 --title "三条结论" --out c.png \
    --data '{"items":[{"t":"标题","d":"说明"}]}'

  python gen_diagram.py --mode stages --title "三层递进" --out d.png \
    --data '{"items":[{"t":"手","d":"执行"},{"t":"心","d":"判断"},{"t":"人","d":"责任"}]}'

通用参数：
  --style  mint(默认，薄荷蓝) / cream(暖奶油) / beige(米色) / amber / ocean
  --width  画布宽度，默认 1080（公众号正文宽度）
  --fs     字号总缩放，默认 1.6。手机阅读基准：正文 24px→38px，
           因为 1080px 的图在手机上被缩到约 375 CSS px 显示，
           24px 的字落屏只剩 8px，必须放大才看得清。

数据里颜色：right 卡可加 "bad":true 变成红色警示卡。
"""

import argparse
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

from fontkit import load as load_kit_font

# 字体路径由 fontkit.resolve_font 统一解析（可再分发中文字体优先，找不到即抛异常）。
# 见模块顶部 import 与 README「字体配置与许可」。

# 把文本切成「不可拆单元」：英文/数字整词一段，其余逐字符
TOKEN = re.compile(r"[A-Za-z0-9_.\-/]+|.")
# 中文标点不允许出现在行首
NO_LINE_START = "，。、；：？！）】》”’%·—…"

# 数字 + 量词：换行时不能被拆（"一分不扣" 不能断成 "一" / "分不扣"）
NUMS = "零一二三四五六七八九十百千万0123456789"
UNITS = "个分条种步类家款张年天次元块位项页人秒笔遍层"

# 页面左右留白固定，不随字号缩放，否则放大字号后文字区反而变窄
MARGIN = 48

# 字号总缩放。sp() 把所有间距/行高按同一系数等比放大，版面比例保持不变。
SCALE = 1.6

# 顶部副标 / 底部结论。底部结论对应「峰值-终值」的终值：一段体验的记忆由
# 最强那一点和结尾决定，中间过程几乎不计。图只给过程不给结论，读者滑完
# 就散了，记不住这张图要他干什么。
TITLE = SUB = FOOT = ""

# 画布宽（main 里按 --width 覆盖）。字号红线要按它现算，不能写死。
CANVAS_W = 1080

# 显著点：这一项用 accent 实心强调，其余保持白卡。None = 不强调。
# 一排完全同构的元素，读者一个都记不住（隔离效应），必须留一个落点。
HERO = None


def sp(v):
    """按字号缩放系数换算像素（间距、行高、胶囊高度都走这里）。"""
    return int(round(v * SCALE))


STYLES = {
    "mint": {
        "bg1": "#f5fbf9", "bg2": "#e4f4ef",
        "accent": "#1f9e8f", "accent_soft": "#e2f4f0",
        "title": "#12342d", "body": "#4d6b62",
        "card": "#ffffff", "border": "#d8eae4",
        "bad": "#d6604d", "bad_soft": "#fdeeeb", "bad_border": "#f5d3cc",
    },
    "cream": {
        "bg1": "#fffaf4", "bg2": "#fbeedd",
        "accent": "#d98450", "accent_soft": "#fbe9d8",
        "title": "#3b2416", "body": "#7a5b45",
        "card": "#ffffff", "border": "#ead9c6",
        "bad": "#c9503f", "bad_soft": "#fdeeeb", "bad_border": "#f2d2cb",
    },
    "beige": {
        "bg1": "#fbfaf7", "bg2": "#efece4",
        "accent": "#8a7a52", "accent_soft": "#efeade",
        "title": "#2a2721", "body": "#6b655a",
        "card": "#ffffff", "border": "#e0dbcd",
        "bad": "#b5543f", "bad_soft": "#fbeceb", "bad_border": "#eed3cd",
    },
    "amber": {  # 秋日暖光：温暖治愈、干货感（对应 themes.md amber）
        "bg1": "#fff6ec", "bg2": "#fce7d6",
        "accent": "#d97758", "accent_soft": "#fdeadd",
        "title": "#4a2e1d", "body": "#7a5b45",
        "card": "#ffffff", "border": "#f0d8c4",
        "bad": "#c0392b", "bad_soft": "#fdecec", "bad_border": "#f3cfca",
    },
    "ocean": {  # 深海静谧：理性专业、稳重（对应 themes.md ocean）
        "bg1": "#f0f5fa", "bg2": "#e3edf6",
        "accent": "#2f6fa8", "accent_soft": "#e3eef8",
        "title": "#1f3a52", "body": "#45617a",
        "card": "#ffffff", "border": "#cfdcec",
        "bad": "#c0392b", "bad_soft": "#fdecec", "bad_border": "#f0c9c4",
    },
}


# ---------------------------------------------------------------- 跟随封面取色
def _rgb2hsv(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    df = mx - mn
    if df == 0:
        h = 0.0
    elif mx == r:
        h = (60 * ((g - b) / df)) % 360
    elif mx == g:
        h = 60 * ((b - r) / df) + 120
    else:
        h = 60 * ((r - g) / df) + 240
    s = 0.0 if mx == 0 else df / mx
    return h, s, mx


def _hsv2rgb(h, s, v):
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    seg = int(h // 60) % 6
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x),
               (0, x, c), (x, 0, c), (c, 0, x)][seg]
    return (int(round((r + m) * 255)), int(round((g + m) * 255)), int(round((b + m) * 255)))


def _hex(c):
    return "#%02x%02x%02x" % c


def _mix(c, target, p):
    return tuple(int(round(c[i] + (target[i] - c[i]) * p)) for i in range(3))


def _rel_lum(c):
    def lin(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = _rel_lum(a), _rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def palette_from_cover(path, min_contrast=4.6):
    """从封面图取主色，派生整套配图色板。

    **为什么必须有这个函数**：2026-11-09 封面换成奶油底砖红插画后，正文配图
    仍旧是 ocean 深蓝，同一篇里两套色系；11-10 又犯一次。根因不是谁忘了，
    是「配图用哪个 style」这个参数靠人记——而人一定会忘。
    让工具自己读封面，这个参数就不存在了。

    取色逻辑：缩小 → 丢掉接近白/接近黑的像素 → 按色相饱和度分桶 → 取最大桶。
    插画里主体（人物、机器人）面积最大且最饱和，所以取到的就是品牌红。
    """
    img = Image.open(path).convert("RGB")
    w, h = img.size
    img = img.resize((96, max(8, int(96 * h / max(w, 1)))))
    px = list(img.getdata())

    buckets = {}
    bg_cand = {}
    for r, g, b in px:
        hh, ss, vv = _rgb2hsv(r, g, b)
        if ss >= 0.30 and 0.22 <= vv <= 0.94:       # 主体色：够饱和、不是白也不是黑
            key = (int(hh // 20), int(ss // 0.25))
            acc = buckets.setdefault(key, [0, 0, 0, 0])
            acc[0] += r; acc[1] += g; acc[2] += b; acc[3] += 1
        elif ss < 0.14 and vv > 0.88:               # 浅底：低饱和高亮
            key = (int(hh // 30), 0)
            acc = bg_cand.setdefault(key, [0, 0, 0, 0])
            acc[0] += r; acc[1] += g; acc[2] += b; acc[3] += 1

    if not buckets:
        return None
    mod = max(buckets.values(), key=lambda a: a[3])
    accent = tuple(int(round(mod[i] / mod[3])) for i in range(3))
    if bg_cand:
        bmod = max(bg_cand.values(), key=lambda a: a[3])
        paper = tuple(int(round(bmod[i] / bmod[3])) for i in range(3))
    else:
        paper = (252, 249, 246)
    paper = _mix(paper, (255, 255, 255), 0.35)

    ah, as_, av = _rgb2hsv(*accent)
    # accent 会当实心块用、上面压白字（--hero）。对白字压不住的亮色（土黄、橙）
    # 必须压暗到够——不压的话 --hero 那块就是白字糊在浅黄上，等于没有强调
    # （2026-11-10 m3t8v1 那张封面取到 (187,155,59)，对白字只有 2.67）。
    _guard = 0
    while contrast(accent, (255, 255, 255)) < 4.5 and av > 0.20 and _guard < 60:
        av -= 0.02
        accent = _hsv2rgb(ah, as_, av)
        _guard += 1
    title = _hsv2rgb(ah, min(0.42, as_ * 0.72), 0.20)     # 深调：保住色相，压到近黑
    body = _hsv2rgb(ah, min(0.34, as_ * 0.60), 0.40)
    soft = _mix(accent, (255, 255, 255), 0.86)
    border = _mix(accent, (255, 255, 255), 0.72)
    bg1 = _mix(paper, (255, 255, 255), 0.45)
    bg2 = _mix(paper, soft, 0.55)

    s = {
        "bg1": _hex(bg1), "bg2": _hex(bg2),
        "accent": _hex(accent), "accent_soft": _hex(soft),
        "title": _hex(title), "body": _hex(body),
        "card": "#ffffff", "border": _hex(border),
        "bad": "#c0392b", "bad_soft": "#fdecec", "bad_border": "#f0c9c4",
    }

    # 红线：正文小字必须 >=4.5:1，标题大字 >=3:1。取色是随机的，必须每次核。
    card_bg = hexrgb(s["card"])
    for name, need in (("title", 4.6), ("body", 4.6), ("accent", 3.0)):
        r = contrast(hexrgb(s[name]), card_bg)
        if r < need:
            return None                              # 不合格就退回 amber，不硬出图
    return s


def ft(size, bold=False):
    size = max(10, int(round(size * SCALE)))
    # 字号红线（判据见 docs/配图标准.md §3.1）：图片满屏显示时手机屏宽
    # 360 CSS px，任何文字不得低于 12 CSS px → 本画布下限 12×W/360。
    # 原来这里没有任何下限，mode_list 的小标签用到 19（=30px，手机仅 10px）。
    floor = int(round(12.0 * CANVAS_W / 360.0))
    assert size >= floor, (
        '字号 %dpx 低于红线 %dpx（画布 %dpx ≈ 手机 12 CSS px）。\n'
        '装不下就删字，不要缩字号。判据见 docs/配图标准.md §3.1'
        % (size, floor, CANVAS_W))
    # 字体与字重实例化统一由 fontkit.load 处理（2026-11-14 下沉）。
    # 原来这里自己写了一行 set_variation_by_name，其余三个脚本各漏一边，
    # 同一批图里的标题粗细就对不上了。
    return load_kit_font(size, bold=bold)


def wrap(d, text, font, max_w):
    """中英混排换行：英文整词不拆、中文标点不落行首、末行不留孤字。"""
    lines, cur = [], ""
    for tok in TOKEN.findall(str(text)):
        if cur and d.textlength(cur + tok, font=font) > max_w:
            if tok in NO_LINE_START:          # 标点跟随上一行，不另起
                cur += tok
                continue
            lines.append(cur)
            cur = tok
        else:
            cur += tok
    if cur:
        lines.append(cur)
    lines = lines or [""]
    # 末行只剩 1-2 个字时（"…所有权利" 掉成 "利"），从上一行匀一个单元下来。
    # 只匀「1-2 字尾行」这一种情况：试过放宽到「末行不到上一行三成宽」，
    # 结果把「大多数人」拆成「大多数 / 人从这档开始」，还把「、」匀到行首——
    # 为了让尾行好看一点而拆词，反而更难读，退回来了。
    while len(lines) > 1 and len(lines[-1]) < 3:
        prev = TOKEN.findall(lines[-2])
        if len(prev) <= 4 or prev[-1] in NO_LINE_START:
            break
        cand_prev, cand_last = "".join(prev[:-1]), prev[-1] + lines[-1]
        if d.textlength(cand_last, font=font) > max_w:
            break
        lines[-2], lines[-1] = cand_prev, cand_last
    # 数字和它后面的量词不能被换行拆开（"一分不扣" 掉成 "一 / 分不扣"）
    # 必须放在孤字均衡之后：否则孤字均衡会把量词重新拆开
    for _ in range(4):
        moved = False
        for i in range(len(lines) - 1):
            prv, nxt = lines[i], lines[i + 1]
            if prv and nxt and prv[-1] in NUMS and nxt[0] in UNITS:
                cand = prv[-1] + nxt
                if d.textlength(cand, font=font) <= max_w:
                    lines[i], lines[i + 1] = prv[:-1], cand
                    moved = True
        if not moved:
            break
    return lines


def paint_bg(img, s, W, H):
    """竖向柔和渐变，比纯色更有呼吸感。"""
    d = ImageDraw.Draw(img)
    c1, c2 = hexrgb(s["bg1"]), hexrgb(s["bg2"])
    for y in range(H):
        r = y / max(H - 1, 1)
        d.line([(0, y), (W, y)],
               fill=tuple(int(c1[i] + (c2[i] - c1[i]) * r) for i in range(3)))
    # 右上角柔光
    d.ellipse([W - 240, -120, W + 120, 240], fill=s["accent_soft"])


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def draw_title(d, W, y, title, sub, s):
    """主标题优先缩到单行（不折行、不把最后一个字甩到第二行），最小缩到 32 号。"""
    max_w = W - MARGIN * 2
    size = 46
    f = ft(size, True)
    while size > 32 and d.textlength(title, font=f) > max_w:
        size -= 2
        f = ft(size, True)
    lines = wrap(d, title, f, max_w)
    lh = int(round(size * SCALE * 1.32))
    for ln in lines:
        d.text((MARGIN, y), ln, font=f, fill=s["title"])
        y += lh
    y += sp(8)
    if sub:
        fs = ft(26)
        for ln in wrap(d, sub, fs, W - MARGIN * 2):
            d.text((MARGIN, y), ln, font=fs, fill=s["body"])
            y += sp(38)
        y += sp(12)
    # 强调短线
    d.rounded_rectangle([MARGIN, y, MARGIN + sp(60), y + sp(6)],
                        radius=3, fill=s["accent"])
    return y + sp(36)


def rounded_card(d, box, s, fill=None, outline=None, r=18, shadow=True):
    x0, y0, x1, y1 = box
    if shadow:
        d.rounded_rectangle([x0 + 3, y0 + 4, x1 + 3, y1 + 4], radius=r,
                            fill="#00000018")
    d.rounded_rectangle([x0, y0, x1, y1], radius=r,
                        fill=fill or s["card"],
                        outline=outline or s["border"], width=2)


# ---------------- 版式 1：steps ----------------
def mode_steps(d, W, y, data, s):
    """竖排流程卡：标题换行、高度按标题+描述动态计算，防止描述顶出卡片。"""
    items = data.get("items", [])
    left, right = MARGIN, W - MARGIN
    cw = right - left
    pad = sp(28)
    circle = sp(30)
    inner = cw - pad * 2 - (circle * 2 + sp(16))  # 减去序号圆与它右侧的间距
    f_t, f_d = ft(32, True), ft(26)
    lh_t, lh_d = sp(44), sp(38)
    for idx, it in enumerate(items):
        tl = wrap(d, it.get("t", ""), f_t, inner)
        dl = wrap(d, it.get("d", ""), f_d, inner)
        # 上边距 + 标题行 + 间距 + 描述行 + 下边距（含 descent 和圆角安全边距）
        h = max(sp(110), sp(26) + len(tl) * lh_t + sp(16) + len(dl) * lh_d + sp(44))
        rounded_card(d, [left, y, right, y + h], s)
        # 序号圆
        cx, cy = left + pad + circle, y + sp(34)
        d.ellipse([cx - circle, cy - circle, cx + circle, cy + circle], fill=s["accent"])
        n = str(it.get("n") or (idx + 1))
        fb = ft(26, True)
        d.text((cx - d.textlength(n, font=fb) / 2, cy - sp(18)), n, font=fb, fill="#ffffff")
        tx = left + pad + circle * 2 + sp(16)
        ty = y + sp(26)
        for ln in tl:
            d.text((tx, ty), ln, font=f_t, fill=s["title"])
            ty += lh_t
        dy = ty + sp(14)
        for ln in dl:
            d.text((tx, dy), ln, font=f_d, fill=s["body"])
            dy += lh_d
        y += h + sp(16)
    return y


# ---------------- 版式 2：compare ----------------
def mode_compare(d, W, y, data, s):
    """左右对比卡：先按实际内容计算每列所需高度，再统一画卡，避免文字被截。"""
    L, R = data.get("left", {}), data.get("right", {})
    gap, left, right = sp(22), MARGIN, W - MARGIN
    cw = (right - left - gap) // 2
    pad = sp(26)
    fi = ft(26)
    lh_i = sp(34)      # 条目行高，跟 fi 字号一起放大
    bullet_off = sp(32)  # 圆点 + 缩进

    def col_height(items):
        # 顶部标签区 + 每项实际行高 + 底部边距
        h = sp(92)
        for t in items:
            lines = wrap(d, t, fi, cw - pad * 2 - bullet_off)
            h += len(lines) * lh_i + sp(14)
        h += sp(30)
        return h

    li = L.get("items", []) or []
    ri = R.get("items", []) or []
    h = max(col_height(li), col_height(ri))

    def col(box, head, items, bad):
        rounded_card(d, box, s,
                     fill=s["bad_soft"] if bad else s["card"],
                     outline=s["bad_border"] if bad else s["border"])
        x0, y0, x1, _ = box
        accent = s["bad"] if bad else s["accent"]
        # 标签胶囊先按卡片内宽缩字，避免长标签顶出卡片右边
        hsize = 30
        fh = ft(hsize, True)
        while hsize > 20 and d.textlength(head, font=fh) + sp(40) > cw - sp(16):
            hsize -= 2
            fh = ft(hsize, True)
        hw = d.textlength(head, font=fh) + sp(40)
        # 两栏都用实心时重量一样，读者看不出哪栏是「该做的」——
        # 强调色只该给一边。bad 栏改成白底红字红框（空心），重量降一档，
        # 语义反而更清楚：实心 = 建议你做，空心 = 别做。
        d.rounded_rectangle([x0 + sp(20), y0 + sp(20), x0 + sp(20) + hw, y0 + sp(20) + sp(46)],
                            radius=sp(23),
                            fill="#ffffff" if bad else accent,
                            outline=accent if bad else None,
                            width=3 if bad else 1)
        d.text((x0 + sp(40), y0 + sp(28)), head, font=fh,
               fill=accent if bad else "#ffffff")
        iy = y0 + sp(92)
        for t in items:
            lines = wrap(d, t, fi, cw - pad * 2 - bullet_off)
            d.ellipse([x0 + pad, iy + sp(10), x0 + pad + sp(11), iy + sp(21)], fill=accent)
            for ln in lines:
                d.text((x0 + pad + sp(26), iy), ln, font=fi,
                       fill=s["body"] if not bad else "#8a4034")
                iy += lh_i
            iy += sp(14)
        return box[3]

    # 2026-11-09 修：原来只认 "t"，写成 "head" 会被静默忽略、退回 A/B，图上就看不出两栏各自代表什么。
    end1 = col([left, y, left + cw, y + h], L.get("t") or L.get("head") or "A", li, bool(L.get("bad")))
    end2 = col([left + cw + gap, y, right, y + h], R.get("t") or R.get("head") or "B", ri, bool(R.get("bad")))
    return max(end1, end2) + sp(16)


# ---------------- 版式 3：list ----------------
def mode_list(d, W, y, data, s, cols):
    """网格清单卡：标题与描述均做换行与溢出保护，确保内容不顶出卡片。"""
    items = data.get("items", [])
    gap, left, right = sp(20), MARGIN, W - MARGIN
    cw = (right - left - gap * (cols - 1)) // cols
    pad = sp(18)
    f_t, f_d = ft(30, True), ft(24)
    lh_t, lh_d = sp(40), sp(34)   # 标题/描述行高
    gap_td = sp(18)               # 标题与描述间距
    tag_h = sp(48)                # 小标签占用的高度（含边距）
    rows = (len(items) + cols - 1) // cols

    # 先量每行高度
    heights = []
    for r in range(rows):
        rh = 0
        for c in range(cols):
            idx = r * cols + c
            if idx >= len(items):
                continue
            it = items[idx]
            max_w = cw - pad * 2
            top_extra = tag_h if it.get("k") else 0
            tl = wrap(d, it.get("t", ""), f_t, max_w)
            dl = wrap(d, it.get("d", ""), f_d, max_w)
            # 卡片高度 = 上边距 + 标签占用 + 标题行高 + 间距 + 描述行高 + 下边距 + 圆角安全边距
            h = pad + top_extra + len(tl) * lh_t + gap_td + len(dl) * lh_d + pad + sp(22)
            rh = max(rh, h)
        heights.append(max(rh, sp(110)))

    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            if idx >= len(items):
                continue
            it = items[idx]
            is_hero = (HERO is not None and idx == HERO)
            x0 = left + c * (cw + gap)
            rounded_card(d, [x0, y, x0 + cw, y + heights[r]], s,
                         fill=(s["accent"] if is_hero else None))
            bad = it.get("bad")
            if is_hero:
                # 白底 + accent 字。原来用 #ffffff33 半透明白底配白字，
                # 出图后「合计」两个字几乎看不见——强调块上再叠浅色等于没叠。
                accent, tag_bg, fg_t, fg_d = s["accent"], "#ffffff", "#ffffff", "#ffffff"
            else:
                accent = s["bad"] if bad else s["accent"]
                tag_bg, fg_t, fg_d = s["accent_soft"], s["title"], s["body"]
            fh2 = ft(24, True)
            top_extra = 0
            if it.get("k"):
                kw = d.textlength(it["k"], font=fh2) + sp(26)
                d.rounded_rectangle([x0 + sp(20), y + sp(20),
                                     x0 + sp(20) + kw, y + sp(20) + sp(30)],
                                    radius=sp(15), fill=tag_bg)
                d.text((x0 + sp(33), y + sp(23)), it["k"], font=fh2, fill=accent)
                top_extra = tag_h
            max_w = cw - pad * 2
            # 标题换行
            tl = wrap(d, it.get("t", ""), f_t, max_w)
            ty = y + pad + top_extra
            for ln in tl:
                d.text((x0 + pad, ty), ln, font=f_t, fill=fg_t)
                ty += lh_t
            # 描述换行
            dy = ty + gap_td
            for ln in wrap(d, it.get("d", ""), f_d, max_w):
                d.text((x0 + pad, dy), ln, font=f_d, fill=fg_d)
                dy += lh_d
        y += heights[r] + gap
    return y


# ---------------- 版式 4：stages ----------------
def mode_stages(d, W, y, data, s):
    """横向阶段条：标题换行、描述起始随标题行数动态下移，避免溢出。"""
    items = data.get("items", [])
    n = max(len(items), 1)
    gap, left, right = sp(18), MARGIN, W - MARGIN
    aw = sp(26)  # 箭头区
    cw = (right - left - gap * (n - 1) - aw * (n - 1)) // n
    pad = sp(24)
    f_t, f_d, f_n = ft(30, True), ft(24), ft(24, True)
    lh_t, lh_d = sp(40), sp(34)

    # 先量每阶段高度
    hs = []
    for it in items:
        max_w = cw - pad * 2
        tl = wrap(d, it.get("t", ""), f_t, max_w)
        dl = wrap(d, it.get("d", ""), f_d, max_w)
        # 上边距 + 序号区 + 标题行 + 间距 + 描述行 + 下边距 + 圆角安全边距
        h = pad + sp(50) + len(tl) * lh_t + sp(16) + len(dl) * lh_d + pad + sp(24)
        hs.append(max(sp(150), h))
    h = max(hs)

    for i, it in enumerate(items):
        x0 = left + i * (cw + gap + aw)
        rounded_card(d, [x0, y, x0 + cw, y + h], s)
        d.rounded_rectangle([x0 + pad, y + sp(20), x0 + pad + sp(40), y + sp(20) + sp(40)],
                            radius=sp(20), fill=s["accent"])
        num = str(i + 1)
        d.text((x0 + pad + sp(20) - d.textlength(num, font=f_n) / 2, y + sp(28)),
               num, font=f_n, fill="#ffffff")
        max_w = cw - pad * 2
        tl = wrap(d, it.get("t", ""), f_t, max_w)
        ty = y + sp(74)
        for ln in tl:
            d.text((x0 + pad, ty), ln, font=f_t, fill=s["title"])
            ty += lh_t
        dy = ty + sp(16)
        for ln in wrap(d, it.get("d", ""), f_d, max_w):
            d.text((x0 + pad, dy), ln, font=f_d, fill=s["body"])
            dy += lh_d
        if i < n - 1:
            ax = x0 + cw + 4
            ay = y + h // 2
            d.line([(ax, ay), (ax + aw - sp(10), ay)], fill=s["accent"], width=3)
            d.polygon([(ax + aw - sp(10), ay - sp(6)), (ax + aw - sp(2), ay),
                       (ax + aw - sp(10), ay + sp(6))], fill=s["accent"])
    return y + h + sp(16)


# ---------------- 版式 5：ladder ----------------
def mode_ladder(d, W, y, data, s, hero=None):
    """阶梯卡：竖排，块宽逐级收窄表达「量级/重量」，hero 项单独上色。

    为什么不画成四张等高卡片：心理学上的**隔离效应（Von Restorff）**——
    一排完全同构的元素，读者一个都记不住。四条一样的白卡横平竖直地堆着，
    看完的感受是「不错」，但复述不出任何一条。阶梯先把「重/轻」变成
    可见的形状（具体性效应：形状比形容词好加工），再挑一项上色给出落点。

    hero：想让人记住的那一项的下标。只允许一个，多一个等于没有。
    """
    items = data.get("items", [])
    n = max(len(items), 1)
    left = MARGIN
    full = W - MARGIN - left
    gap = sp(13)
    pad = sp(19)

    widths = []
    for i, it in enumerate(items):
        if it.get("w") is not None:
            widths.append(float(it["w"]))
        else:
            # 递减幅度 0.30：再狠一点最窄那块就装不下说明，会挤成三行（试过 0.46）
            widths.append(1.0 - 0.30 * (i / max(n - 1, 1)))
    if hero is not None and 0 <= hero < n:
        widths[hero] = max(widths[hero], 0.94)

    # 先量高度（同一套 draw 行为，measure 与真画一致）
    hs, layouts = [], []
    for i, it in enumerate(items):
        is_hero = (hero is not None and i == hero)
        bw = int(full * widths[i])
        f_t = ft(36 if is_hero else 30, True)
        f_d = ft(24)
        f_k = ft(24, True)
        lh_t, lh_d = sp(46 if is_hero else 38), sp(31)
        # 标签宽按实际字宽算。写死 62 时「中」这种单字标签后面会空出一大截，
        # 主名跟着往里缩，看起来整块没对齐（第一版出图就是这样）。
        label_w = int(d.textlength(it["k"], font=f_k) + sp(20)) if it.get("k") else 0
        max_w = bw - pad * 2 - label_w
        tl = wrap(d, it.get("t", ""), f_t, max_w)
        # 说明用悬挂缩进：从块左边起、不跟着主名缩进。可用宽多出约 100px，
        # 一行能放下的字就多了一截，断行少一次，图也短一截（第一版这里多断一行）。
        dl = wrap(d, it.get("d", ""), f_d, bw - pad * 2) if it.get("d") else []
        h = pad + len(tl) * lh_t + (sp(8) + len(dl) * lh_d if dl else 0) + pad
        hs.append(max(h, sp(86)))
        layouts.append((tl, dl, bw, f_t, f_d, f_k, lh_t, lh_d, label_w, is_hero))

    for i, it in enumerate(items):
        tl, dl, bw, f_t, f_d, f_k, lh_t, lh_d, label_w, is_hero = layouts[i]
        x0, x1 = left, left + bw
        if is_hero:
            d.rounded_rectangle([x0, y, x1, y + hs[i]], radius=sp(18), fill=s["accent"])
            fg_t = fg_d = fg_k = "#ffffff"
        else:
            rounded_card(d, [x0, y, x1, y + hs[i]], s)
            fg_t, fg_d = s["title"], s["body"]
            fg_k = s["accent"]
        if it.get("k"):
            d.text((x0 + pad, y + pad + (lh_t - sp(30)) // 2),
                   it["k"], font=f_k, fill=fg_k)
        tx = x0 + pad + label_w
        ty = y + pad
        for ln in tl:
            d.text((tx, ty), ln, font=f_t, fill=fg_t)
            ty += lh_t
        if dl:
            ty += sp(8)
            for ln in dl:
                d.text((x0 + pad, ty), ln, font=f_d, fill=fg_d)
                ty += lh_d
        y += hs[i] + gap
    return y


# ---------------- 主流程：先量高度，再真正画 ----------------
def draw_foot(d, W, y, s):
    """底部一句结论（终值）。居中、加粗、accent 色——全图最该被记住的一句。

    不加这一句的后果很具体：阶梯图四档讲完就结束了，读者记住了「有四档」，
    但不知道「我该用哪档」。峰已经给了（hero 高亮），尾却没给。
    """
    y += sp(18)
    f = ft(30, True)
    lines = wrap(d, FOOT, f, W - MARGIN * 2 - sp(20))
    lh = sp(46)
    for ln in lines:
        d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=s["accent"])
        y += lh
    return y + sp(6)


def measure(mode, W, data, s, cols, hero=None):
    probe = Image.new("RGB", (W, 200))
    d = ImageDraw.Draw(probe)
    y = draw_title(d, W, sp(44), TITLE, SUB, s)
    if mode == "steps":
        y = mode_steps(d, W, y, data, s)
    elif mode == "compare":
        y = mode_compare(d, W, y, data, s)
    elif mode == "list":
        y = mode_list(d, W, y, data, s, cols)
    elif mode == "ladder":
        y = mode_ladder(d, W, y, data, s, hero)
    else:
        y = mode_stages(d, W, y, data, s)
    if FOOT:
        y = draw_foot(d, W, y, s)
    return y + sp(24)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=["steps", "compare", "list", "stages", "ladder"])
    ap.add_argument("--title", required=True)
    ap.add_argument("--sub", default="")
    ap.add_argument("--foot", default="",
                    help="底部一句结论。图上只给过程不给结论，读者滑完就散了；"
                         "这一句是「终值」，填住阶梯收窄后右下角的空白。")
    ap.add_argument("--data", required=True, help="JSON 字符串")
    ap.add_argument("--cols", type=int, default=2, help="list 版式列数")
    ap.add_argument("--style", default="mint", choices=list(STYLES))
    ap.add_argument("--match-cover", default="",
                    help="封面图路径。传了就从封面取主色派生色板，覆盖 --style。"
                         "**出正文配图时默认就该传**，配图配色跟随封面是硬规则，别再靠人记。")
    ap.add_argument("--hero", type=int, default=None,
                    help="要让人记住的那一项下标（0 起）。一排同构元素里必须有一个显著点，"
                         "否则读者看完说不出讲了什么。只许一个。")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--fs", type=float, default=1.6,
                    help="字号总缩放，默认 1.6（手机阅读基准）；设 1.0 回到旧版小字")
    ap.add_argument("--out", default="diagram.png")
    ap.add_argument("--channel", default="",
                    help="渠道标识；传 greenbook/贴图/小绿书 会拒绝生成（贴图禁用代码卡片图）")
    a = ap.parse_args()

    # ⚠️ 贴图 / 小绿书（greenbook）禁用本脚本（代码卡片图）。
    # 判断与文案的唯一真身在 channels.py —— 别名表和拒绝话术写两处必有一处漏。
    from channels import reject_greenbook
    if reject_greenbook(a.channel, "gen_diagram（代码卡片图生成器）"):
        sys.exit(2)

    global TITLE, SUB, SCALE, FOOT, CANVAS_W, HERO
    TITLE, SUB, SCALE, FOOT = a.title, a.sub, max(0.6, min(2.2, a.fs)), a.foot
    CANVAS_W, HERO = a.width, a.hero
    s, used = STYLES[a.style], a.style
    if a.match_cover:
        if not os.path.exists(a.match_cover):
            print("❌ 找不到封面图：%s" % a.match_cover)
            sys.exit(2)
        got = palette_from_cover(a.match_cover)
        if got:
            s, used = got, "跟随封面 %s" % os.path.basename(a.match_cover)
        else:
            print("⚠️ 封面取色不合格（对比度过不了线），退回 --style %s" % a.style)
    W = a.width
    data = json.loads(a.data)

    H = measure(a.mode, W, data, s, a.cols, a.hero)
    img = Image.new("RGB", (W, H), s["bg1"])
    d = ImageDraw.Draw(img)
    paint_bg(img, s, W, H)
    d2 = ImageDraw.Draw(img, "RGBA")
    # 复刻 measure 的绘制（ImageDraw 行为一致）
    y = draw_title(d2, W, sp(44), TITLE, SUB, s)
    y_title_end = y
    if a.mode == "steps":
        y = mode_steps(d2, W, y, data, s)
    elif a.mode == "compare":
        y = mode_compare(d2, W, y, data, s)
    elif a.mode == "list":
        y = mode_list(d2, W, y, data, s, a.cols)
    elif a.mode == "ladder":
        y = mode_ladder(d2, W, y, data, s, a.hero)
    else:
        y = mode_stages(d2, W, y, data, s)
    # 守卫：正文区画完后 y 必须往下走。若仍等于标题底，说明某个版式函数的
    # 返回值没被接住 —— 结论句会直接压在卡片上（2026-11-11 就是这样出的图）。
    if y is None or y <= y_title_end:
        raise SystemExit(
            "❌ 版式 %s 没有推进 y（%r <= 标题底 %r）：返回值丢了，"
            "结论句会画到卡片上，拒绝出图" % (a.mode, y, y_title_end)
        )
    if FOOT:
        draw_foot(d2, W, y, s)

    # 输出目录不存在时自建（2026-11-14 修）。
    # 原来要等到这张图画完才在 save 阶段抛 FileNotFoundError——渲染全跑完了才挂，
    # 是最伤人的一种失败。gen_cards / annotate_shot / render_riso 都会自建，这里补齐。
    _out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(_out_dir, exist_ok=True)
    img.save(a.out, quality=94)
    print(f"✅ {a.out}  {W}×{H}  mode={a.mode} style={used} fs={SCALE}")


if __name__ == "__main__":
    main()
