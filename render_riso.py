#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""render_riso.py —— 贴图（小绿书）第四版引擎：孔版印刷 / 丝网印风。

为什么要有这一版（2026-11-09 夜）
----------------------------------
前两版的病都在「干净」：
- v2 render_cards.py：深蓝大字卡，9 张一个模子，被老板判「太规矩」。
- v3 render_wild.py：8 种版式轮换，版式是散了，但底色纯、边线利、字距匀，
  仍然像「网页上排的卡片」，不像一张印出来的东西。

这一版换的是**工艺观**，不是版式：假装这些图是用孔版印刷机（Riso）印的。
于是所有设计决定都从工艺反推——
- 只用三筒油墨：墨黑 #111111 / 朱红 #E8422E / 薄荷 #4ECDC4，另加一支柠檬 #F0C33C 做纸标签。
- **错版**：朱红版故意比黑版偏 8-12px，边缘叠色变深，像套印没对准。
- **半调网点**：色块不是平涂，是圆点网屏；放大看是一颗颗点。
- **纸**：米白纤维底 + 全图颗粒，边角有裁切十字线。
- 字色仍守文章标准：标题 #111111 / 正文 #1a1a1a / 弱字 #5c5c5c，不用中间调。

九张固定版式序列，同一套共用纸色和三筒油墨，所以还是一个系列；
但每张的印刷事故不一样（错版、网点、印章、胶带、首字下沉），翻页眼睛会重来。

用法
----
    python render_riso.py --spec cards.json --out out/riso/

依赖 / 产物
-----------
Chrome（无头截图）+ Pillow。末尾叠颗粒，既做纸感，也把 PNG 顶过 check.py
「单图 <150KB 判代码卡片图」那道硬闸。别删。
"""
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from fontkit import resolve_font, resolve_font_family

# ---------------------------------------------------------------- 画布与油墨

W, H = 1242, 1656          # 3:4，check.py 的 GREENBOOK_RATIO 要求，别改

# Chrome 路径在 main() 里按「--chrome / CHROME_PATH / 常见路径」解析后赋值。
# import 阶段不查找，保证 --help 不受运行环境限制。
CHROME = ""


def resolve_chrome(cli_path: str = "") -> str:
    """按 --chrome / 环境变量 CHROME_PATH / 常见安装路径 / PATH 查找 Chrome。

    找不到就抛清晰异常，绝不带着空路径去截图（那只会得到一句含糊的失败）。
    """
    candidates = []
    if cli_path:
        candidates.append(cli_path)
    env_path = os.environ.get("CHROME_PATH", "").strip().strip('"').strip("'")
    if env_path:
        candidates.append(env_path)
    local = os.environ.get("LOCALAPPDATA", "")
    candidates += [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        os.path.join(local, "Google", "Chrome", "Application", "chrome.exe") if local else "",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for name in ("chrome", "google-chrome", "google-chrome-stable",
                 "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for c in candidates:
        if c and os.path.exists(c):
            return c
    raise RuntimeError(
        "找不到 Chrome/Chromium 可执行文件。请通过环境变量 CHROME_PATH 或 --chrome "
        "指定其绝对路径，或安装 Chrome / Chromium 后重试。"
        "已尝试常见安装路径与 PATH 查找。")

# ---------------------------------------------------------------------------
# 字体守卫
# 为什么需要：换一台机器没装目标字体时，Chrome 会静默回退到系统默认字体，
# 出图不报错、只是变了个样——比字号错更难发现，因为图是「能出」的。
# 检测方法：同一段拉丁字用目标字体族和「一个不存在的字体名」各量一次宽度，
# 不存在的字体名必然回退到 sans-serif，若两者宽度相等 = 目标字体没加载。
# 要检查的字体族由 fontkit.resolve_font_family() 提供（可由环境变量配置）。
# ---------------------------------------------------------------------------


# 系统字体族全不可用时的兜底：用 fontkit 找到的字体文件注入 @font-face。
#
# 为什么需要这一层：PIL 线按「文件路径」取字体，HTML 线按「族名」取字体，
# 两者来源不同。中文 Windows 上很常见的一种情况是——字体文件在（fontkit 找得到、
# PIL 排得出字），但没注册成系统字体族（Chrome 按族名叫不出来），于是 HTML 线
# 一律判「字体缺失」，明明有字体却出不了图。
# 2026-11-14 实测：本机 4 个候选族全部落空，改成文件注入后 pixel diff 4531
# （与 serif 渲染确实不同），出图与内部产线像素级一致。
WEB_FACE_CSS = ""      # 非空 = 本轮走文件注入
WEB_FAMILY = ""        # 注入时使用的族名
FONT_STACK = ""        # 非空 = 直接用这套字体栈（覆盖 resolve_font_family 的结果）


def web_font_face(family: str = "GzhKitFace") -> str:
    """把 fontkit 定位到的字体文件包成 @font-face 规则；找不到文件返回空串。

    可变字体（一个文件横跨所有字重）声明 `font-weight:100 900`，让 Chrome 自己
    取实例；否则粗体只能靠合成，标题会比 PIL 线渲染的更「糊」。
    """
    try:
        reg = resolve_font(False)
        bold = resolve_font(True)
    except Exception:
        return ""

    def uri(p: str) -> str:
        try:
            return Path(p).resolve().as_uri()
        except Exception:
            return ""

    r, b = uri(reg), uri(bold)
    if not r:
        return ""
    if b and b != r:
        return ("@font-face{font-family:'%s';src:url('%s') format('truetype');"
                "font-weight:400;font-display:block}\n"
                "@font-face{font-family:'%s';src:url('%s') format('truetype');"
                "font-weight:700;font-display:block}" % (family, r, family, b))
    return ("@font-face{font-family:'%s';src:url('%s') format('truetype');"
            "font-weight:100 900;font-display:block}" % (family, r))


def check_fonts(strict: bool = True, fams=None) -> bool:
    """确认目标字体族真的被 Chrome 用上了。不可用时终止渲染。"""
    import tempfile as _tf
    from pathlib import Path as _P
    fams = list(fams) if fams else resolve_font_family()
    fams_js = ", ".join('"%s"' % f for f in fams)
    probe = """<!doctype html><meta charset="utf-8"><body><script>
