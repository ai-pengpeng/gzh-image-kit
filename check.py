#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推草稿前的硬性卡口 check.py

把原来靠「模型自觉」的软规则，变成跑不过就退出的硬校验。
目的：换任何大模型，产出下限都被兜住——文案水准可能有起伏，
但「能不能发、能不能声明原创」的底线不会破。

硬性错误（ERROR）：任一不过 → exit(1)，禁止 push
  1. 标题 ≤ 64 字节（UTF-8）
  2. 正文 ≤ 20000 字符（微信上限）
  3. 无 <style> / class= / flex / grid / position:absolute|fixed / var(--x)（微信会剥）
  4. ≥ 1 处原创锚点（品牌规则，默认关闭；需 --brand-rules 开启并配置关键词）
  5. HTML 里引用的本地图片真实存在
  6. 文件可读、非空

软性提醒（WARN）：默认只提醒；加 --strict 升级为 ERROR
  a. 有可见 <h1> 大标题
  b. 结尾留口子（留言 / 评论区 / 发消息 / 说说你，取代旧的「下一站」预告）
  c. 有来源标注（明显借鉴时必须写）

推流向检查（见 references/growth.md）：
  7. 无诱导互动话术（ERROR，命中会降权/限流）
  8. 无夸张表述（WARN，防标题党）
  9. 微信 SEO 关键词布局（需 --keyword）
 10. 段落长度 ≤220 字（WARN，保完读率）
 11. 正文配图 3–5 张（WARN，拉停留时长）
 12. 有收藏钩子（WARN，触发二次推荐）
12b. 假对比句壳机检「不是A而是B」一类（顾问级：一定显示，永不阻断）

用法：
  .venv\\Scripts\\python scripts/check.py --html article.html --title "你的标题"
  .venv\\Scripts\\python scripts/check.py --html article.html --title "标题" --strict
  .venv\\Scripts\\python scripts/check.py --html article.html --title "标题" --keyword "公众号运营"
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

BANNED = [
    ("<style", "内联样式铁律：文章里不能出现 <style> 块"),
    ("class=", "class= 会被微信剥离，必须改内联 style"),
    ("display: flex", "flex 布局会被微信剥离"),
    ("display:flex", "flex 布局会被微信剥离"),
    ("grid", "grid 布局 / grid-template 会被微信剥离"),
    ("position: absolute", "position:absolute 会被微信剥离"),
    ("position:absolute", "position:absolute 会被微信剥离"),
    ("position: fixed", "position:fixed 会被微信剥离"),
    ("position:fixed", "position:fixed 会被微信剥离"),
    ("var(--", "CSS 变量 var(--x) 会被微信剥离"),
    ("::before", "伪元素 ::before 会被微信剥离"),
    ("::after", "伪元素 ::after 会被微信剥离"),
    ('color:#1a4d8f', '颜色过多：全文≤3色，不用蓝色'),
    ('color:#c53030', '颜色过多：全文≤3色，不用红色'),
    ('color:#c0392b', '颜色过多：全文≤3色，不用红色'),
    ('color:#e07b39', '颜色过多：全文≤3色，不用橙色'),
    ('color:#2b6cb0', '颜色过多：全文≤3色，不用辅助蓝'),
]

SOURCE_MARKERS = ["数据出处", "来源标注", "参考来源", "参考链接", "原创整理",
                  "归原作者", "原创复盘", "未引用外部", "无外部来源", "本文基于"]

# ── 成稿占位（与 publish.py / ima_sync.py 同源，改一处要同步改另外两处）──
# 占位是写给作者看的备注：读者只当文章没写完，同步进 ima 还会污染问答召回。
# 两个反复踩的反例：
#   ① 裸「待补」只在行首才算占位——方法论里写「标记待补，不要替我编造」是在讨论这个词；
#   ② 匹配前必须先剥掉反引号内联代码——规则文档列举样例（TODO/TBD）会把自己拦下来。
PLACEHOLDER_PATTERNS = [
    r"【待\s*(补|填|确认|查|定)",
    r"^\s*[>＞✎✍✏▶▸·•｜|\-\*]*\s*待\s*(补|填|确认|查)(?=\s*[:：　，,。、]|\s*$)",
    r"此处(补|填|待)[^\n]{0,10}",
    r"（\s*待\s*(补|填)[^）]*）",
    r"\{\{[^}]{0,40}\}\}",
    r"\b(TBD|TODO)\b",
    r"(?<![0-9A-Za-z#])X{4,}",
]

# ── 推流红线 / 加分项（见 references/growth.md）──
# 诱导互动话术：命中会被算法识别为营销号并降权 → 硬性 ERROR
REDLINE_PHRASES = [
    "不转不是", "不转发不是", "看完不转", "必须转发", "转发抽奖", "转发到 3 个",
    "点赞过万", "不点赞", "集赞", "不赞不是", "在看过万", "转发超过",
]
# 夸张表述：标题承诺与正文不符会被判标题党 → 软性提醒
HYPE_WORDS = ["震惊", "不看后悔", "速看", "删前", "紧急通知", "惊天", "绝密", "99%的人", "万万没想到"]
# 收藏钩子：收藏会触发「二次推荐」，等于多一轮免费流量
COLLECT_HINTS = ["收藏", "码住", "存下来", "存好"]

# ── 结构铁律（2026-11-04 定，来源是两次退稿）──
# 三条：给一件能拿走的东西 / 图注自包含 / 结尾给出口。
# 都是 WARN：机器判得粗，判错的代价只是多看一眼，判漏的代价是又退一次稿。
# 「答案前置」不做机器判——句式误报率太高（叙事型开头也能做到答案前置），归人格提示词管。
# 按身份分岔：出现两次以上，说明作者在替不同读者分别给做法
BRANCH_HINTS = ["如果你", "发自己号的", "接商单的", "做企业号的", "不剪的", "要精剪的",
                "刚起步", "已经有号"]
# 结尾给出口：最后一段要落到「能做什么」，不是「有多危险」
# 只收「动词型」提示：名词型的「收藏」「点赞」是钩子，不算出路
EXIT_HINTS = ["现在", "今天", "今晚", "就能", "花不了", "五分钟", "十分钟",
              "打开", "照着", "翻出来", "翻一遍", "试一下", "试一试", "先做",
              "动手", "核一遍", "换一首", "留个"]
# 结尾留口子：邀请读者说话，不是把他送去另一篇（2026-11-05 取代「下一站」预告）
# 2026-11-11 补「发我 / 问我 / 回我 / 私信」：本号结尾实际写法是「把报错原文发我」
# 「拿不准的可以问我」，原词表只认「留言 / 评论区」，三篇 11-12 稿全被误报成「没让读者说话」。
CTA_HINTS = ["留言", "评论区", "评论里", "发消息", "说说你", "丢过来", "贴过来",
             "告诉我", "我都能收到", "你说了算",
             "发我", "问我", "回我", "私信", "后台发"]
# 图里不许有只在文章内成立的指向：读者存的是图，不是文章
CAPTION_BAD_REFS = ["见第", "见上", "见下", "如前", "如后", "后文", "下文", "上文",
                    "第几节", "下文详", "前面说过"]

# ── 品牌规则配置（默认关闭，仅 --brand-rules 开启时生效）────────────────────
# 开源版默认不含任何专有栏目标记：关键词由使用者按需注入，仓库内零硬编码。
#   GZH_CHECK_BRAND_ANCHORS  逗号分隔的「原创锚点」关键词（--min-opinion 计数用）
#   GZH_CHECK_BRAND_ALIASES  逗号分隔的「别名 / 历史写法」关键词（出现即报错）
#   GZH_CHECK_BRAND_CANON    唯一合法栏目名（报错提示用，可留空）
def _env_words(name):
    return tuple(w.strip() for w in os.environ.get(name, "").split(",") if w.strip())


BRAND_ANCHORS = _env_words("GZH_CHECK_BRAND_ANCHORS")
BRAND_ALIASES = _env_words("GZH_CHECK_BRAND_ALIASES")
BRAND_CANON = os.environ.get("GZH_CHECK_BRAND_CANON", "").strip()

# ── 姿势级 AI 味量化（参考 references/editor_checklist.md）──
# 人类写作句长爆发式起伏，AI 像节拍器式均匀；下列词是 AI 腔高频信号。
# 仅作 WARN 提示、不阻断发布；改写仍按 writing-system 11 条白名单规则执行。
CONN_WORDS = ["此外", "而且", "然而", "因此", "所以", "综上所述", "值得注意的是",
              "不可否认", "换句话说", "换言之", "与此同时", "由此可见"]
AI_WORDS = ["赋能", "格局", "范式", "生态", "抓手", "痛点", "底层逻辑", "至关重要",
            "彰显", "无缝", "直观", "强大", "不难发现", "深入探讨", "不断演变",
            "众所周知", "总而言之"]

# ── 假对比句壳机检（2026-11-10 补，规则源：炼丹炉 ai_tell_linter.py）──
# 来由：deai-promax 把「不是 A 而是 B」列为最高优先级三毒，但只有规范、没有执行环节。
#       实测 11-10 三篇在发稿件分别命中 2 / 5 / 6 处，全部原样留在正文里。
# 做法：调用上游脚本，不在本文件复制正则——单一事实源留在炼丹炉，
#       上游改规则我们跟着生效；脚本缺失时降级为提醒，不拦发布。
# 路径：环境变量 OPSWORK_AI_TELL_LINTER → 默认 skill 安装位。
# 口径：**顾问级**——一定会显示命中原文，但不进 errors，也不参与 --strict 升级。
#   原因：发布链路默认带 --strict，而回测 11-01 起 14 篇在发稿，12 篇有命中、中位数 3 处、
#   最高 8 处——升成硬错等于每篇都被拒，闸门从此作废（老教训：永远在报的检查比没有更糟）。
#   上游自己写明「命中不等于一定要改」，且会误伤双向否定
#   （「不是官方报价，也不是我实测的账单」也命中）。
#   确需放行的句子，写进稿件目录 ai_tell_allow.txt（每行一段原文片段）。
AI_TELL_LINTER_ENV = "OPSWORK_AI_TELL_LINTER"
AI_TELL_ALLOW_NAME = "ai_tell_allow.txt"
AI_TELL_MAX_SHOW = 8           # 命中太多时只列前 8 处，避免刷屏盖住别的结论

