# gzh-image-kit · 公众号图片工具箱

一套**纯本地**的微信公众号图片生成工具：大字报贴图、文章卡组、步骤配图、孔版风格贴图、截图标注——内置可读性守卫（字号下限、对比度 ≥ WCAG 4.5:1、体积硬闸）。

> 状态：**v0.1** ——本工具箱从一个真实运营的公众号产线剥离而来，已去品牌化；
> 样张在 `examples/`，判据全文在 `docs/配图标准.md`。

## 工具一览

| 工具 | 用途 | 依赖 |
|---|---|---|
| **`render_riso.py`** | **主力出图**：孔版印刷风格贴图引擎，1242×1656 满幅。九种版式自动轮转（错版巨字、半调网点、胶带、引文、大数字…），纸感颗粒 | Pillow + Chrome |
| `dazi_kit.py` | 3:4 竖版大字报贴图渲染库，字号红线与对比度红线内置为断言 | Pillow |
| `gen_cards.py` | 长文 draft → 900×1200 竖版贴图卡组（自动拆卡）。**轻量版**：不依赖 Chrome，视觉也比 riso 朴素一档 | Pillow |
| `gen_diagram.py` | 步骤 / 对比 / 清单 / 阶段 四版式公众号**长文配图**（inside article，不是贴图） | Pillow |
| `annotate_shot.py` | 截图标注：红框 / 箭头 / 圆圈 / 序号 | Pillow |
| `check.py` | 产出图体检：字号、对比度、体积、比例、序号、水印 | Pillow |
| `fontkit.py` | 共享字体入口：`load(size, bold)` 统一取字体并处理可变字体（VF）字重 | Pillow |
| `channels.py` | 渠道口径唯一真身：哪个渠道能不能用代码渲染图、渠道别名表 | 标准库 |

## 快速开始

```bash
pip install -r requirements.txt

# 配置中文字体（必需，见下方「字体配置与许可」）
export GZH_IMAGE_KIT_FONT_REG=/path/to/SourceHanSansSC-Regular.otf
export GZH_IMAGE_KIT_FONT_BOLD=/path/to/SourceHanSansSC-Bold.otf
# Windows PowerShell 用：
#   $env:GZH_IMAGE_KIT_FONT_REG="C:/path/to/SourceHanSansSC-Regular.otf"
#   $env:GZH_IMAGE_KIT_FONT_BOLD="C:/path/to/SourceHanSansSC-Bold.otf"

python render_riso.py --spec examples/cards_riso.json --out examples/riso
```

`examples/` 里有现成的样张：`examples/riso/`（riso 六张一套，上面这条命令就是重跑它）、
`examples/cards/`（gen_cards 六张）、`examples/diagram.png`（步骤配图）。
**先看样张再动手**——这个工具的价值全在视觉上，光看参数看不出差别。

## 四条常用命令

```bash
# 1. 一套贴图（主力，1242×1656，九种版式自动轮转）
#    cards.json 里每张卡写 tag / head / hero / points / caption；
#    hero 里可以用 \n 手动指定断点（对仗句、金句必须自己控）
python render_riso.py --spec examples/cards_riso.json --out out/riso/

# 2. 长文 draft → 图卡组（轻量版，不需要 Chrome，自动拆卡）
python gen_cards.py --in draft.md --out cards/ --tag AI实操 --account 你的号名 \
  --benefit "全程免费，十分钟上手" --keywords 贴图,排版

# 3. 长文正文里的步骤配图（还有 compare / list / stages / ladder 四种版式）
python gen_diagram.py --mode steps --title "三分钟出一套图" \
  --data "$(cat steps.json)" --style mint --out out/steps.png

# 4. 出完整组图后体检（比例、体积上下限、序号连续、右下角水印）
python check.py --images out/riso/ --channel greenbook

# 5. 查渲染脚本里的字号与文字色对比度
python check.py --card-fonts render_riso.py
```

`--out` 指向不存在的目录会自动创建，不用先 mkdir。

`examples/` 里有完整可复现的输入与产出（含 6 张样张），
每条命令都能照着跑一遍——见 `examples/README.md`。

## 字体配置与许可

本仓库**不附带任何字体文件**，也不引用不可再分发的系统专有字体。所有出图脚本
（`dazi_kit.py` / `gen_cards.py` / `gen_diagram.py` / `annotate_shot.py` /
`render_riso.py`）统一通过 `fontkit.py` 的 `load(size, bold)` 取字体；**找不到可用
中文字体时抛清晰异常，绝不静默退回默认字体**（项目红线：静默回退曾造成
「图能出、只是悄悄换了字体」的事故）。