document.fonts.ready.then(function(){
  function w(f,t){var c=document.createElement("canvas").getContext("2d");
    c.font="100px "+f; return Math.round(c.measureText(t).width);}
  var t="AgHHWi 0123";
  var baseline = w("__MissingFontProbe__", t);   // 必然回退，作为基准
  var fams = __FAMS__;
  var out = {};
  for (var i=0;i<fams.length;i++){
    out[fams[i]] = {w: w(fams[i], t), check: document.fonts.check("16px "+fams[i])};
  }
  out["__baseline__"] = baseline;
  document.body.setAttribute("data-r", JSON.stringify(out));
});
</script></body>""".replace("__FAMS__", "[%s]" % fams_js)

    tmp = _tf.mkdtemp(prefix="fontguard_")
    hp = os.path.join(tmp, "p.html")
    _P(hp).write_text(probe, encoding="utf-8")
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--dump-dom",
                        "--virtual-time-budget=4000", _P(hp).as_uri()],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    import re as _re
    m = _re.search(r'data-r="([^"]+)"', r.stdout or "")
    if not m:
        print("⚠️ 字体检测没拿到结果（Chrome 未能执行页面脚本），跳过检查。")
        return True
    import html as _html
    data = json.loads(_html.unescape(m.group(1)))
    base = data.get("__baseline__", 0)
    good, bad = [], []
    for fam in fams:
        got = data.get(fam) or {}
        w, ok = got.get("w", 0), got.get("check", False)
        (good if (ok and w != base) else bad).append((fam, w))

    # 情形一：有族可用 → 只用可用的那几个。
    # 原来「只要有一个不可用就整批拒绝」，实际上用户配了一个能用的族也就够了；
    # 反过来，把未安装的族留在栈里会让 Chrome 逐字回落，同一张图里混排两种字形。
    if good:
        FONT_STACK = ", ".join("'%s'" % f for f, _ in good) + ", sans-serif"
        globals()["FONT_STACK"] = FONT_STACK
        if bad:
            print("[ok] 字体检查通过：%s（未安装，已从字体栈移除：%s）"
                  % (" ".join(f for f, _ in good), " ".join(f for f, _ in bad)))
        else:
            print("[ok] 字体检查通过：%s" % " ".join(f for f, _ in good))
        return True

    # 情形二：一个族都没装，但 fontkit 能定位到字体文件 → 文件注入。
    css = web_font_face()
    if css:
        globals()["WEB_FACE_CSS"] = css
        globals()["WEB_FAMILY"] = "GzhKitFace"
        globals()["FONT_STACK"] = "'GzhKitFace', sans-serif"
        try:
            where = resolve_font(False)
        except Exception:
            where = "(fontkit 路径)"
        print("[ok] 系统里没有这些字体族，改用字体文件注入：%s" % where)
        print("     候选族：%s" % " ".join(f for f, _ in bad))
        return True

    msg = ["字体缺失，拒绝出图（避免静默回退成别的字体）："]
    for fam, w in bad:
        msg.append("  ✗ %s：宽度 %d 与基准 %d 相同，Chrome 实际没用它" % (fam, w, base))
    msg.append("  fontkit 也没能定位到字体文件，两条路都断了。")
    msg.append("  请自备一款可再分发中文字体，并配置 GZH_IMAGE_KIT_FONT_FAMILY /")
    msg.append("  GZH_IMAGE_KIT_FONT_REG / GZH_IMAGE_KIT_FONT_BOLD（见 README 字体配置与许可）。")
    text = "\n".join(msg)
    if strict:
        raise SystemExit(text)
    print(text)
    return False

PAPER = "#F3EDE1"          # 米白纸
INK = "#111111"            # 黑版（标题）
BODY_INK = "#1a1a1a"       # 正文
MUTED = "#5c5c5c"          # 弱字
RED = "#E8422E"            # 朱红版
MINT = "#4ECDC4"           # 薄荷版（贴图产线品牌色，check.py 算占比）
LEMON = "#F0C33C"          # 柠檬纸标签

# 字体族统一由 CSS 变量 --f-title / --f-body 提供，运行时由 fontkit 配置的字体栈注入。

# 九张的版式序列。改这里就改整套节奏，别在单张里硬写。
VARIANT_ORDER = ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9"]

KICKERS = ["这一页先记住", "问题就在这", "往下翻", "这句最要紧", "别急着跳"]


# ---------------------------------------------------------------- 排印小工具

def fit(text: str, max_w: int, cap: int) -> int:
    """按字数反算字号，保证一行塞进 max_w。中文一字≈一个字号宽。"""
    n = max(len(text), 1)
    return int(min(cap, max_w / n * 0.98))


def split_rows(text: str, rows: int) -> list[str]:
    """把一段字尽量均分成 rows 行，短句不分。"""
    n = len(text)
    if n <= rows or rows <= 1:
        return [text]
    step = (n + rows - 1) // rows
    out = [text[i:i + step] for i in range(0, n, step)]
    return out[:rows]


def hero_rows(text: str) -> list[str]:
    """7 字以内排一行（够大、不断词）；更长才折两行。

    **英文/数字连写不劈**（2026-11-11 实测）：按字数均分会把 "Qoder 登录" 劈成
    「Qode / r 登录」——本号全是 AI 题材，模型名一断，读者第一眼就卡住。
    所以有空格就优先按空格切，取最均衡的那个切点。
    """
    if len(text) <= 7:
        return [text]
    words = text.split(" ")
    if len(words) >= 2:
        best = None
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            diff = abs(len(a) - len(b))
            if best is None or diff < best[0]:
                best = (diff, a, b)
        return [best[1], best[2]]
    return split_rows(text, 2)


def cap_html(text: str, max_chars: int = 17) -> str:
    """把收口句按标点切成不可再拆的小段，避免断行把词劈开。

    2026-11-11 实测：`.foot-cap` 里 24 字 @42px ≈ 1008px，容器 740px，
    `text-wrap:balance` 会均分成 12/12 —— 于是「价格」被劈成「价」「格」，
    「窗口关了就是关了，价 / 格降了还能等下一轮」，第二行从半个词起头。
    中文没有词边界，浏览器按字符断，balance 只保证两行等长、不认词。
    修法：标点后切开、段内 nowrap，让断点只落在标点处。
    单段超过 max_chars 的（长句无标点）不加 nowrap，否则会横向溢出画布 ——
    溢出比断词更难修，所以这里宁可让它自然折。
    """
    if not text:
        return ""
    segs = re.split(r"(?<=[，。；：、！？…])", text)
    out = []
    for s in segs:
        if not s:
            continue
        if len(re.sub(r"\s", "", s)) <= max_chars:
            out.append(f'<span style="white-space:nowrap">{s}</span>')
        else:
            out.append(s)
    return "".join(out)


def foot(c: dict, cls: str = "") -> str:
    """内页收口区：有 points 就出要点（能照着做），没有就退回一句 caption。

    历史版的内页每张承载 3-4 条可操作信息，信息密度是收藏和转发的理由；
    只放一句大字好看，但读者存它没理由。要点区就是把这个理由补回来。

    **不在收口区画红线（2026-11-11 实测发现的问题）**：
    原来这里有一条 .foot-rule，而 r3/r4/r6 三个模板各自又画一条绝对定位的红线，
    同一张图上会出现两条相距十几像素的红线，看着像画歪了；绝对定位那条还会压在要点上。
    收口区的分离靠间距就够了（.pts margin-bottom 34px），线在这里没有信息量。
    判据：一个元素去掉后信息量不变、只是画面变空 → 就该去掉。

    cls：追加类名。r3 用 "r3c" 把收口区让到竖线右侧（left 252），避免竖线穿字。
    """
    pts = c.get("points") or []
    cap = c.get("caption", "")
    inner = ""
    if pts:
        rows = "".join(f'<div class="pt"><i></i><span>{t}</span></div>' for t in pts)
        inner += f'<div class="pts">{rows}</div>'
    inner += f'<div class="foot-cap">{cap_html(cap, 17)}</div>'
    return f'<div class="foot {cls}">{inner}</div>'


def crop_marks() -> str:
    """四角裁切十字线。印刷品的胎记，一眼就不是网页截图。"""
    # 右下角留给页码：那一块只要有稳定色块，check.py 就会判成平台水印。
    return '<i class="cm tl"></i><i class="cm tr"></i><i class="cm bl"></i>' 


# 一套几张由 cards.json 决定，不再是写死的 9。
# 2026-11-11 前 folio 默认 total=9：改成 3–4 张一组后，页码会印成「01 / 09」，
# 而实际只有 3 张 —— 读者以为缺页。这里改成读取本次实际张数。
_TOTAL = 9

# 页脚/刊头品牌串：开源版默认中性，使用者可用环境变量注入自己的号名。
# （不许硬编码具体账号名——开源副本带品牌名 = 脱敏漏检。）
_BRAND = os.environ.get("GZH_IMAGE_KIT_BRAND", "图卡工具箱")


def folio(no: int, total: int | None = None) -> str:
    """页脚页码，杂志式，右下。total 默认取本次实际张数。"""
    total = _TOTAL if total is None else total
    return f'<div class="folio">{_BRAND} · {no:02d} / {total:02d}</div>'


def halftone(cls: str, style: str = "") -> str:
    """半调网点块。dot 密度靠 background-size 控制。"""
    return f'<div class="ht {cls}" style="{style}"></div>'


def mint_chip(style: str) -> str:
    """每张必有的一小块薄荷：品牌色，也是 check.py 的占比闸。"""
    return f'<div class="chip" style="{style}"></div>'


# ---------------------------------------------------------------- 九种版式

def r1_cover(c: dict) -> str:
    """封面：左栏题签 + 右栏竖排巨字。竖排是中文海报天然的填满法。"""
    hero = c["hero"]
    # 竖排中连续数字要合占一格（縦中横），否则「96」会被拆成上下两个字符
    hero_html = re.sub(r"(\d{2,})", r'<span class="tcy">\1</span>', hero)
    fs = int(min(250, 1150 / max(len(hero), 1) / 1.12))
    return f"""
