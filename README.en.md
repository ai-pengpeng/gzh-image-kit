# gzh-image-kit

**Deterministic image toolkit for turning articles into readable social cards.**

Type-safe by geometry, not by vibes: font sizes are computed against the target screen, contrast is checked against WCAG, and the same input always produces the same image. No API keys, no accounts, no network.

> Status: **v0.1**. Extracted from a real, daily-running publishing pipeline and de-branded. Samples in `examples/`, full rationale in `docs/配图标准.md` (Chinese).
>
> 中文说明见 [README.md](README.md)。

---

## Why this exists

If you write long-form posts, you end up needing images: a cover card, a step diagram, a screenshot with an arrow, a 6-slide carousel. Three common approaches, all painful:

| Approach | Problem |
|---|---|
| Design it by hand | Doesn't scale past a couple posts a week |
| Ask a generative model | Text comes out as *painted glyphs* — garbled, uncorrectable, different every run |
| Screenshot some HTML | Works, until you notice the body text is 9px on a phone |

This toolkit takes the third path but treats **readability as a hard constraint**, not a style choice. Every guard in the code has a reason, and every reason is traceable to a shipped post that got it wrong.

It was built for a Chinese-language WeChat publication, which is why the CJK and font-licensing handling is unusually thorough — that's the part most Western tools skip, and it's the part that quietly ruins output.

## Tools

| Script | What it does | Needs |
|---|---|---|
| **`render_riso.py`** | **Main engine.** Risograph-style cards at 1242×1656, full-bleed. Nine layouts rotate automatically (misregistered display type, halftone dots, tape, pull-quote, oversized numerals…), with paper-grain texture | Pillow + Chrome |
| `dazi_kit.py` | 3:4 poster renderer. Font-size and contrast limits are enforced as assertions, not conventions | Pillow |
| `gen_cards.py` | Markdown draft → 900×1200 card set, auto-split into slides. **Lightweight**: no Chrome, plainer visuals | Pillow |
| `gen_diagram.py` | In-article diagrams: steps / compare / list / stages | Pillow |
| `annotate_shot.py` | Screenshot annotation: rect / arrow / circle / index | Pillow |
| `check.py` | Output audit: font size, contrast, file size, aspect ratio, frame numbering, watermark | Pillow |
| **`doctor.py`** | **Environment check.** Python / Pillow / Chrome / CJK fonts in one pass, with download and install commands for whatever is missing | stdlib |
| `fontkit.py` | Shared font loader. Handles variable-font (VF) weight instancing — `load(size, bold=True)` | Pillow |
| `channels.py` | Single source of truth for per-channel rules (which channels accept code-rendered images) | stdlib |

## Quick start

```bash
pip install -r requirements.txt

# 0. Check your environment first — tells you if Chrome or a CJK font is missing,
#    and prints the exact download + install commands if so.
python doctor.py

# 1. Render a set (a working spec ships in the repo)
python render_riso.py --spec examples/cards_riso.json --out out/riso/
```

**Look at the samples first** (`examples/riso/`, `examples/cards/`, `examples/diagram.png`). The value of this kit is entirely visual — parameters alone won't tell you anything.

### Fonts are auto-detected

Nothing to configure in the normal case. Resolution order:

1. `GZH_IMAGE_KIT_FONT_REG` / `_BOLD` — explicit, highest priority. A path that doesn't exist is an **error**, not a silent fallback.
2. Open-licensed CJK fonts installed on the system — Source Han Sans, Noto Sans SC/CJK, Sarasa Gothic, LXGW WenKai, WenQuanYi, MiSans, HarmonyOS Sans, Alibaba PuHuiTi…
3. System CJK faces (Microsoft YaHei, PingFang, DengXian). Used **on your machine only, never redistributed**; picking this tier prints which font it used and reminds you to check the licence.

If all three tiers fail, you get an exception that contains the download URL and install commands for Windows / macOS / Linux.

> **No font files are bundled.** The toolkit will never silently substitute a different typeface. That rule exists because a silent fallback once shipped images that looked fine and were legally unusable.

To make output reproducible across machines, pin an open font:

```bash
export GZH_IMAGE_KIT_FONT_REG=/path/to/SourceHanSansSC-Regular.otf
export GZH_IMAGE_KIT_FONT_BOLD=/path/to/SourceHanSansSC-Bold.otf
```

- Noto Sans SC — <https://fonts.google.com/noto/specimen/Noto+Sans+SC>
- Source Han Sans — <https://github.com/adobe-fonts/source-han-sans/releases>

