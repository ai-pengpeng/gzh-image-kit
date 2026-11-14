#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_cards.py —— 长文 → 公众号贴图（竖版卡组）自动拆卡器

为什么有这个工具：贴图是公众号推荐重构期的独立流量入口（搜一搜独立分类、
看一看 2-3 屏一遇、不占群发配额），且推荐权重里「收藏」最高——干货清单类
最容易持续爆。长文负责信任转化，贴图负责让陌生人停下来，一篇长文拆一组
贴图，同一份素材吃两条流量。

爆款法则（2026-11 拆解《普通人如何做出爆款公众号贴图》85页 + 外部实测）：
  1. 首图 3 秒定生死：大字报型，主标题 ≤8 字，一眼看清讲什么
  2. 完读率靠节奏：一卡一个要点，页码 X/N 促滑到底，卡数 5-10 张
  3. 收藏权重最高：清单/步骤浓缩成卡，每行 ≤15 字，好抄好存
  4. 系统会 OCR 卡面文字参与搜索打标签：关键词要出现在卡面上
  5. 结尾轻引导（禁诱导）：合集入口 + 「评论区聊聊」，不喊加微
  6. 视觉统一：全组一套配色、一种字体（微软雅黑），固定模板反复用

规格：900 x 1200（3:4 竖版）PNG，与主流贴图规格同源。

拆卡规则（draft.md → 卡组）：
  H1          → 首卡大字报（--cover-title 可覆盖，默认自动取短）
  每个 H2     → 一张要点卡（列表项优先，无列表取段落首句）
  「澎澎说」引用块 → 一张金句卡（收藏向素材，淡底色）
  「核实说明」引用块 → 跳过（贴图不放核实细节，长文里看）
  代码块      → 跳过，卡面提示「完整代码见文末长文」
  正文「合集「X」」→ 提进尾卡
  尾卡        → 号名 + 合集 pill + 引导语 + 话题标签

用法：
  python gen_cards.py --in draft.md --out cards/ --tag "AI实操" --account "AI澎"
  可选：--cover-title "8字内主标题" --style ocean|mint --keywords "元宝,微信AI"

