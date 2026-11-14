# -*- coding: utf-8 -*-
"""fontkit.py —— 共享字体解析（发布前脱敏改造新增的中文字体统一入口）。

本仓库所有需要中文字体的脚本都从这里取字体，不再各自硬编码系统字体路径。

项目红线：**找不到可用字体时抛 FontNotFoundError，绝不静默退回默认字体。**
静默默认字体曾造成「图能出、不报错、只是悄悄换了个字体」的事故，出图后极难发现。

resolve_font(bold=False) 的查找顺序（三档，逐档回退）：
  1. **环境变量** GZH_IMAGE_KIT_FONT_REG / GZH_IMAGE_KIT_FONT_BOLD（按 bold 选）；
     设了但文件不存在就抛异常，明确告诉使用者配置错了。
  2. **开源可再分发字体**（思源黑体 / Noto CJK / Sarasa / 文泉驿…）：
     扫描系统字体目录，按文件名识别。这一档最稳——自己用、发给别人用、商用都清楚。
  3. **系统自带的中文黑体**（微软雅黑 / 等线 / 黑体 / 苹方 / 冬青黑体）：
     按已知绝对路径查找。**只在本机运行时使用，绝不随仓库分发**；
     用到这一档会往 stderr 打一条醒目提示，告诉你字体授权要自己确认。
  4. 三档都不通才抛 FontNotFoundError，异常里直接给出下载地址与命令。

> 为什么加第 3 档（2026-11-14，外部实测反馈）
> -------------------------------------------------
> 原来的白名单只认开源字体，本意是「不把字体文件打包进仓库」。但那条规矩被执行成了
> 「运行时也不许用系统字体」，于是**一台只有微软雅黑的中文 Windows 会被完全堵死**：
> 文件在、能用、合法，却报 FontNotFoundError。
> 两个独立外部测试者都卡在这一步（其中一位是运气好在系统目录翻到了 NotoSansSC-VF.ttf）。
> 正确的边界是：**分发**只用可再分发字体，**运行时**允许用本机已授权的字体，
> 且必须把「你现在用的是哪个、授权要自己看」说出来——这才是原来那条红线的本意。

字体配置：
  - 推荐自备一款允许再分发 / 商用的中文字体，如思源黑体（SIL OFL 1.1）、
    Noto Sans CJK SC（SIL OFL 1.1）、Sarasa Gothic（SIL OFL 1.1）。
  - render_riso.py 走 Chrome + CSS，用 GZH_IMAGE_KIT_FONT_FAMILY
    指定 CSS font-family 候选（逗号分隔）；同样先做字体文件硬校验。
  - 本仓库不附带任何字体文件。
"""
from __future__ import annotations

import glob
import os
import sys
from functools import lru_cache
from pathlib import Path

ENV_REG = "GZH_IMAGE_KIT_FONT_REG"
ENV_BOLD = "GZH_IMAGE_KIT_FONT_BOLD"
ENV_FAMILY = "GZH_IMAGE_KIT_FONT_FAMILY"


class FontNotFoundError(RuntimeError):
    """找不到可用的中文字体。按红线要求绝不静默退回默认字体。"""


