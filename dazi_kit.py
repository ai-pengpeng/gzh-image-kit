# -*- coding: utf-8 -*-
"""大字报版式助手 —— 贴图文字卡的唯一共享实现（3:4 1080×1440，照 风格档案/dazi.md）。

**这是唯一维护点。** 2026-11-10 从 `内容/20261110-五篇-v2/_dazi_kit.py` 提升到这里：
原先它躺在某一期目录里，下一期就重写一个，字号红线跟着丢——标准落地做不好就是这个机制。
新的贴图渲染脚本请 `sys.path` 指到本目录 `from dazi_kit import *`，不要再复制一份。

版式特征：黑巨字撑版心、荧光绿重音(面积<=10%)、语义色唯一(黑常态/绿正向/蓝断点/红错误)、
一页一句话、副标不重复巨字用字、底部留白<=120px、只用品字形(雅黑一族)。
巨字按宽反算循环降号 + assert；字少塌版时放大字号垂直居中，不塞回文字。

**字号红线**：所有字号必须 ≥ MIN_FONT_PX，f() 里有 assert 兜底。
判据与换算公式见 `本仓库/docs/配图标准.md` §3.1。
"""
import os
from PIL import Image, ImageDraw

REF = r"<expert-refs>"
FONT_R = r'C:\Windows\Fonts\msyh.ttc'
FONT_B = r'C:\Windows\Fonts\msyhbd.ttc'

W, H = 1080, 1440
MX = 72                      # 版心边距
CW = W - 2 * MX              # 版心宽 936
GIANT_RATIO = 0.86           # 巨字最宽行占版心比例

# 字号红线（2026-11-10 定，见 本仓库/docs/配图标准.md §3.1）
# 1080 逻辑画布 → 手机 360 CSS px，缩放 3 倍；36px 图片字 = 12 CSS px = 可读下限。
# 旧版这里页脚 26 / 眉 28 / 付句 29，换算到手机只有 8.7~9.7px，读起来费劲。


def min_font_px(canvas_w=None):
    """可读下限随画布走，不是一个固定数。

    图片px = 12 CSS px × 画布宽 / 360（360 = 保守屏宽，见配图标准 §3.1）。
    1080→36 / 1024→34 / 900→30 / 2160→72。
    早先这里写死 36，换画布就失效——2026-11-10 改成按 W 反算。
    """
    w = W if canvas_w is None else canvas_w
    return max(12, int(round(12.0 * w / 360.0)))


MIN_FONT_PX = min_font_px()

# ---- 色板（语义唯一） ----
# **对比度红线（2026-11-10 定）**：任何**文字色**对 BG 必须 ≥4.5:1（小字）
# 或 ≥3:1（巨字/大字号）。字号够大但对比度不够，读起来一样费劲——
# 实测旧灰 (150,155,162) 只有 2.68:1，那是「字明明变大了还是发虚」的真正原因。
# 判据与实测表见 本仓库/docs/配图标准.md §3.4；_verify_palette() 在导入时自检。
BG = (250, 250, 251)
INK = (18, 18, 20)           # 黑 = 常态                    17.9:1 ✅
GREEN = (0, 164, 108)        # 荧光绿 = 巨字重音（大字号专用）3.09:1 ✅ 大字
GREEN_D = (0, 124, 78)       # 深绿 = 品牌位/小字            5.04:1 ✅（原 0,138,94 仅 4.20）
CAPS = (222, 245, 234)       # 淡绿胶囊底色（底色，非文字）
BLUE = (26, 92, 180)         # 蓝 = 断点                     6.23:1 ✅
RED = (210, 58, 48)          # 红 = 错误                     4.59:1 ✅
GRAY = (105, 111, 119)       # 次级小字                      4.86:1 ✅（原 150,155,162 仅 2.68）
LINE_G = (226, 229, 233)

# 只准用于装饰（分隔线、图标、色块），**不许当文字色**
DECO_ONLY = {
    (150, 155, 162): '旧灰 GRAY_LIGHT，对 BG 仅 2.68:1，小字发虚',
    (222, 245, 234): '淡绿胶囊底色 CAPS，1.10:1',
    (226, 229, 233): '分隔线 LINE_G，1.18:1',
}


