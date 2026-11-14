# 开源剥离 TODO（发布前必须清零）

> 扫描时间：2026-11-14。发布标准：下表全部勾完 + `grep` 复扫零命中。

## 一、品牌词与个人路径（grep 已定位）

- [ ] `dazi_kit.py:18` — `REF` 指向本机 WorkBuddy 专家包目录 `<workspace>/...` → 参数化或删除
- [ ] `dazi_kit.py:113` — `BRAND = '澎澎 ｜ AI × 职场'` → 改为可选参数，默认中性
- [ ] `gen_cards.py:24/190/220` — 「澎澎说」引用块规则 → 改为可配置的「金句引用块」规则
- [ ] `render_riso.py:206/490` — 注释里的「澎澎指出」→ 改中性描述（如「实测发现」）
- [ ] `check.py` — 12 处品牌命中（「澎澎说」原创锚点 ≥1、栏目口径「主理人说/彭彭说」检查等）→ **决策**：文章类检查规则与「贴图体检」混在一起，开源版应只保留图片体检部分，或把品牌规则全部参数化

## 二、字体许可（合规硬项）

- [ ] 5 个工具硬编码 `C:\Windows\Fonts\msyh*.ttc`（微软雅黑）——**不允许再分发** → 改为：优先读 `GZH_IMAGE_KIT_FONT` 环境变量 / `--font` 参数，默认回退系统字体查找列表（含思源黑体 SourceHanSansSC）；README 注明字体许可
- [ ] examples 示例图如含微软雅黑渲染成品 → 用思源黑体重渲后发布

## 三、环境参数化

- [ ] `render_riso.py` — Chrome 路径硬编码 → 环境变量/参数 + 自动查找
- [ ] 全部工具统一 `--out` 输出目录参数（检查是否还有写死盘符）

## 四、发布前复核

- [ ] `grep -rE "27515|C:\\\\Users|D:\\\\OpsWork|D:\\\\ai_workspace|api_key|secret|token"` 零命中
- [ ] 每个工具跑一次 `--help`，确认可独立执行
- [ ] `examples/` 放 3-6 张效果示例图（本仓库挑样张，用思源黑体重渲）
- [ ] README 补每个工具的示例命令 + 一张效果图
- [ ] git tag v0.1.0

## 账号信息（推送目标）

- GitHub：`ai-pengpeng`（改名自 old-account，进行中）
- Gitee 镜像：`ai-pengpeng`（改名自 old-account，进行中）