# 一档：本机已装、**运行时可以放心用**的中文字体。按顺序匹配文件名片段，
# 靠前的优先（同一台机器上装了好几种时，选许可证最干净的）。
#
# 值 = (档位标签, 许可说明)。档位不在 label 里区分「开源」与「免费商用」——
# 两种都只是**在你机器上渲染**，本仓库从不分发字体文件；差别只在提示语怎么写。
_KNOWN_FONTS = (
    # —— 开源，可自由使用与再分发（SIL OFL / Apache）——
    ("SourceHanSans", "open", "思源黑体，SIL OFL 1.1，可自由使用与再分发"),
    ("SourceHanSerif", "open", "思源宋体，SIL OFL 1.1，可自由使用与再分发"),
    ("NotoSansCJK", "open", "Noto Sans CJK，SIL OFL 1.1，可自由使用与再分发"),
    ("NotoSerifCJK", "open", "Noto Serif CJK，SIL OFL 1.1，可自由使用与再分发"),
    ("NotoSansSC", "open", "Noto Sans SC，SIL OFL 1.1，可自由使用与再分发"),
    ("NotoSerifSC", "open", "Noto Serif SC，SIL OFL 1.1，可自由使用与再分发"),
    ("Sarasa", "open", "更纱黑体，SIL OFL 1.1，可自由使用与再分发"),
    ("LXGWWenKai", "open", "霞鹜文楷，SIL OFL 1.1，可自由使用与再分发"),
    ("WenQuanYi", "open", "文泉驿，GPL + 字体例外，可自由使用与再分发"),
    ("DroidSansFallback", "open", "Droid Sans Fallback，Apache 2.0"),
    # —— 免费商用（**不是开源**：允许免费使用，但嵌入/再分发条款要自己确认）——
    ("MiSans", "free", "小米 MiSans，官方声明免费商用；嵌入与再分发请查其许可"),
    ("HarmonyOS_Sans", "free", "华为 HarmonyOS Sans，免费商用；嵌入与再分发请查其许可"),
    ("AlibabaPuHuiTi", "free", "阿里巴巴普惠体，免费商用；嵌入与再分发请查其许可"),
    ("OPPOSans", "free", "OPPO Sans，免费商用；嵌入与再分发请查其许可"),
)

# 二档：系统自带的中文黑体。**只在本机运行时使用，绝不随仓库分发。**
# 用绝对路径而不是文件名匹配：这些字体装在哪是确定的，扫目录匹配容易误中
# 同名的私人文件，也可能把「其实不是中文黑体」的东西当成字体用。
# 字段：(常规体, 粗体, 显示名, 授权提醒, CSS 族名候选)
# CSS 族名必须一并给出：这类字体本来就已装成系统族，让 Chrome 直接用它，
# 比走 @font-face 更稳——msyh.ttc / PingFang.ttc 是 TrueType Collection
# （一个文件里装多套字），Chrome 对 TTC 做 @font-face 需要索引，容易失败。
_SYSTEM_CJK = (
    ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
     "微软雅黑 Microsoft YaHei", "微软雅黑由方正开发，商用需取得授权",
     ["Microsoft YaHei", "微软雅黑"]),
    ("C:/Windows/Fonts/Deng.ttf", "C:/Windows/Fonts/Dengb.ttf",
     "等线 DengXian", "随 Windows 附带，商用授权范围请自行确认",
     ["DengXian", "等线"]),
    ("C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simhei.ttf",
     "黑体 SimHei", "随 Windows 附带，商用授权范围请自行确认",
     ["SimHei", "黑体"]),
    ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/PingFang.ttc",
     "苹方 PingFang SC", "随 macOS 附带，商用授权范围请自行确认",
     ["PingFang SC"]),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc",
     "/System/Library/Fonts/Hiragino Sans GB.ttc",
     "冬青黑体 Hiragino Sans GB", "随 macOS 附带，商用授权范围请自行确认",
     ["Hiragino Sans GB"]),
    ("/usr/share/fonts/truetype/arphic/uming.ttc",
     "/usr/share/fonts/truetype/arphic/uming.ttc",
     "AR PL UMing", "文鼎开源字体，可自由使用",
     ["AR PL UMing CN", "AR PL UMing"]),
)

# 二档命中时只提示一次，不在每张图前刷屏。
_NOTICE_SHOWN = False

# 找不到字体时的出口：给能直接照做的命令，而不是「去装个字体」。
# 这两个地址在 _emit_notice 里还要再提一次，所以只在这里定义一遍——
# 「两处都写一遍并要求同步」本身就是缺陷。
_NOTO_URL = "https://fonts.google.com/noto/specimen/Noto+Sans+SC"
_SOURCEHAN_URL = "https://github.com/adobe-fonts/source-han-sans/releases"

