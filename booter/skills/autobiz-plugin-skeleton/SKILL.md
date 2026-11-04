---
name: autobiz-plugin-skeleton
description: 以配置骨架引导用户自己完成 AutoBiz 看板插件：用选择题确定起点和模块，生成带 [TODO] 占位的 workflow.json 和模块配置，讲清每个字段怎么填后停下来让用户填写，检查通过后导入已有技能或引导填写空白 SKILL.md，最后打包。当用户想自己动手写插件配置、要一份可以照着填的配置模板，或说“先给我骨架、我自己填”时使用；想完全通过对话由助手建模时改用 autobiz-plugin-creator。
metadata:
  version: 1.1.0
---

# 看板插件骨架引导

带用户走完：**选择起点和模块 → 生成骨架 → 用户填配置 → 检查 → 技能（导入或填写空白）→ 打包**。配置和技能内容由用户决定；你负责提供选项、解释每个字段、调用 CLI、转述检查结果。

## 提问方式

需要用户做决定时用 `request_user_input` 出选择题，尽量不让用户自由发挥：

- 每轮 1–3 个问题；每题有简短的 `header`、稳定的 `snake_case` `id`、完整的 `question`，以及 2–3 个互斥选项（每个选项有 `label` 和 `description`）；
- 推荐项排第一，`label` 以 ` (Recommended)` 结尾；
- 不要手工加“其他”选项，客户端会自动提供自由输入；需要路径、名称这类具体内容时，在问题里说明“可以在 Other 中直接填写”，选项给出最常见的取值；
- 候选超过 3 个时，先在消息里列出完整清单，选择题只放最相关的 2–3 个；
- 用户已经说清楚的内容不要再问；必须等用户回答，不要替用户选；
- `request_user_input` 不可用时，用文字列出同样的问题和选项，让用户回复编号。

## 调用 CLI

本技能与 `autobiz-plugin-creator` 在同一个插件包中，共用它的 CLI（下文写作 `<pyz>`）：

```bash
python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/autobiz-plugin.pyz" <命令> --json
```

- 对已有插件目录的命令加 `-C "<插件目录>"`；Windows 上把 `python3` 换成 `python`；
- `${pluginPath}` 没有被替换时，按本文件所在目录的同级目录定位 `../autobiz-plugin-creator/scripts/autobiz-plugin.pyz`；
- 退出码：`0` 成功（可能有 warning）；`1` 有 error，没有写入任何文件；`2` 用法错误；
- `--json` 输出 `{"ok", "issues": [{level, code, file, pointer, message, hint}], "written": [...]}`。判断一律以退出码和 `issues` 为准，不要自己宣称“检查通过”。

## 流程

### 1. 选择起点和模块

先运行 `hook list --json`（不需要插件目录）拿到全部全局钩子，再出第一轮选择题：

| id | 问题 | 选项 |
|---|---|---|
| `start_point` | 从什么起点开始？ | **空白骨架，自己填 (Recommended)**：只有结构和 `[TODO]` 占位；**lite 样例**：需求 → 规格 → 计划 → 编码四个节点，已填好；**fullstack 样例**：Biz → Dev → Ops 七个节点，已填好 |
| `plugin_dir` | 插件放在哪个目录？（必须不存在或为空，可以在 Other 中填写路径） | 当前工作区下的 `my-plugin`；上一级目录下的 `my-plugin` |
| `artifact_sync` | 要不要把节点产物上传到外部服务？ | **不需要 (Recommended)**；需要（启用产物同步模块） |

第二轮：

| id | 问题 | 选项 |
|---|---|---|
| `knowledge` | 要不要按所选发布单元加载知识？ | **不需要 (Recommended)**；需要，由插件拉取知识仓库；需要，由 DevClaw 组装 |
| `global_hooks` | 要不要启用全局钩子？（先在消息里列出 `hook list` 的全部钩子和说明） | **全部启用，之后删掉不要的 (Recommended)**；都不要 |
| `session_policy` | 节点的运行策略？ | **全部用默认的 multi (Recommended)**；需要给个别节点单独配置（生成 session 模块） |