> **可变字体（VF）**：如果 `GZH_IMAGE_KIT_FONT_BOLD` 指向的是 `NotoSansSC-VF.ttf`
> 这类可变字体，文件本身不区分常规 / 粗体两层，必须显式做 variation instancing
> 才会出粗体。`fontkit.load(size, bold=True)` 已内置这一步（先按名字取 `Bold`，
> 退化到按 `wght` 轴设 700），所以**出图脚本一律不要自己 `ImageFont.truetype`**，
> 否则整套图会悄无声息地全部落在常规字重。

请自备一款**允许再分发 / 商用**的中文字体，推荐思源黑体 Source Han Sans SC
或 Noto Sans CJK SC（均为 SIL OFL 1.1）。配置方式（优先级从高到低）：

1. 环境变量 `GZH_IMAGE_KIT_FONT_REG` / `GZH_IMAGE_KIT_FONT_BOLD`：分别指向常规体与
   粗体字体文件的绝对路径。设了但文件不存在会直接报错，不会偷偷换字体。
2. 不设环境变量时，`fontkit.py` 会在常见系统字体目录里查找上述开源字体；
   找不到就抛 `FontNotFoundError`。

`render_riso.py` 通过 Chrome + CSS 渲染，字体走两条路，按顺序试：

1. **CSS 字体族**：`GZH_IMAGE_KIT_FONT_FAMILY`（逗号分隔，如 `Source Han Sans SC,Noto Sans CJK SC`），
   渲染前实测 Chrome 到底有没有用上它；几个族里有一个能用就用那一个，用不上的从字体栈里剔除
   （留着会让同一张图混排两种字形）。
2. **字体文件直注**：系统里一个族都没装、但 `fontkit` 能找到字体文件时，脚本自己生成
   `@font-face` 把文件喂给 Chrome，不要求「字体已注册成系统字体」。

> 第 2 条是 2026-11-14 补的。原来的逻辑是「族名找不到就拒绝出图」——听着更安全，实际把
> 一大批机器堵死在第一步：**字体文件在（PIL 排得出字），但没注册成系统字体族（Chrome 按
> 族名叫不出来）**。中文 Windows 上这是常态，尤其手工拷进 `C:\Windows\Fonts` 的开源字体。
> 两条线（PIL 按路径、Chrome 按族名）取字体的来源不同，必须能对上，否则「有字体却出不了图」。
> 只有当**两条路都断**时才拒绝出图，红线不变：绝不静默回退成别的字体。

Chrome 路径用环境变量 `CHROME_PATH` 或 `--chrome` 指定，脚本也会自动查找常见安装路径，
找不到抛清晰异常。

字体许可由使用者自行负责：请确认所选字体的许可证允许你的使用场景，并按需
在产出物中附上字体许可声明。

## 设计理念

1. **可读性是红线，不是建议**——字号下限由画布宽现算（目标屏幕字号 × 画布宽 / 360），任何文字 ≥ 手机 12 CSS px；次级灰对浅底对比度 ≥ 4.5:1。
2. **守卫要能验证自己**——每条检查规则带样本自检，规则抓不到样本时报「守卫失效」，而不是静默通过。
3. **纯本地**——零账号凭据、零商业 API key，断网也能用。

## 更多

- **判据全文**：`docs/配图标准.md`——字号红线换算公式、对比度阈值、断行规则、
  配色跟随封面、六条视觉机制。代码里每条守卫都能在这里找到依据。
- **效果样张**：`examples/`（可复现，命令都在 `examples/README.md`）。
- **渠道差异**：`check.py --images <目录>` 默认走通用体检；
  加 `--channel greenbook`（别名 `贴图` / `小绿书`）走贴图渠道硬闸。
  代码渲染的图卡不适用于该渠道，`gen_cards.py` / `gen_diagram.py` 会直接拒绝。
- **教程与实例**：微信公众号「**AI澎**」，后台回复「**贴图**」获取最新版与示例。
- **代码托管**：GitHub `ai-pengpeng/gzh-image-kit`（主仓）｜Gitee `ai-pengpeng/gzh-image-kit`（国内镜像）

## License

MIT © 2026 澎澎