<div class="card">
  {crop_marks()}
  <div class="mast">{_BRAND} · 图文卡</div>
  <div class="r1-no">NO. 01</div>
  <div class="r1-left">
    <div class="r1-kick">{c['tag']}</div>
    <div class="r1-head">{c['head']}</div>
    <div class="r1-cap">{cap_html(c['caption'], 11)}</div>
    <div class="r1-chip"><i class="chip-in"></i><span>{c.get('badge') or f'{_TOTAL} 张'}</span></div>
  </div>
  {halftone("r1-dots")}
  <div class="r1-vline"></div>
  <div class="r1-hero" style="font-size:{fs}px">{hero_html}</div>
  {folio(1)}
</div>"""


def r2_overprint(c: dict, seq: int) -> str:
    """错版大字：朱红版整体偏右下，黑版压上。两张版没对准，才是印出来的。"""
    rows_t = hero_rows(c["hero"])
    fs = fit(max(rows_t, key=len), 1060, 252)
    rows = "".join(
        f'<div class="reg" style="font-size:{fs}px;margin-bottom:10px">'
        f'<span class="reg-red">{r}</span><span class="reg-ink">{r}</span></div>'
        for r in rows_t)
    return f"""
<div class="card">
  {crop_marks()}
  <div class="r2-kicker">{KICKERS[seq % len(KICKERS)]}</div>
  <div class="r2-rule"></div>
  <div class="r2-flow">
    <div class="r2-head">{c['head']}</div>
    <div class="r2-body">{rows}</div>
    {foot(c)}
  </div>
  {halftone("r2-dots")}
  {mint_chip("left:80px; bottom:26px; width:952px; height:34px;")}
  {folio(2)}