按回答生成：

- 选了 lite 或 fullstack：`new "<插件目录>" --from lite|fullstack --yes --json`，样例的配置都已填好，第 2 步改成“按自己的流程修改”；
- 选了空白骨架：`new "<插件目录>" --skeleton --module board [--module artifactSync] [--module knowledge] [--module globalHooks] [--module session] --json`。`board` 总是带上（至少要填看板上的流程名称）。

### 2. 讲清怎么填，然后停下来

逐个文件说明要填什么（见下文「填写指南」，只讲用户选中的模块），再出一道选择题：

| id | 问题 | 选项 |
|---|---|---|
| `fill_mode` | 配置怎么填？ | **我自己填，填好告诉你 (Recommended)**；我描述流程，你起草后给我确认再写入 |

- 选“自己填”：**停下来**，等用户说填好了再继续；用户问到某个字段时按填写指南解释，必要时给例子，由用户决定；
- 选“起草”：让用户用一两句话描述流程，按填写指南整理成“seq → 阶段 → 节点 id → 显示名 → 技能 → 产出文件”表格回显，用户确认后才写入文件。

### 3. 检查配置

```bash
python3 "<pyz>" -C "<插件目录>" lint --json
```

- `TODO_FIELD`：按 `file`、`pointer` 列出还没填的占位，原样转述 `message`；
- 其他 error（`INPUT_SCHEMA`、`SEQ_DUP`、`SEQ_STAGE_ORDER`、`NODE_DUP`、`SKILL_SHARED`、`ARTIFACT_REF_UNKNOWN`、`GLOBAL_HOOK_UNKNOWN` 等）：转述 `message` 和 `hint`，指出要改的文件和位置，必要时结合填写指南说明正确写法；
- 只剩 warning（`SKILL_MISSING`、artifactSync 简述的 `TODO_FIELD`）时可以继续，技能在下一步处理，简述要在打包前填完。

有 error 就**停下来**让用户改，改好后再 `lint`，直到没有 error。

### 4. 技能

出一道选择题：

| id | 问题 | 选项 |
|---|---|---|
| `skill_source` | 节点技能从哪里来？ | **已有技能集合目录 (Recommended)**：目录下一级是各技能（或多一层 `autobiz/`、`autodev/`、`autoops/` 分组），路径在 Other 中填写；**没有，生成空白 SKILL.md 自己写**；**只有其中几个**：先导入已有的，其余生成空白 |

**导入已有技能**：再问 agents 目录（`modules/session.json` 引用了子代理文件时需要）：选项为“没有 agents 目录”和“与技能集合同级的 `agents/`”，其他路径在 Other 中填写。然后：

```bash
python3 "<pyz>" -C "<插件目录>" add skills --from "<技能集合目录>" [--agents "<agents 目录>"] --json
```

- 技能目录名就是技能名，必须与 `workflow.json` 中节点的 `skill` 一致；导入后仍报 `SKILL_MISSING` 的节点，说明名字对不上或缺技能，告诉用户；
- 这条命令会同时生成插件：节点技能按节点阶段放进 `skills/autobiz/`、`skills/autodev/`、`skills/autoops/`（正文里对旧路径的引用一并改掉，挪动列在 `changes.skills.moved`），没有技能的节点生成空白 `SKILL.md`；
- 报 `LEGACY_ENTRY_REF` 是技能正文里残留的旧状态命令（调用 `update_state.py`、`hooks/update_checkpoint.py` 等）：把行号和所在小节告诉用户，用户确认后再删。

**没有技能**：运行 `doctor --json`，列出生成的空白文件（`changes.skills.created`），引导用户逐个填写，**停下来**等用户填完：

