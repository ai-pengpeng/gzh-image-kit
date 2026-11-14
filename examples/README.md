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

## 还没提供样张的部分

- **greenbook（贴图 / 小绿书）渠道的正典样张**：该渠道要的是生图模型出的插画，
  不是代码渲染的卡片，本仓库不产这类图，所以这里没有样张。
  它的规格写在 `check.py` 的 greenbook 硬闸里（体积 ≥150KB、3:4、品牌绿占比）。
- **孔版印刷（render_riso）**：需要 Chrome 环境，样张另附。