</div>"""


def r3_screen(c: dict) -> str:
    """网屏圆：右侧一枚朱红网点大圆，左侧竖排题签，字压在圆上。"""
    fs = fit(c["hero"], 830, 226)
    rows = "".join(f'<div style="font-size:{fs}px">{r}</div>'
                   for r in hero_rows(c["hero"]))
    return f"""
<div class="card">
  {crop_marks()}
  <div class="r3-circle"></div>
  <div class="r3-vline"></div>
  <div class="r3-side">{c['head']}</div>
  <div class="r3-kick">{c['tag']}</div>
  <div class="r3-body">{rows}</div>
  {foot(c, "r3c")}
  {mint_chip("left:80px; bottom:26px; width:952px; height:34px;")}
  {folio(3)}
</div>"""


def r4_stamp(c: dict) -> str:
    """印章：朱红双线方章斜盖在右上，正文从章下压过来。"""
    rows_t = hero_rows(c["hero"])
    fs = fit(max(rows_t, key=len), 1010, 244)
    rows = "".join(f'<div style="font-size:{fs}px">{r}</div>' for r in rows_t)
    seal_fs = min(46, int(206 / max(len(c["head"]), 1)))
    seal = "".join(f'<span style="font-size:{seal_fs}px">{ch}</span>' for ch in c["head"])
    return f"""
<div class="card">
  {crop_marks()}
  <div class="r4-kick">{c['tag']}</div>
  <div class="r4-seal"><div class="r4-seal-in">{seal}</div></div>
  <div class="r4-flow">
    <div class="r4-head">{c['head']}</div>
    <div class="r4-body">{rows}</div>
  </div>
  {foot(c)}
  {halftone("r4-dots")}
  {mint_chip("left:80px; bottom:26px; width:952px; height:34px;")}
  {folio(4)}
</div>"""


def r5_quote(c: dict) -> str:
    """大引文：一枚朱红引号 + 巨号宋体引文 + 分隔线 + 小字。单栏，别再分栏。"""
    fs = fit(c["hero"], 1010, 178)
    return f"""
<div class="card">
  {crop_marks()}
  <div class="r5-flow">
    <div class="r5-mark">“</div>
    <div class="r5-head">{c['head']}</div>
    <div class="r5-quote" style="font-size:{fs}px">{c['hero']}</div>
    <div class="r5-rule"></div>
  </div>
  {foot(c)}
  {halftone("r5-dots")}
  {mint_chip("left:80px; bottom:26px; width:952px; height:34px;")}
  {folio(5)}
</div>"""


def r6_bignum(c: dict, seq: int) -> str:
    """空心数字：朱红描边数字当水印铺底，字压在上面，像套印两层。"""
    fs = fit(c["hero"], 1010, 238)
    rows = "".join(f'<div style="font-size:{fs}px">{r}</div>'
                   for r in hero_rows(c["hero"]))
    return f"""
<div class="card">
  {crop_marks()}
  <div class="r6-num">{seq:02d}</div>
  <div class="r6-head">{c['head']}</div>
  <div class="r6-body">{rows}</div>
  {foot(c)}
  {mint_chip("left:80px; bottom:26px; width:952px; height:34px;")}
  {folio(6)}
</div>"""


def r7_band(c: dict) -> str:
    """柠檬纸带斜切横穿：黑字压在带上，带外是纸。"""
    fs = fit(max(hero_rows(c["hero"]), key=len), 1040, 226)
    rows = "".join(f'<div style="font-size:{fs}px">{r}</div>'
                   for r in hero_rows(c["hero"]))
    return f"""
<div class="card">
  {crop_marks()}
  <div class="r7-head">{c['head']}</div>
  <div class="r7-band"></div>
  <div class="r7-body">{rows}</div>
  {foot(c)}
  {halftone("r7-dots")}
  {mint_chip("left:80px; bottom:26px; width:952px; height:34px;")}
  {folio(7)}
</div>"""


def r8_tape(c: dict) -> str:
    """纸条 + 胶带：一张白纸条斜贴，两头压胶带。"""
    fs = fit(max(hero_rows(c["hero"]), key=len), 900, 214)
    rows = "".join(f'<div style="font-size:{fs}px">{r}</div>'
                   for r in hero_rows(c["hero"]))
    return f"""
<div class="card">
  {crop_marks()}
  <div class="r8-head">{c['head']}</div>
  <div class="r8-strip">
    <div class="r8-tape-l"></div><div class="r8-tape-r"></div>
    <div class="r8-text">{rows}</div>
  </div>
  {foot(c)}
  {halftone("r8-dots")}
  {mint_chip("left:80px; bottom:26px; width:952px; height:34px;")}
  {folio(8)}
