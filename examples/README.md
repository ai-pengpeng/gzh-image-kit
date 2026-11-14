# examples · 效果样张

这里的图全部由本仓库的脚本生成，输入是 `sample_draft.md` 与 `steps_data.json`。
**可复现**：照下面的命令重跑，出来的图应该和仓库里这几张一致（字体不同会略有差异）。

## 卡组（gen_cards）

```bash
python gen_cards.py \
  --in examples/sample_draft.md \
  --out examples/cards \
  --tag 工具箱 \
  --account 你的号名 \
  --keywords 贴图,字号,可读性
```

产出 6 张 900×1200（3:4 竖版）：

| 文件 | 是什么 | 看什么 |
|---|---|---|
| `cards/card_01.png` | 封面 | 主标题 3 秒讲清讲什么；副标给一句利益点 |
| `cards/card_02.png` | 小节要点 | 一张卡最多 6 条，多了就拆卡 |
| `cards/card_03.png` | 小节要点 | 要点超过一行时按词断行，不劈词 |
| `cards/card_04.png` | 小节要点 | 序号与总数（03/06）在右上角 |
| `cards/card_05.png` | 金句 | 引语卡居中，字号比要点大一档 |
| `cards/card_06.png` | 尾卡 | 合集名 + 关键词 + 引导语 |

> `--benefit` 不传时，首卡副标会用文章首句兜底（`cards/meta.json` 里
> `benefit_auto: true` 表示这一句是自动来的）。兜底只是不空着，不如手写一句。

## 步骤图（gen_diagram）

```bash
python gen_diagram.py \
  --mode steps \
  --title "三分钟出一套图" \
  --sub "从装依赖到体检收工" \
  --foot "每一步都能单独重跑，不用从头再来" \
  --data "$(cat examples/steps_data.json)" \
  --style mint \
  --out examples/diagram.png
```

| 文件 | 规格 | 看什么 |
|---|---|---|
| `diagram.png` | 1080×2188 | 五步纵向排列，底部一句结论（`--foot`）收口 |

## 出完图要体检

```bash
# 通用档：比例、体积上下限、序号连续、右下角水印
python check.py --images examples/cards

# 渲染脚本里的字号与文字色对比度（静态）
python check.py --card-fonts gen_cards.py
```

两条都应该 PASS。若有 FAIL，先看提示里指的判据章节（`docs/配图标准.md`）。

## 孔版印刷卡组（render_riso）

这是本仓库的门面：9 款版式、套色错位、颗粒网屏，全套由 `render_riso.py` 用 Chrome
跑 CSS 渲染出来，不经过任何生图模型。

```bash
python render_riso.py --spec examples/cards_riso.json --out out/riso/
```

产出 6 张 1242×1656（3:4 竖版），对应仓库里 `examples/riso/` 这 6 张：

| 文件 | 版式 | 看什么 |
|---|---|---|
| `riso/贴图为什么传得开-01.png` | `r1` 封面·竖排巨字 | 竖排是中文海报天然的填满法；题签用朱红，全套唯一强调色 |
| `riso/贴图为什么传得开-02.png` | `r2` 错版大字 | 套色故意错开一点点，别对齐——对齐就没印刷味了 |
| `riso/贴图为什么传得开-03.png` | `r3` 网屏圆 | 网屏是颗粒，不是渐变；放大看能看见点 |
| `riso/贴图为什么传得开-04.png` | `r4` 朱红印章 | 印章负责给版面「压住」，别配满 |
| `riso/贴图为什么传得开-05.png` | `r5` 大引文 | 纸条+胶带是唯一允许的「装饰」，它承担层级不承担信息 |
| `riso/贴图为什么传得开-06.png` | `r9` 收尾 | 收口区只放一句要带走的话 |

`cards_riso.json` 里每张卡的 `v` 指定版式，**各版式吃的字段不一样**。
动手前先跑一遍这张表，别靠猜：

```bash
python render_riso.py --print-layouts
```

只想改文案的话，复制一份 `cards_riso.json` 改 `head` / `hero` / `points` 就行，
不用碰代码。**配色、版式顺序、字号策略、画布尺寸都是刻意的**，不开放配置——
这些是这套图「像一套」的原因，改了就散。

## 还没提供样张的部分

- **greenbook（贴图 / 小绿书）渠道的正典样张**：该渠道要的是生图模型出的插画，
  不是代码渲染的卡片，本仓库不产这类图，所以这里没有样张。
  它的规格写在 `check.py` 的 greenbook 硬闸里（体积 ≥150KB、3:4、品牌绿占比）。
