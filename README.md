# gzh-image-kit · 公众号图片工具箱

一套**纯本地**的微信公众号图片生成工具：大字报贴图、文章卡组、步骤配图、孔版风格贴图、截图标注——内置可读性守卫（字号下限、对比度 ≥ WCAG 4.5:1、体积硬闸）。

> 状态：**v0.1** ——本工具箱从一个真实运营的公众号产线剥离而来，已去品牌化；
> 样张在 `examples/`，判据全文在 `docs/配图标准.md`。

## 工具一览

| 工具 | 用途 | 依赖 |
|---|---|---|
| **`render_riso.py`** | **主力出图**：孔版印刷风格贴图引擎，1242×1656 满幅。九种版式自动轮转（错版巨字、半调网点、胶带、引文、大数字…），纸感颗粒 | Pillow + Chrome |
| `dazi_kit.py` | 3:4 竖版大字报贴图渲染库，字号红线与对比度红线内置为断言 | Pillow |
| `gen_cards.py` | 长文 draft → 900×1200 竖版**图卡组**（自动拆卡）。**轻量版**：不依赖 Chrome，视觉也比 riso 朴素一档。注意这不是 greenbook 渠道的「贴图」，见「渠道差异」 | Pillow |
| `gen_diagram.py` | 步骤 / 对比 / 清单 / 阶段 四版式公众号**长文配图**（inside article，不是贴图） | Pillow |
| `annotate_shot.py` | 截图标注：红框 / 箭头 / 圆圈 / 序号 | Pillow |
| `check.py` | 产出图体检：字号、对比度、体积、比例、序号、水印 | Pillow |
| **`doctor.py`** | **环境体检**：Python / Pillow / Chrome / 中文字体一次查完，缺什么直接给下载与安装命令 | 标准库 |
| `fontkit.py` | 共享字体入口：`load(size, bold)` 统一取字体并处理可变字体（VF）字重 | Pillow |
| `channels.py` | 渠道口径唯一真身：哪个渠道能不能用代码渲染图、渠道别名表 | 标准库 |

## 快速开始

```bash
pip install -r requirements.txt

# 0. 先体检（强烈建议，尤其第一次用）
#    它会告诉你 Chrome 有没有、中文字体缺不缺、缺的话去哪下、下完放哪。
#    有 ❌ 就照它给的命令做，做完重跑一次；没 ❌ 直接往下。
python doctor.py

# 1. 出图（示例配置，仓库自带）
python render_riso.py --spec examples/cards_riso.json --out out/riso/
```

**字体不用预先配**：脚本会自动找——先看环境变量，再看系统里装的开源中文字体
（思源黑体 / Noto Sans SC / 霞鹜文楷…），最后退到系统自带的中文黑体
（微软雅黑 / 苹方 / 等线）。**找不到才报错，并把下载地址和安装命令一起打出来。**

想用指定的字体（推荐，这样别人重跑你的配置能出一样的图）：

```bash
# bash
export GZH_IMAGE_KIT_FONT_REG=/path/to/SourceHanSansSC-Regular.otf
export GZH_IMAGE_KIT_FONT_BOLD=/path/to/SourceHanSansSC-Bold.otf
# Windows PowerShell
#   $env:GZH_IMAGE_KIT_FONT_REG="C:/path/to/SourceHanSansSC-Regular.otf"
#   $env:GZH_IMAGE_KIT_FONT_BOLD="C:/path/to/SourceHanSansSC-Bold.otf"
```

> **`--out` 只别指向 `examples/`**：那会直接覆盖官方样张，之后就再没有「合格产出长什么样」的
> 参照物了。仓库根的 `out/` 已在 `.gitignore` 里，写进去不会误提交，但为了不跟样张混，建议直接写你自己的目录。

`examples/` 里有现成的样张：`examples/riso/`（riso 六张一套，上面这条命令就是重跑它）、
`examples/cards/`（gen_cards 六张）、`examples/diagram.png`（步骤配图）。
**先看样张再动手**——这个工具的价值全在视觉上，光看参数看不出差别。