_DOWNLOAD_HINT = """\
去哪儿弄（挑一个，都是开源可商用，SIL OFL 1.1）：

  A. Noto Sans SC（单文件，最省事，约 10MB）
     %s
     页面右上「Download family」→ 解压得到 NotoSansSC-VariableFont_wght.ttf

  B. 思源黑体 Source Han Sans（分字重，粗细可控，约 30MB）
     %s
     下 SourceHanSansSC.zip，里面 OTF/ 目录取 Regular 与 Bold

  C. 国内网络打不开上面两个：在 Gitee 搜「思源黑体」或「Noto Sans SC」，
     一般有人做了镜像仓库，下载同样可用（注意核对是 OFL 协议）

装好之后二选一：

  1) 装进系统字体目录（推荐，装一次以后都不用管）
     Windows：右键字体文件 →「为所有用户安装」
     macOS  ：双击 → 字体册 →「安装字体」
     Linux  ：cp *.ttf ~/.local/share/fonts/ && fc-cache -f
     然后重跑刚才那条命令，脚本会自动扫描到，不用设任何环境变量。

  2) 不装，直接指过去（适合把字体放在项目目录里）
     export GZH_IMAGE_KIT_FONT_REG="/绝对路径/NotoSansSC-VariableFont_wght.ttf"
     export GZH_IMAGE_KIT_FONT_BOLD="/绝对路径/同上或另一个粗体文件"

排查完可以跑 `python doctor.py` 复查环境。""" % (_NOTO_URL, _SOURCEHAN_URL)


