#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""doctor.py —— 环境体检。装完先跑这一条，别等出图失败了再猜。

    python doctor.py

它检查四件事，每件都给「现在什么状态 + 不行的话怎么办」：

  1. Python 与 Pillow        —— 出图的基本盘
  2. Chrome / Chromium       —— 主力引擎靠它截图
  3. 中文字体                —— 最容易卡住的一关
  4. 示例数据能否出图        —— 可选，加 --render 实际跑一张验证

为什么要有这个脚本（2026-11-14，两个外部实测者的反馈）
------------------------------------------------------
两位新用户卡在同一处：字体。README 写了「自备一款思源黑体或 Noto Sans SC」，
也给了下载地址，但都是**先跑、失败、回头看文档**的顺序。其中一位运气好，
在自己机器的系统字体目录里翻到了可用的字体才过去。

体检把这一步提前：一条命令告诉你「你缺什么、去哪下、下完放哪」，
不用先撞一次墙。
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OK, WARN, BAD = "✅", "⚠️ ", "❌"

TROUBLE = []
# 不阻塞出图、但必须在结论里说一句的事（现在只有一条：字体是本机碰巧有的）。
NOTES = []


def say(mark: str, title: str, detail: str = "", fix: str = "") -> None:
    print("%s %s" % (mark, title))
    if detail:
        for line in detail.strip().splitlines():
            print("     " + line)
    if fix:
        for line in fix.strip().splitlines():
            print("     → " + line)
    if mark == BAD:
        TROUBLE.append(title)
    print()


def check_python() -> None:
    v = sys.version_info
    if v < (3, 8):
        say(BAD, "Python %d.%d —— 版本太低，本仓库要求 3.8+" % (v.major, v.minor),
            fix="装一个 3.10 以上的 Python 再来。")
        return
    say(OK, "Python %d.%d.%d（%s）" % (v.major, v.minor, v.micro, platform.system()),
        detail=sys.executable)

    try:
        import PIL
        say(OK, "Pillow %s" % PIL.__version__)
    except Exception as e:
        say(BAD, "Pillow 没装（%s）" % e,
            fix="pip install -r requirements.txt")