def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG 相对对比度，返回 1~21。"""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _verify_palette():
    """导入即自检：小字色必须 ≥4.5:1，巨字重音色 ≥3:1。不合格直接出不了图。"""
    small = {'INK': INK, 'GREEN_D': GREEN_D, 'GRAY': GRAY, 'BLUE': BLUE, 'RED': RED}
    bad = []
    for name, rgb in small.items():
        r = contrast(rgb, BG)
        if r < 4.5:
            bad.append('%s 只有 %.2f:1（小字需 >=4.5:1）' % (name, r))
    big = contrast(GREEN, BG)
    if big < 3.0:
        bad.append('GREEN 只有 %.2f:1（大字重音需 >=3:1）' % big)
    assert not bad, ('色板不达对比度红线：' + '；'.join(bad) +
                     '\n判据见 本仓库/docs/配图标准.md §3.4')


_verify_palette()


def _guard_text_color(fill):
    """拦住「拿浅色当文字色」——这是字号变大后仍然发虚的头号原因。"""
    if isinstance(fill, (tuple, list)):
        key = tuple(fill[:3])
        if key in DECO_ONLY:
            raise AssertionError(
                '这个颜色不能当文字色：%s。\n小字请用 INK / GRAY / GREEN_D（均 >=4.5:1），'
                '判据见 本仓库/docs/配图标准.md §3.4' % DECO_ONLY[key])
    return fill

BRAND = '澎澎 ｜ AI × 职场'

_font_cache = {}


def f(size, bold=True):
    """取字体。字号低于红线直接报错——让标准在运行时生效，不靠人记。

    红线按当前 W 现算，不引用模块级常量：画布一改（比如换 2160 出图），
    常量就过期了，而这里永远是对的。
    """
    floor = min_font_px(W)
    assert size >= floor, (
        '字号 %dpx 低于红线 %dpx（%d 画布 ≈ 手机 12 CSS px）。\n'
        '装不下就删字，不要缩字号。判据见 本仓库/docs/配图标准.md §3.1' % (size, floor, W))
    from PIL import ImageFont
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_B if bold else FONT_R, size)
    return _font_cache[key]


def metr(size, bold=True):
    ft = f(size, bold)
    return ft.getmetrics()


def tw(draw, text, size, bold=True):
    return draw.textlength(text, font=f(size, bold))


def put_bl(draw, text, size, fill, x, y_base, bold=True):
    """y_base 为基线(底部)锚。fill 会过对比度守卫，浅色当文字色直接报错。"""
    _guard_text_color(fill)
    ft = f(size, bold)
    w = draw.textlength(text, font=ft)
    # 画出版心 = 右侧出血被手机边裁掉。之前没人拦，靠出图后目检才发现（2026-11-10 补）。
    assert x >= MX * 0.25 and x + w <= W - MX * 0.25, (
        '文字出界：左 %.0f / 右 %.0f，安全区 %.0f~%.0f（内容 %r）。\n'
        '拆成两行或删字，不要缩字号。' % (x, x + w, MX * 0.25, W - MX * 0.25, text[:16]))
    asc, _ = ft.getmetrics()
    draw.text((x, y_base - asc), text, font=ft, fill=fill)
    return x + w


def put_c(draw, text, size, fill, cx, y_base, bold=True):
    put_bl(draw, text, size, fill, cx - tw(draw, text, size, bold) / 2.0, y_base, bold)


def giant_fit(draw, lines, start=132, floor=64, ratio=GIANT_RATIO, bold=True):
    """巨字整体一个字号：最宽行 <= ratio*版心，循环降号。返回 (size, widest)。"""
    max_w = CW * ratio
    size = start
    while size > floor:
        widest = max(tw(draw, t, size, bold) for t in lines)
        if widest <= max_w:
            return size, widest
        size -= 2
    widest = max(tw(draw, t, size, bold) for t in lines)
    assert widest <= CW, 'giant_fit: 最宽行仍超版心 %s' % lines
    return size, widest


def new_page():
    img = Image.new('RGB', (W, H), BG)
    return img, ImageDraw.Draw(img)


def eyebrow(draw, text, fill=GREEN_D, y=78, size=36, bold=False):
    put_bl(draw, text, size, fill, MX, y, bold=bold)


FOOT_BASELINE = H - 68      # 页脚基线：文字底距画布底 ≈60px ≈ 手机 20 CSS px
                            # 原来 baseline 1396，文字底距底仅 36px（手机 12px），贴着边看很紧


def foot(draw, pageno, brand=BRAND):
    """底部：左品牌深绿 / 右页码灰。内容区底界 CONTENT_BOTTOM=1296。"""
    put_bl(draw, brand, 36, GREEN_D, MX, FOOT_BASELINE, bold=False)
    pw = tw(draw, pageno, 36, True)
    put_bl(draw, pageno, 36, GRAY, W - MX - pw, FOOT_BASELINE)


def draw_check(d, cx, cy, r=30, color=GREEN, w=8):
    d.line([(cx - r * 0.6, cy), (cx - r * 0.1, cy + r * 0.5)], fill=color, width=w)
    d.line([(cx - r * 0.1, cy + r * 0.5), (cx + r * 0.75, cy - r * 0.6)], fill=color, width=w)


def draw_cross(d, cx, cy, r=30, color=RED, w=8):
    d.line([(cx - r * 0.6, cy - r * 0.6), (cx + r * 0.6, cy + r * 0.6)], fill=color, width=w)
    d.line([(cx + r * 0.6, cy - r * 0.6), (cx - r * 0.6, cy + r * 0.6)], fill=color, width=w)


def capsule(draw, cx, cy, text, size=36, pad_x=30, pad_y=14, fill=CAPS, fg=GREEN_D):
    """淡绿胶囊，返回 (x0,y0,x1,y1)。cy 为垂直中心。"""
    asc, desc = f(size, False).getmetrics()
    twd = tw(draw, text, size, False)
    bw, bh = twd + 2 * pad_x, asc + desc + 2 * pad_y
    x0, y0 = cx - bw / 2.0, cy - bh / 2.0
    draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=bh / 2.0, fill=fill)
    # 胶囊文字压在淡绿底上，比白底更难读，单独核一次「fg 对胶囊底」
    assert contrast(fg, fill) >= 4.5, (
        '胶囊文字对胶囊底只有 %.2f:1，需 >=4.5:1（fg=%s fill=%s）'
        % (contrast(fg, fill), fg, fill))
    _guard_text_color(fg)
    draw.text((x0 + pad_x, y0 + pad_y), text, font=f(size, False), fill=fg)
    return (x0, y0, x0 + bw, y0 + bh)


def giant_page(pageno, eyebrow_text, giant_lines, sub_lines=(), note=None,
               note_capsule=False, giant_color=INK, accent_last=None):
    """标准巨字页：眉(顶部) + 巨字(垂直居中) + 副标 + 底部注 + 页脚。
    accent_last: 把巨字最后一行的指定子串用 GREEN 画（传入 (line_index, start, end)）。
    返回 PIL.Image。"""
    img, d = new_page()
    eyebrow(d, eyebrow_text)

    gsize, _ = giant_fit(d, giant_lines)
    glh = int(gsize * 1.24)
    ssize = 40
    slh = 66
    subs_h = len(sub_lines) * slh if sub_lines else 0
    note_h = (96 if note_capsule else 64) if note else 0
    block_h = len(giant_lines) * glh + 40 + subs_h + (36 + note_h if note else 0)
    top = 150 + max(0, (1146 - 150 - block_h) // 2)   # 内容区 150..1296

    y = top
    for i, t in enumerate(giant_lines):
        yb = y + int(gsize * 0.92)
        if accent_last is not None and i == accent_last[0]:
            pre, seg = t[:accent_last[1]], t[accent_last[1]:accent_last[2]]
            x = MX + (CW - tw(d, t, gsize)) / 2.0
            x = put_bl(d, pre, gsize, giant_color, x, yb)
            x = put_bl(d, seg, gsize, GREEN, x, yb)
            put_bl(d, t[accent_last[2]:], gsize, giant_color, x, yb)
        else:
            put_c(d, t, gsize, giant_color, W // 2, yb)
        y += glh
    y += 40
    for t in sub_lines:
        put_c(d, t, ssize, GRAY, W // 2, y + ssize, bold=False)
        y += slh
    if note:
        y += 36
        if note_capsule:
            capsule(d, W // 2, y + 30, note)
        else:
            put_c(d, note, 36, INK, W // 2, y + 36, bold=False)
    foot(d, pageno)
    return img


def pairs_page(pageno, eyebrow_text, head, pairs, note=None):
    """对号入座页：head 小标题 + 逐行 (标记, 主句, 付句)。
    标记: 'ok' | 'no' | 'q'（绿勾/红叉/灰问）或 ('num', n)。"""
    img, d = new_page()
    eyebrow(d, eyebrow_text)

    hsize, hwid = giant_fit(d, [head], start=72, floor=44, ratio=0.80)
    rows = []
    for mk, main, sub in pairs:
        rows.append((mk, main, sub))
    msize = 45
    row_h = 164
    block_h = int(hsize * 0.92) + 56 + len(rows) * row_h + (36 + 64 if note else 0)
    top = 150 + max(0, (1146 - 150 - block_h) // 2)
    put_c(d, head, hsize, INK, W // 2, top + int(hsize * 0.92))
    y = top + int(hsize * 0.92) + 56
    for mk, main, sub in rows:
        cy = y + row_h // 2 - 14
        cx = MX + 34
        if mk == 'ok':
            d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=CAPS)
            draw_check(d, cx, cy, r=24, color=GREEN_D, w=7)
        elif mk == 'no':
            d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=(251, 233, 231))
            draw_cross(d, cx, cy, r=24, color=RED, w=7)
        elif isinstance(mk, tuple) and mk[0] == 'num':
            d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=INK)
            put_c(d, str(mk[1]), 40, (255, 255, 255), cx, cy + 14)
        else:
            d.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=(236, 238, 241))
            put_c(d, '?', 40, GRAY, cx, cy + 14)
        tx = MX + 108
        put_bl(d, main, msize, INK, tx, cy + 6)
        if sub:
            put_bl(d, sub, 36, GRAY, tx, cy + 60, bold=False)
        y += row_h
    if note:
        y += 30
        capsule(d, W // 2, min(y + 34, 1250), note)
    foot(d, pageno)
    return img
