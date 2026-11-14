# gzh-image-kit · 公众号图片工具箱

一套**纯本地**的微信公众号图片生成工具：大字报贴图、文章卡组、步骤配图、孔版风格贴图、截图标注——内置可读性守卫（字号下限、对比度 ≥ WCAG 4.5:1、体积硬闸）。

> 状态：**v0.1 开发中**——本工具箱从一个真实运营的公众号产线剥离而来，正在完成去品牌化与文档，示例图陆续补充。

## 工具一览

| 工具 | 用途 | 依赖 |
|---|---|---|
| `dazi_kit.py` | 3:4 竖版大字报贴图渲染库，字号红线与对比度红线内置为断言 | Pillow |
| `gen_cards.py` | 长文 draft → 900×1200 竖版贴图卡组（自动拆卡） | Pillow |
| `gen_diagram.py` | 步骤 / 对比 / 清单 / 阶段 四版式公众号配图，5 套配色 | Pillow |
| `render_riso.py` | 孔版印刷（Riso）风格贴图引擎：错版、半调网点、纸感颗粒 | Pillow + Chrome |
| `annotate_shot.py` | 截图标注：红框 / 箭头 / 圆圈 / 序号 | Pillow |
| `check.py` | 产出图静态体检：字号、对比度、体积三道硬闸 | Pillow |
| `fontkit.py` | 共享字体解析模块：统一 `resolve_font()`，找不到可用中文字体时抛异常、绝不静默回退 | 标准库 |

## 快速开始

```bash
pip install -r requirements.txt

# 配置中文字体（必需，见下方「字体配置与许可」）
export GZH_IMAGE_KIT_FONT_REG=/path/to/SourceHanSansSC-Regular.otf
export GZH_IMAGE_KIT_FONT_BOLD=/path/to/SourceHanSansSC-Bold.otf
# Windows PowerShell 用：
#   $env:GZH_IMAGE_KIT_FONT_REG="C:/path/to/SourceHanSansSC-Regular.otf"
#   $env:GZH_IMAGE_KIT_FONT_BOLD="C:/path/to/SourceHanSansSC-Bold.otf"

python gen_diagram.py --help
```

## 字体配置与许可

本仓库**不附带任何字体文件**，也不引用不可再分发的系统专有字体。所有出图脚本
（`dazi_kit.py` / `gen_cards.py` / `gen_diagram.py` / `annotate_shot.py` /
`render_riso.py`）统一通过 `fontkit.py` 的 `resolve_font()` 取字体；**找不到可用
中文字体时抛清晰异常，绝不静默退回默认字体**（项目红线：静默回退曾造成
「图能出、只是悄悄换了字体」的事故）。

请自备一款**允许再分发 / 商用**的中文字体，推荐思源黑体 Source Han Sans SC
或 Noto Sans CJK SC（均为 SIL OFL 1.1）。配置方式（优先级从高到低）：

1. 环境变量 `GZH_IMAGE_KIT_FONT_REG` / `GZH_IMAGE_KIT_FONT_BOLD`：分别指向常规体与
   粗体字体文件的绝对路径。设了但文件不存在会直接报错，不会偷偷换字体。
2. 不设环境变量时，`fontkit.py` 会在常见系统字体目录里查找上述开源字体；
   找不到就抛 `FontNotFoundError`。

`render_riso.py` 通过 Chrome + CSS 渲染，另用 `GZH_IMAGE_KIT_FONT_FAMILY`
（逗号分隔，如 `Source Han Sans SC,Noto Sans CJK SC`）指定 CSS 字体族候选，
同样先做字体文件硬校验。Chrome 路径用环境变量 `CHROME_PATH` 或 `--chrome`
指定，脚本也会自动查找常见安装路径，找不到抛清晰异常。

字体许可由使用者自行负责：请确认所选字体的许可证允许你的使用场景，并按需
在产出物中附上字体许可声明。

## 设计理念

1. **可读性是红线，不是建议**——字号下限由画布宽现算（目标屏幕字号 × 画布宽 / 360），任何文字 ≥ 手机 12 CSS px；次级灰对浅底对比度 ≥ 4.5:1。
2. **守卫要能验证自己**——每条检查规则带样本自检，规则抓不到样本时报「守卫失效」，而不是静默通过。
3. **纯本地**——零账号凭据、零商业 API key，断网也能用。

## 更多

- **教程与实例**：微信公众号「**AI澎**」，后台回复「**贴图**」获取最新版与示例。
- **Gitee 镜像**（国内访问更稳）：建设中。

## License

MIT © 2026 澎澎