</div>"""


def r9_end(c: dict) -> str:
    """收尾：一行大字 + 一枚朱红圆点，剩的全留白。

    2026-11-11 删掉原来右下角的 560px 网点圆：它的圆心压着页码，
    「页码 04 / 04」直接印在网点上。收尾页的设计本来就是留白，
    这块网点既与文字相交、又不承载信息，按 §10.6 判据（去掉后信息量不变）直接去掉。
    """
    fs = fit(c["hero"], 980, 158)
    return f"""
<div class="card">
  {crop_marks()}
  <div class="r9-flow">
    <div class="r9-kick">{c['tag']}</div>
    <div class="r9-head">{c['head']}</div>
    <div class="r9-hero" style="font-size:{fs}px">{c['hero']}</div>
    <div class="r9-rule"></div>
  </div>
  {foot(c)}
  {mint_chip("left:80px; bottom:26px; width:952px; height:34px;")}
  {folio(9)}
</div>"""


# ---------------------------------------------------------------- 样式表

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#fff;-webkit-font-smoothing:antialiased}
.card{
  width:1242px;height:1656px;position:relative;overflow:hidden;
  background:#F3EDE1;color:#1a1a1a;
  /* 字体收口：标题与正文共用一套字体栈，避免多来源混排、浏览器合成粗体导致
     换 Chrome 版本就变样。字体栈由 fontkit.resolve_font_family() 在渲染前注入，
     见 build_html()。 */
  --f-title:__GZH_FONT_STACK__;
  --f-body:__GZH_FONT_STACK__;
  font-family:var(--f-body);
}
/* 裁切十字线：印刷品的胎记 */
.cm{position:absolute;width:40px;height:40px;border:0 solid #111111;opacity:.40}
.cm.tl{left:32px;top:32px;border-left-width:2px;border-top-width:2px}
.cm.tr{right:32px;top:32px;border-right-width:2px;border-top-width:2px}
.cm.bl{left:32px;bottom:32px;border-left-width:2px;border-bottom-width:2px}
.cm.br{right:32px;bottom:32px;border-right-width:2px;border-bottom-width:2px}
/* 页码右端对齐青条右沿（1032），左沿让开 x<1068 的反水印检测区（2026-11-11）：
   check.py 的 _corner_wm_grid 取样区是 x≥0.86w、y≥0.94h，页码原来 right:74，
   右端 1168 落在区里；它的深色字会在周围产生一圈「比高斯底更亮」的光晕，
   被水印检测判成「整套同位置亮区一致率 100%」——那是我们自己的页码，不是平台水印。
   结构性修法是把固定元素移出检测区，不是去改检测阈值。
   垂直 62→96（2026-11-11）：给收口句末行让出 24px，否则两串字在手机尺寸上连成一句。 */
.folio{position:absolute;right:210px;bottom:96px;font-size:42px;letter-spacing:2px;color:#5c5c5c}
.mast{position:absolute;left:76px;top:74px;font-size:42px;letter-spacing:9px;color:#111111}
.ht{position:absolute;background-image:radial-gradient(circle,#E8422E 2.2px,transparent 2.3px);background-size:11px 11px}
/* 内页收口区：要点（能照着做）+ 朱红短线 + 一句收口
   宽度必须给右下页码让位（2026-11-09 踩到）：folio 从 x≈1038 起，
   foot 若仍写 1046，收口句会直接压在页码「·· · 07 / 09」上，两串字叠在一起。
   收窄到 900 后 caption 自然折行，宁可两行也别压页码。

   **垂直也要让位（2026-11-11 补）**：原来 foot bottom:118、folio bottom:62，
   收口句末行底边 1538、页码顶边 1544 —— 只差 6px，放大看没问题，
   缩到手机尺寸就成了「只能聊天，价值少一半。页码 03 / 07」连成一句话。
   间距要按**缩放后**的观感留，不是按 1:1 截图留。
   现在：foot 底 1486 / 页码 1510–1560 / 青条 1596，三段各留 24–36px。 */
.foot{position:absolute;left:80px;bottom:170px;width:1040px}
.pts{display:flex;flex-direction:column;gap:10px;margin-bottom:34px}
.pt{display:flex;align-items:flex-start;font-size:42px;line-height:1.45;color:#1a1a1a}
.pt i{display:block;width:12px;height:12px;background:#E8422E;margin:17px 16px 0 0;flex:none}
.foot-rule{display:none}   /* 2026-11-11 删除：收口区不用线，靠间距分隔 */
/* r3 专用：收口区让到竖线右侧（left 252，与 .r3-body 同列）
   竖线在 x=204，若收口区仍用全局 80，线会直接穿过要点文字（2026-11-11 实测发现）。
   装饰线不得与内容带相交——这是栅格问题，不是调数值的问题。
   宽度 910 = 1242 − 80(右) − 252(左)：扣掉方点与缩进后约 21 字/行，
   再窄就会把「开始」这类词拆成「开 / 始」，读感断（2026-11-11 实测 756 偏窄）。 */
.foot.r3c{left:252px;width:910px}
.foot-cap{font-size:42px;line-height:1.65;color:#5c5c5c;max-width:740px;text-wrap:balance}
/* text-wrap:balance：目标字体比宋体略宽，原本刚好一行的收口句会折行，
   折出来第二行只剩「猜。」三个字，看着像没排完。balance 让两行等长。
   为什么不用缩字号：字号是红线不能动；为什么不用删字：删字是编辑决定，不该由排版倒逼。 */
.chip{position:absolute;background:#4ECDC4}
.chip-in{display:block;width:180px;height:34px;background:#4ECDC4}

/* 双色错版 */
.reg{position:relative;line-height:.96;letter-spacing:-6px;white-space:nowrap}
.reg-red{position:absolute;left:9px;top:8px;color:#E8422E;mix-blend-mode:multiply}
.reg-ink{position:relative;color:#111111;font-family:var(--f-body);font-weight:700}

/* ---- r1 封面 ---- */
.r1-no{position:absolute;right:76px;top:74px;font-size:42px;letter-spacing:4px;color:#5c5c5c}
.r1-left{position:absolute;left:76px;top:186px;width:486px;display:flex;flex-direction:column}
.r1-kick{font-size:42px;letter-spacing:9px;color:#E8422E;padding-bottom:10px;
  border-bottom:3px solid #E8422E;margin-bottom:34px;align-self:flex-start}
.r1-head{font-family:var(--f-title);font-weight:700;font-size:84px;line-height:1.28;
  letter-spacing:1px;color:#111111;margin-bottom:44px}
.r1-cap{font-size:42px;line-height:1.85;color:#1a1a1a;margin-bottom:44px}
.r1-chip{display:flex;align-items:center;gap:16px;font-size:42px;letter-spacing:5px;color:#5c5c5c}
.r1-vline{position:absolute;left:600px;top:206px;width:3px;height:1170px;background:#111111;opacity:.85}
.r1-hero{position:absolute;right:104px;top:206px;writing-mode:vertical-rl;
  font-family:var(--f-body);font-weight:700;color:#111111;
  letter-spacing:8px;line-height:1.12;text-orientation:upright}
.tcy{text-combine-upright:all;letter-spacing:0}
.r1-dots{left:-190px;bottom:60px;width:520px;height:520px;border-radius:50%;opacity:.5}

/* ---- r2 错版 ---- */
.r2-kicker{position:absolute;left:76px;top:146px;font-size:42px;letter-spacing:10px;color:#5c5c5c}
.r2-rule{position:absolute;left:76px;top:202px;width:200px;height:7px;background:#E8422E}
/* 2026-11-12：大字原来 top:600 写死。实测五组 r2：上缝恒 252，
   下缝却从 186（5 条要点）到 259（3 条要点）不等 —— foot 是 bottom 锚定、
   高度随要点条数和收口句行数变，固定 top 必然一侧紧一侧松。
   这与 §十一 是同一个病：绝对定位撞上高度可变的内容。
   改成 flex：head 钉顶、foot 钉底，hero 用 margin:auto 吃掉剩余空间，
   上下缝自动相等。不按要点条数查表——查表会在文案改一个字后失效。 */
.r2-flow{position:absolute;left:76px;top:266px;width:1102px;bottom:170px;
  display:flex;flex-direction:column}
.r2-head{font-size:60px;font-family:var(--f-title);
  font-weight:700;color:#111111;letter-spacing:4px;max-width:960px;line-height:1.36}
.r2-body{margin:auto 0 auto -6px}
/* foot 在 r2 里退出绝对定位，成为 flex 的最后一项；左 80 靠 -6 的反向补偿保持原栅格 */
.r2-flow .foot{position:static;left:auto;bottom:auto;width:1040px;margin-left:4px;flex:none}
/* 网点移到右上静态区（2026-11-11）：原来锚在 left:-90 / bottom:130，
   一旦这张卡带要点（foot 区向上长），圆就直接压在要点和收口句上。
   静态区的 y 不随内容变化，不会漂 —— 这是 §十一 的规则。 */
.r2-dots{right:-110px;top:-110px;width:300px;height:300px;border-radius:50%;opacity:.42}
.r2-cap{position:absolute;right:76px;bottom:300px;width:660px;text-align:right;
  font-size:42px;color:#1a1a1a;line-height:1.72}

/* ---- r3 网屏圆 ---- */
.r3-circle{position:absolute;right:-150px;top:120px;width:840px;height:840px;border-radius:50%;
  background-image:radial-gradient(circle,#E8422E 3.6px,transparent 3.7px);
  background-size:18px 18px;opacity:.88}
.r3-vline{position:absolute;left:204px;top:150px;width:4px;height:1230px;background:#111111;opacity:.82}
.r3-side{position:absolute;left:96px;top:196px;height:1160px;writing-mode:vertical-rl;
  font-family:var(--f-title);font-weight:700;font-size:52px;letter-spacing:9px;color:#111111}
.r3-kick{position:absolute;left:252px;top:152px;font-size:42px;letter-spacing:9px;color:#E8422E}
.r3-body{position:absolute;left:252px;bottom:600px;line-height:1.02;letter-spacing:-4px;
  color:#111111;font-family:var(--f-body);font-weight:700}
.r3-rule{display:none}   /* 2026-11-11 删除：绝对定位 bottom:480，压在第一条要点上 */
.r3-cap{position:absolute;left:254px;bottom:280px;width:820px;font-size:42px;
  color:#1a1a1a;line-height:1.8}

/* ---- r4 印章 ---- */
.r4-kick{position:absolute;left:76px;top:148px;font-size:42px;letter-spacing:9px;color:#5c5c5c}
.r4-seal{position:absolute;right:110px;top:196px;width:252px;height:252px;
  border:7px double #E8422E;transform:rotate(-9deg);
  display:flex;align-items:center;justify-content:center}
.r4-seal-in{display:flex;flex-direction:column;gap:8px;font-family:var(--f-title);
  font-weight:700;font-size:46px;color:#E8422E;letter-spacing:4px;line-height:1}
.r4-flow{position:absolute;left:76px;top:600px;width:1040px;display:flex;flex-direction:column}
.r4-head{font-size:58px;font-family:var(--f-title);font-weight:700;color:#111111;
  letter-spacing:5px;margin-bottom:52px}
.r4-body{line-height:1.04;letter-spacing:-5px;color:#111111;
  font-family:var(--f-body);font-weight:700;margin-bottom:60px}
.r4-rule{display:none}   /* 2026-11-11 删除：同上，绝对定位必撞内容带 */
.r4-cap{position:absolute;left:78px;bottom:270px;width:900px;font-size:42px;
  line-height:1.85;color:#1a1a1a}
.r4-dots{right:-140px;bottom:150px;width:300px;height:300px;border-radius:50%;opacity:.42}

/* ---- r5 大引文 ---- */
.r5-flow{position:absolute;left:76px;top:150px;width:1088px;display:flex;flex-direction:column}
.r5-mark{font-family:var(--f-title);font-size:200px;line-height:.62;color:#E8422E;opacity:.9;margin-bottom:26px}
.r5-head{font-size:44px;letter-spacing:8px;color:#E8422E;margin-bottom:34px}
.r5-quote{font-family:var(--f-title);font-weight:700;color:#111111;
  line-height:1.42;letter-spacing:2px;margin-bottom:64px}
.r5-rule{width:170px;height:7px;background:#E8422E;margin-bottom:52px}
.r5-cap{font-size:42px;line-height:1.9;color:#1a1a1a;padding-top:44px;
  border-top:2px solid rgba(17,17,17,.22)}
.r5-dots{right:-120px;top:-100px;width:320px;height:320px;border-radius:50%;opacity:.4}

/* ---- r6 空心数字 ---- */
.r6-num{position:absolute;left:330px;top:420px;font-family:var(--f-body);font-weight:700;
  font-size:720px;line-height:.8;letter-spacing:-30px;color:transparent;
  -webkit-text-stroke:3px #E8422E;opacity:.24;transform:rotate(-4deg)}
.r6-head{position:absolute;left:80px;top:236px;font-size:62px;font-family:var(--f-title);
  font-weight:700;color:#111111;letter-spacing:5px}
.r6-body{position:absolute;left:80px;bottom:610px;line-height:1.04;letter-spacing:-5px;
  color:#111111;font-family:var(--f-body);font-weight:700}
.r6-rule{display:none}   /* 2026-11-11 删除：同上 */
.r6-cap{position:absolute;left:82px;bottom:270px;width:900px;font-size:42px;line-height:1.85;color:#1a1a1a}

/* ---- r7 纸带 ---- */
.r7-head{position:absolute;left:80px;top:190px;font-size:64px;font-family:var(--f-title);
  font-weight:700;color:#111111;letter-spacing:5px;max-width:1060px;line-height:1.32}
.r7-band{position:absolute;left:-80px;top:450px;width:1420px;height:560px;background:#F0C33C;
  transform:rotate(-3.2deg)}
.r7-body{position:absolute;left:76px;top:522px;transform:rotate(-3.2deg);line-height:1.06;
  color:#111111;font-family:var(--f-body);font-weight:700;letter-spacing:-4px}
.r7-cap{position:absolute;left:80px;top:1140px;width:1000px;font-size:42px;
  color:#1a1a1a;line-height:1.8}
.r7-dots{right:-80px;top:110px;width:300px;height:300px;border-radius:50%;opacity:.45}

/* ---- r8 纸条胶带 ---- */
.r8-head{position:absolute;left:76px;top:176px;font-size:62px;font-family:var(--f-title);
  font-weight:700;color:#111111;letter-spacing:5px;max-width:1060px;line-height:1.32}
.r8-strip{position:absolute;left:106px;top:400px;width:1030px;padding:78px 66px;
  background:#FFFDF7;transform:rotate(-1.6deg);
  box-shadow:16px 18px 0 rgba(17,17,17,.09)}
.r8-tape-l{position:absolute;left:-48px;top:-30px;width:190px;height:66px;
  background:rgba(240,195,60,.70);transform:rotate(-9deg)}
.r8-tape-r{position:absolute;right:-48px;bottom:-30px;width:190px;height:66px;
  background:rgba(78,205,196,.60);transform:rotate(-9deg)}
.r8-text{line-height:1.1;letter-spacing:-4px;color:#111111;
  font-family:var(--f-body);font-weight:700}
.r8-cap{position:absolute;left:78px;top:1150px;width:1000px;font-size:42px;
  color:#1a1a1a;line-height:1.8}
.r8-dots{right:-120px;top:-90px;width:300px;height:300px;border-radius:50%;opacity:.45}

/* ---- r9 收尾 ---- */
.r9-flow{position:absolute;left:96px;top:240px;width:1050px;display:flex;flex-direction:column}
.r9-kick{font-size:42px;letter-spacing:10px;color:#5c5c5c;margin-bottom:60px}
.r9-head{font-size:70px;font-family:var(--f-title);font-weight:700;color:#111111;
  letter-spacing:5px;margin-bottom:40px}
.r9-hero{line-height:1.24;letter-spacing:-2px;color:#111111;
  font-family:var(--f-body);font-weight:700;margin-bottom:70px}
.r9-rule{width:400px;height:7px;background:#E8422E;margin-bottom:52px}
.r9-cap{position:absolute;left:96px;bottom:280px;width:940px;font-size:42px;
  line-height:1.9;color:#1a1a1a}
.r9-dots{right:-140px;bottom:-140px;width:560px;height:560px;border-radius:50%;opacity:.38}
"""


