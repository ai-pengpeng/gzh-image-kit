# 开源剥离 TODO（发布前必须清零）

> 扫描时间：2026-11-14。发布标准：下表全部勾完 + `grep` 复扫零命中。
> 复核时间：2026-11-14（脱敏改造完成后逐项复核，详见文末「复核记录」）。

## 一、品牌词与个人路径

- [x] `dazi_kit.py` — `REF` 指向本机专家包目录 → 已改为可选常量 `REF = None`（默认不依赖，用到再检查）。
- [x] `dazi_kit.py` — `BRAND` 人设串 → 已改为中性默认值 `图卡工具箱`，仍可通过 `foot(..., brand=...)` 外部传入。
- [x] `gen_cards.py` — 引用块栏目规则 → 已改为可配置的「金句引用块」：默认中性关键词 `金句 / 观点`，新增 `--quote-keywords` 注入自定义关键词。
- [x] `render_riso.py` — 两处注释里的人名 → 已改为「实测发现」。
- [x] `check.py` — 品牌检查 → 已改为**默认关闭**的品牌规则模块：新增 `--brand-rules`（默认 False），关闭时跳过全部品牌相关检查；锚点 / 别名关键词改由 `GZH_CHECK_BRAND_*` 环境变量注入，规则骨架（计数、阈值、报错）保留；`--min-opinion` 保留，仅开关开启时生效。开源版默认即纯图片 / 文章体检工具。
- [x] **品牌名残留补扫（2026-11-14 15:00，首版脱敏漏检）**——首轮敏感词清单没含「AI澎」本体，页脚品牌串被当成普通字符串漏过。冒烟出图时从**产物图上**发现（守卫查产物不查清单的又一次验证）。已改：`gen_cards.py` 默认 `--account` 与函数默认值「AI澎」→「图卡工具箱」、用法示例改「你的号名」；`render_riso.py` 新增 `_BRAND = os.environ.get("GZH_IMAGE_KIT_BRAND", "图卡工具箱")` 统一注入页脚/刊头，页码重编号正则改品牌无关（`[^<]*· `）；`check.py` 注释里内部路径 `config/persona/p-ai-peng.md` 删除。复扫 *.py 零命中（README 的「AI澎」引流锚点与「© 澎澎」版权署名是设计要求，保留）。

## 二、字体许可（合规硬项）

- [x] 5 个出图工具硬编码系统专有字体路径 → 已新增共享模块 `fontkit.py`：`resolve_font(bold=False)` 优先读 `GZH_IMAGE_KIT_FONT_REG` / `GZH_IMAGE_KIT_FONT_BOLD`，其次按候选列表（思源黑体 SourceHanSansSC / Noto Sans CJK SC / 常见系统字体路径）查找，最后扫描系统字体目录；**找不到即抛 `FontNotFoundError`，绝不静默退回默认字体**。`render_riso.py` 走 CSS 字体族（`GZH_IMAGE_KIT_FONT_FAMILY`）。README 已补「字体配置与许可」小节。
- [ ] examples 示例图如含专有字体渲染成品 → 用可再分发字体重渲后发布。**未完成**：`examples/` 当前为空目录，本次未提供任何示例图，无成品可重渲；待补齐样张后处理。

## 三、环境参数化

- [x] `render_riso.py` — Chrome 路径硬编码 → 已改为环境变量 `CHROME_PATH` / `--chrome` 参数 + 常见路径自动查找 + PATH 查找；找不到抛清晰异常。
- [x] 全部工具统一 `--out` 输出目录参数（检查是否还有写死盘符）→ 已复核：4 个出图脚本均有 `--out`，`check.py` / `dazi_kit.py` 不出图无需；`render_riso.py` 用法示例中写死的盘符路径已改为中性 `out/riso/`，仓库内无写死输出盘符。

## 四、发布前复核

- [x] 任务给定的敏感词 `grep -rE ... *.py` 复扫零命中 → 已实测零命中；另用宽松关键词（含专有字体名、个人路径字样）复扫 `*.py`，亦零命中。
- [x] 每个工具跑一次 `--help`，确认可独立执行 → 已实测：7 个 `.py` 全部 `exit=0`；`--quote-keywords` / `--chrome` / `--brand-rules` 出现在对应帮助里；`fontkit.py` / `dazi_kit.py` 为模块、库，无 CLI，导入正常无输出。
- [ ] `examples/` 放 3-6 张效果示例图（挑样张，用可再分发字体重渲）→ **未完成**：需先自备字体并实际渲染出图，本次仅做代码脱敏，未生成示例图；`examples/` 仍为空。
- [ ] README 补每个工具的示例命令 + 一张效果图 → **未完成**：本次按必做项只补了字体配置小节、快速开始与工具一览，未补全量示例命令与效果图（依赖上一条示例图）。
- [ ] git tag v0.1.0 → **未完成**：按本次约定「不 git commit，由使用者统一提交」，打 tag 同属发布动作，留待提交后进行。

## 复核记录（2026-11-14）

- `py_compile`：`python -m py_compile *.py`，7 个脚本（含新增 `fontkit.py`）全部通过，无语法错误。
- `--help`：见上，全部可独立执行，新增参数均出现。
- 字体红线：环境变量指向不存在的字体时 `resolve_font()` 抛 `FontNotFoundError` 并给出配置指引，未静默回退；本机自动查找到 `NotoSansSC-VF.ttf`（OFL），常规 / 粗体解析正常。
- 附带修复：`check.py` 原本在导入时 `from app.core.spec import CARD_MIN`（内部产线依赖），开源副本必然 ImportError，会导致 `--help` 崩溃；已用 try/except 退回中性默认 6，其余逻辑不动。
- 改动范围：仅 `<repo>/` 目录内文件；未触碰用户指定的其它目录与当前工作目录里的原文件。

## 账号信息（推送目标）— 2026-11-14 14:45 改名全部完成

- GitHub：`ai-pengpeng`（改名自 old-account ✅ 已生效，旧 URL 90 天自动重定向；代码推送进行中，网络断续由后台任务重试）
- Gitee 镜像：`ai-pengpeng`（改名自 old-account ✅ 已生效，2026-11-14 14:40 用户完成；旧地址 10 分钟后释放）
- 双端远端地址均已指向 `ai-pengpeng/gzh-image-kit`，Gitee 匿名访问 200、`git ls-remote` 通过、与本地 `2eabc6c` 同步
- 凭据文件 `<credentials-file>` 旧用户名已更新；README 镜像链接与新地址一致
