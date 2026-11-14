# -*- coding: utf-8 -*-
"""fontkit 的回归测试（不需要本机装任何字体）。

守的是 2026-11-14 这次改动的三条具体规则——都是**肉眼看不出来**的错误，
只能靠断言拦：

1. **不许跨族凑字重**：常规来自 A 家族、粗体来自 B 家族，同一张图里两种字形混排。
   看着「有点怪」但说不清哪怪，比粗细不对更难发现。
2. **可变字体算「粗细都有」**：机器上同时装 `NotoSansSC-VF.ttf` 和 `MiSans` 四个字重时，
   不能因为 VF 文件名里没有 `Regular` 就把它排到 MiSans 后面——OFL 的许可证更干净。
3. **找不到字体时的报错必须带出口**：两个外部实测者都卡在这一步，
   报错只写「请自备字体」等于把人堵在第一步。

跑：`python -m pytest tests/ -q`
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("fontkit", ROOT / "fontkit.py")
fk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fk)


# ── 1. 不许跨族凑字重 ────────────────────────────────────────────────────────

def _f(path, rank, tier="open"):
    return (path, rank, tier, "note")


def test_bold_never_comes_from_another_family():
    """A 家族只有常规、B 家族只有粗体时，宁可粗体用 A 的常规，也不许跨到 B。"""
    files = [
        _f("C:/x/SourceHanSans-Regular.otf", 0),
        _f("C:/x/NotoSansSC-Bold.ttf", 3),
    ]
    reg = fk._pick(files, bold=False)
    bold = fk._pick(files, bold=True)
    assert reg[0].endswith("SourceHanSans-Regular.otf"), reg
    assert bold[0].endswith("SourceHanSans-Regular.otf"), (
        "粗体跨到别的家族去了：%s" % (bold[0],))


def test_same_family_when_both_weights_exist():
    files = [
        _f("C:/x/NotoSansSC-Regular.ttf", 3),
        _f("C:/x/NotoSansSC-Bold.ttf", 3),
    ]
    assert fk._pick(files, True)[0].endswith("NotoSansSC-Bold.ttf")
    assert fk._pick(files, False)[0].endswith("NotoSansSC-Regular.ttf")


# ── 2. 可变字体 = 粗细都有 ──────────────────────────────────────────────────

def test_variable_font_beats_a_family_with_no_regular_suffix():
    """VF 文件没有 Regular 字样，但它本身就覆盖常规，不该因此落榜。"""
    files = [
        _f("C:/x/NotoSansSC-VF.ttf", 3),            # 开源，rank 更靠前
        _f("C:/x/MiSans-Regular.ttf", 10, "free"),  # 免费商用，rank 更靠后
        _f("C:/x/MiSans-Bold.ttf", 10, "free"),
    ]
    assert fk._pick(files, False)[0].endswith("NotoSansSC-VF.ttf"), (
        "VF 因为文件名没 Regular 被排到后面了")
    bold = fk._pick(files, True)
    assert bold[0].endswith("NotoSansSC-VF.ttf"), (
        "粗体跑去了另一个家族：%s" % (bold[0],))


def test_is_variable_recognises_common_names():
    for n in ("NotoSansSC-VF.ttf", "NotoSansSC-VariableFont_wght.ttf",
              "SourceHanSansSC-Variable.otf"):
        assert fk._is_variable(n), n
    for n in ("MiSans-Regular.ttf", "SourceHanSansSC-Bold.otf"):
        assert not fk._is_variable(n), n


# ── 3. 白名单排序：开源优先于免费商用 ──────────────────────────────────────

def test_open_license_outranks_free_commercial():
    open_rank = fk._match_known("SourceHanSansSC-Regular.otf")[0]
    free_rank = fk._match_known("MiSans-Regular.ttf")[0]
    assert open_rank < free_rank
    assert fk._match_known("NotoSansSC-VF.ttf")[1] == "open"
    assert fk._match_known("MiSans-Bold.ttf")[1] == "free"


def test_unknown_font_is_not_matched():
    assert fk._match_known("Comic Sans MS.ttf") is None
    assert fk._match_known("arialuni.ttf") is None


# ── 4. 报错必须带出口 ───────────────────────────────────────────────────────

def test_error_message_carries_download_and_install_steps(monkeypatch):
    """空机器上必须能照报错做完，不许只说「请自备字体」。"""
    monkeypatch.setattr(fk, "_scan_font_files", lambda: [])
    monkeypatch.setattr(fk, "_SYSTEM_CJK", ())
    fk._find_font_cached.cache_clear()
    try:
        fk.font_info(False)
    except fk.FontNotFoundError as e:
        msg = str(e)
    else:
        raise AssertionError("空机器上居然没抛 FontNotFoundError")
    finally:
        fk._find_font_cached.cache_clear()

    for need in ("fonts.google.com", "source-han-sans", "Gitee",
                 "Windows", "macOS", "Linux", "doctor.py"):
        assert need in msg, "报错里缺「%s」，说明出口不完整：\n%s" % (need, msg)


def test_env_pointing_at_missing_file_is_a_hard_error(monkeypatch):
    monkeypatch.setenv(fk.ENV_REG, "C:/definitely/not/here.ttf")
    fk._find_font_cached.cache_clear()
    try:
        fk.font_info(False)
    except fk.FontNotFoundError as e:
        assert "not/here.ttf" in str(e)
    else:
        raise AssertionError("环境变量指错文件却没报错")
    finally:
        fk._find_font_cached.cache_clear()


# ── 5. 三档降级顺序 ────────────────────────────────────────────────────────

def test_falls_back_to_system_font_when_no_open_font(monkeypatch):
    """一台只有微软雅黑的干净中文 Windows 必须能出图（这正是原版本堵死的场景）。"""
    monkeypatch.setattr(fk, "_scan_font_files", lambda: [])
    monkeypatch.setattr(fk, "_SYSTEM_CJK", (
        ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
         "微软雅黑", "商用需授权", ["Microsoft YaHei", "微软雅黑"]),
    ))
    monkeypatch.setattr("os.path.exists", lambda p: True)
    fk._find_font_cached.cache_clear()
    fk._NOTICE_SHOWN = False
    try:
        info = fk.font_info(False)
        assert info["tier"] == "system", info
        assert fk.resolve_font_family() == ["Microsoft YaHei", "微软雅黑"], (
            "系统字体档没把原生族名交出去，Chrome 会叫不出来")
    finally:
        fk._find_font_cached.cache_clear()


if __name__ == "__main__":
    raise SystemExit(
        "用 pytest 跑：python -m pytest tests/ -q\n（本文件不提供自研断言器，"
        "避免又多一套测试口径）")