- frontmatter 的 `description`：写“做什么；在什么情况下使用”，看板上的节点描述也取自这里；
- 正文：这个节点的工作步骤、要产出哪些文件（与 `workflow.json` 中的 `outputs` 一致）、完成前要满足的条件（例如测试通过、评审结论明确）；
- `<!-- plugin workflow: begin state -->` 到 `<!-- plugin workflow: end state -->` 之间是状态维护片段，**不能改也不能删**，正文里也不要再写调用 `update_state.py` 的命令；
- 参考资料放进技能目录的 `references/`，脚本放进 `scripts/`，并在正文中写明什么时候用哪个文件。

### 5. 打包

用户说技能都填好后：

```bash
python3 "<pyz>" -C "<插件目录>" doctor --json
python3 "<pyz>" -C "<插件目录>" package --json
```

- 改了技能 `description` 后必须先 `doctor`，否则报 `BUILD_STALE`；
- `package` 会先做完整检查：报 `TODO_PLACEHOLDER` 说明还有没填的 `[TODO: …]`（空白技能的 `description`、artifactSync 的简述等），报 `LEGACY_ENTRY_REF` 说明技能正文里还有旧状态命令。转述位置，**停下来**让用户改完，再从 `doctor` 重来；
- 成功时告诉用户生成的 zip：`package.path` 是相对插件目录的路径（默认 `dist/<plugin.id>-<version>.zip`），可以直接导入 DevClaw。

## 填写指南

### plugin.scaffold.json

| 字段 | 怎么填 |
|---|---|
| `plugin.id` | 只含英文字母、数字、短横线和下划线，不超过 64 字符，例如 `my-plugin`、`Doc_Review`。它也是安装目录名和状态文件中的 `pluginId`，**发布后不能改** |
| `plugin.name` | 插件名，显示在 DevClaw 中 |
| `plugin.description` | 一句话说明插件做什么 |
| `plugin.version` | 版本号，默认 `0.1.0`，发布新版时递增 |

`workflow`、`modules` 是对其他文件的引用，保持生成时的样子即可。

### workflow.json

顶层只有 `nodes`，按阶段分成 `biz`、`dev`、`ops` 三组（只能用这三个名字，可以只写其中几组）。每个节点：

| 字段 | 怎么填 |
|---|---|
| `id` | 节点 id，小写字母开头，只含小写字母、数字和 `_`，全局不重复，不加阶段前缀（写 `plan`，不写 `dev_plan`）。它决定 checkpoint 名：`plan_in_progress`、`plan_done` |
| `seq` | 执行顺序，正整数，全局不重复，可以跳号；必须按 biz → dev → ops 递增（biz 的节点不能排在 dev 后面） |
| `name` | 看板上的显示名，例如“需求澄清” |
| `skill` | 技能目录名，小写字母、数字和连字符；一个技能只绑定一个节点。技能会按节点阶段放在 `skills/autobiz/`、`skills/autodev/` 或 `skills/autoops/` 下 |
| `outputs` | 节点产出的文件，路径相对 Feature 目录，可以用 glob（`specs/**/*.md`）；可选产出写成 `{"path": "PR_BODY.md", "optional": true}`；没有产出（例如编码节点）就删掉这个字段 |
| `terminal` | 可选。`true` 表示终态节点（例如“归档”），只能是 `seq` 最大的节点，不能有 `outputs`，完成后流程进入 `archived` |

关键提醒：

- 推进到 `_done` 时会检查必需产出都存在且不为空，缺了会被拦下，所以 `outputs` 只写节点一定会产出的文件；
- 两个节点不要声明同一个产出文件；
- 例子：

```json
{
  "nodes": {
    "biz": [ { "id": "prd", "seq": 1, "name": "需求", "skill": "my-prd", "outputs": ["PRD.md"] } ],
    "dev": [
      { "id": "plan", "seq": 2, "name": "计划", "skill": "my-plan", "outputs": ["plan.md"] },
      { "id": "code", "seq": 3, "name": "编码", "skill": "my-code" }
    ],
    "ops": [ { "id": "archive", "seq": 4, "name": "归档", "skill": "my-archive", "terminal": true } ]
  }
}
```