# ── 人味指标（2026-11-05 定）──
# 来由：朱雀启发式给本产线两篇只判 14 分和 30 分（越低越像人），词面已经很干净，
# 但读者仍说「AI 味重」。真差别不在词，在两处：
#   ① 谁在说话 —— 「我」占人称的比例。产线常见「我 5 / 你 45」，那是说明书比例。
#   ② 有没有带日期的经历 —— 哪天、多少钱、报什么错。
# 只 WARN；阈值定在「明显偏了」才报，避免变成每篇都响的噪音。
PERSON_MIN_RATIO = 0.25        # 「我」占「我+你」的下限
EXPERIENCE_MIN = 0.5           # 带日期经历的下限（处 / 千字）
EXP_RE = (r"(上周|上个月|上月|昨天|前天|那天|当时|去年|今年|年初|年底|"
          r"凌晨|半夜|\d+月\d+[日号]|\d+点\d+分?|"
          r"花了\s*\d+|\d+\s*块钱|\d+\s*元)")


# ─────────────────────────────────────────────────────────────────────────────
# 贴图 / 小绿书（greenbook）硬闸
# 这个渠道的贴图是**生图模型出的插画**，不是代码渲染的卡片。
# 真因：早期多批贴图误用了代码卡片图（单张仅 30–60KB、扁平文字卡），
#       与渠道正典「奶油暖白 #FAF7F2 + 薄荷绿 #4ECDC4、3:4 竖版插画」严重不符。
# 所以这里用「体积 + 品牌绿占比 + 张数」三个可量化的信号判定「是不是代码卡混进来了」。
# ─────────────────────────────────────────────────────────────────────────────
GREENBOOK_MINT = (0x4E, 0xCD, 0xC4)   # 品牌绿 #4ECDC4
GREENBOOK_MIN_KB = 150                # 插画 ≥150KB；代码卡实测只有 30–60KB
GREENBOOK_MAX_KB = 1536               # 平台单图上限 1.5MB（早期版本不查上限，超限照样过闸）
# 张数下限从口径表取（TT-CARD-MIN），这里只转发，避免同一个数字写两遍。
# 保留常量名 GREENBOOK_MIN_COUNT 是为了不动下面几十处引用。
# 开源副本没有内部 app.core.spec：导入失败时退回中性默认 6，保证 --help 等能独立运行。
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.core.spec import CARD_MIN as GREENBOOK_MIN_COUNT  # noqa: E402
except ImportError:
    GREENBOOK_MIN_COUNT = 6
GREENBOOK_RATIO = 4.0 / 3.0           # 3:4 竖版

# 通用图片组体检的上下限（与渠道无关）。上限对齐多数平台单图 10MB；
# 下限不是硬闸——低于这个数只是「可能压得太狠」，报提醒让人看一眼。
GENERIC_MAX_KB = 10 * 1024
GENERIC_MIN_KB = 20


def _count_mint(im):
    """统计薄荷绿品牌色 #4ECDC4 的占比（降采样提速）。
    采用色相带检测：插画实际渲染的是「高饱和薄荷绿 #4ECDC4 ↔ 柔和灰薄荷」
    一整段绿青色（色相 125°–190°，G 为最大通道，饱和度 ≥0.12）。
    精确匹配法会误杀合规图（同一批里 6 张全部判 0.00%）。
    奶油底(R最大)、蓝色角色(B最大)、灰白(低饱和)均不命中。"""
    try:
        small = im.convert("RGB").resize((180, 240))
    except Exception:
        return 0.0
    px = small.load()
    W, H = small.size
    hit = 0
    total = 0
    step = 3  # 降采样，兼顾速度与稳健
    for y in range(0, H, step):
        for x in range(0, W, step):
            r, g, b = px[x, y]
            total += 1
            if g < r or g < b or g < 90:
                continue  # 品牌绿必须 G 为最大通道且不过暗
            mn = min(r, b)
            if g == mn:
                continue  # 灰白无饱和度
            sat = (g - mn) / g
            if sat < 0.12:
                continue
            hue = 60.0 * (2.0 + (b - r) / (g - mn))
            if 125.0 <= hue <= 190.0:
                hit += 1
    return (hit / total) if total else 0.0


def _corner_wm_grid(im):
    """右下角落点区（x≥0.86w, y≥0.94h）「亮于高斯参考底」mask，归一到 64×32 网格。
    生图工具常在右下角压一行半透明白字水印，实测落点 x≥0.88w、y≥0.96h，
    框位留余量罩住；判据 diff>8（亮差检测）。
    返回 list[bool]（2048 格）或 None（图太小）。"""
    from PIL import ImageChops, ImageFilter
    w, h = im.size
    x0, y0 = int(w * 0.86), int(h * 0.94)
    box = im.crop((x0, y0, w, h)).convert("L")
    if box.width < 8 or box.height < 8:
        return None
    ref = box.filter(ImageFilter.GaussianBlur(8))
    diff = ImageChops.subtract(box, ref)
    mask = diff.point(lambda v: 255 if v > 8 else 0).resize((64, 32))
    px, data = mask.load(), []
    for y in range(32):
        for x in range(64):
            data.append(px[x, y] > 0)
    return data


# ── 贴图文字卡字号体检（2026-11-10 补）────────────────────────────────
# 为什么审脚本而不是审图片：PNG 里没有字号信息，读不出来。
# 为什么必须审：贴图渲染脚本每期现场新写，`dazi_kit.py` 里有 assert 兜底，
# 但绕过 kit 自己写 draw.text 的脚本没人管。标准要真落地，就得有个能主动跑的东西。
CARD_SCREEN_W = 360      # 手机屏宽基准（CSS px）
CARD_MIN_CSS = 12        # 可读下限（CSS px），见 docs/配图标准.md §3.1

_FONT_CALL_RE = re.compile(
    # 函数名集合必须覆盖每个脚本实际用的封装名。
    # 2026-11-14 补 `ft`：gen_diagram.py 的字体封装叫 ft()，不在原集合里，
    # 于是这个脚本**一个字号都没被查过**，却一路显示「✅ 都达标」——
    # 守卫报的是自己正则写窄了，不是脚本没问题（同 EXP_RE 那次教训）。
    r"(?:font|_sign_font|ft|f)\(\s*(\d{2,3})\s*[,)]"                    # font(26) / ft(26)
    # 两参数形式 font(FONT_REG, 34) —— 2026-11-11 补。共享渲染器 render_cards.py
    # 整个文件都是这个写法，漏了这条等于整份文件一个字号都没查（假 PASS 的来源之一）。
    r"|(?:font|_sign_font|ft|f)\(\s*[^,()]+,\s*(\d{2,3})\s*[,)]"
    r"|(?:put_bl|put_c)\(\s*[^,]+,\s*[^,]+,\s*(\d{2,3})\s*,"            # put_bl(d, txt, 26, ...)
    # 绕过封装直接建字体的写法，漏了这条等于只防一半（2026-11-10 补）
    r"|(?:ImageFont\.truetype|load(?:_kit_font)?)\(\s*[^,()]+,\s*(\d{2,3})\s*[,)]")
# 字号常写成 int(34 * S)（S = 画布/基准的缩放系数）。先把这层壳剥掉再匹配，
# 否则一个都抓不到。S 不等于 1 时实际像素 = 基数×S，但基数与画布下限同比例，
# 判定结论不变——抓基数就够。
_SCALED_FONT_RE = re.compile(r"int\(\s*(\d{2,3})\s*\*\s*[A-Za-z_][\w.]*\s*\)")

# 脚本整体缩放字号时的两个特征：模块级 `SCALE = 1.6` + 函数内 `round(size * SCALE)`。
# 两个都命中才当作「需要换算」，避免把随便一个同名字段当成缩放系数。
_SCALE_DEF_RE = re.compile(r"^SCALE\s*=\s*([\d.]+)\s*$", re.M)
_SCALE_APPLY_RE = re.compile(r"round\(\s*size\s*\*\s*SCALE\s*\)")
# HTML/CSS 渲染的贴图（render_riso.py 走 playwright 截图，字号全在 CSS 里）。
# 2026-11-11 发现：这类渲染器一个 `font(` 调用都没有，只扫 Python 会直接报「没抓到」，
# 而它恰恰是问题最重的一套（21~34px 共 12 处）。CSS 也要一并扫。
_CSS_FONT_RE = re.compile(r"font-size:\s*(\d{1,4}(?:\.\d+)?)px")
_CANVAS_RE = re.compile(r"^\s*W\s*,\s*H\s*=\s*(\d{3,4})\s*,\s*(\d{3,4})", re.M)
# 画布宽度也可能来自 argparse 默认值（render_cards.py 是 --width default=1242，
# 模块里只有 BASE_W = 1080），不读这条就会按 1080 判、下限少算 5px。
_CANVAS_ARG_RE = re.compile(r'--width["\']?\s*,\s*type=int\s*,\s*default\s*=\s*(\d{3,4})')

# 低对比度色值：不能当文字色（对奶油白底 <4.5:1）。只做顾问提醒——它出现在
# draw.line / 色块里是合法的，扫到就说是提醒，不阻断。判据见配图标准 §3.4。
_LOW_CONTRAST_COLORS = {
    (150, 155, 162): "2.68:1",
    (222, 245, 234): "1.10:1",
    (0, 182, 122): "2.53:1（旧荧光绿，已加深为 0,164,108）",
    (138, 160, 182): "2.65:1（旧 MUTED #8aa0b6，已改为 92,113,135）",
    (207, 220, 236): "1.37:1（BORDER 边框色，只能画线）",
}

