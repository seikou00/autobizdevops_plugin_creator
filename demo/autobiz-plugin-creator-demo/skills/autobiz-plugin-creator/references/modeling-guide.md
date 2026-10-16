# 建模指南：把业务流程拆成节点、产物和校验

看板插件的核心流程只有一个概念：**节点**。每个节点由一个技能负责，读取前面节点的产物，产出自己的产物，完成时可以执行一条校验命令。节点按数组顺序线性推进。

## 1. 拆分步骤

| 步骤 | 问自己 | 写到哪里 |
|---|---|---|
| 1. 列出工作 | 这件事分几步完成？每一步交付什么文件？ | 每一步是一个节点，`name` 是显示名 |
| 2. 定技能 | 每一步由哪个技能负责？ | 节点的 `skill`；一个节点一个技能 |
| 3. 定产物 | 这一步产出哪些文件？叫什么名字？ | 节点的 `outputs`：`{产物 id: 路径}` |
| 4. 定依赖 | 这一步要读前面哪些文件？ | 节点的 `inputs`：前面节点的产物 id |
| 5. 定完成标准 | 文件存在就算完成，还是要检查内容？ | 需要检查内容时写 `validate` 单行命令 |
| 6. 分组 | 看板上要不要按阶段分组？ | 节点的 `stage`，同一阶段连续排列 |
| 7. 显示与策略 | 产物要不要中文显示名？节点要不要特别的运行策略？ | `modules/board.json`、`modules/session.json` |

## 2. 判断标准

- **一个节点对应看板上的一格**：用户能看到"进行中""已完成"。如果某一步不需要在看板上单独显示，就不必拆成节点；
- **产物是文件**：路径相对 `FEATURE_DIR`（`<项目>/.autobizdevops/<插件 ID>/features/<feature>/`）。多个文件组成一个产物时写数组，数量不定时用 glob（`specs/*/spec.md`）；
- **框架只检查文件是否存在**：空文件也算存在。内容是否合格（不为空、结构完整、结论明确）由校验命令判断；
- **校验命令是单行命令**：不经过 shell，不支持管道、重定向和 `&&`。复杂的检查写成脚本，放在 `skills/<skill>/scripts/` 下，用 `${skillPath}/scripts/…` 引用。

## 3. 正反例

| 反例 | 问题 | 正例 |
|---|---|---|
| `起草` 节点读取 `review`（评审意见），但评审在后面 | `INPUT_FORWARD`：只能读前面节点的产物 | 去掉这个读取；要根据评审意见修改时，在评审后面加一个 `修订` 节点 |
| 节点 `biz.review` 和 `dev.review` | `CHECKPOINT_DUP`：最后一段都是 `review`，checkpoint 都叫 `review_in_progress` | 改成 `biz.review` 和 `dev.code_review` |
| 阶段顺序 Biz、Dev、Biz | `STAGE_ORDER`：看板分组不连续 | 调整节点顺序，或把第三个节点改到 Ops 阶段 |
| 产物路径写成 `/Users/me/project/PRD.md` 或 `../PRD.md` | `PATH_UNSAFE`：项目路径由 DevClaw 运行时传入 | 只写 `PRD.md` |
| 产物命名为 `state.json` | `PATH_UNSAFE`：与框架的保留文件冲突 | 换一个名字，例如 `review_state.json` |
| 校验命令 `cat REVIEW.md \| grep 结论` | 不经过 shell，管道不生效 | `${python} ${skillPath}/scripts/check_review.py --feature-dir ${featureDir}` |
| 在 `workflow.json` 的节点里写 `description` 或产物显示名 | `INPUT_SCHEMA`：核心流程只写业务骨架 | 写到 `modules/board.json` 的 `display.nodes`、`display.artifacts` |
| 用一个节点完成"评审并修改" | 看板上看不出评审是否已经结束，产物也混在一起 | 拆成 `评审`（产出 REVIEW.md）和 `修订`（读取 REVIEW.md，更新正文） |

## 4. 示例

### 文档起草与评审（2 个节点）

| # | 节点 id | 显示名 | 技能 | 读取 | 产出 | 完成时校验 |
|---|---|---|---|---|---|---|
| 1 | draft | 起草 | doc-draft | — | draft = DRAFT.md | — |
| 2 | review | 评审 | doc-review | draft | review = REVIEW.md | 检查评审结论是否齐全 |

### 需求开发（4 个节点，lite 插件）

| # | 节点 id | 显示名 | 阶段 | 技能 | 读取 | 产出 |
|---|---|---|---|---|---|---|
| 1 | biz.prd | 需求清洗 | Biz | autobiz-prd | — | requirements = PRD.md |
| 2 | dev.specs | 规格生成 | Dev | autodev-sepc | requirements | proposal = proposal.md；specs = specs/*/spec.md；design = design.md |
| 3 | dev.plan | 任务计划 | Dev | autodev-plan | requirements、proposal、specs、design | plan = plan.md |
| 4 | dev.code | 增量编码 | Dev | autodev-code | requirements、proposal、specs、design、plan | — |