## 六条常用命令

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
#    --images 收目录或单张 PNG；单文件点查自动跳过组级检查（张数/序号/跨图水印）
python check.py --images out/riso/ --channel greenbook

# 5. 查渲染脚本里的字号与文字色对比度
python check.py --card-fonts render_riso.py

# 6. 截图标注（红框 / 箭头 / 圆圈 / 序号）
python annotate_shot.py --in shot.png --out out/shot_anno.png \
  --items '[{"type":"rect","box":[120,260,500,320]},
            {"type":"arrow","frm":[600,300],"to":[510,300]},
            {"type":"label","text":"这行是关键","at":[610,290]}]'
```

`--out` 指向不存在的目录会自动创建，不用先 mkdir。

`dazi_kit.py` / `fontkit.py` / `channels.py` 是库（无 CLI），被上述脚本引用；
`dazi_kit` 把字号红线与对比度红线内置为断言，可用 `check.py --card-fonts` 静态体检。

`examples/` 里有完整可复现的输入与产出（含 6 张样张），
每条命令都能照着跑一遍——见 `examples/README.md`。

## 版式 × 字段对照表

`cards.json` 里每张卡用 `v` 指定版式。**不同版式吃的字段不一样**——配了不吃的字段不会报错，
只是不会出现在图上。所以先看这张表（由 `python render_riso.py --print-layouts` 生成，
不要手抄）：

| 版式 | 名称 | tag | head | hero | points | caption | badge |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `r1` | 封面·竖排巨字 | ✓ | ✓ | ✓ | · | ✓ | ✓ |
| `r2` | 错版大字 | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| `r3` | 网屏圆 | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| `r4` | 朱红印章 | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| `r5` | 大引文 | · | ✓ | ✓ | ✓ | ✓ | · |
| `r6` | 空心数字 | · | ✓ | ✓ | ✓ | ✓ | · |
| `r7` | 柠檬纸带 | · | ✓ | ✓ | ✓ | ✓ | · |
| `r8` | 纸条+胶带 | · | ✓ | ✓ | ✓ | ✓ | · |
| `r9` | 收尾 | ✓ | ✓ | ✓ | ✓ | ✓ | · |

- `hero` 支持 `\n` 手动指定断点，但**九种版式的断法不一样**：横向版式断成**行**，
  `r1` 竖排巨字断成**列**（右起第一列在最右，从右往左读）。对仗句、金句必须自己控断点。
  > 自己能验的例子：`"hero": "甲\n乙乙"` 出 `r1`，**「甲」在右边那列，「乙乙」在左边那列**。
  > （写这条是因为 2026-11-14 有个测试者用「第一行\n第二行」验，两组都以「第」开头、
  > `一` 和 `二` 在竖排里都是横杠，把方向读反了——不是实现错，是这个例子不好验。）
- **`tag` / `head` / `hero` 是硬必填**：表里打 ✓ 就代表这款版式真要用它，缺一个就
  **一张图都不出**，而且一次把每张缺什么都报出来（不会出到一半才崩，也不会甩一屏英文栈）。
- `badge` 是封面左下角那枚张数徽章里的字：默认显示「N 张」，配了就换成你写的；只有 `r1` 用。
- `points` 和 `caption` 进的是同一块收口区：有 `points` 出要点，没有才退回 `caption`。
- `r1` 的 `caption`、`r9` 的大字遇到长句会自动断行，**不会把最后两个字甩到单独一行**（防孤行）。
  但断点由引擎按标点算，不一定是你想要的那一处——要控就自己写 `\n`。经验值：`hero` 每段 ≤10 字。
- `r5`–`r8` 是单栏大字版式，**故意不吃 `tag`**：标签会打断大字。不是 bug。
- 题签（`tag`）的颜色是有意的层级：`r1` 封面用朱红（全套唯一强调色），内页一律灰。
  内页要收敛，让巨字当主角——不是没统一。
- 不写 `v` 时按 `r1…r9` 顺序轮转。
- `subdir` 是 `render_cards.py`（另一款卡片引擎）的输出子目录，本引擎不读；
  同一个 `cards.json` 常被两个引擎共用，所以它在顶层出现是合法的。
- 渲染前会体检一遍字段。配了不吃的字段只提示、不报错，且**同一字段的多张合并成一行**：

  ```
  [i] （提示）第 4、6 张配了 tag，这几款版式不显示它——不影响出图，想确认某款用哪些字段看 `--print-layouts`
  ```

  真错误（字段名拼错、`v` 不存在、`idx` 与顺序对不上）仍然是 `[!]`，并且会拦住出图。

页面品牌串（页眉「X · 图文卡」、页脚「X · 02 / 06」）三个入口，优先级从高到低：
`--brand 你的号名` > `cards.json` 的 `"brand"` > `"footer"` 里 `·` 前第一段 > 环境变量 `GZH_IMAGE_KIT_BRAND`。



## 字体配置与许可

先说结论：**正常情况你什么都不用配。** 只有脚本自己找不到字体时，才需要动手。

本仓库**不附带任何字体文件**。所有出图脚本（`dazi_kit.py` / `gen_cards.py` /
`gen_diagram.py` / `annotate_shot.py` / `render_riso.py`）统一通过 `fontkit.py`
取字体；找不到可用中文字体时抛清晰异常，**绝不静默退回默认字体**
（项目红线：静默回退曾造成「图能出、只是悄悄换了字体」的事故）。

### 字体按三档查找

| 档 | 找什么 | 说明 |
|---|---|---|
| 1 | 环境变量 `GZH_IMAGE_KIT_FONT_REG` / `_BOLD` | 你明确指定，优先级最高；指的文件不存在会直接报错，不会偷偷换 |
| 2 | 系统里装的开源 / 免费商用中文字体 | 思源黑体、Noto Sans SC/CJK、更纱黑体、霞鹜文楷、文泉驿、MiSans、HarmonyOS Sans、阿里巴巴普惠体…按白名单文件名识别，**优先选许可证最干净的** |
| 3 | 系统自带的中文黑体 | 微软雅黑、等线、黑体、苹方、冬青黑体。**只在你机器上用，不随仓库分发**；用到这一档会打一条提示，写明用的是哪份字体、授权要自己确认，并给出开源字体的下载地址与安装动作 |

三档都不通才报错，异常里直接写清下载地址 + Windows / macOS / Linux 三种安装命令。

> **为什么有第 3 档**（2026-11-14，外部实测反馈）
> 原来的白名单只认开源字体，本意是「不把字体文件打包进仓库」。但那条规矩被执行成了
> 「运行时也不许用系统字体」，结果**一台只有微软雅黑的中文 Windows 会被完全堵死**：
> 文件在、能用、合法，却报 `FontNotFoundError`。两个独立外部测试者都卡在这一步。
> 正确的边界是：**分发**只用可再分发字体，**运行时**允许用本机已授权的字体——
> 前提是把「你现在用的哪个、授权自己看」说出来，这才是原来那条红线的本意。

### 想稳定复现，就配一款开源字体

第 2、3 档都是「你机器上碰巧有什么就用什么」。**你要把配置发给别人、或者换台机器重跑，
出来的字可能就不一样了。** 想彻底稳定，装一款开源字体并固定下来：

- Noto Sans SC —— <https://fonts.google.com/noto/specimen/Noto+Sans+SC>（右上 Download family）
- 思源黑体 Source Han Sans —— <https://github.com/adobe-fonts/source-han-sans/releases>
- 国内打不开：在 Gitee 搜「思源黑体」/「Noto Sans SC」，一般有人做镜像（认准 SIL OFL 协议）

装进系统字体目录后重跑 `python doctor.py`，它应该报「字体：开源可再分发」。
或者不装，用上面第 1 档的环境变量直接指过去。

> **可变字体（VF）**：如果指向的是 `NotoSansSC-VF.ttf` 这类可变字体，文件本身不区分
> 常规 / 粗体两层，必须显式做 variation instancing 才会出粗体。
> `fontkit.load(size, bold=True)` 已内置这一步（先按名字取 `Bold`，退化到按 `wght` 轴设 700），
> 所以**出图脚本一律不要自己 `ImageFont.truetype`**，否则整套图会悄无声息地全部落在常规字重。

### Chrome 端的两条路

`render_riso.py` 通过 Chrome + CSS 渲染，字体走两条路，按顺序试：

1. **CSS 字体族**：`GZH_IMAGE_KIT_FONT_FAMILY`（逗号分隔，如 `Source Han Sans SC,Noto Sans CJK SC`）；
   不设时按第 2/3 档自动给出族名。渲染前实测 Chrome 到底有没有用上它，几个族里有一个能用
   就用那一个，用不上的从字体栈里剔除（留着会让同一张图混排两种字形）。
2. **字体文件直注**：系统里一个族都没装、但 `fontkit` 能找到字体文件时，脚本自己生成
   `@font-face` 把文件喂给 Chrome，不要求「字体已注册成系统字体」。

> 第 2 条是 2026-11-14 补的。原来的逻辑是「族名找不到就拒绝出图」——听着更安全，实际把
> 一大批机器堵死在第一步：**字体文件在（PIL 排得出字），但没注册成系统字体族（Chrome 按
> 族名叫不出来）**。中文 Windows 上这是常态，尤其手工拷进 `C:\Windows\Fonts` 的开源字体。
> 两条线（PIL 按路径、Chrome 按族名）取字体的来源不同，必须能对上，否则「有字体却出不了图」。

Chrome 路径用环境变量 `CHROME_PATH` 或 `--chrome` 指定，脚本也会自动查找常见安装路径，
找不到抛清晰异常。

### 许可

字体许可由使用者自行负责。开源字体（OFL / Apache）商用无虞；系统自带字体（微软雅黑、
苹方等）随操作系统授权，**用于商业产出前请确认其条款**。`python doctor.py` 会明确告诉你
当前用的是哪一档、哪一款。

## 设计理念

1. **可读性是红线，不是建议**——字号下限由画布宽现算（目标屏幕字号 × 画布宽 / 360），任何文字 ≥ 手机 12 CSS px；次级灰对浅底对比度 ≥ 4.5:1。
2. **守卫要能验证自己**——每条检查规则带样本自检，规则抓不到样本时报「守卫失效」，而不是静默通过。
3. **纯本地**——零账号凭据、零商业 API key，断网也能用。

## 更多

- **判据全文**：`docs/配图标准.md`——字号红线换算公式、对比度阈值、断行规则、
  配色跟随封面、六条视觉机制。代码里每条守卫都能在这里找到依据。
- **效果样张**：`examples/`（可复现，命令都在 `examples/README.md`）。
- **渠道差异**：`check.py --images <目录或单张 PNG>` 默认走通用体检；
  加 `--channel greenbook`（别名 `贴图` / `小绿书`）走贴图渠道硬闸。
  代码渲染的图卡不适用于该渠道，`gen_cards.py` / `gen_diagram.py` 生成前就会直接拒绝；
  已经生成的卡组误喂给 greenbook 硬闸时，报错会一次说清两条出路（换 render_riso 出插画，或走通用体检）。
- **教程与实例**：微信公众号「**AI澎**」，后台回复「**贴图**」获取最新版与示例。
- **代码托管**：GitHub `ai-pengpeng/gzh-image-kit`（主仓）｜Gitee `ai-pengpeng/gzh-image-kit`（国内镜像）

## License

MIT © 2026 澎澎