def _font_dirs():
    """常见系统字体目录（运行时扫描，不分发字体文件）。"""
    dirs = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        dirs.append(os.path.join(windir, "Fonts"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    home = str(Path.home())
    dirs += [
        os.path.join(home, ".fonts"),
        os.path.join(home, ".local", "share", "fonts"),
        os.path.join(home, "Library", "Fonts"),
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/Library/Fonts",
        "/System/Library/Fonts",
        "C:/Windows/Fonts",
    ]
    return dirs


def _match_known(name: str):
    """按白名单匹配文件名，返回 (rank, tier, note)；不匹配返回 None。

    rank 越小越优先——装了好几种时，先用许可证最干净的。
    """
    low = name.lower()
    for rank, (key, tier, note) in enumerate(_KNOWN_FONTS):
        if key.lower() in low:
            return rank, tier, note
    return None


def _scan_font_files():
    """扫描系统字体目录，返回匹配白名单的 [(路径, rank, tier, note)]，按优先级排。"""
    out, seen = [], set()
    for d in _font_dirs():
        if not os.path.isdir(d):
            continue
        for pat in ("*.ttf", "*.ttc", "*.otf", "*.otc"):
            for p in glob.glob(os.path.join(d, "**", pat), recursive=True):
                # 同一个目录会以不同大小写/分隔符出现（C:/Windows/Fonts 与 %WINDIR%\Fonts），
                # 不归一化就会把同一份字体列两遍，看着像装了两款。
                key = os.path.normcase(os.path.realpath(p))
                if key in seen:
                    continue
                hit = _match_known(os.path.basename(p))
                if hit:
                    seen.add(key)
                    out.append((p, hit[0], hit[1], hit[2]))
    return sorted(out, key=lambda x: (x[1], x[0]))


_HEAVY_KEYS = ("bold", "heavy", "semibold", "black", "medium")
_LIGHT_KEYS = ("regular", "normal", "light", "book")
_VF_KEYS = ("vf", "variablefont", "variable", "wght")


def _is_variable(path: str) -> bool:
    """文件名像不像可变字体（VF）。

    可变字体一个文件横跨全部字重，所以「有没有粗体」对它不成立——
    族内有一份 VF 就等于粗细都齐。这一条不加，机器上同时装着
    「Noto Sans SC VF + MiSans 四个字重」时会选中 MiSans，
    明明 Noto 的许可证更干净（OFL），却因为文件名里没有 Regular 而落榜。
    """
    low = os.path.basename(path).lower()
    return any(k in low for k in _VF_KEYS)


def _has_weight(group, keys) -> bool:
    return any(any(k in os.path.basename(f[0]).lower() for k in keys) for f in group)


def _pick(files, bold: bool):
    """挑字体。**先定字体族，再在族内挑字重**。

    为什么必须按族挑而不是全表挑：全表挑会挑出「常规来自 A 家族、粗体来自 B 家族」，
    同一张图里两种字形混排——这正是 README 里反复警告的那类问题，肉眼看着「有点怪」
    但说不清哪里怪，比粗细不对更难发现。
    """
    if not files:
        return None
    groups = {}
    for f in files:
        groups.setdefault(f[1], []).append(f)   # 按白名单 rank 分族

    def complete(group) -> bool:
        """这个族常规与粗体都拿得到吗（VF 视为都拿得到）。"""
        if any(_is_variable(f[0]) for f in group):
            return True
        return _has_weight(group, _HEAVY_KEYS) and _has_weight(group, _LIGHT_KEYS)

    order = sorted(groups.items(), key=lambda kv: (0 if complete(kv[1]) else 1, kv[0]))
    # 先把「用哪一族」定下来，之后**只在这一族里找字重**。
    # 这一步不能省：如果边找边跨族，会出现「A 家族没常规→跳到 B 家族拿粗体」，
    # 同一张图两种字形混排（2026-11-14 由 tests/test_fontkit.py 抓到）。
    family = order[0][1]
    for f in family:
        if _is_variable(f[0]):
            return f          # VF 一个文件覆盖全部字重，load() 负责实例化
    keys = _HEAVY_KEYS if bold else _LIGHT_KEYS
    for f in family:
        if any(k in os.path.basename(f[0]).lower() for k in keys):
            return f
    # 这一族没有该字重：用它的第一个文件，绝不跨族凑
    return family[0]


def _system_cjk(bold: bool):
    """二档：返回 (路径, 显示名, 授权提醒, 是否缺粗体, CSS 族名候选)；没有返回 None。

    粗体优先取配对的粗体文件；没有配对（如黑体、苹方）就退回常规体——
    这是合法情况，但要让人知道标题会是常规字重，不能悄悄糊过去。
    """
    for reg, bld, label, lic, fams in _SYSTEM_CJK:
        if not os.path.exists(reg):
            continue
        want = bld if (bold and bld and os.path.exists(bld)) else reg
        no_bold = bold and want == reg
        return want, label, lic, no_bold, fams
    return None


def _emit_notice(label: str, lic: str, path: str, no_bold: bool) -> None:
    """二档命中时提示一次。走 stderr，不污染 stdout 里可被脚本解析的输出。

    这不是「报错」，是「能出图，但换个字体更好」——用户从输出里看不出自己
    是靠哪份字体出的图，也想不到换台机器图就变了样，所以这里必须把
    「去装一款开源字体」写成能直接照做的两步，而不是一句「建议装个字体」。
    进程内只打一次；装了开源/免费字体的人走一档，根本看不到这段。
    """
    global _NOTICE_SHOWN
    if _NOTICE_SHOWN:
        return
    _NOTICE_SHOWN = True
    sys.stderr.write(
        "\n[i] 字体：用的是本机系统字体「%s」\n"
        "    %s\n"
        "    这份字体只在你机器上用，不会随本仓库分发；对外发布前请自行确认授权范围。\n"
        "    文件：%s\n"
        "\n"
        "    图能出，但建议换一款开源中文字体——免费商用，换台机器也能出一样的图：\n"
        "      下载 %s（页面右上 Download family）\n"
        "      解压后双击 .ttf 安装即可，脚本下次自动认出来，不用配环境变量。\n"
        "      国内打不开：Gitee 搜「思源黑体」或「Noto Sans SC」，有镜像（认准 SIL OFL）。\n"
        "      还有别的下载源 / 想排查环境：`python doctor.py`。\n" % (label, lic, path, _NOTO_URL))
    if no_bold:
        sys.stderr.write(
            "    ⚠ 这份字体没有配对的粗体文件：标题会用常规字重，看起来会偏细。\n"
            "      想要粗标题，请用「A. Noto Sans SC」那条路（它自带 100–900 全部字重）。\n")
    sys.stderr.write("\n")


def _find_font_ex(bold: bool) -> tuple:
    """内部查找，返回 (路径, 档位, 显示名)。找不到就抛 FontNotFoundError。

    档位取值：env / open / system。给 doctor.py 和提示语用。
    """
    env_name = ENV_BOLD if bold else ENV_REG
    env_val = os.environ.get(env_name, "").strip().strip('"').strip("'")
    if env_val:
        if os.path.exists(env_val):
            return env_val, "env", os.path.basename(env_val)
        raise FontNotFoundError(
            "环境变量 %s 指向的字体文件不存在：%s\n"
            "请改成真实存在的字体文件绝对路径，或清掉这个变量让脚本自动查找：\n"
            "  Windows PowerShell：Remove-Item Env:%s\n"
            "  Windows cmd       ：set %s=\n"
            "  macOS / Linux     ：unset %s\n\n%s"
            % (env_name, env_val, env_name, env_name, env_name, _DOWNLOAD_HINT))

    # 一档：本机已装的中文字体（开源 / 免费商用两类，都只在本机渲染）
    files = _scan_font_files()
    chosen = _pick(files, bold) or _pick(files, not bold)
    if chosen:
        path, _rank, tier, note = chosen
        return path, tier, "%s（%s）" % (os.path.basename(path), note)

    # 二档：系统自带中文黑体（本机运行时合法，不随仓库分发）
    sys_hit = _system_cjk(bold)
    if sys_hit:
        path, label, lic, no_bold, _fams = sys_hit
        _emit_notice(label, lic, path, no_bold)
        return path, "system", label

    # 三档：都没有 → 把出口写进异常
    raise FontNotFoundError(
        "找不到可用的中文字体。按项目红线，绝不静默退回默认字体"
        "（静默回退曾造成「图能出、只是悄悄换了字体」的事故）。\n"
        "已经找过：环境变量 → 系统字体目录里的开源中文字体 → 系统自带中文黑体，三档都没命中。\n\n"
        + _DOWNLOAD_HINT)


@lru_cache(maxsize=8)
def _find_font_cached(bold: bool) -> tuple:
    return _find_font_ex(bold)


def _find_font(bold: bool) -> str:
    """内部查找，结果按 bold 缓存。找不到就抛 FontNotFoundError。"""
    return _find_font_cached(bool(bold))[0]


def font_info(bold: bool = False) -> dict:
    """当前会用的字体详情：{path, tier, name}。给 doctor.py / 排障用。

    tier: env（环境变量指定）/ open（开源可再分发）/ system（本机系统字体）。
    找不到字体时抛 FontNotFoundError。
    """
    path, tier, name = _find_font_cached(bool(bold))
    return {"path": path, "tier": tier, "name": name}


def resolve_font(bold: bool = False) -> str:
    """返回可用于 PIL.ImageFont.truetype 的字体文件路径。

    bold=True 取粗体文件，bold=False 取常规体文件。找不到时抛 FontNotFoundError。

    注意：**更推荐用 load(size, bold)**，它在这之上还处理了可变字体。
    """
    return _find_font(bool(bold))


# ── 可变字体（VF）── 2026-11-14 新增 ────────────────────────────────────────
# 事故：有人的 GZH_IMAGE_KIT_FONT_BOLD 指向 NotoSansSC-VF.ttf（本机唯一开源中文字体，
# fontkit 自动扫描也会命中它）。VF 文件本身只有一条「轴」，常规与粗体是同一个文件
# 的不同坐标——`ImageFont.truetype(path, size)` 拿到的是轴的默认位置（Regular），
# 于是整套卡渲染出来全是常规字重，标题明显偏细，而且**不报错**。
# 原本只有 gen_diagram.py 自己写了 set_variation_by_name("Bold")，
# 其余三个脚本各漏一边，同一批图里标题粗细不一致。
# 处理：下沉到 fontkit，四个脚本统一走 load()。
_BOLD_VARIATION_NAMES = ("Bold", "SemiBold", "DemiBold", "Heavy", "Black")
_BOLD_WGHT = 700


def _font_variation_names(font):
    """取出该字体的可变轴命名实例（非可变字体返回空列表）。"""
    try:
        names = font.get_variation_names()
    except Exception:
        return []
    out = []
    for n in names or []:
        try:
            out.append(n.decode("utf-8", "ignore") if isinstance(n, bytes) else str(n))
        except Exception:
            continue
    return out


def _apply_bold_variation(font) -> bool:
    """把可变字体实例化到粗稿位置。成功返回 True。

    两条路径：优先按命名实例（最贴近设计者意图），退化到按 wght 轴设 700。
    都失败就返回 False，调用方照常使用默认字重——不抛异常，
    因为「该字体没有粗体轴」是合法情况，不是配置错误。
    """
    names = _font_variation_names(font)
    for want in _BOLD_VARIATION_NAMES:
        for got in names:
            if got.strip().lower() == want.lower():
                try:
                    font.set_variation_by_name(got)
                    return True
                except Exception:
                    pass
    try:
        axes = font.get_variation_axes()
    except Exception:
        return False
    if not axes:
        return False
    vals = []
    for a in axes:
        nm = a.get("name") if isinstance(a, dict) else getattr(a, "name", b"")
        if isinstance(nm, bytes):
            nm = nm.decode("utf-8", "ignore")
        lo = a.get("minimum", 0) if isinstance(a, dict) else 0
        hi = a.get("maximum", 1000) if isinstance(a, dict) else 1000
        if str(nm).lower() in ("wght", "weight"):
            vals.append(min(max(_BOLD_WGHT, lo), hi))
        else:
            dflt = a.get("default", lo) if isinstance(a, dict) else lo
            vals.append(dflt)
    if not vals:
        return False
    try:
        font.set_variation_by_axes(vals)
        return True
    except Exception:
        return False


def load(size: int, bold: bool = False):
    """取一个可直接 draw 的字体对象：`load(40)` / `load(40, bold=True)`。

    这是**所有出图脚本取字体的唯一入口**。相比 `ImageFont.truetype(resolve_font(bold), size)`，
    它多做一件事：可变字体（VF）会被实例化到对应字重，不会静默落在 Regular。

    `resolve_font` 仍保留（render_riso 等需要路径的场景仍用它），
    但凡是「要拿去画字」的地方都应该走 load()。
    """
    from PIL import ImageFont

    path = resolve_font(bold)
    font = ImageFont.truetype(path, size)
    if bold:
        _apply_bold_variation(font)
    return font


def resolve_font_family():
    """返回 CSS font-family 的候选族名列表，供 Chrome/HTML 渲染脚本使用。

    优先读环境变量 GZH_IMAGE_KIT_FONT_FAMILY（逗号分隔）；否则按 fontkit 实际
    会用的那档字体给出族名：
      - 一档（开源字体文件）：给常见开源中文字体的中性族名；
      - 二档（系统自带黑体）  ：给该字体的**原生族名**（它本来就装成系统族，
        Chrome 直接叫得出来，比走 @font-face 稳；TTC 集合文件做 @font-face 需要索引）。
    内部先调用 resolve_font() 做字体文件硬校验：本机没有可用字体就直接抛
    FontNotFoundError，避免「字体没配也照样出图」的静默回退。真正的 Chrome
    端字体加载仍由 render_riso.py 的 check_fonts() 实测兜底。
    """
    info = font_info(False)  # 红线：找不到字体就抛异常，不静默
    raw = os.environ.get(ENV_FAMILY, "").strip()
    if raw:
        fams = [x.strip().strip('"').strip("'") for x in raw.split(",") if x.strip()]
        if fams:
            return fams
    if info["tier"] == "system":
        for reg, bld, _label, _lic, fams in _SYSTEM_CJK:
            if info["path"] in (reg, bld):
                return list(fams)
    return ["Source Han Sans SC", "Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Micro Hei"]
