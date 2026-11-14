# -*- coding: utf-8 -*-
"""fontkit.py —— 共享字体解析（发布前脱敏改造新增的中文字体统一入口）。

本仓库所有需要中文字体的脚本都从这里取字体，不再各自硬编码系统字体路径。

项目红线：**找不到可用字体时抛 FontNotFoundError，绝不静默退回默认字体。**
静默默认字体曾造成「图能出、不报错、只是悄悄换了个字体」的事故，出图后极难发现。

resolve_font(bold=False) 的查找顺序：
  1. 环境变量 GZH_IMAGE_KIT_FONT_REG / GZH_IMAGE_KIT_FONT_BOLD（按 bold 选）；
     设了但文件不存在就抛异常，明确告诉使用者配置错了。
  2. 候选列表：可再分发开源中文字体（思源黑体 SourceHanSansSC /
     Noto Sans CJK SC 等）与常见系统字体路径（仅运行时查找，不随仓库分发字体文件）。
  3. 系统字体目录扫描，找本机已安装的可再分发中文字体。
  4. 仍找不到就抛 FontNotFoundError，提示如何配置。

字体配置：
  - 推荐自备一款允许再分发 / 商用的中文字体，如思源黑体（SIL OFL 1.1）或
    Noto Sans CJK SC（SIL OFL 1.1），通过上面两个环境变量指定绝对路径。
  - render_riso.py 走 Chrome + CSS，用 GZH_IMAGE_KIT_FONT_FAMILY
    指定 CSS font-family 候选（逗号分隔）；同样先做字体文件硬校验。
  - 本仓库不附带任何字体文件，也不引用不可再分发的系统专有字体路径。
"""
from __future__ import annotations

import glob
import os
from functools import lru_cache
from pathlib import Path

ENV_REG = "GZH_IMAGE_KIT_FONT_REG"
ENV_BOLD = "GZH_IMAGE_KIT_FONT_BOLD"
ENV_FAMILY = "GZH_IMAGE_KIT_FONT_FAMILY"


class FontNotFoundError(RuntimeError):
    """找不到可用的中文字体。按红线要求绝不静默退回默认字体。"""


# 可再分发开源中文字体的常见文件名片段（OFL / Apache 等）。
# 只按名字匹配这些，避免误选不可再分发的系统专有字体。
_OPEN_FONT_NAMES = (
    "SourceHanSans", "SourceHanSerif", "NotoSansCJK", "NotoSerifCJK",
    "NotoSansSC", "NotoSerifSC", "Sarasa", "LXGWWenKai", "WenQuanYi",
    "DroidSansFallback",
)


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


def _is_open_font(name: str) -> bool:
    low = name.lower()
    return any(k.lower() in low for k in _OPEN_FONT_NAMES)


def _scan_font_files():
    """扫描系统字体目录，返回可再分发中文字体文件路径列表。"""
    out = []
    for d in _font_dirs():
        if not os.path.isdir(d):
            continue
        for pat in ("*.ttf", "*.ttc", "*.otf", "*.otc"):
            for p in glob.glob(os.path.join(d, "**", pat), recursive=True):
                if _is_open_font(os.path.basename(p)):
                    out.append(p)
    return sorted(set(out))


def _pick(files, bold: bool):
    """从候选里挑粗体 / 常规：优先文件名带字重关键字的，否则取第一个。"""
    if not files:
        return None
    heavy = ("bold", "heavy", "semibold", "black", "medium")
    light = ("regular", "normal", "light", "book")
    keys = heavy if bold else light
    for f in files:
        low = os.path.basename(f).lower()
        if any(k in low for k in keys):
            return f
    return files[0]


@lru_cache(maxsize=2)
def _find_font(bold: bool) -> str:
    """内部查找，结果按 bold 缓存。找不到就抛 FontNotFoundError。"""
    env_name = ENV_BOLD if bold else ENV_REG
    env_val = os.environ.get(env_name, "").strip().strip('"').strip("'")
    if env_val:
        if os.path.exists(env_val):
            return env_val
        raise FontNotFoundError(
            "环境变量 %s 指向的字体文件不存在：%s\n"
            "请改成真实存在的字体文件绝对路径，或取消该变量改用候选字体。"
            % (env_name, env_val))

    files = _scan_font_files()
    chosen = _pick(files, bold) or _pick(files, not bold)
    if chosen:
        return chosen

    raise FontNotFoundError(
        "找不到可用的中文字体。按项目红线，绝不静默退回默认字体。\n"
        "请自备一款允许再分发 / 商用的中文字体（如思源黑体 SourceHanSansSC、"
        "Noto Sans CJK SC，均为 SIL OFL 1.1），然后二选一：\n"
        "  1) 设置环境变量 %s / %s 指向常规体与粗体文件绝对路径；\n"
        "  2) 把该字体安装到系统字体目录（文件名含 SourceHanSans / NotoSansSC 等可识别字样）。\n"
        "详见 README「字体配置与许可」。"
        % (ENV_REG, ENV_BOLD))


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

    优先读环境变量 GZH_IMAGE_KIT_FONT_FAMILY（逗号分隔）；否则给一组可再分发
    开源中文字体的中性候选族名。

    内部先调用 resolve_font() 做字体文件硬校验：本机没有可用字体就直接抛
    FontNotFoundError，避免「字体没配也照样出图」的静默回退。真正的 Chrome
    端字体加载仍由 render_riso.py 的 check_fonts() 实测兜底。
    """
    resolve_font(False)  # 红线：找不到字体就抛异常，不静默
    raw = os.environ.get(ENV_FAMILY, "").strip()
    if raw:
        fams = [x.strip().strip('"').strip("'") for x in raw.split(",") if x.strip()]
        if fams:
            return fams
    return ["Source Han Sans SC", "Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Micro Hei"]