依赖：pillow；中文字体 C:/Windows/Fonts/msyhbd.ttc
"""
import argparse
import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

W, H = 900, 1200
PAD = 64

# ---- ocean 五色（与 render_f.py / gen_cover.py ocean 严格同源）----
ACCENT = (47, 111, 168)     # #2f6fa8
TITLE = (31, 58, 82)        # #1f3a52
BODY = (69, 97, 122)        # #45617a
MUTED = (92, 113, 135)      # #5c7187  注释/小字。原 #8aa0b6 对白底仅 2.65:1，
                            # 和贴图那边 GRAY 2.68:1 是同一种病：字够大但太浅，看着发虚。
                            # 现 4.95:1（小字需 >=4.5:1，判据见 本仓库/docs/配图标准.md §3.4）
BORDER = (207, 220, 236)    # #cfdcec
SOFT = (227, 238, 248)      # #e3eef8
PAPER = (252, 253, 255)

# mint 备选（沿用 gen_cover mint）
MINT = dict(bg_top=(226, 244, 237), accent=(29, 158, 117),
            title=(28, 32, 30), body=(70, 78, 74),
            soft=(214, 238, 227), border=(190, 222, 206), muted=(120, 150, 138))
OCEAN = dict(bg_top=(240, 246, 252), accent=ACCENT, title=TITLE, body=BODY,
             soft=SOFT, border=BORDER, muted=MUTED)
STYLES = {"ocean": OCEAN, "mint": MINT}

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
]

# 字号红线（2026-11-10 定，见 本仓库/docs/配图标准.md §3.1）
# 判据：图片满屏显示时，手机屏宽 360 CSS px；任何文字不得低于 12 CSS px。
# 本脚本画布 900 宽 → 12 × 900 / 360 = 30px 为下限。
MIN_FONT_PX = round(12 * W / 360)


def font(size: int):
    assert size >= MIN_FONT_PX, (
        '字号 %dpx 低于红线 %dpx（画布 %dpx 宽 ≈ 手机 12 CSS px）。\n'
        '装不下就删字，不要缩字号。判据见 本仓库/docs/配图标准.md §3.1'
        % (size, MIN_FONT_PX, W))
    for c in FONT_CANDIDATES:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _tokens(text: str):
    """切成不可分割单元：连续 ASCII 词（Claude、5.2、30%）算一个，中文和标点逐字。

    不加这层的话「Claude Fable 5.2」会被劈成「Clau / de Fable 5.2」——
    本号全是 AI 题材，模型名一断，读者第一眼就卡住（2026-11-10 出图时发现）。
    """
    out, buf = [], ""
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch in "-._%+&/'@#"):
            buf += ch
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
    if buf:
        out.append(buf)
    return out


# 中文排版禁则：这些字符不许出现在行首（避头点）。出现就「悬挂」到上一行末尾。
_NO_LINE_START = "，。、；：？！）】》」』’”…·,.;:?!)]}"


def _hang_punct(lines):
    """行首标点挂到上一行尾。允许上一行轻微超宽——标点视觉重量轻，
    比「，」孤零零顶在行首好看得多（2026-11-10 出图发现）。

    也处理「整行只剩一个句号」：挂上去后该行变空，直接删掉，不留空行。
    """
    i = 1
    while i < len(lines):
        while lines[i] and lines[i][0] in _NO_LINE_START:
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
        if not lines[i]:
            lines.pop(i)
            continue
        i += 1
    return lines


def wrap(text: str, fnt, max_w: int, max_lines: int = 2):
    """按词断行（英文不劈行）；超 max_lines 截断加省略号。返回行列表。"""
    lines, cur = [], ""

    def flush():
        if cur:
            lines.append(cur)

    for tk in _tokens(text):
        if tk == "\n":
            flush()
            cur = ""
            if len(lines) >= max_lines:
                break
            continue
        if d.textlength(cur + tk, font=fnt) <= max_w:
            cur += tk
            continue
        # 放不下
        if cur.strip():
            lines.append(cur)
            cur = "" if tk.isspace() else tk
        else:
            # 单个词本身就超宽（超长英文/URL）→ 只能按字符硬切
            cur = ""
            for ch in tk:
                if d.textlength(cur + ch, font=fnt) <= max_w:
                    cur += ch
                else:
                    lines.append(cur)
                    cur = ch
                    if len(lines) >= max_lines:
                        break
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if lines and len(lines) >= max_lines:
        # 截断检查：还有没画出来的内容就补省略号
        consumed = sum(len(x) for x in lines)
        if consumed < len(text.rstrip()):
            last = lines[-1]
            while last and d.textlength(last + "…", font=fnt) > max_w:
                last = last[:-1]
            lines[-1] = last + "…"
    return [x for x in _hang_punct([x for x in lines if x])]


# 全局 draw 供 wrap 测量（在 render 时赋值）
d = None


# ---------------------------------------------------------------- 解析 markdown
def parse(md: str):
    """draft.md → dict(title, sections[{title, points[]}], quote, collection, accounts_note)"""
    lines = md.replace("\r\n", "\n").split("\n")
    title = ""
    sections = []          # {title, points}
    quotes = []            # 引用块（澎澎说）
    collection = ""
    i = 0
    cur_sec = None
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1
            i += 1
            continue
        m = re.match(r"^#\s+(.*)$", s)
        if m and not title:
            title = m.group(1).strip()
            i += 1
            continue
        m = re.match(r"^##\s+(.*)$", s)
        if m:
            cur_sec = {"title": m.group(1).strip(), "points": []}
            sections.append(cur_sec)
            i += 1
            continue
        if s.startswith(">"):
            text = s.lstrip("> ").strip()
            if text:
                if "数据出处" in text or "核实说明" in text or "核实" in text[:6]:
                    pass  # 跳过核实块
                elif "澎澎说" in text or "💡" in text:
                    pass  # 栏目标题行，不是金句本体
                else:
                    quotes.append(re.sub(r"\*\*", "", text))
            i += 1
            continue
        if s == "---":
            i += 1
            continue
        m = re.search(r"合集「\*?\*?([^」*]+)", s)
        if m and not collection:
            collection = m.group(1).strip()
        if s.startswith("|"):  # 表格行 → 每行成一条要点
            if cur_sec is not None:
                cells = [c.strip() for c in s.strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    cur_sec["points"].append("｜".join(x for x in cells if x))
            i += 1
            continue
        m = re.match(r"^[-*+]\s+(.*)$", s)
        if m:
            if cur_sec is not None:
                cur_sec["points"].append(re.sub(r"[`]", "", re.sub(r"\*\*", "", m.group(1).strip())))
            i += 1
            continue
        if cur_sec is not None:
            # 段落 → 按句切，前两句各成一条（保留长文判断句的味道）
            plain = re.sub(r"`", "", re.sub(r"\*\*", "", s))
            for sent in re.split(r"(?<=[。！？])", plain):
                sent = sent.strip()
                # 以冒号收尾的是半句（后面还有内容），单独成本条只会切碎
                if len(sent) >= 10 and not sent.endswith(("：", ":")):
                    cur_sec["points"].append(sent)
                if len(cur_sec["points"]) >= 6:
                    break
        i += 1
    return dict(title=title, sections=sections, quotes=quotes, collection=collection)


def shorten_cover_title(title: str, max_len: int = 8) -> str:
    """自动取短标题：优先截数字短语，否则硬截 max_len 字。"""
    t = re.sub(r"[？?！!。：:，,]", "", title)
    m = re.search(r"[\d＠@元宝\w]+[^，。]{0,6}", t)
    t = t[:max_len] if len(t) > max_len else t
    return t


# ---------------------------------------------------------------- 绘制
def new_card(st):
    img = Image.new("RGB", (W, H), PAPER)
    dr = ImageDraw.Draw(img)
    # 顶部渐变薄条 + 底部 accent 线，建立系列识别
    for y in range(14):
        c = tuple(int(a + (b - a) * y / 14) for a, b in zip((255, 255, 255), st["soft"]))
        dr.line([(0, y), (W, y)], fill=c)
    dr.rectangle([0, H - 10, W, H], fill=st["soft"])
    dr.rectangle([0, H - 10, W * 0.18, H], fill=st["accent"])
    return img, dr


def pill(dr, x, y, text, bg, fg, fnt):
    tw = dr.textlength(text, font=fnt)
    ph = fnt.size + 18
    dr.rounded_rectangle([x, y, x + tw + 36, y + ph], radius=ph // 2, fill=bg)
    dr.text((x + 18, y + 9), text, font=fnt, fill=fg)
    return ph


def draw_cover(img, dr, st, main_title, tag, benefit, account, total):
    """首卡：大字报。主标题特大居中，3 秒讲清讲什么。"""
    y = 130
    if tag:
        fnt = font(30)
        y += pill(dr, PAD, y, tag, st["accent"], (255, 255, 255), fnt) + 46
    # 主标题：按长度自动降字号 92→72→56
    fnt = None
    for size in (92, 76, 60):
        fnt = font(size)
        lines = wrap(main_title, fnt, W - PAD * 2, max_lines=3)
        if len(lines) <= 2 and all(dr.textlength(x, font=fnt) <= W - PAD * 2 for x in lines):
            break
    for ln in lines:
        tw = dr.textlength(ln, font=fnt)
        dr.text(((W - tw) / 2, y), ln, font=fnt, fill=st["title"])
        y += int(fnt.size * 1.35)
    # accent 下划线块
    y += 26
    uw = int(W * 0.32)
    dr.rounded_rectangle([(W - uw) / 2, y, (W + uw) / 2, y + 12], radius=6, fill=st["accent"])
    y += 66
    if benefit:
        fnt = font(34)
        tw = dr.textlength(benefit, font=fnt)
        dr.text(((W - tw) / 2, y), benefit, font=fnt, fill=st["body"])
        y += 58
    # 中部留白 + 底部引导
    fnt = font(30)
    tip = "左右滑动，看完这 %d 张 →" % total
    tw = dr.textlength(tip, font=fnt)
    dr.text(((W - tw) / 2, H - 220), tip, font=fnt, fill=st["accent"])
    fnt = font(30)
    tw = dr.textlength(account, font=fnt)
    dr.text(((W - tw) / 2, H - 150), account, font=fnt, fill=st["muted"])
    return img


def draw_points_card(img, dr, st, no, total, sec_title, points, account, keywords):
    """要点卡：一卡一个要点。序号徽章 + 卡题 + 3-5 条短句 + 页码。"""
    y = 96
    # 序号徽章 + 页码
    badge = font(40)
    num = "%02d" % no
    dr.ellipse([PAD, y, PAD + 84, y + 84], fill=st["soft"], outline=st["accent"], width=3)
    tw = dr.textlength(num, font=badge)
    dr.text((PAD + (84 - tw) / 2, y + 16), num, font=badge, fill=st["accent"])
    fnt_page = font(30)
    pg = "%02d / %02d" % (no, total)
    tw = dr.textlength(pg, font=fnt_page)
    dr.text((W - PAD - tw, y + 26), pg, font=fnt_page, fill=st["muted"])
    y += 84 + 40
    # 卡题：自动字号（≤12 字用 46px，否则 38px），换行最多 2 行
    for size in (46 if len(sec_title) <= 12 else 38, 32):
        fnt = font(size)
        lines = wrap(sec_title, fnt, W - PAD * 2 - 8, max_lines=2)
        if len(lines) < 2 or size == 32:
            break
    for ln in lines:
        dr.text((PAD, y), ln, font=fnt, fill=st["title"])
        y += int(fnt.size * 1.4)
    y += 18
    dr.rectangle([PAD, y, PAD + 72, y + 8], fill=st["accent"])
    y += 44
    # 要点：每条带 accent 圆点，每行 ≤15 字宽度自适应，最多 5 条
    fnt_p = font(31)
    shown = points[:5]
    for pt in shown:
        dr.ellipse([PAD + 2, y + 14, PAD + 16, y + 28], fill=st["accent"])
        for ln in wrap(pt, fnt_p, W - PAD * 2 - 34, max_lines=2):
            dr.text((PAD + 34, y), ln, font=fnt_p, fill=st["body"])
            y += int(fnt_p.size * 1.55)
        y += 26
        if y > H - 190:
            break
    # 卡面 OCR 关键词（搜索打标签），放底部弱字
    if keywords:
        fnt_k = font(30)
        dr.text((PAD, H - 176), "# " + "  # ".join(keywords), font=fnt_k, fill=st["muted"])
    fnt_a = font(30)
    dr.text((PAD, H - 124), account, font=fnt_a, fill=st["muted"])
    return img


def draw_quote_card(img, dr, st, no, total, quote_text, account):
    """金句卡：淡底大引号 + 金句，收藏向素材。"""
    y = 150
    fnt_q = font(120)
    dr.text((PAD, y), "\u201c", font=fnt_q, fill=st["border"])
    y += 130
    fnt = font(40)
    lines = wrap(quote_text, fnt, W - PAD * 2, max_lines=8)
    for ln in lines:
        dr.text((PAD, y), ln, font=fnt, fill=st["title"])
        y += int(fnt.size * 1.6)
    fnt_a = font(30)
    dr.text((PAD, H - 152), "—— %s" % account, font=fnt_a, fill=st["muted"])
    pg = "%02d / %02d" % (no, total)
    fnt_p = font(30)
    tw = dr.textlength(pg, font=fnt_p)
    dr.text((W - PAD - tw, H - 152), pg, font=fnt_p, fill=st["muted"])
    return img


def draw_tail_card(img, dr, st, account, collection, keywords, tip):
    """尾卡：轻引导——合集入口 + 评论区聊聊，不喊加微。"""
    y = 200
    fnt = font(56)
    for ln in ["这篇先到这", "觉得有用的话"]:
        tw = dr.textlength(ln, font=fnt)
        dr.text(((W - tw) / 2, y), ln, font=fnt, fill=st["title"])
        y += 84
    y += 40
    if collection:
        fnt_p = font(30)
        pill(dr, (W - 320) / 2, y, "合集 · %s" % collection, st["soft"], st["accent"], fnt_p)
        y += 110
    if tip:
        fnt_b = font(30)
        lines = wrap(tip, fnt_b, W - PAD * 2, max_lines=2)
        for ln in lines:
            tw = dr.textlength(ln, font=fnt_b)
            dr.text(((W - tw) / 2, y), ln, font=fnt_b, fill=st["body"])
            y += 52
    if keywords:
        fnt_k = font(30)
        kw = "  ".join("#" + k for k in keywords)
        tw = dr.textlength(kw, font=fnt_k)
        dr.text(((W - tw) / 2, H - 330), kw, font=fnt_k, fill=st["muted"])
    fnt_a = font(38)
    tw = dr.textlength(account, font=fnt_a)
    dr.text(((W - tw) / 2, H - 220), account, font=fnt_a, fill=st["accent"])
    fnt_s = font(32)          # 原 26px：900 画布换算到手机仅 10.4px，低于 12px 下限
                              # （上一轮只改了 fnt_k 的 28，漏了这条——体检工具抓出来的）
    cta = "点赞 · 在看 · 评论区聊聊"
    tw = dr.textlength(cta, font=fnt_s)
    dr.text(((W - tw) / 2, H - 150), cta, font=fnt_s, fill=st["muted"])
    return img


# ---------------------------------------------------------------- 主流程
def build_cards(md: str, out_dir: str, *, style="ocean", cover_title="",
                tag="", account="AI澎", keywords=None, benefit="", tip=""):
    global d
    st = STYLES[style]
    data = parse(md)
    title = data["title"]
    if not title:
        raise SystemExit("draft.md 里没有找到 H1 标题")
    main = cover_title or shorten_cover_title(title)
    kws = keywords or []

    # 卡组规划：首卡 + 小节卡 + 金句卡(≤1) + 尾卡
    sec_cards = [s for s in data["sections"] if s["points"] or s["title"]]
    quote = " ".join(data["quotes"]) if data["quotes"] else None
    total = 1 + len(sec_cards) + (1 if quote else 0) + 1
    if total > 10:
        sec_cards = sec_cards[: 10 - 3 - (1 if quote else 0)]
        total = 1 + len(sec_cards) + (1 if quote else 0) + 1

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    n = 0

    def save(img):
        nonlocal n
        n += 1
        p = os.path.join(out_dir, "card_%02d.png" % n)
        img.save(p, "PNG")
        paths.append(p)

    img, dr = new_card(st); d = dr
    save(draw_cover(img, dr, st, main, tag, benefit, account, total))
    for i, sec in enumerate(sec_cards, 1):
        img, dr = new_card(st); d = dr
        save(draw_points_card(img, dr, st, i + 1, total,
                              sec["title"], sec["points"], account, kws))
    if quote:
        img, dr = new_card(st); d = dr
        save(draw_quote_card(img, dr, st, len(sec_cards) + 2, total, quote, account))
    img, dr = new_card(st); d = dr
    save(draw_tail_card(img, dr, st, account, data["collection"], kws, tip))
    return paths


def main():
    ap = argparse.ArgumentParser(description="长文 → 公众号贴图卡组（900x1200 竖版）")
    ap.add_argument("--in", dest="src", required=True, help="draft.md 路径")
    ap.add_argument("--out", dest="dst", required=True, help="输出目录（建议文章目录/cards/）")
    ap.add_argument("--style", default="ocean", choices=list(STYLES.keys()))
    ap.add_argument("--cover-title", default="", help="首卡主标题（≤8 字最优，默认自动截取）")
    ap.add_argument("--tag", default="", help="首卡类别 pill，如 AI实操")
    ap.add_argument("--benefit", default="", help="首卡利益点一句，如 全程免费 10分钟上手")
    ap.add_argument("--account", default="AI澎", help="号名（页脚/尾卡）")
    ap.add_argument("--keywords", default="", help="逗号分隔关键词，进卡面底部参与 OCR 检索")
    ap.add_argument("--tip", default="", help="尾卡一句引导语")
    ap.add_argument("--no-meta", action="store_true", help="不写 cards/meta.json")
    a = ap.parse_args()
    with open(a.src, encoding="utf-8") as f:
        md = f.read()
    kws = [k.strip() for k in re.split(r"[,，]", a.keywords) if k.strip()]
    paths = build_cards(md, a.dst, style=a.style, cover_title=a.cover_title,
                        tag=a.tag, account=a.account, keywords=kws,
                        benefit=a.benefit, tip=a.tip)
    # 卡组元数据：贴图发布（push_cards.py）要读标题/摘要/号名/合集，
    # 不靠参数人工再传一遍——一次生成，发布时直接用。
    if not a.no_meta:
        meta = {
            "cover_title": a.cover_title or shorten_cover_title(md.splitlines()[0].lstrip("# ").strip()),
            "tag": a.tag,
            "benefit": a.benefit,
            "account": a.account,
            "keywords": kws,
            "tip": a.tip,
            "style": a.style,
            "count": len(paths),
            "cards": [os.path.basename(p) for p in paths],
        }
        meta_path = os.path.join(a.dst, "meta.json")
        with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("[ok] 卡组元数据 -> %s" % meta_path)
    print("[ok] %d 张卡 -> %s" % (len(paths), a.dst))
    for p in paths:
        print("  ", os.path.basename(p))


if __name__ == "__main__":
    main()