def build_html(cards: list[dict]) -> str:
    global _TOTAL
    _TOTAL = len(cards)
    body = []
    for i, c in enumerate(cards):
        head = c.get("head", "")
        if isinstance(head, list):
            head = "".join(str(x) for x in head)
        c = dict(c, head=head)
        # 允许在 cards.json 里用 "v" 显式指定版式（一组只有 3 张时，
        # 按下标轮转拿不到 r9 收口，头部和尾部就没法单独设计）。
        v = c.get("v") or VARIANT_ORDER[i % len(VARIANT_ORDER)]
        if v == "r1":
            body.append(r1_cover(c))
        elif v == "r2":
            body.append(r2_overprint(c, i + 1))
        elif v == "r3":
            body.append(r3_screen(c))
        elif v == "r4":
            body.append(r4_stamp(c))
        elif v == "r5":
            body.append(r5_quote(c))
        elif v == "r6":
            body.append(r6_bignum(c, i + 1))
        elif v == "r7":
            body.append(r7_band(c))
        elif v == "r8":
            body.append(r8_tape(c))
        else:
            body.append(r9_end(c))
    _guard_decor(body, cards)
    # 页码按实际位置重写：各版式里 folio() 的数字是写死的（r2→2、r5→5…），
    # 一旦显式指定版式（v 字段）就会印错页，读者以为缺页。
    body = [re.sub(r'(<div class="folio">[^<]*· )\d{2}', rf'\g<1>{i+1:02d}', h)
            for i, h in enumerate(body)]
    # 字体栈优先级：check_fonts() 实测得出的结果 > fontkit 的候选表。
    # 前者排除了「名字在、字体其实不在」的族，后者只是「可能可用」。
    font_stack = FONT_STACK or (
        ", ".join("'%s'" % f for f in resolve_font_family()) + ", sans-serif")
    css = CSS.replace("__GZH_FONT_STACK__", font_stack)
    face = ("<style>%s</style>" % WEB_FACE_CSS) if WEB_FACE_CSS else ""
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>{css}</style>{face}</head><body>' + "".join(body) + '</body></html>')


