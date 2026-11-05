---
name: autobiz-plugin-creator
description: AutoBiz 看板插件开发助手。通过对话把业务流程梳理成节点和产物，写出核心配置 workflow.json、plugin.scaffold.json 和 modules/*.json，调用 autobiz-plugin 生成、检查、模拟并打包可以导入 DevClaw 的插件。当用户要新建看板插件、给插件加节点或产物、导入已有技能、启用知识模块或产物同步，或想了解插件脚手架怎么用时使用。
metadata:
  version: 1.0.0
---

# 看板插件开发助手

帮开发者用对话完成 AutoBiz 看板插件：梳理流程 → 写核心配置 → `doctor` 生成 → `check` 检查 → `simulate` 演示 → `package` 打包。生成和校验全部交给 CLI，判断以退出码和 `--json` 输出的 Issue 为准。

## 调用 CLI

命令写作：

```bash
python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/autobiz-plugin.pyz" -C "<插件目录>" <命令> --json
```

- Windows 上把 `python3` 换成 `python`；
- `${pluginPath}` 没有被替换时（装在 DevClaw 以外的 agent 中），按本文件所在目录定位 `scripts/autobiz-plugin.pyz`；
- 退出码：`0` 成功（可能有 warning）；`1` 有 error，没有写入任何文件；`2` 用法错误；
- `--json` 输出 `{"ok", "issues": [{level, code, file, pointer, message, hint}], "written": [...]}`，doctor 另有 `changes`，check 另有 `contract`，simulate 另有 `simulation`，package 另有 `package`，add skills 成功时另有 `importedSkills`。

| 用途 | 命令 |
|---|---|
| 新建 | `new "<插件目录>" --yes --answers -`（回答从 stdin 读入，格式见下文） |
| 加节点 | `add node <id> --name <名称> --skill <技能> --stage biz\|dev\|ops --seq <n> [--output <路径> …] [--optional-output <路径> …] [--terminal]` |
| 导入技能 | `add skills --from "<已有技能集合目录>"` 一次导入集合中的全部技能，支持 `<集合>/<分组>/<技能>/` 一层分组，共享资源按原路径拷入；单个技能用 `add skill <技能名> --from "<已有技能目录>"`，不带 `--from` 时生成空白 `SKILL.md` |
| 模块 | `module list`；`module enable knowledge [--set assembly.assembler=devclaw]`；`module enable artifactSync --set allowedFrom=plan:done`；`module disable <id>` |
| 全局钩子 | 插件全局钩子模块 `globalHooks`：`hook list` 查看脚手架自带的公共钩子（如 `secrets-check` 明文密码检查、`performance-check` 前端性能检查）；问用户要不要启用，要就 `hook enable <id> …`（写 `modules/globalHooks.json`），或在 `new` 的回答中写 `"globalHooks": {"hooks": [...]}`；`hook disable <id>` 关闭 |
| 重新生成 | `doctor`（先看影响时加 `--dry-run`） |
| 检查 | `lint`（只查核心配置）、`check`（再加技能内容、漂移和契约测试） |
| 演示 | `simulate [--to <checkpoint>]` |
| 打包 | `package` |

## 文件归属

| 文件 | 能否修改 |
|---|---|
| `plugin.scaffold.json`、`workflow.json`、`modules/*.json` | 能，这是本技能的主要产出 |
| `skills/<分组>/<技能>/` 中状态维护片段以外的内容、`hooks/`、`agents/` | 只有用户确认后才改；节点技能按节点阶段放在 `skills/autobiz\|autodev\|autoops/` 下，doctor 会把放错位置的挪过去 |
| `SKILL.md` 中 `<!-- plugin workflow: begin state -->` 到 `<!-- plugin workflow: end state -->` 之间 | 不能，由 doctor 维护 |
| `plugin.json`、`board_core/`、`runtime/`、`.scaffold/` | 不能；要改就改核心配置再 doctor |

## 核心配置要点

细节以 CLI 报出的 Issue（`code`、`pointer`、`hint`）和插件目录 `.scaffold/` 下的 Schema 为准，这里只列建模时要用到的规则。

`workflow.json` 顶层只有 `nodes`，按 `biz`、`dev`、`ops` 分组。每个节点最多 6 个字段：

| 字段 | 规则 |
|---|---|
| `id` | 小写字母开头，只含小写字母、数字和 `_`，各分组合起来不能重复，不加阶段前缀（写 `plan`，不写 `dev.plan`） |
| `seq` | 正整数，全部节点按它从小到大执行；不能重复，可以跳号，要按 biz → dev → ops 递增 |
| `name` | 显示名 |
| `skill` | 小写连字符；一个技能只能绑定一个节点 |
| `outputs` | 产出的文件名（相对 Feature 目录，可以含 glob），可选输出写成 `{"path": "…", "optional": true}`；编码节点通常不写 |
| `terminal` | 终态节点：只能是 `seq` 最大的节点，不能有 `outputs`，完成后推进到 `archived` |

- 产物 id 由路径推导：取最后一个不含 glob 的段，转小写、去掉 `.md`，非字母数字换成 `_`（`PRD.md` → `prd`，`specs/**/*.md` → `specs`）。两个路径推导出同一个 id 时改文件名；
- 推进到 `_done` 时框架检查必需输出存在且非空；更严格的完成条件（代码已提交、测试通过、评审结论明确）写进技能正文，作为执行完成命令的前提；
- v1 不能配置节点输入、校验命令、动态阶段和跳过节点。

模块配置：

| 文件 | 什么时候需要 |
|---|---|
| `modules/board.json` | 改看板名称、描述、对话提示、系统提示，或目标平台、解释器 |
| `modules/session.json` | 改默认运行策略（`agentMode`），或给节点单独配置策略、子代理 |
| `modules/knowledge.json` | 需要按所选发布单元加载知识；`assembly.assembler` 选 `plugin`（插件组装）或 `devclaw`；声明 `source` 表示由插件拉取知识仓库 |
| `modules/artifactSync.json` | 需要把产物上传到外部服务；`allowedFrom` 或 `allowedCheckpoints` 二选一，`artifacts` 显式列出要上传的产物路径及简述。同步技能每次同步前按实际代码生成 `FEATURE_API_DETAIL.md` 并自动上传，不要把它写进 `artifacts`（不是节点输出，会报 `ARTIFACT_REF_UNKNOWN`），改简述时写在 `extraPaths` |

知识沉淀入口固定开启，不用问。不需要改默认值的模块不写文件。

`new --answers` 的格式：

```json
{
  "plugin": { "id": "doc-review", "name": "Doc-Review-Kanban", "version": "0.1.0", "description": "文档起草与评审" },
  "nodes": [
    { "id": "draft", "name": "起草", "stage": "biz", "seq": 1, "skill": "doc-draft", "outputs": ["DRAFT.md"] },
    { "id": "review", "name": "评审", "stage": "biz", "seq": 2, "skill": "doc-review", "outputs": ["REVIEW.md"] }
  ],
  "skills": { "doc-draft": null, "doc-review": "/path/to/doc-review" }
}
```

`board`、`session`、`knowledge`、`artifactSync` 可选，内容与对应的模块配置文件相同；写了 `knowledge`、`artifactSync` 即表示启用。`skills` 为技能名 → 已有技能目录，`null` 表示先不提供。

## 流程

一次只问一组问题，等用户回答后再继续。

1. **定位**：确认是新建还是修改。插件目录中已有 `plugin.scaffold.json` 就是修改，先读取现有配置。新建时确认插件目录、插件 ID（提醒发布后不可修改）、插件名；这一步不调用 CLI。
2. **建模**：让用户用自然语言描述流程，按 [建模指南](references/modeling-guide.md) 整理成“seq → 阶段 → 节点 → 技能 → 输出产物”表格回显，用户确认后才写入。新建时调用 `new --yes --answers -`；修改时调用 `add node` 或编辑 `workflow.json`，写完运行 `lint`。
3. **技能资源**：对每个节点确认是导入已有技能，还是先不提供（生成空白 `SKILL.md`）。同一目录下有多个技能时用 `add skills --from` 一次导入；单个技能用 `add skill --from`。`agents/` 不会自动创建：来源旁边有 agents 目录时加 `--agents <目录>` 一并导入。导入后报出的 `LEGACY_ENTRY_REF` 是技能正文里的旧状态命令：按 hint 与用户确认后删掉，状态只由开头的状态维护片段维护。
4. **模块**：询问目标平台、节点运行策略、是否需要知识模块（组装方由谁担任）、是否需要产物同步模块（从哪个节点起允许同步、上传哪些产物）。用 `module enable` 或编辑 `modules/*.json`。
5. **生成**：运行 `doctor`。对新生成的空白 `SKILL.md`，与用户确认触发场景后填写 `description`，再运行一次 `doctor`：节点描述取自 `description`，改了不重新生成会报 `BUILD_STALE`。
6. **校验**：运行 `check`，把 Issue 按原文转述给用户，修改输入后重试。
7. **演示**：运行 `simulate`，展示每个节点的状态；用户满意后运行 `package`。

## 规则

- 只修改核心配置和用户确认过的技能资源，不得修改 generated、managed、module 文件来绕过校验，也不得直接修改 `runtime/config/*`；
- 每次修改核心配置后都运行 `lint`，没有 error 才继续；一组修改完成后运行 `doctor`，再运行 `check`；
- `--force`、`--allow-id-change`、`--allow-layout-change`、`--allow-major-upgrade` 只在用户看过对应的 Issue 并明确同意后才加，执行后把放行时的 warning 原样转述；
- 插件已经发布后，不得修改 `plugin.id` 和 `runtime.metaRoot`；
- 涉及节点业务逻辑的技能正文和校验规则由用户负责，只能起草，不能把未经确认的流程或规则写进去；
- 所有判断以 CLI 的退出码和 Issue 为准，不得自行宣称“校验通过”。