### modules/board.json

| 字段 | 怎么填 |
|---|---|
| `display.workflowLabel` | 看板上的流程名称，例如“需求开发” |
| `display.workflowDescription` | 可选，流程的一句话说明 |
| `display.dialogTips` | 可选，用户发起对话时的提示语，可以用 `${projectCode}`、`${pluginWorkspace}`、`${projectDir}` |
| `display.systemPromptInject` | 可选，注入系统提示的内容；不写就用默认值（已含 Feature 产物目录），一般不需要改 |

### modules/session.json

| 字段 | 怎么填 |
|---|---|
| `policies.default.agentMode` | 默认运行策略：`multi`（默认）、`solo`、`agent_team`、`workflow` |
| `policies.nodes.<阶段>[]` | 给个别节点单独配置：`{"id": "<节点 id>", "agentMode": "agent_team"}`；还可以加 `toolCustomConfig`、`subagentConfig`（`disabledBuiltinSubagents` 禁用的内置子代理，`customSubagentFiles` 自带的子代理文件，如 `agents/explore.md`） |

`customSubagentFiles` 引用的文件要放在插件的 `agents/` 下，导入技能时用 `--agents` 一起拷进来。

### modules/knowledge.json

| 字段 | 怎么填 |
|---|---|
| `assembly.assembler` | `plugin`：插件自己组装知识；`devclaw`：交给 DevClaw 组装 |
| `source.url` | 知识仓库的 HTTPS 地址；插件不负责拉取知识仓库就删掉整个 `source` |
| `source.sshUrl`、`source.ref` | 可选，SSH 地址和分支（默认 `main`） |

### modules/artifactSync.json

| 字段 | 怎么填 |
|---|---|
| `allowedFrom` | 从哪个节点完成起允许同步，写成 `<节点 id>:done`，例如 `plan:done` |
| `artifacts` | 要上传的产物：键是产物路径，必须与 `workflow.json` 某个节点 `outputs` 中的写法**完全一致**；值是简述 |
| `excludeCheckpoints`、`extraPaths` | 可选：不允许同步的 checkpoint；产物之外要一起上传的路径（glob → 简述） |

同步技能每次同步前会按实际代码生成接口交付文档 `FEATURE_API_DETAIL.md`，并自动把它加进同步范围。它不是节点输出，**不要写进 `artifacts`**，否则报 `ARTIFACT_REF_UNKNOWN`；只有要改它的简述时，才在 `extraPaths` 里写 `"FEATURE_API_DETAIL.md": "<简述>"`。

### modules/globalHooks.json

骨架里已经列出全部可用的全局钩子，**删掉不需要的**即可，不用自己写 id。每个钩子做什么以 `hook list` 的说明为准，目前有：

| id | 做什么 |
|---|---|
| `secrets-check` | 写入 `.yaml`、`.yml`、`.properties` 时发现明文的密码、密钥、token 就拦截，提示先加密 |
| `performance-check` | 编码节点（`code`）完成前，检查工作区 `git diff` 中变动的前端文件的 7 条性能规则，发现问题就拦截 |

一个都不要时，把入口文件 `modules` 中的 `globalHooks` 引用也删掉。产物检查钩子始终启用，不在这里列。

## 规则

- 配置和技能内容由用户决定；只有用户选择“起草”或明确要求代填某一处时才改，写入前先让用户确认，改完告诉用户改了哪里；
- 不得修改 `plugin.json`、`board_core/`、`runtime/`、`.scaffold/`、`hooks/artifact_guard.py`，也不得改 `SKILL.md` 中的状态维护片段，或用其他方式绕过检查；
- `doctor` 的 `--force`、`--allow-id-change` 等放行参数只在用户看过对应 Issue 并明确同意后才加；
- Issue 按原文转述，带上文件和位置；不要自行判断“没问题”。