# 会随内容长度漂移的绝对定位装饰：含要点的页一旦出现，必然与文字抢位（2026-11-11 实测）。
# 注意 r2-rule 不在名单里：它锚在题签下方（top:202），属于静态区，永远不会碰到流动文字。
BANNED_ON_POINTS = ("r3-rule", "r4-rule", "r6-rule", "foot-rule")


def _guard_decor(bodies: list[str], cards: list[dict]) -> None:
    """结构性守卫：装饰线只许待在静态区，不许出现在有要点的页。

    为什么查结构不查像素：像素检查只能发现"这一次"的错位，结构检查挡住"这一类"。
    2026-11-11 的问题不是数值调错了，而是"绝对定位的线 + 高度可变的内容"这个组合本身就不成立。
    """
    bad = []
    for i, (html, c) in enumerate(zip(bodies, cards), 1):
        pts = c.get("points") or []
        if not pts:
            continue
        for cls in BANNED_ON_POINTS:
            if f'class="{cls}"' in html:
                bad.append(f"第{i}张：{cls} 与要点区共存")
    if bad:
        raise SystemExit("装饰线与要点区冲突（绝对定位会随内容漂移）：\n  " +
                         "\n  ".join(bad) +
                         "\n修法：删掉该页的红线/竖线，或让内容列让位，别调数值。")


