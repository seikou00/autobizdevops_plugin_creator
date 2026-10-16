---
name: autobiz-plugin-creator
description: AutoBiz 看板插件开发助手（演示版）。通过对话把已有技能串成看板流程，写出核心配置 workflow.json、plugin.scaffold.json 和 modules/*.json，检查后生成可以导入 DevClaw 的插件，并在本机模拟 DevClaw 调用验证。当用户要新建看板插件、把技能组装成插件、给插件加节点或产物、给节点加完成校验，或想了解插件脚手架怎么用时使用。
metadata:
  version: 0.2.0-demo
---

# 看板插件开发助手（演示版）

帮开发者把**已有的技能**组装成一个 DevClaw 看板插件：对话梳理流程 → 写核心配置 → 检查 → build 生成插件 → simulate 模拟 DevClaw 调用 → 打包。

演示版与正式版（`autobiz-plugin` CLI）的差别：生成与校验由本技能 `scripts/` 下的脚本完成；不支持知识模块和产物同步（build 会报 `DEMO_UNSUPPORTED`）；会话上下文只含流程信息，不含知识。

## 脚本

以下命令中 `<插件目录>` 换成实际路径。Windows 上把 `python3` 换成 `python`。如果 `${pluginPath}` 没有被替换成实际路径，就用本文件所在目录定位 `scripts/`。

| 用途 | 命令 |
|---|---|
| 列出技能 | `python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/demo_skills.py" list "<插件目录>" [--from "<技能来源目录>"]` |
| 导入技能 | `python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/demo_skills.py" import "<插件目录>" --from "<技能目录>" [--name <技能名>]` |
| 检查 | `python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/demo_lint.py" "<插件目录>" [--preview]` |
| 生成插件 | `python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/demo_build.py" "<插件目录>" [--validator-stubs]` |
| 模拟 DevClaw | `python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/demo_simulate.py" "<插件目录>" [--skip-validate]` |
| 打包 | `python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/demo_package.py" "<插件目录>"` |

退出码：`0` 成功（可能有 warning）；`1` 有 error，build 不会写任何文件；`2` 用法错误。

## 文件归属

| 文件 | 谁维护 | 本技能能否修改 |
|---|---|---|
| `plugin.scaffold.json`、`workflow.json`、`modules/*.json` | 开发者与 agent | 能，这是本技能的主要产出 |
| `skills/<技能>/` 下托管片段以外的内容、`hooks/`、`agents/` | 开发者 | 只有用户确认后才改 |
| `skills/<技能>/SKILL.md` 中 `<!-- scaffold:begin … -->` 到 `<!-- scaffold:end … -->` 之间 | build | 不能，由 build 更新 |
| `plugin.json`、`board_core/`、`runtime/`、`.scaffold/` | build | 不能；要改就改核心配置再 build |

## 流程

一次只问一组问题，等用户回答后再继续。每个问题都给出默认值，用户说"默认"或"跳过"就用默认值。

### 1. 定位

1. 确认是**新建**还是**修改**插件。插件目录中已有 `plugin.scaffold.json` 就是修改，先读取现有配置；
2. 确认插件目录，默认为当前工作目录下的 `<插件 ID>/`；
3. 收集基础信息：
   - **插件 ID**：规范化后告诉用户。规则：转小写，非字母数字字符改为 `-`，合并连续的 `-`，去掉首尾的 `-`（`Doc Review` → `doc-review`）。提醒用户 **ID 发布后不能修改**，也不能用 `features`、`archive`、`issues`、`reviews`、`logs`、`plugins`；
   - **插件名**：DevClaw 中显示的名字，可以含大写；
   - **版本**：默认 `0.1.0`；
   - **一句话描述**。

### 2. 盘点技能

问用户准备好的技能放在哪里：

- 已经在 `<插件目录>/skills/` 下：直接运行"列出技能"；
- 在别的目录：先运行"列出技能"并带上 `--from` 看来源中有哪些技能，用户选定后逐个"导入技能"。

把列出的技能整理成表格（技能名、description、模板、脚本）回显给用户，作为下一步建模的素材。没有现成技能的节点，build 会生成技能桩文件。

### 3. 建模

请用户用自己的话描述流程：分几步、每一步用哪个技能、产出什么文件、读前面哪一步的文件、怎样才算完成。可以根据技能的 description 建议顺序和产物，但要让用户确认。整理成表格回显：

| # | 节点 id | 显示名 | 阶段 | 技能 | 读取 | 产出（产物 id = 路径） | 模板 | 完成时校验 |
|---|---|---|---|---|---|---|---|---|
| 1 | draft | 起草 | — | doc-draft | — | draft = DRAFT.md | templates/DRAFT.md | — |
| 2 | review | 评审 | — | doc-review | draft | review = REVIEW.md | — | 检查评审结论 |

**用户确认表格后才写入 `workflow.json`**。规则（细节和正反例见 `references/modeling-guide.md`）：

- **节点 id**：小写字母开头，可以用 `.` 分段（`dev.plan`）。最后一段决定 checkpoint 名（`plan_in_progress`、`plan_done`），各节点的最后一段不能重复；
- **技能**：用盘点出的技能名；新技能用小写字母和数字，`-` 连接；
- **阶段**：可选，用作看板分组；同一阶段的节点必须连续；
- **产物**：在第一个产出它的节点 `outputs` 中定义，id 为小写字母、数字、下划线；路径相对 `FEATURE_DIR`，可以用 glob，多个文件写数组；
- **读取**：只能读前面节点产出的产物；
- **模板**：路径相对技能目录，优先用技能已有的 `templates/` 文件；
- **校验命令**：完成时执行的单行命令，不经过 shell。可用占位符：`${python}`、`${pluginPath}`、`${skillPath}`、`${projectPath}`、`${featureDir}`、`${feature}`、`${nodeId}`。技能 `scripts/` 下已有校验脚本时直接引用；没有时起草 `${python} ${skillPath}/scripts/check_<节点>.py --feature-dir ${featureDir}`，并在 build 时问用户是否生成骨架；
- **不写进 workflow.json**：节点描述、产物显示名、看板文案（放 `modules/board.json`）；运行策略（放 `modules/session.json`）；项目路径、Feature 名等运行上下文。

写入后立即运行"检查"。

### 4. 模块

依次询问，全部取默认值的类别不写文件，也不在入口文件中引用：

1. **看板**（`modules/board.json`）：目标平台（默认 darwin、linux、win32）；产物显示名（默认文件名）；节点描述；是否开启知识沉淀入口（`capabilities.knowledgeSedimentation`）。演示版不支持产物同步；
2. **会话与 Agent**（`modules/session.json`）：默认 `solo` 并启用 task；是否给某些节点单独配置 `agentMode`（`solo`、`multi`、`agent_team`、`workflow`）或外挂子代理（`agents/*.md`，文件要存在）；
3. **知识**：演示版不支持，告诉用户正式版可以启用。

写模块文件时同步更新 `plugin.scaffold.json` 的 `modules` 引用。写完运行"检查"。

### 5. 检查

- **有 error**：把每条 Issue 的 code、文件、位置和说明原样转述，给出修改建议。只改写法（字段名、路径格式）可以直接改；会改变流程（节点顺序、读取关系、产物）的先征得用户同意。改完重新检查，直到没有 error；
- **只有 warning**：逐条解释。build 之前出现 `SKILL_MISSING`、`TEMPLATE_MISSING`、`COMMAND_SCRIPT_MISSING` 是正常的；
- 没有运行脚本、或退出码不是 0 时，不要说"检查通过"。

需要先讲解会生成什么时，运行带 `--preview` 的检查。

### 6. 生成插件

运行"生成插件"。节点有校验命令而脚本不存在时，先问用户是否生成校验器骨架（加 `--validator-stubs`；骨架检查产物非空，业务规则由开发者补充）。然后：

- 列出写入的文件，按归属讲解：`generated`（清单、看板配置、编译配置）和 `managed`（runtime/ 下的入口）不能手改；`seeded`（技能桩、模板桩、校验器骨架）只在缺失时创建；已有的 SKILL.md 只插入或更新 `state`、`artifacts` 两个托管片段；
- 打开一个技能的 SKILL.md，展示插入的"技能状态维护"片段：技能开始和完成时如何推进 checkpoint；
- 处理 build 报出的问题：
  - `SKILL_NAME_MISMATCH`、`SKILL_FRONTMATTER`（error）：技能的 frontmatter 不对，和用户确认后修改 frontmatter，或修改 workflow.json 中的技能名；
  - `LEGACY_ENTRY_REF`（warning）：技能正文里还有旧的状态维护段落（例如 `hooks/update_state.py`），会和托管片段冲突。给用户看这段内容，确认后删除；
  - `DRIFT_MANAGED`：有人手改了托管文件，问清原因；确认要覆盖时才加 `--force`；
- 改了核心配置或技能后，重新运行"生成插件"。

### 7. 模拟 DevClaw

运行"模拟 DevClaw"，向用户讲解输出：创建项目和 Feature → 每个节点依次注入会话上下文、推进到 `_in_progress`、写入桩产物、推进到 `_done`（执行校验命令）→ 查询看板状态。

- 节点校验因为桩产物不合格而失败是正常的，说明校验命令确实在起作用；想看完整流程时加 `--skip-validate`；
- 其他步骤失败时，按输出中的原因修改配置或技能，重新 build 再模拟。

### 8. 打包

运行"打包"，告诉用户 zip 的位置（`<插件目录>/dist/<插件 ID>-<版本>.zip`），按导入其他插件的方式导入 DevClaw。导入后看板上会出现各节点，创建 Feature 后可以按节点发起会话。

## 规则

- 只修改"文件归属"表中允许修改的文件；不要为了通过检查去改脚本、Schema 或生成的文件；
- 每次修改核心配置后都运行检查，没有 error 才进入下一步；修改后要重新 build；
- 以脚本的退出码和输出为准，不自行判断"已通过"；
- 技能正文和校验规则属于业务逻辑，由开发者决定，agent 只能起草并经用户确认；
- 已经发布的插件不能修改 `plugin.id` 和 `runtime.layout`（build 会报 `PLUGIN_ID_CHANGED`、`LAYOUT_CHANGED`）；
- 每个配置文件开头写 `$schema`：入口文件和 workflow.json 用 `./.scaffold/<名称>.schema.json`，模块文件用 `../.scaffold/modules/<名称>.schema.json`。build 会生成这些 Schema，之后 IDE 就能补全。

## 示例

`plugin.scaffold.json`：

```json
{
  "$schema": "./.scaffold/plugin-scaffold.schema.json",
  "scaffoldVersion": 1,
  "plugin": { "id": "doc-review", "name": "Doc-Review-Kanban", "version": "0.1.0", "description": "文档起草与评审" },
  "modules": { "board": "./modules/board.json" }
}
```

`workflow.json`：

```json
{
  "$schema": "./.scaffold/workflow.schema.json",
  "nodes": [
    { "id": "draft", "name": "起草", "skill": "doc-draft",
      "outputs": { "draft": "DRAFT.md" }, "templates": ["templates/DRAFT.md"] },
    { "id": "review", "name": "评审", "skill": "doc-review",
      "inputs": ["draft"], "outputs": { "review": "REVIEW.md" },
      "validate": "${python} ${skillPath}/scripts/check_review.py --feature-dir ${featureDir}" }
  ]
}
```

`modules/board.json`：

```json
{
  "$schema": "../.scaffold/modules/board.schema.json",
  "display": { "artifacts": { "draft": "文档草稿", "review": "评审意见" } },
  "capabilities": { "knowledgeSedimentation": { "enabled": true } }
}
```

## 参考

- `references/input-config.md`：全部字段、默认值、编译规则（§6）和检查规则（§7.2）；
- `references/modeling-guide.md`：如何把业务流程拆成节点、产物和校验，含正反例；
- `schemas/`：各配置文件的 JSON Schema。