def check_chrome() -> None:
    """与 render_riso.resolve_chrome 同一套查找顺序，只读不写。"""
    cli = ""
    env = os.environ.get("CHROME_PATH", "").strip().strip('"').strip("'")
    local = os.environ.get("LOCALAPPDATA", "")
    cands = [c for c in [
        env,
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        os.path.join(local, "Google", "Chrome", "Application", "chrome.exe") if local else "",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium", "/usr/bin/chromium-browser",
    ] if c]
    for name in ("chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            cands.append(found)
    for c in cands:
        if c and os.path.exists(c):
            if not env and c != cli:
                say(OK, "Chrome 找到了", detail=c)
            else:
                say(OK, "Chrome 找到了（来自 %s）" % ("CHROME_PATH" if c == env else "自动查找"),
                    detail=c)
            return
    say(BAD, "没找到 Chrome / Chromium",
        detail="render_riso.py（主力出图）和字体实测都要用它截图。\n"
               "gen_cards.py / gen_diagram.py 不需要 Chrome，可以先跑那两个。",
        fix="装 Chrome：https://www.google.cn/chrome/\n"
            "或已装在别处就设环境变量：export CHROME_PATH=\"/你的/chrome 路径\"")


def check_font() -> None:
    try:
        import fontkit
    except Exception as e:
        say(BAD, "字体模块加载失败（%s）" % e, fix="确认 doctor.py 和 fontkit.py 在同一目录。")
        return

    print("[i] 字体白名单扫描到的候选（越靠前越优先）：")
    try:
        cands = fontkit._scan_font_files()
    except Exception:
        cands = []
    if cands:
        for path, rank, tier, note in cands[:8]:
            print("     %s [%s] %s" % ("·", tier, path))
        if len(cands) > 8:
            print("     … 还有 %d 个" % (len(cands) - 8))
    else:
        print("     （一个都没扫到）")
    print()

    try:
        reg = fontkit.font_info(False)
        bold = fontkit.font_info(True)
    except Exception as e:
        msg = str(e)
        # 按「环境变量到底设没设」判病因，**不要按报错正文里的关键词判**：
        # 「三档都没命中」那段正文里本来就有「已经找过：环境变量 → …」几个字，
        # 用关键词判会让「一个中文字体都没有」的机器被误诊成「环境变量写错了」。
        # 2026-11-14 干净机器实测撞出来的：没设任何变量，却报「变量指向的文件不存在」。
        env_set = [k for k in (fontkit.ENV_REG, fontkit.ENV_BOLD)
                   if (os.environ.get(k) or "").strip()]
        head, sep, tail = msg.partition("去哪儿弄")
        if env_set:
            say(BAD, "字体环境变量指向的文件不存在", detail=head.strip(),
                fix="把 %s 改成真实存在的文件绝对路径；或清掉这个变量"
                    "（Windows：set %s=　/macOS·Linux：unset %s），"
                    "让脚本按三档自动查找。" % ("、".join(env_set), env_set[0], env_set[0]))
        else:
            say(BAD, "找不到可用的中文字体",
                detail="这是新用户最容易卡住的一关，别慌，下面三条路都能通。")
        print(msg if not sep else "去哪儿弄" + tail)
        print()
        return

    tier = reg["tier"]
    if tier == "env":
        say(OK, "字体：环境变量指定", detail=reg["path"])
    elif tier == "open":
        say(OK, "字体：开源可再分发", detail=reg["name"],
            fix="" if bool(bold and bold["path"] == reg["path"]) else
            "常规与粗体不是同一个文件，确认两者来自同一家族。")
    elif tier == "free":
        say(WARN, "字体：免费商用字体（不是开源）", detail=reg["name"],
            fix="自己用没问题。要把图给别人复现、或做商业项目，建议换成开源字体\n"
                "（思源黑体 / Noto Sans SC，SIL OFL 1.1，见下文）。")
        NOTES.append("字体用的是本机「%s」，换台机器重跑字形会变" % reg["name"])
    elif tier == "system":
        say(WARN, "字体：本机系统自带", detail=reg["name"],
            fix="自己用没问题，但别人下载这个仓库后**不一定有你这份字体**，\n"
                "出图效果会跟着变。想稳定复现就换开源字体（见下文）。")
        NOTES.append("字体用的是本机「%s」，换台机器重跑字形会变" % reg["name"])

    if reg["path"] != (bold["path"] if bold else ""):
        print("     常规：%s" % reg["path"])
        print("     粗体：%s" % (bold["path"] if bold else "(缺失)"))
        print()

    # 出问题时的出口，和 fontkit 的报错同一份文案
    if tier in ("system",):
        print("     想换成开源字体（推荐，一次装好永久省心）：")
        for line in fontkit._DOWNLOAD_HINT.splitlines():
            print("     " + line)
        print()


def check_optional() -> None:
    """可选项：不装也能跑部分功能，只提示不拦。"""
    try:
        import playwright  # noqa: F401
        say(OK, "playwright 已装（只有部分扩展脚本用得到）")
    except Exception:
        say(WARN, "playwright 没装 —— 不影响出图",
            fix="确实需要再装：pip install playwright && playwright install chromium")


def check_render() -> None:
    """--render：真出一张图，验证整条链路。"""
    root = Path(__file__).resolve().parent
    spec = root / "examples" / "cards_riso.json"
    if not spec.exists():
        say(WARN, "跳过实测出图：找不到 examples/cards_riso.json")
        return
    out = Path(tempfile.mkdtemp(prefix="doctor_"))
    print("[i] 实跑一张验证链路（输出到临时目录，不碰仓库）…")
    r = subprocess.run([sys.executable, str(root / "render_riso.py"),
                        "--spec", str(spec), "--out", str(out), "--no-grain"],
                       cwd=str(root), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    made = sorted(out.glob("*.png"))
    if r.returncode == 0 and made:
        say(OK, "出图成功：%d 张" % len(made), detail=str(out))
    else:
        say(BAD, "出图失败（退出码 %d）" % r.returncode,
            detail=(r.stdout or "")[-800:] + (r.stderr or "")[-800:])


def main() -> int:
    ap = argparse.ArgumentParser(description="gzh-image-kit 环境体检")
    ap.add_argument("--render", action="store_true", help="额外实跑一张图验证整条链路")
    a = ap.parse_args()

    print("=" * 62)
    print("gzh-image-kit 环境体检")
    print("=" * 62)
    print()
    check_python()
    check_chrome()
    check_font()
    check_optional()
    if a.render:
        check_render()

    print("=" * 62)
    if TROUBLE:
        print("结论：还有 %d 项不通 —— %s" % (len(TROUBLE), "、".join(TROUBLE)))
        print("      照上面 → 后面那几行做，做完重跑 `python doctor.py`。")
        return 1
    print("结论：环境没问题，可以直接出图。")
    if NOTES:
        # 「没问题」这四个字太容易让人只读第一行就走。
        # 能出图 ≠ 出的图和作者一样：字体是本机碰巧有的，换台机器字形就变。
        # 这句话必须出现在结论里，而不是只藏在上面那一大段里——
        # 2026-11-14 新人实测：他第一遍就是只看结论、没读字体段。
        print("      但有一件事要知道：%s。" % "；".join(NOTES))
        print("      自己用无所谓；要把图发给别人复现、或换台电脑重跑，"
              "按上面「字体」那段装一款开源字体更稳。")
    print()
    print()
    print("下一步：")
    print("  python render_riso.py --spec examples/cards_riso.json --out out/riso/")
    print("  先看 examples/riso/ 里的样张，再看自己的产出，对照着调。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