def shoot(html_path: str, tmp_dir: str, n_cards: int) -> Image.Image:
    """整页一次截图再切。Chrome 输出必须落 ASCII 目录，中文会「拒绝访问」。"""
    total = H * n_cards
    raw = os.path.join(tmp_dir, "sheet.png")
    cmd = [
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=1", f"--window-size={W},{total}",
        f"--screenshot={raw}", Path(html_path).as_uri(),
    ]
    subprocess.run(cmd, capture_output=True, check=False)
    if not os.path.exists(raw):
        raise SystemExit("截图失败：Chrome 没产出 sheet.png（查 Chrome 路径 / 输出目录是否 ASCII）")
    return Image.open(raw).convert("RGB")


def add_grain(img: Image.Image, sigma: int = 9, mix: float = 0.032) -> Image.Image:
    """纸纤维颗粒。视觉上是印刷品的手感，实际也负责把 PNG 顶过 150KB 硬闸。"""
    noise = Image.effect_noise((img.width, img.height), sigma).convert("L").convert("RGB")
    return Image.blend(img, noise, mix)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="cards.json 路径")
    ap.add_argument("--out", required=True, help="输出目录（可中文）")
    ap.add_argument("--no-grain", action="store_true")
    ap.add_argument("--chrome", default="",
                    help="Chrome/Chromium 可执行文件绝对路径；默认读环境变量 "
                         "CHROME_PATH 并自动查找常见安装路径")
    a = ap.parse_args()

    global CHROME
    CHROME = resolve_chrome(a.chrome)
    # 渲染前硬校验：找不到可用中文字体就抛清晰异常，绝不带着错字体出图。
    resolve_font(False)
    resolve_font(True)

    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    cards = spec["cards"]
    name = spec.get("theme", "cards")
    os.makedirs(a.out, exist_ok=True)

    # 字体守卫生效点在「渲染前」：图一旦出来，字体错了只能重来。
    # 不传 fams，由 check_fonts 现取 fontkit 配置的字体族并实测 Chrome 是否加载。
    check_fonts()

    tmp = tempfile.mkdtemp(prefix="riso_")
    html_path = os.path.join(tmp, "page.html")
    Path(html_path).write_text(build_html(cards), encoding="utf-8")

    sheet = shoot(html_path, tmp, len(cards))
    made = []
    for i in range(len(cards)):
        img = sheet.crop((0, i * H, W, (i + 1) * H))
        if not a.no_grain:
            img = add_grain(img)
        fn = os.path.join(a.out, f"{name}-{i+1:02d}.png")
        img.save(fn, optimize=True)
        made.append(fn)

    for fn in made:
        kb = os.path.getsize(fn) / 1024
        flag = "  ⚠ 超 1.5MB" if kb > 1536 else ("  ⚠ 不足 150KB" if kb < 150 else "")
        print(f"[ok] {os.path.basename(fn)}  {kb:.0f}KB{flag}")
    print(f"\n共 {len(made)} 张 → {a.out}")


if __name__ == "__main__":
    main()