Re-run `python doctor.py` afterwards; it should report the font as open-licensed and redistributable.

## Readability guards

The rules that make the output actually legible on a phone:

- **Font size floor is computed, not hardcoded.** `target_css_px × canvas_width / 360`. Every string lands at ≥12 CSS px on a 360 pt-wide screen. A 1080-wide canvas therefore needs ≥36 px. Change the canvas width and the floor moves with it.
- **Secondary-grey-on-light contrast ≥4.5:1** (WCAG AA), checked at render time.
- **Guards test themselves.** Each rule ships a sample it must catch; if a rule stops catching its sample, the guard reports *itself* as broken rather than passing silently.
- **File-size gates** catch the classic failure of exporting a text-only card at full photographic resolution, or a photograph at thumbnail quality.

`check.py` audits existing output, and works on a directory or a single PNG:

```bash
python check.py --images out/riso/          # group audit
python check.py --images out/cover.png      # single file
python check.py --card-fonts render_riso.py # static audit of a renderer
```

## Layouts and fields

`cards.json` assigns a layout per card with `v`. **Different layouts consume different fields** — unused fields don't error, they just don't appear.

The authoritative matrix is printed by `python render_riso.py --print-layouts` (Chinese layout names, generated from the code). The table below is that same matrix with English names, kept here for readability — **trust the command if the two ever disagree**.

| Layout | Name | tag | head | hero | points | caption | badge |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `r1` | Cover · vertical display | ✓ | ✓ | ✓ | · | ✓ | ✓ |
| `r2` | Misregistered display | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| `r3` | Halftone circle | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| `r4` | Vermilion seal | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| `r5` | Pull quote | · | ✓ | ✓ | ✓ | ✓ | · |
| `r6` | Outline numerals | · | ✓ | ✓ | ✓ | ✓ | · |
| `r7` | Lemon tape | · | ✓ | ✓ | ✓ | ✓ | · |
| `r8` | Note + tape | · | ✓ | ✓ | ✓ | ✓ | · |
| `r9` | Closing | ✓ | ✓ | ✓ | ✓ | ✓ | · |

- `hero` accepts `\n` to force a line break. Note that **the nine layouts break differently**: horizontal layouts break into *lines*, while `r1` (vertical display type) breaks into *columns* read right-to-left, so `"hero": "A\nBB"` puts `A` in the right column.
- `tag` / `head` / `hero` are **hard requirements** per layout. Miss one and zero images are produced — with all missing fields reported in a single pass, not a stack trace halfway through.
- `r5`–`r8` deliberately ignore `tag`; a label would cut across the display type. Not a bug.

## Common commands

```bash
# 1. A full card set (main path)
python render_riso.py --spec examples/cards_riso.json --out out/riso/

# 2. Markdown draft → card set (no Chrome needed, auto-split)
python gen_cards.py --in draft.md --out cards/ --tag your-topic \
  --account "Your Name" --benefit "Free, 10 minutes to learn"

# 3. In-article step diagram (also: compare / list / stages / ladder)
python gen_diagram.py --mode steps --title "Five steps" \
  --data "$(cat steps.json)" --style mint --out out/steps.png

# 4. Audit the output
python check.py --images out/riso/

# 5. Annotate a screenshot
python annotate_shot.py --in shot.png --out out/annotated.png \
  --items '[{"type":"rect","box":[120,260,500,320]},
            {"type":"arrow","frm":[600,300],"to":[510,300]},
            {"type":"label","text":"this line matters","at":[610,290]}]'
```

`--out` creates missing directories. Keep it away from `examples/` unless you intend to overwrite the reference samples.

`dazi_kit.py`, `fontkit.py` and `channels.py` are libraries without a CLI.

## Who makes this

Maintained by 澎澎 (Pengpeng), who publishes a Chinese-language newsletter about AI tooling. The toolkit is what that pipeline actually runs on — problems get fixed here first, because a post that ships tonight can't wait.

- Full rationale and standards (Chinese): [`docs/配图标准.md`](docs/配图标准.md)
- Reproducible samples and their inputs: [`examples/README.md`](examples/README.md)
- Mirror (mainland China): <https://gitee.com/ai-pengpeng/gzh-image-kit>

Issues and pull requests are welcome. If you hit a font or Chrome problem, `python doctor.py` output pasted into the issue saves a round trip.

## License

MIT © 2026 澎澎

Fonts are not included and are the user's responsibility. Open-licensed fonts (OFL / Apache) are fine commercially; system fonts ship under the OS licence — check terms before commercial use. `doctor.py` always tells you which tier and which font you're on.