# ── 动态对比度体检（2026-11-10 补）────────────────────────────────────────
# 为什么要有：上面那张白名单是「已知踩过的坑」清单，只能防回退，防不了**新写的浅色**。
# 2026-11-10 发布那批贴图里，(146,122,104) 3.78:1 和 (150,132,120) 3.58:1 都不是旧坑，
# 白名单一个都没命中——图上看着"淡淡的挺高级"，手机上就是一片糊。
# 现在改为：从脚本里读出它自己的底色，再把每个文字色跟底色现算一遍对比度。
_RGB_TRIPLE = re.compile(r"\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)")
_PALETTE_BG_KEY = re.compile(
    r"""['"](BG|CARD|CARDBG|PAPER|BASE|CANVAS_BG|WHITE)['"]\s*:\s*"""
    r"""\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)""")
_IMAGENEW_RE = re.compile(
    r"""Image\.new\(\s*['"]RGB['"]\s*,\s*\([^)]*\)\s*,\s*"""
    r"""\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)""")


def _rel_lum(rgb):
    def lin(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(c1, c2):
    a, b = _rel_lum(c1), _rel_lum(c2)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _bg_candidates(src):
    """从脚本里读出它自己的底色候选（色板键 BG/CARD/... + Image.new 底色）。"""
    out = set()
    for m in _PALETTE_BG_KEY.finditer(src):
        out.add(tuple(int(m.group(i)) for i in (2, 3, 4)))
    for m in _IMAGENEW_RE.finditer(src):
        out.add(tuple(int(m.group(i)) for i in (1, 2, 3)))
    return out


def _dyn_low_contrast(line, bgs, canvas):
    """现算这一行文字色的对比度，返回 [(rgb, 对比度, 要求)] —— 只在不达标时返回。

    要求值按字号分档（WCAG）：小字 4.5:1，大字 3:1。
    大字线取 24 CSS px ≈ 画布 24×canvas/360。
    """
    if not bgs:
        return []
    sizes = [int(x) for x in re.findall(r"(?:text|put_bl|put_c|capsule)[^\d]{0,40}?(\d{2,3})", line)]
    big = bool(sizes) and min(sizes) >= 24 * canvas / 360.0
    need = 3.0 if big else 4.5
    bad = []
    for m in _RGB_TRIPLE.finditer(line):
        rgb = tuple(int(m.group(i)) for i in (1, 2, 3))
        if rgb in bgs:
            continue
        worst = min(_contrast(rgb, bg) for bg in bgs)
        if worst < need:
            bad.append((rgb, round(worst, 2), need))
    return bad


def audit_card_fonts(target):
    """扫描贴图渲染脚本里的硬编码字号 + 低对比度文字色。

    判据：图片满屏显示时手机屏宽 360 CSS px，任何文字不得低于 12 CSS px；
         换算 图片px = 12 × 画布宽 / 360。
         文字色对奶油白底须 >=4.5:1（小字），字号达标但颜色太浅照样读得费劲。
    返回 (canvas_w, 字号命中列表, 低对比度颜色命中列表)；target 可为目录或单个 .py。
    """
    import glob as _glob
    if os.path.isdir(target):
        paths = sorted(_glob.glob(os.path.join(target, "*.py")))
    else:
        paths = [target] if os.path.exists(target) else []

    canvas_guess = 1080      # 找不到画布定义时按 1080 算（本号贴图主画布）
    canvas_found = None      # 实际读到的画布宽；原来错误地返回了 guess，
                             # 结果 gen_cards.py(900) 被显示成 1080、下限 30 被显示成 36
    hits, color_hits = [], []
    n_font_seen = 0          # 匹配到的字号调用数——用来区分「查了没问题」和「一个都没查到」
    # 「这一行在画文字」——不能只认固定函数名：脚本里常写 d.text(...) / draw.text(...)，
    # 变量名各不相同。改为「含 text/put_/capsule 且不是纯图形调用」，两种写法都覆盖。
    _TEXT_KW = ("text", "put_bl", "put_c", "capsule")
    _SHAPE_KW = (".line(", "rectangle(", "ellipse(", "polygon(")
    for p in paths:
        try:
            src = Path(p).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # 剥掉 int(34 * S) 这层壳，否则整份文件一个字号都匹配不到
        src_norm = _SCALED_FONT_RE.sub(r"\1", src)
        # 脚本自己把字号整体缩放过（如 gen_diagram 的 `SCALE = 1.6` 与
        # `size = round(size * SCALE)`）：静态扫描必须按这个系数换算，
        # 否则会把 ft(24) 报成 24px，而它实际渲的是 38px —— 误报一多，
        # 这道闸就会被当成噪音绕过（2026-11-14 补）。
        _sm = _SCALE_DEF_RE.search(src)
        scale = float(_sm.group(1)) if (_sm and _SCALE_APPLY_RE.search(src)) else 1.0
        m = _CANVAS_RE.search(src) or _CANVAS_ARG_RE.search(src)
        canvas = int(m.group(1)) if m else canvas_guess
        if m and canvas_found is None:
            canvas_found = canvas
        floor = round(CARD_MIN_CSS * canvas / CARD_SCREEN_W)
        bgs = _bg_candidates(src)
        for lineno, line in enumerate(src_norm.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for m2 in _FONT_CALL_RE.finditer(line):
                num = m2.group(1) or m2.group(2) or m2.group(3) or m2.group(4)
                if not num:
                    continue
                n_font_seen += 1
                px = int(round(int(num) * scale))
                if px < floor:
                    hits.append((os.path.basename(p), lineno, px, floor,
                                 round(px * CARD_SCREEN_W / canvas, 1), line.strip()[:56]))
            # CSS 字号（HTML 渲染的贴图）
            for m3 in _CSS_FONT_RE.finditer(line):
                n_font_seen += 1
                px = int(round(float(m3.group(1))))
                if px < floor:
                    hits.append((os.path.basename(p), lineno, px, floor,
                                 round(px * CARD_SCREEN_W / canvas, 1), line.strip()[:56]))
            # 低对比度色值只在这行确实在画文字时才提——画线/填色块用浅色合法
            is_text = any(k in line for k in _TEXT_KW) and not any(k in line for k in _SHAPE_KW)
            if is_text:
                seen = set()
                for rgb, ratio in _LOW_CONTRAST_COLORS.items():
                    pat = r"\(\s*%d\s*,\s*%d\s*,\s*%d\s*\)" % rgb
                    if re.search(pat, line):
                        color_hits.append((os.path.basename(p), lineno, rgb, ratio,
                                           line.strip()[:56]))
                        seen.add(rgb)
                # 动态：不在白名单里的新浅色也要抓
                for rgb, cr, need in _dyn_low_contrast(line, bgs, canvas):
                    if rgb in seen:
                        continue
                    color_hits.append((os.path.basename(p), lineno, rgb,
                                       "%.2f:1（需 ≥%.1f）" % (cr, need),
                                       line.strip()[:56]))
    return (canvas_found or canvas_guess), hits, color_hits, len(paths), n_font_seen


# ── 封面体检（2026-11-10 补，与 push_draft.check_cover_is_art 同判据）──────
# 为什么要在 check.py 再放一份：push_draft 的守卫在**推草稿**那一端，
# 而深蓝字卡是在**出封面**那一刻产生的。上游出事、下游才拦，中间全靠人肉发现——
# 2026-11-10 就是这样：三篇又是字卡，直到推之前才被人工看到。
# 多一个能随时单跑的入口，出完封面立刻查，不用等到推。
COVER_ART_MIN_LUM = 150     # 插画海报奶油底实测 201~211；hero 深蓝字卡实测 53~56


def audit_covers(paths):
    """封面体检：平均亮度低于 150 判为深色字卡。返回问题列表。"""
    from PIL import Image
    problems = []
    for p in paths:
        try:
            with Image.open(p) as im:
                lum = sum(im.convert("L").resize((300, 128)).tobytes()) / (300 * 128)
        except Exception as e:
            problems.append("%s 读不出来：%s" % (os.path.basename(p), e))
            continue
        if lum < COVER_ART_MIN_LUM:
            problems.append(
                "%s 平均亮度 %.0f，判定为深色字卡（插画海报应 ≥150）。"
                "封面默认走插画：先用生图模型出无字插画 → 再用本工具叠字"
                % (os.path.basename(p), lum))
        else:
            print("  ✅ %s  亮度 %.0f（插画海报）" % (os.path.basename(p), lum))
    return problems


# ── 配图色相体检（2026-11-10 补）─────────────────────────────────────────
# 为什么要有这条：配色跟随封面已经定过两次（MEMORY 里写着「配图跟随封面主色系」），
# 11-09 和 11-10 各回退一次。11-10 那一篇是砖红封面 + 深蓝配图，
# 出图当时没人看出来，是做完才发现。人眼对「同一篇里两套色系」不敏感，
# 对色相差 200° 这个数字敏感——那就交给机器看。
FIG_HUE_MAX_DELTA = 30      # 色相偏差容忍度（度）。砖红 8° vs 深蓝 210° = 202°，一查一个准


def _dominant_hue(path, s_min=0.35, v_lo=0.18, v_hi=0.95):
    """取图里「最显眼的那批彩色像素」的主色相。

    只统计饱和度够高、亮度中段的像素：浅底（奶油白、淡绿胶囊）饱和度低，
    近黑文字亮度低，都会被排除，剩下的就是强调色/插画主体。
    返回 (色相角度, 占比) ；没有足够彩色像素时返回 None（纯文字图不判定）。
    """
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((120, 120))
        px = list(im.getdata())
    if not px:
        return None
    buckets = {}
    for r, g, b in px:
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        mx, mn = max(r, g, b), min(r, g, b)
        df = mx - mn
        if mx <= 0 or df / mx < s_min or not (v_lo <= mx <= v_hi):
            continue
        if mx == r:
            h = (60 * ((g - b) / df)) % 360
        elif mx == g:
            h = 60 * ((b - r) / df) + 120
        else:
            h = 60 * ((r - g) / df) + 240
        k = int(h // 15)
        acc = buckets.setdefault(k, [0, 0.0])
        acc[0] += 1
        acc[1] += h
    if not buckets:
        return None
    best = max(buckets.values(), key=lambda a: a[0])
    share = best[0] / float(len(px))
    if share < 0.008:                 # 彩色像素不到千分之八 = 这张图没有强调色
        return None
    return best[1] / best[0], share


def audit_figure_hue(cover, figs):
    """配图主色必须跟随封面主色（色相差 ≤30°）。返回顾问级提示列表。"""
    if not os.path.exists(cover):
        return ["找不到封面图：%s" % cover]
    ch = _dominant_hue(cover)
    if ch is None:
        return ["封面取不到主色（%s），无法判定配图配色" % os.path.basename(cover)]
    out = []
    print("  封面主色相 %.0f°（%s）" % (ch[0], os.path.basename(cover)))
    for f in figs:
        if not os.path.exists(f):
            out.append("找不到配图：%s" % os.path.basename(f))
            continue
        fh = _dominant_hue(f)
        if fh is None:
            print("  · %s 无强调色，跳过" % os.path.basename(f))
            continue
        d = abs(fh[0] - ch[0]) % 360
        d = min(d, 360 - d)
        if d > FIG_HUE_MAX_DELTA:
            out.append(
                "%s 主色相 %.0f°，与封面 %.0f° 差 %.0f°（上限 %d°）——同一篇里两套色系。"
                "出图时加 --match-cover <封面图> 自动跟随"
                % (os.path.basename(f), fh[0], ch[0], d, FIG_HUE_MAX_DELTA))
        else:
            print("  ✅ %s 主色相 %.0f°，与封面差 %.0f°" % (os.path.basename(f), fh[0], d))
    return out


def check_greenbook_images(image_dir):
    """贴图（小绿书）硬闸：禁止代码卡片图、单图 ≤1.5MB、3:4 竖版、张数 ≥6、序号连续、#4ECDC4 品牌色。"""
    import glob as _glob
    from PIL import Image as _Image

    errors, warns = [], []
    if not os.path.isdir(image_dir):
        return ["贴图目录不存在：%s" % image_dir], [], []
    files = sorted(_glob.glob(os.path.join(image_dir, "*.png")))
    if not files:
        return ["贴图目录 %s 下没有 PNG 文件" % image_dir], [], []

    print("🔍 贴图硬闸（greenbook）：%s  （%d 张）" % (image_dir, len(files)))
    for f in files:
        name = os.path.basename(f)
        size_kb = os.path.getsize(f) / 1024.0
        try:
            with _Image.open(f) as im:
                w, h = im.size
                ratio = (h / w) if w else 0.0
                mint = _count_mint(im)
        except Exception as e:
            errors.append("%s 无法读取图像：%s" % (name, e))
            continue
        # 1) 代码卡片图检测（硬错误）：生图模型出的插画 ≥150KB，代码卡仅 30–60KB
        if size_kb < GREENBOOK_MIN_KB:
            errors.append(
                "%s 仅 %.0fKB（%dx%d）—— 疑似代码卡片图（gen_diagram / gen_cards），"
                "本渠道禁用！需要生图模型出的 AI 插画（单图 ≥150KB）。"
                % (name, size_kb, w, h))
        # 1b) 单图体积上限（硬错误，2026-10-15 补）：微信贴图单图 ≤1.5MB
        elif size_kb > GREENBOOK_MAX_KB:
            errors.append(
                "%s %.0fKB > %dKB 上限（微信贴图单图 ≤1.5MB，超限会被压缩/拒收），"
                "请压体积后重出。" % (name, size_kb, GREENBOOK_MAX_KB))
        else:
            print("  ✅ %s  %dx%d  %.0fKB（体量符合插画规格，未超限）"
                  % (name, w, h, size_kb))
        # 2) 3:4 竖版（硬错误）
        if abs(ratio - GREENBOOK_RATIO) > 0.03:
            errors.append("%s 比例 %dx%d（%.2f）不是 3:4 竖版，贴图必须为 1.33"
                          % (name, w, h, ratio))
        # 3) 品牌色 #4ECDC4（软提醒 / --strict 升 ERROR）
        if mint < 0.002:
            warns.append("%s 未检出薄荷绿品牌色 #4ECDC4（占比 %.2f%%），请确认配色含 #4ECDC4"
                         % (name, mint * 100))
        else:
            print("  ✅ %s  薄荷绿 #4ECDC4 占比 %.2f%%" % (name, mint * 100))
    # 4) 张数（软/硬，2026-10-15 补）：不满 6 张不许发
    if len(files) < GREENBOOK_MIN_COUNT:
        errors.append("贴图仅 %d 张 < %d 张下限（正典：不满 6 张不许发，算法推荐极低）"
                      % (len(files), GREENBOOK_MIN_COUNT))
    elif len(files) != GREENBOOK_MIN_COUNT:
        warns.append("贴图 %d 张，正典为 6 张一套（7-9 张亦可，但需确认叙事仍连贯）"
                     % len(files))
    # 5) 序号连续性（软提醒，2026-10-15 补）：文件名尾部序号应连成 1..N
    nums = {}
    for f in files:
        b = os.path.basename(f)
        m = re.search(r"(\d{1,2})\.png$", b)
        if not m:
            warns.append("%s 文件名尾部未见序号（建议 {YYYYMMDD}-{题目}-01.png）" % b)
        else:
            nums[int(m.group(1))] = b
    if nums:
        want, got = set(range(1, len(files) + 1)), set(nums)
        if got != want:
            warns.append("序号不连续：检出 %s，期望 1..%d（缺号/重号会让后台图序错乱）"
                         % (sorted(got), len(files)))
        else:
            print("  ✅ 序号连续          1..%d" % len(files))
    # 6) 右下角水印残留（跨图交集检测，2026-10-15 补）：整套同位置亮区一致率高 → 水印。
    #    原理：生图工具的水印位置固定（x≥0.88w,y≥0.96h），N 张图同格同时亮才计一致；
    #    画面内容（气泡/高光）位置随机，不会形成高交集。
    #    本仓库不附带去水印工具（那一步是平台专属的），检出后请用任意图片编辑器
    #    覆盖右下角固定区域再发；早期版本不查水印，导致整套图带着水印发出去。
    grids = []
    for f in files:
        try:
            with _Image.open(f) as im:
                g = _corner_wm_grid(im)
            if g:
                grids.append(g)
        except Exception:
            pass
    if len(grids) >= 3:
        n = len(grids)
        cells = len(grids[0])
        consist_max = 0.0
        for c in range(cells):
            k = sum(1 for g in grids if g[c])
            if k / n > consist_max:
                consist_max = k / n
        if consist_max > 0.6:
            errors.append(
                "右下角疑似平台水印残留：整套 %d 张同位置亮区一致率 %.0f%%（阈值 60%%）。"
                "本仓库不附带去水印工具（该步骤依赖平台专属脚本）。"
                "请用任意图片编辑器覆盖右下角固定区域后重跑本检查。"
                % (n, consist_max * 100))
        elif consist_max > 0.35:
            warns.append("右下角亮区一致率 %.0f%%，疑似水印或固定 UI 元素，建议目视确认" % (consist_max * 100))
        else:
            print("  ✅ 右下角水印检测      同位置亮区一致率 %.0f%%（<35%%，无固定水印）" % (consist_max * 100))
    return errors, warns, []


def check_images_generic(image_dir):
    """通用图片组体检（2026-11-14 新增，channel 无关）。

    为什么需要这一档：原来 `--images` 被**硬绑**到 greenbook 闸上，
    长文配图用户出一整套图之后，只有 `--card-fonts`（静态查脚本源码）和
    `--cover`（查封面亮度）可用——比例、体积上限、序号连续、水印交集这些
    现成逻辑全用不上，等于换个渠道就失明。

    与 greenbook 档的区别只有三条硬判据：
      · 体积下限（greenbook 要 ≥150KB 判「不是代码卡」；通用档不设下限）
      · 单图上限（通用 10MB；greenbook 1.5MB）
      · 比例（通用接受 3:4 与 1:1，其余给提醒；greenbook 只认 3:4）

    比例、序号、水印三段逻辑与 greenbook 档同源，改一处两边一起变。
    """
    import glob as _glob
    from PIL import Image as _Image

    errors, warns = [], []
    if not os.path.isdir(image_dir):
        return ["图片目录不存在：%s" % image_dir], [], []
    files = sorted(_glob.glob(os.path.join(image_dir, "*.png")))
    if not files:
        return ["图片目录 %s 下没有 PNG 文件" % image_dir], [], []

    print("🔍 图片组通用体检：%s  （%d 张）" % (image_dir, len(files)))
    for f in files:
        name = os.path.basename(f)
        size_kb = os.path.getsize(f) / 1024.0
        try:
            with _Image.open(f) as im:
                w, h = im.size
        except Exception as e:
            errors.append("%s 无法读取图像：%s" % (name, e))
            continue
        ratio = (h / w) if w else 0.0
        if size_kb > GENERIC_MAX_KB:
            errors.append("%s %.1fMB > %dMB 上限（多数平台单图限 10MB，超限会被压缩/拒收）"
                          % (name, size_kb / 1024, GENERIC_MAX_KB // 1024))
        elif size_kb < GENERIC_MIN_KB:
            warns.append("%s 仅 %.0fKB（%dx%d），疑似压缩过度或图过小，"
                         "手机上会发虚" % (name, size_kb, w, h))
        # 3:4 与 1:1 都是合规比例；其余只提醒，不阻断（长文配图比例可以自由）
        if abs(ratio - 4 / 3.0) > 0.03 and abs(ratio - 1.0) > 0.03:
            warns.append("%s 比例 %dx%d（%.2f），既不是 3:4 也不是 1:1；"
                         "公众号正文配图建议 3:4" % (name, w, h, ratio))
        else:
            print("  ✅ %s  %dx%d  %.0fKB" % (name, w, h, size_kb))

    if len(files) < 3:
        warns.append("只有 %d 张图；长文正文配图建议 3–5 张（拉停留时长）" % len(files))

    # 序号连续性
    nums = {}
    for f in files:
        b = os.path.basename(f)
        m = re.search(r"(\d{1,2})\.png$", b)
        if m:
            nums[int(m.group(1))] = b
    if nums:
        want, got = set(range(1, len(files) + 1)), set(nums)
        if got != want:
            warns.append("序号不连续：检出 %s，期望 1..%d（缺号/重号会让后台图序错乱）"
                         % (sorted(got), len(files)))
        else:
            print("  ✅ 序号连续          1..%d" % len(files))

    # 右下角水印（与 greenbook 同一套交集检测）
    grids = []
    for f in files:
        try:
            with _Image.open(f) as im:
                g = _corner_wm_grid(im)
            if g:
                grids.append(g)
        except Exception:
            pass
    if len(grids) >= 3:
        n = len(grids)
        consist_max = 0.0
        for c in range(len(grids[0])):
            k = sum(1 for g in grids if g[c])
            if k / n > consist_max:
                consist_max = k / n
        if consist_max > 0.6:
            errors.append(
                "右下角疑似平台水印残留：%d 张同位置亮区一致率 %.0f%%（阈值 60%%）。"
                "请用任意图片编辑器覆盖右下角固定区域后重跑。"
                % (n, consist_max * 100))
        elif consist_max > 0.35:
            warns.append("右下角亮区一致率 %.0f%%，疑似水印或固定 UI 元素，建议目视确认"
                         % (consist_max * 100))
        else:
            print("  ✅ 右下角水印检测      同位置亮区一致率 %.0f%%（<35%%，无固定水印）"
                  % (consist_max * 100))
    return errors, warns, []


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)


def _ai_tell_linter_path():
    """找假对比机检脚本：环境变量优先，其次 skill 默认安装位。找不到返回空串。"""
    p = os.environ.get(AI_TELL_LINTER_ENV, "").strip()
    if p:
        return p if os.path.exists(p) else ""
    default = Path.home() / ".workbuddy" / "skills" / "taishang-laojun" / "scripts" / "ai_tell_linter.py"
    return str(default) if default.exists() else ""


def check_ai_tell(plain, base):
    """跑一遍假对比机检。成功返回 (hard_blocks, soft_warnings)，脚本缺失返回 None。

    任何异常（脚本报错、输出不是 JSON、超时）都按「未执行」处理，
    绝不让一个外挂检查把发布流程卡死在这个环节。
    """
    linter = _ai_tell_linter_path()
    if not linter:
        return None
    cmd = [sys.executable, linter, "-", "--format", "json"]
    # 2026-11-10 修：base 是 article.html 所在目录（通常就是 pub/），
    # 而白名单习惯放稿件目录，两层都要找，否则摆在稿件根目录的白名单永远不生效。
    for _d in (base, os.path.dirname(os.path.abspath(base))):
        allow = os.path.join(_d, AI_TELL_ALLOW_NAME)
        if os.path.exists(allow):
            cmd += ["--allow", allow]
            break
    try:
        out = subprocess.run(cmd, input=plain, capture_output=True, text=True,
                             encoding="utf-8", timeout=60)
        data = json.loads(out.stdout or "{}")
    except Exception:
        return None
    return data.get("hard_blocks") or [], data.get("soft_warnings") or []


def run_check(args):
    errors, warns = [], []
    # 顾问级提醒：一定会显示，但**不参与 --strict 升级**，永不阻断发布。
    # 设立原因见第 12b 项注释——假对比几乎每篇都有，升成硬错等于把闸门调成噪音。
    advisories = []

    if not os.path.exists(args.html):
        print(f"❌ [ERROR] 找不到正文文件：{args.html}")
        return ["文件不存在"], [], []

    html = open(args.html, encoding="utf-8").read()
    base = os.path.dirname(os.path.abspath(args.html))

    # 1. 标题字节
    if args.title:
        n = len(args.title.encode("utf-8"))
        if n > 64:
            errors.append(f"标题 {n} 字节 > 64 上限（差 {n-64}），请缩短：{args.title}")
        else:
            print(f"✅ 标题字节            {n}/64")
    else:
        warns.append("未提供 --title，跳过 64 字节校验（建议在 checklist 里必填）")

    # 2. 正文长度
    ln = len(html)
    if ln > 20000:
        errors.append(f"正文 {ln} 字符 > 20000 上限，微信会拒收")
    elif ln < 800:
        warns.append(f"正文仅 {ln} 字符，过短，检查是否漏了章节")
    else:
        print(f"✅ 正文长度            {ln} 字符")

    # 2.5 未填占位（占位会原样发给读者，且污染 ima 问答召回）
    ph_hits = []
    for _i, _line in enumerate(html.splitlines(), 1):
        _plain = re.sub(r"<[^>]+>", "", _line).replace("&nbsp;", " ")
        _plain = re.sub(r"`[^`]*`", "", _plain).strip()
        if not _plain:
            continue
        for _p in PLACEHOLDER_PATTERNS:
            if re.search(_p, _plain):
                ph_hits.append((_i, _plain[:80]))
                break
    if ph_hits:
        _detail = "\n        - ".join("第 %d 行：%s" % (i, s) for i, s in ph_hits[:6])
        errors.append(
            "正文有 %d 处未填占位，禁止发表（补齐真实内容，或删掉那一段）：\n        - %s"
            % (len(ph_hits), _detail))
    else:
        print("✅ 无未填占位          正文里没有待补 / TODO 类残留")

    # 3. 禁用样式
    low = html.lower()
    hit = [msg for pat, msg in BANNED if pat.lower() in low]
    if hit:
        errors.append("检测到微信会剥离的写法：\n        - " + "\n        - ".join(sorted(set(hit))))
    else:
        print("✅ 内联样式合规        无 <style>/class/flex/grid/伪元素")

    # 3b. 装饰竖边（2026-11-11 补，复核时第三次指出）
    #     事故链：h2 的竖线 11-09 删了 → callout 的竖线也删了 → 指令框的 border-left
    #     一直活到 11-12 的稿子上才被发现。三次都以为「竖线已经清了」，因为
    #     test_style_lock 那条断言始终是绿的：样例稿里没有围栏块。
    #     教训是守卫要装在产物这一端——渲染器里可能还有下一条路径没想到。
    #     editorial 是唯一出稿皮肤，产物里出现 border-left 就等于竖边回潮。
    _bars = len(re.findall(r"border-left", low))
    if _bars:
        _sample = re.findall(r"border-left:[^;\"]+", html)[:2]
        errors.append(
            "正文出现 %d 处 border-left 竖边（%s）。editorial 不挂彩色竖边："
            "框只用「浅底 + 1px 细边 + 8px 圆角」，层级交给字号/字重/留白。"
            "重出即可（python tools/bin/render_f.py --in draft.md --out pub/article.html）"
            % (_bars, "；".join(_sample)))
    else:
        print("✅ 无装饰竖边          正文里没有 border-left")

    # 3c. 反引号不许露给读者（2026-11-11 补，同批修竖线时发现）
    #     事故：正文写着「找 `ernie-5.5-flash-preview`」，两个斜撇原样发出去。
    #     render_f 的 inline() 当时只认 **，反引号没人转。现在行内代码渲染成等宽片、
    #     整段代码进框，产物里只要还剩反引号就是漏了。
    _ticks = strip_tags(html).count("`")
    if _ticks:
        errors.append(f"正文露出 {_ticks} 个反引号（Markdown 标记没转成样式）。"
                      f"行内代码应渲染成等宽片、整段代码应进框；重出即可")
    else:
        print("✅ 无反引号残留        行内代码已转样式")

    # 4. 原创锚点（品牌规则，默认关闭）
    #    开源版把专有栏目名做成外部注入的关键词表，仓库内不保留任何具体栏目标记；
    #    关键词、别名、合法名均由 GZH_CHECK_BRAND_* 环境变量提供，规则骨架不变：
    #    计数 → 与 --min-opinion 阈值比较 → 不足则报错。
    if args.brand_rules:
        nopin = sum(html.count(w) for w in BRAND_ANCHORS)
        need = max(1, args.min_opinion)
        if nopin < need:
            errors.append(f"原创锚点 {nopin} 处，需 ≥{need} 处（组件 ⑫），否则难以声明原创")
        else:
            print(f"✅ 原创锚点观点块        {nopin} 处")

    # 5. 本地图片存在性
    imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    missing = []
    for src in imgs:
        if src.startswith(("http://", "https://", "data:")):
            continue
        p = os.path.join(base, src.replace("./", ""))
        if not os.path.exists(p):
            missing.append(src)
    if missing:
        errors.append("引用的本地图片不存在（推送会失败）：" + "、".join(missing))
    else:
        print(f"✅ 正文图片            引用 {len(imgs)} 张，均存在")

    # 6. 推流红线：诱导互动话术（会被判营销号降权/限流）
    hits = [w for w in REDLINE_PHRASES if w in html]
    if hits:
        errors.append("检测到诱导互动话术（会降权/限流）：" + "、".join(hits)
                      + "\n        改为自然的开放式提问，见 references/growth.md 红线清单")
    else:
        print("✅ 无诱导互动话术      合规")

    # 6b. 破折号禁令（2026-11-02 补，发布标准第六节：平台把「——」渲染成「，，」）
    _plain_6 = strip_tags(html)
    dash_hits = _plain_6.count("——")
    if dash_hits:
        errors.append(f"破折号「——」出现 {dash_hits} 处（发布标准第六节全篇禁用，平台会渲染成「，，」），改成逗号/冒号/句号")
    else:
        print("✅ 无破折号            合规")

    # 6c. 系列编号禁令（2026-11-07 补）
    # 事故：稿子写「这是免费额度系列第 2 篇」，核实发现该题材已发 15 篇以上；
    # 且一天发 3 篇时中间会插别的系列，序号必然错位。改用真实事件故事线承接。
    _num_hits = re.findall(r"第\s*\d+\s*篇", _plain_6)
    if _num_hits:
        errors.append(f"出现系列编号 {len(_num_hits)} 处（{'、'.join(_num_hits[:3])}）。"
                      f"规则：禁止任何「第N篇」写法，无法核实真实序号且发表顺序不可控。"
                      f"改用故事线承接（如「10月27号我写过…这篇给原料」），预告只说内容不说序号")
    else:
        print("✅ 无系列编号          合规")

    # 6d. 栏目名口径（品牌规则，默认关闭）：别名 / 历史写法出现即报错
    if args.brand_rules:
        bad_alias = [w for w in BRAND_ALIASES if w in _plain_6]
        if bad_alias:
            errors.append("出现栏目别名 %s（应统一为「%s」）"
                          % ("、".join(bad_alias), BRAND_CANON or "统一栏目名"))
        else:
            print("✅ 栏目名口径          合规")

    # 「下一站」停用（2026-11-09）不在这里查：check.py 读的是渲染后的 HTML，
    # 而 render_f.py 已经把该标题跳掉了，这里永远查不到——查不到还留着，就是假闸。
    # 真正的卡口在 G3.yaml 的 g3-no-next-station（读正文 Markdown），只 WARN。

    # 7. 夸张表述（标题党嫌疑）
    hype = [w for w in HYPE_WORDS if w in html]
    if hype:
        warns.append(f"含夸张表述：{'、'.join(hype)}——标题承诺须与正文一致，否则被判标题党降权")
    else:
        print("✅ 无夸张表述          合规")

    # 8. 微信 SEO：关键词布局（搜一搜是被严重低估的长尾流量）
    plain = strip_tags(html)
    if args.keyword:
        kw = args.keyword
        in_title = kw in (args.title or "")
        cnt = plain.count(kw)
        head = plain[:400]
        if not in_title:
            warns.append(f"核心关键词「{kw}」未进标题（建议放前 15 字，直接影响搜一搜曝光）")
        if kw not in head:
            warns.append(f"核心关键词「{kw}」未出现在前 400 字，建议开头即点题")
        if cnt < 3:
            warns.append(f"核心关键词「{kw}」全文仅 {cnt} 次，建议自然出现 3–5 次（约每 400 字一次）")
        else:
            print(f"✅ 关键词布局          「{kw}」×{cnt}"
                  + ("，标题已含" if in_title else "（标题未含）"))
    else:
        warns.append("未指定 --keyword，跳过微信 SEO 检查（搜一搜长尾流量建议必做）")

    # 9. 完读率友好度：段落长度
    pblocks = re.findall(r"<p\b[^>]*>(.*?)</p>", html, re.S)
    lens = [len(strip_tags(b)) for b in pblocks]
    longest = max(lens, default=0)
    if longest > 220:
        warns.append(f"最长段落约 {longest} 字，建议拆到 ≤150 字/段（移动端完读率友好）")
    else:
        print(f"✅ 段落长度            最长约 {longest} 字")

    # 10. 配图数量（提升停留时长）
    if len(imgs) < 3:
        warns.append(f"正文配图 {len(imgs)} 张，建议 3–5 张（拉长阅读停留时长，利于进推荐池）")
    elif len(imgs) > 8:
        warns.append(f"正文配图 {len(imgs)} 张偏多，控制在 3–5 张更稳")

    # 11. 收藏钩子（触发「二次推荐」）
    if not any(h in html for h in COLLECT_HINTS):
        warns.append("缺收藏钩子（如「建议收藏，下次照着做」）——收藏触发二次推荐，等于多一轮免费流量")
    else:
        print("✅ 收藏钩子            有")

    # 12. 姿势级 AI 味量化（参考 references/editor_checklist.md，WARN 不阻断）
    if not plain:
        plain = strip_tags(html)
    sentences = [s.strip() for s in re.split(r"[。！？!?；;]", plain) if s.strip()]
    if sentences:
        slens = [len(s) for s in sentences]
        mean_len = sum(slens) / len(slens)
        cv = (statistics.pstdev(slens) / mean_len) if (len(slens) > 1 and mean_len) else 0.0
        conn = sum(plain.count(w) for w in CONN_WORDS)
        conn_density = conn / len(sentences)
        parens = plain.count("（") + plain.count("）") + plain.count("(") + plain.count(")")
        ai_hits = sum(plain.count(w) for w in AI_WORDS)
        flags = []
        if cv < 0.35:
            flags.append("句长变异系数 %.2f（<0.35，句子太均匀，像 AI 节拍器）" % cv)
        if conn_density > 0.4:
            flags.append("连接词密度 %.2f 个/句（>0.4，此外/然而/因此 堆砌）" % conn_density)
        if parens > 5:
            flags.append("括号 %d 个（>5，滥用打断阅读）" % parens)
        if ai_hits > 3:
            flags.append("高频 AI 词命中 %d 个（>3，赋能/格局/底层逻辑…）" % ai_hits)
        if flags:
            warns.append("AI 味姿势指标预警：" + "；".join(flags)
                         + "（详见 references/editor_checklist.md，仅提示不阻断）")
        else:
            print("✅ AI 味姿势指标       句长CV=%.2f 连接词%.2f/句 括号%d AI词%d"
                  % (cv, conn_density, parens, ai_hits))
    else:
        warns.append("正文过短，无法做 AI 味姿势量化")

    # 12b. 假对比句壳机检（2026-11-10 补，顾问级：一定显示，但永不阻断）
    #      「不是 A，是 B」是产线最顽固的 AI 腔，也是 deai-promax 判定的最高优先级三毒。
    #      它和上面第 12 条分开算：第 12 条看词面密度，这条看句式结构。
    #      ⚠️ 它绝不进 errors，也不进 warns（warns 会被 --strict 整体升级）：
    #         回测 11-01 起 14 篇在发稿，12 篇有命中、中位数 3 处，
    #         而发布链路默认带 --strict —— 升上去等于每篇都被拒，闸门作废。
    ai_tell = check_ai_tell(plain, base)
    if ai_tell is None:
        advisories.append("假对比机检未执行：找不到 ai_tell_linter.py"
                          "（检查 %s 或环境变量 %s）"
                          % ("~/.workbuddy/skills/taishang-laojun", AI_TELL_LINTER_ENV))
    else:
        hard, soft = ai_tell
        if hard:
            shown = hard[:AI_TELL_MAX_SHOW]
            detail = "\n        - ".join(
                "第 %s 行｜%s｜%s" % (h.get("line"), h.get("pattern"), str(h.get("text"))[:60])
                for h in shown)
            more = "" if len(hard) <= AI_TELL_MAX_SHOW else "\n        …另有 %d 处未列出" % (len(hard) - AI_TELL_MAX_SHOW)
            advisories.append("假对比句壳 %d 处（不是A而是B 一类，删前半句多半不损失信息）："
                              "\n        - %s%s\n        确需保留的句子写进 %s 后重跑"
                              % (len(hard), detail, more, AI_TELL_ALLOW_NAME))
        else:
            print("✅ 假对比句壳        0 处")
        if soft:
            print("   假对比软提醒        %d 处（空转词/句式，按语境判断，不单独报警）" % len(soft))

    # 13. 人味指标（2026-11-05）
    # AI 味不在词上，在人上。词面那层由上面第 12 条管，这一条管两个更硬的东西。
    prose_all = plain
    for cut in ("参考来源", "数据出处", "参考链接"):
        if cut in prose_all:
            prose_all = prose_all.split(cut)[0]
            break
    n_wo, n_ni = prose_all.count("我"), prose_all.count("你")
    zh_n = len(re.findall(r"[\u4e00-\u9fff]", prose_all))
    ratio = n_wo / (n_wo + n_ni) if (n_wo + n_ni) else 0.0
    exp_hits = len(re.findall(EXP_RE, prose_all))
    exp_density = exp_hits / zh_n * 1000 if zh_n else 0.0
    if zh_n >= 600:
        bad = []
        if ratio < PERSON_MIN_RATIO:
            bad.append("「我」只占人称 %.0f%%（我 %d / 你 %d）——读起来是说明书："
                       "一个什么都知道的讲解员对抽象的读者说话" % (ratio * 100, n_wo, n_ni))
        if exp_density < EXPERIENCE_MIN:
            bad.append("带日期的经历 %.1f 处/千字（我 %d 处）——没有「哪天、多少、报什么错」，"
                       "这篇的经验换个人也能写" % (exp_density, exp_hits))
        if bad:
            warns.append("人味不足：" + "；".join(bad)
                         + "（补 1 到 2 处「我试了什么、结果如何」即可，别通篇加）")
        else:
            print("✅ 人味指标            我占 %.0f%% / 经历 %.1f 处每千字"
                  % (ratio * 100, exp_density))

    # 14. 结构铁律（能拿走的东西 / 图注自包含 / 结尾给出口）
    # 机器判得粗，所以只 WARN：误判代价是多看一眼，漏判代价是又退一次稿。
    # 「答案前置」故意不做机器判：它靠句式判断太容易误报（叙事型开头也能答案前置），
    # 归人格提示词管，人在审稿时看第一屏就够。
    body = plain if plain else strip_tags(html)

    n_li = len(re.findall(r"<li\b", html))
    n_branch = sum(body.count(w) for w in BRANCH_HINTS)
    if imgs or n_li >= 3 or n_branch >= 2:
        print("✅ 能拿走的东西        图 %d 张 / 清单 %d 项 / 分岔 %d 处"
              % (len(imgs), n_li, n_branch))
    else:
        warns.append("没检测到「能拿走的东西」：既无配图、无 ≥3 项清单、也无按身份分岔的段落。"
                     "读完只有「哦，知道了」，就是搬运")

    caps = [c.strip() for c in re.findall(r"<p[^>]*>\s*▲\s*([^<]*)</p>", html)]
    bad_caps = [c for c in caps if any(b in c for b in CAPTION_BAD_REFS)]
    if bad_caps:
        warns.append("图注里有只在文章内成立的指向（%s）——读者存的是图不是文章，"
                     "改成自包含或写「见文末」" % "、".join(bad_caps[:2]))
    elif caps:
        print("✅ 图注自包含          %d 条图注均无内部指向" % len(caps))

    # 文末来源清单不算「结尾」——先切掉，否则每篇都会被误判
    prose = body
    for cut in ("参考来源", "数据出处", "参考链接"):
        if cut in prose:
            prose = prose.split(cut)[0]
            break
    tail = prose[-600:]
    if any(w in tail for w in EXIT_HINTS):
        print("✅ 结尾给出口          有")
    else:
        warns.append("结尾 600 字里没有可执行动作（落到「这件事花不了钱、花不了多久、你现在就能做」）"
                     "——只堆风险不给出路，读者读完只剩焦虑")

    # 标题自我指涉：老读者看得懂，新读者读不懂（人格里写了「不吹旧文」）
    self_ref = [w for w in ("我上个月", "上一篇", "我写过", "我之前说", "前几篇") if args.title and w in args.title]
    if self_ref:
        warns.append("标题带自我指涉（命中「%s」）——老读者有钩子，新读者读不懂；"
                     "涨粉靠新读者，可考虑换成「现在怎么样」的说法" % self_ref[0])

    # 6e. 正文禁 <h1> 重复标题（2026-11-07 老板定规则）
    # 微信发布时的 title 字段就是标题，正文再来一遍 = 读者第一眼看到上下两行同题。
    # 更危险的是「改了标题没同步正文」：两个标题不一致，读者直接看出破绽。
    # 旧逻辑反了（缺 h1 反而提醒），导致 render 加 --keep-title 后每篇都带 h1。
    if "<h1" in low:
        h1_txt = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
        h1_plain = re.sub(r"<[^>]+>", "", h1_txt[0]).strip() if h1_txt else ""
        errors.append(
            "正文出现 <h1> 大标题（「%s」）：标题栏已有标题，正文再写一遍就是重复。"
            "删掉正文首行的「# 标题」，标题只由发布时的 title 字段提供" % h1_plain[:30])
    else:
        print("✅ 正文无 h1 重复标题   合规")

    # 结尾留口子：用自然语言判，不认 💬/👇 这类模板标记——本产线不用那些组件，
    # 旧的两个检查（互动埋点 ⑭ / 结尾引导 ⑮）在每一篇上都报，等于把警报调成了噪音。
    if any(w in prose[-900:] for w in CTA_HINTS):
        print("✅ 结尾留口子          有")
    else:
        warns.append("结尾 900 字里没有一处让读者说话（留言 / 评论 / 发我 / 问我 一类）"
                     "——还没粉丝的时候，「下一篇讲什么」没人跟；一条真留言既是选题，也是推荐信号")

    if not any(m in html for m in SOURCE_MARKERS):
        warns.append("无来源标注（组件 ⑬，推荐文末「数据出处」小字块）——若内容明显借鉴他人，必须文末标注才可声明原创")
    else:
        print("✅ 来源标注            有")

    _check_record(args.html, warns, advisories)

    return errors, warns, advisories


# ── 写后记录：情绪共鸣 + 输出价值（2026-11-09 老板要求）─────────────────────
# 老板原话：「正文我们要的是情绪共鸣 + 输出价值，这个根本……文章写好之后也要
# 在记录文章的地方记录这两个内容，以后做复盘更好。」
#
# 为什么放在 check.py 而不是新做一个命令：
# 这个动作必须发生在「推草稿之前」，而 check.py 是那条路上唯一必跑的一步。
# 另起一个 tools/bin/audit_meta.py，结果一定是「想起来才跑」。
#
# 为什么只 WARN 不 ERROR：
# 记录是给复盘用的，卡住发表得不偿失；但加 --strict 会升级成 ERROR，
# 正式发布走 --strict 就等于强制。
#
# 格式约定「类型｜具体」：类型用来分组看数据（四类枚举），具体用来回忆这篇写了什么。
# 只写类型不写具体，等于只贴了个标签，复盘时还是不知道当时怎么想的。
EMOTION_TYPES = ("确定性利益", "反差打脸", "具体处境共鸣", "悬念", "无")
# 「无」是合法值：skill §十三 写明「情绪钩子不必每篇都有，价值出口是必须项」。
# B 篇那种热点报道硬套情绪，反而变成「不许编情绪」的反面。
VALUE_TYPES = ("可复用动作", "可核验事实", "判断尺子", "省下的成本")
RECORD_MIN_NOTE = 6      # 具体内容至少几个字，防「有｜无」式敷衍
RECORD_LEGACY = ("entry_type", "value_exit")


def _find_record(html_path: str):
    """找这篇稿的记录卡：产物在 pub/ 下时在上一层，直接生成时在同层。"""
    p = Path(html_path).resolve()
    for cand in (p.parent / "meta.json", p.parent.parent / "meta.json"):
        if cand.is_file():
            return cand
    return None


def _parse_record(raw: str):
    """「类型｜具体」→ (类型, 具体)。只认**第一个**竖线，后面的都算具体内容。

    为什么不按 `+` 切成多段：中文里 `+` 太常见（「4 个长期 + 2 个到期日」），
    切了就会把句子切碎，还会把半句话当成类型报错（这个坑当场踩过）。
    多类型时把主类型写在最前面，其余类型作为细节留在具体里即可——
    复盘分组只需要一个主类型。
    """
    text = str(raw or "").strip()
    for sep in ("｜", "|"):
        if sep in text:
            head, _, note = text.partition(sep)
            return head.strip(), note.strip()
    return text, ""


def _check_record(html_path: str, warns: list, advisories: list = None) -> None:
    """写后记录：情绪共鸣（emotion）/ 输出价值（value）缺了进 warns；
    E/V 三时点评分的「做完后」那一档缺了进 advisories（顾问级，永不阻断）。"""
    if not html_path:
        return
    meta_path = _find_record(html_path)
    if meta_path is None:
        warns.append("找不到记录卡 meta.json（情绪共鸣 / 输出价值还没记）——"
                     "建一个含 emotion、value 两个字段的 meta.json 放在稿件目录，复盘要用")
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        warns.append(f"记录卡 {meta_path.name} 读不出来（{exc}），情绪/价值没法核对")
        return
    if not isinstance(meta, dict):
        warns.append(f"记录卡 {meta_path.name} 不是对象，情绪/价值没法核对")
        return

    legacy = [k for k in RECORD_LEGACY if meta.get(k)]
    if legacy:
        warns.append(f"记录卡还在用旧字段名 {'、'.join(legacy)}——2026-11-09 起统一为 "
                     "emotion（情绪共鸣）与 value（输出价值），旧字段不会被任何工具读到")

    problems = []
    for key, label, allowed in (("emotion", "情绪共鸣", EMOTION_TYPES),
                                ("value", "输出价值", VALUE_TYPES)):
        raw = str(meta.get(key) or "").strip()
        if not raw:
            problems.append(f"缺 {key}（{label}）")
            continue
        head, note = _parse_record(raw)
        if not note:
            problems.append(f"{key} 只写了类型「{head}」，没写「具体是什么」（格式：类型｜具体）")
            continue
        if len(note) < RECORD_MIN_NOTE:
            problems.append(f"{key} 的「具体」太短（不足 {RECORD_MIN_NOTE} 字），复盘时想不起当时的意思")
        if head and head not in allowed:
            problems.append(f"{key} 的类型「{head}」不在可选范围（{' / '.join(allowed)}）")

    if problems:
        warns.append("写后记录不全：" + "；".join(problems) +
                     "（填在稿件目录 meta.json，例：\"emotion\": \"反差打脸｜读者也怕自己看不出差别\"）")
    else:
        print("✅ 写后记录            情绪共鸣 + 输出价值 都有")

    # E/V 三时点评分的「做完后」环节（2026-11-10 补）
    # 为什么放这里：2026-11-10 实测全库 104 篇，0 篇填过 e_score/v_score——
    # 规范写了没人跑，就永远不会有。检查必须落在推箱前唯一必跑的那一步上。
    # 口径**与假对比一致：顾问级，一定显示，永不阻断**。理由：存量 100 篇全缺，
    # 一旦进 errors 或 warns（会被 --strict 升级），等于每篇都被拒，闸门立刻作废。
    if advisories is None:
        advisories = []
    score_gaps = []
    scores = {}
    for key, label in (("e_score", "E 情绪共鸣"), ("v_score", "V 价值输出")):
        raw = meta.get(key)
        if raw is None or str(raw).strip() == "":
            score_gaps.append("缺 %s" % key)
            continue
        try:
            n = int(raw)
        except (TypeError, ValueError):
            score_gaps.append("%s 不是整数（现在是 %r）" % (key, raw))
            continue
        if not 0 <= n <= 5:
            score_gaps.append("%s 超出 0-5（现在是 %d）" % (key, n))
            continue
        scores[key] = n
    for key in ("e_note", "v_note"):
        if len(str(meta.get(key) or "").strip()) < RECORD_MIN_NOTE:
            score_gaps.append("缺 %s 或太短（要一句实证，不写形容词）" % key)

    if score_gaps:
        advisories.append(
            "E/V 打分未完成：" + "；".join(score_gaps) +
            "。做完后必须打 e_score / v_score（0-5）并写 e_note / v_note 一句实证，"
            "口径见 docs/standards/02 §三 §四")
    else:
        e, v = scores["e_score"], scores["v_score"]
        if e < 3 or v < 3:
            advisories.append(
                "E/V 低于推箱门槛：E%d V%d（规范要求 E≥3 且 V≥3）。分数已记，但这篇按标准"
                "不该推——补的是不足的那一侧，不是拿另一侧的高分去平均" % (e, v))
        else:
            print("✅ E/V 评分            E%d V%d（合计 %d）" % (e, v, e + v))


def main():
    ap = argparse.ArgumentParser(description="公众号草稿推前硬校验 / 贴图硬闸")
    ap.add_argument("--html", default="", help="正文 HTML 路径（长文校验）")
    ap.add_argument("--title", default="", help="文章标题（校验 64 字节）")
    ap.add_argument("--strict", action="store_true", help="软性提醒也升级为硬性错误")
    ap.add_argument("--min-opinion", type=int, default=1,
                    help="（品牌规则）原创锚点最少几处，默认 1；仅 --brand-rules 开启时生效")
    ap.add_argument("--brand-rules", action="store_true",
                    help="启用品牌规则（默认关闭）；锚点 / 别名关键词由 "
                         "GZH_CHECK_BRAND_ANCHORS / GZH_CHECK_BRAND_ALIASES 环境变量注入")
    ap.add_argument("--keyword", default="", help="核心关键词（微信搜一搜 SEO 布局检查）")
    ap.add_argument("--channel", default="",
                    help="渠道：greenbook（贴图/小绿书，别名 贴图、小绿书）；"
                         "不传 = 通用长文口径。该参数真正参与 --images 的分派")
    ap.add_argument("--images", default="",
                    help="图片目录。配合 --channel greenbook 走贴图硬闸"
                         "（体积下限/3:4/张数/品牌绿/水印）；不传 channel 走通用体检"
                         "（比例/体积上下限/序号连续/水印交集）")
    ap.add_argument("--fig-hue", default="",
                    help="配图配色体检：空格分隔的图片路径，第一个是封面，其余是正文配图。"
                         "查配图主色相是否跟随封面（偏差 ≤30°）。")
    ap.add_argument("--card-fonts", default="",
                    help="贴图渲染脚本或所在目录，体检字号是否低于可读下限（不传则跳过）")
    ap.add_argument("--cover", nargs="+", default=[],
                    help="封面图路径（一张或多张），体检是否为深色字卡")
    args = ap.parse_args()

    # 模式 0a：封面体检（只读，出完封面立刻能跑，不用等推草稿）
    # 2026-11-13 修：以前这里是「传了 --cover 就只查封面、查完 sys.exit(0)」。
    # 于是 `--html 错路径 --cover 封面` 会只查封面就打印「✅ 全部通过」，
    # 正文一条都没查（当天就踩到：render_f 因缺配图没写出 html，check 仍报全过）。
    # 现在：只查封面时才收口，同时还传了别的检查项就继续往下查，结论合并。
    _cover_bad = []
    if args.cover:
        print("🔍 封面体检（%d 张）" % len(args.cover))
        problems = audit_covers(args.cover)
        if problems:
            _cover_bad = problems
            print("\n❌ 封面不合规：")
            for p in problems:
                print("    - " + p)
            print("\n确实是无生图能力时的兜底，push_draft.py 加 --allow-textcard 才放行。")
        else:
            print("✅ 封面体检通过")
        if not (args.html or args.images or args.card_fonts or args.fig_hue):
            sys.exit(1 if _cover_bad else 0)

    # 模式 0c：配图配色体检（只读）——查配图主色相是否跟随封面
    if args.fig_hue:
        parts = args.fig_hue.split()
        if len(parts) < 2:
            print("❌ --fig-hue 至少要两个路径：封面 + 一张配图")
            sys.exit(2)
        print("🔍 配图配色体检（跟随封面）：")
        probs = audit_figure_hue(parts[0], parts[1:])
        if probs:
            print("\n💡 顾问提醒（不改完也能发，但这是「同一篇两套色系」的典型症状）：")
            for p in probs:
                print("    - " + p)
            print("\n判据见 docs/配图标准.md §10.5。")
            if not (args.html or args.images or args.card_fonts or args.cover):
                sys.exit(0)
        else:
            print("✅ 配图配色与封面同色系")
            if not (args.html or args.images or args.card_fonts or args.cover):
                sys.exit(0)

    # 模式 0b：贴图字号体检（只读，不改稿）
    if args.card_fonts:
        canvas, hits, color_hits, n_files, n_font = audit_card_fonts(args.card_fonts)
        floor = round(CARD_MIN_CSS * canvas / CARD_SCREEN_W)
        print("🔍 贴图字号体检：%s" % args.card_fonts)
        print("   画布宽 %dpx  可读下限 %dpx（≈ 手机 %d CSS px）"
              % (canvas, floor, CARD_MIN_CSS, ))
        # 假 PASS 修复（2026-11-11）：以前扫到 0 个脚本、或者一个字号都没匹配上，
        # 也会高高兴兴打印「✅ 都达标」。2026-11-11 那批贴图走 cards.json，
        # 目录里只有 json 没有 .py，于是被显示成「两项都达标」，而实际有
        # 34px/30px 的字号和 1.87:1/2.47:1 的颜色。**没查 ≠ 查了没问题。**
        if n_files == 0:
            print("\n❌ 这里没有可检查的渲染脚本（目录里没有 .py）。")
            print("   如果这批贴图是从 cards.json 生成的，字号在渲染器里，"
                  "请改指渲染器，例如：--card-fonts tools/nsp/render_cards.py")
            sys.exit(2)
        if n_font == 0:
            print("\n❌ 扫了 %d 个脚本，但一个字号调用都没认出来。" % n_files)
            print("   两种可能，处理方式不同：")
            print("   ① 写法超出识别范围（变量拼接、字典取值、字号来自命令行参数）——"
                  "本档静态扫描不适用，请人工确认字号下限；")
            print("   ② 该脚本根本不画文字（如只画框和箭头的标注工具）——"
                  "这种情况下不传 --card-fonts 即可。")
            print("   **不能当作达标**：没查 ≠ 查了没问题。")
            sys.exit(2)
        if hits:
            print("\n❌ 发现 %d 处字号过小：" % len(hits))
            for name, lineno, px, fl, css, code in hits:
                print("    %s:%d  %dpx（下限 %dpx，手机仅 %.1fpx）  %s"
                      % (name, lineno, px, fl, css, code))
            print("\n改了会挤就删字，不要缩字号。判据见 docs/配图标准.md §3.1")
        if color_hits:
            print("\n❌ 发现 %d 处低对比度文字色：" % len(color_hits))
            for name, lineno, rgb, ratio, code in color_hits:
                print("    %s:%d  %s 对奶油白底仅 %s  %s"
                      % (name, lineno, rgb, ratio, code))
            print("\n小字需 ≥4.5:1。字号够大但颜色太浅，读起来一样费劲——"
                  "这是「字变大了还是发虚」的真正原因。判据见 docs/配图标准.md §3.4")
        if not hits and not color_hits:
            print("✅ 未发现低于下限的字号，文字色对比度均达标")
            sys.exit(0)
        sys.exit(1)

    if args.images:
        # --channel 现在是**真参数**，不再只是装饰（2026-11-14 修）。
        # 原来只有 :1168 一处定义，`grep -n "args.channel" check.py` 零命中——
        # 传不传 channel 都走 greenbook 闸，而 --help 写着「与 --channel greenbook 搭配」，
        # 用户会误以为不传就不是那个闸。
        from channels import is_greenbook
        _ch = (args.channel or "").strip()
        if _ch and not is_greenbook(_ch) and _ch.lower() not in ("longform", "长文", "article"):
            print("❌ 不认识的渠道：%s" % _ch)
            print("   可用：greenbook（别名 贴图 / 小绿书 / tie）、longform（长文，可省略）")
            sys.exit(2)
        if is_greenbook(_ch):
            errors, warns, advisories = check_greenbook_images(args.images)
        else:
            errors, warns, advisories = check_images_generic(args.images)
    else:
        if not args.html:
            print("❌ 必须提供 --html（长文）或 --images（贴图）之一")
            sys.exit(1)
        print(f"🔍 推前硬校验：{os.path.basename(args.html)}")
        errors, warns, advisories = run_check(args)

    if warns:
        print("\n⚠️  软性提醒：")
        for w in warns:
            print(f"    - {w}")
        if args.strict:
            errors.extend(warns)

    # 顾问级提醒：只显示，不升级、不阻断。放在软性提醒之后、结论之前，
    # 让它一定被看见，但不会让一篇稿子因为句式重复发表不了。
    if advisories:
        print("\n💡 顾问提醒（不改完也能发，但值得看一眼）：")
        for a in advisories:
            print(f"    · {a}")

    print("\n" + "=" * 46)
    if _cover_bad:
        errors = list(errors) + ["封面不合规 %d 张" % len(_cover_bad)]
    if errors:
        print("❌ FAIL —— 未通过硬性卡口，禁止 push：")
        for e in errors:
            print(f"    ✗ {e}")
        print("=" * 46)
        # 回显**用户刚才真正敲的那条命令**（2026-11-14 修）。
        # 原来写死 `.venv\Scripts\python scripts/check.py`——那是内部产线布局，
        # 本仓库里既没有 .venv 也没有 scripts/，用户照着复制必然 command not found。
        _argv = " ".join(sys.argv[1:]) or "--html article.html --title 标题"
        print("👉 修完上面每一条再重跑：")
        print("   python %s %s" % (os.path.basename(sys.argv[0]), _argv))
        sys.exit(1)

    print("✅ PASS —— 硬性卡口全部通过，可以推草稿。")
    print("   过清单 ≠ 高枕无忧：发表前仍须人工确认「表达是自己的」，并手动开启「声明原创」。")
    print("=" * 46)


if __name__ == "__main__":
    main()
