# 插件标准化输出规范 v1

本文规定脚手架生成的插件**静态形态**：目录、清单、看板配置、内部配置、运行期数据格式、技能格式。命令的调用参数与返回 JSON 等**行为接口**见 [interfaces.md](interfaces.md)。

文中“必须/应当/可以”按 RFC 2119 的含义理解。下文的“宿主”均指 DevClaw；`board.*`、`session.*`、`knowledge.*`、`artifactSync.*` 分别指 `modules/board.json`、`modules/session.json`、`modules/knowledge.json`、`modules/artifactSync.json` 中的字段（input-config.md §4）。

## 1. 目录结构

```text
<plugin>/
├── plugin.scaffold.json                  # developer  入口文件：基础信息与引用（不随包发布）
├── workflow.json                         # developer  核心流程（不随包发布）
├── modules/                              # developer  模块配置，按需存在（不随包发布）
│   └── board.json  session.json  knowledge.json
├── plugin.json                           # generated  插件清单（DevClaw 只读这一份）
├── .codex-plugin/plugin.json             # generated  Codex 清单（可选，plugin.codexManifest）
├── board_core/
│   └── board_config.json                 # generated  固定看板接口（运行期回写字段见 §3.6）
├── skills/                               #            业务技能、模板、脚本及校验器；技能目录也可以在一层分组下（skills/<分组>/<node-skill>/）
│   ├── <node-skill>/SKILL.md             # seeded     每个节点一个，含状态接入托管片段
│   ├── <node-skill>/agents/openai.yaml   # seeded     Codex 技能展示信息（可选）
│   ├── <node-skill>/templates/…          # developer  模板，技能自己维护，脚手架不登记、不生成（D29）
│   ├── <node-skill>/scripts/…            # developer  执行脚本、业务校验器
│   ├── <node-skill>/references/…         # developer
│   └── <sync-skill>/…                    # module     产物同步模块（§7.2）
├── hooks/                                # developer  自定义扩展，原样交付（可含宿主工具钩子 hooks.json）
├── agents/*.md                           # developer  可选 Agent 资源（会话策略引用）
├── runtime/
│   ├── workflow/
│   │   └── update_state.py               # managed    模型提交状态变更
│   ├── adapters/
│   │   ├── init_workspace.py             # managed    DevClaw 创建项目（create_project）
│   │   ├── init_feature.py               # managed    DevClaw 创建 Feature（create_feature）
│   │   ├── inspect_state.py              # managed    DevClaw 查询项目与 Feature（project_status / feature_status）
│   │   ├── inspect_workflow_templates.py # managed    DevClaw 动态工作流（dynamic_workflow）
│   │   ├── skip_node.py                  # managed    DevClaw 跳过节点（skip_node，开启 skip 时调用）
│   │   └── board_events.py               # managed    写入口提交后推送看板事件（interfaces.md §3.5）
│   ├── session/
│   │   └── render_session_context.py     # managed    DevClaw 会话机制（session_context_inject）
│   ├── knowledge/                        # module     知识模块，启用时生成
│   │   ├── inspect_deploy_units.py       #            解析知识清单，提供支持的系统和发布单元
│   │   ├── render_collected_session_context.py  #     内置知识组装脚本（assembler = plugin 时）
│   │   ├── collect-knowledge.js          #            内置组装脚本调用的 collector（需要 Node）
│   │   └── sync_knowledge.py             #            知识仓库同步（声明 knowledge.source 时）
│   ├── common/
│   │   ├── query.py                      # managed    内部只读查询模块
│   │   └── engine.py                     # managed    内部初始化与状态变更模块
│   ├── config/                           # generated  编译后的内部配置（§5）
│   │   └── runtime.json  flow.json  session.json  knowledge.json
│   └── build-manifest.json               # generated  生成文件及构建信息记录（§8）
├── .scaffold/                            # managed    输入配置的 Schema（IDE 补全）
│   ├── plugin-scaffold.schema.json  workflow.schema.json
│   └── modules/board.schema.json  session.schema.json  knowledge.schema.json
├── .githooks/pre-commit                  # seeded     提交前运行 autobiz-plugin lint（input-config.md §7.1）
└── .gitignore                            # seeded
```

`runtime/` 各级目录下的 `__init__.py` 省略未列。入口脚本通过 `__file__` 定位插件根目录，把它加入 `sys.path` 后导入 `runtime.common`。

打包产物（`autobiz-plugin package`）包含：`plugin.json`（开启时另含 `.codex-plugin/plugin.json`）、`board_core/`、`runtime/`、`skills/`、`hooks/`、`agents/`（存在时），以及清单中引用的 `.mcp.json`。不包含 `plugin.scaffold.json`、`workflow.json`、`modules/`、`.scaffold/`、`__pycache__/`。知识目录（`knowledge.root`，默认 `sys/`）在声明了 `knowledge.source` 时是运行期缓存，不打包；未声明时视为开发者提供的资源，原样打包。

## 2. 插件清单

DevClaw 只读取根目录的 `plugin.json`（D5）。`.codex-plugin/plugin.json` 只在 `plugin.codexManifest: true` 时生成，用于兼容 Codex。`marketplace.json` 不生成。

### 2.1 plugin.json（根目录）

```json
{
  "name": "<plugin.name>",
  "version": "<plugin.version>",
  "description": "<plugin.description>",
  "author": { "name": "…", "email": "…" },
  "license": "MIT",
  "keywords": ["…"],
  "skills": "./skills/",
  "mcpServers": "./.mcp.json",
  "hooks": "./hooks/hooks.json"
}
```

`mcpServers`、`hooks` 只在输入中声明了才输出；`author`、`homepage`、`repository`、`license`、`keywords` 未声明时省略。所有路径都是相对插件根目录的路径，以 `./` 开头。

### 2.2 .codex-plugin/plugin.json（可选）

字段形态遵循 Codex plugin-creator 的 `references/plugin-json-spec.md`：

```json
{
  "name": "<plugin.id>",
  "version": "<plugin.version>",
  "description": "<plugin.description>",
  "author": { "name": "…", "email": "…", "url": "…" },
  "homepage": "…", "repository": "…", "license": "MIT", "keywords": ["…"],
  "skills": "./skills/",
  "mcpServers": "./.mcp.json",
  "interface": {
    "displayName": "<interface.displayName | plugin.name>",
    "shortDescription": "<interface.shortDescription | plugin.description>",
    "longDescription": "…", "developerName": "…", "category": "…", "capabilities": ["…"],
    "defaultPrompt": ["…"], "brandColor": "#3B82F6",
    "composerIcon": "./assets/icon.png", "logo": "./assets/logo.png", "screenshots": ["./assets/s1.png"]
  }
}
```

与根清单的区别：

- `name` 取 `plugin.id`（Codex 要求它是小写连字符，并与插件目录名一致；同时作为技能的命名空间），根清单的 `name` 则继续使用 `plugin.name`；
- `interface` 只输出 `displayName`、`shortDescription` 和输入中声明过的字段，不会像 plugin-creator 那样把全部字段填上 `[TODO]`，否则清单在补全之前就是无效的；
- 引用到的 `./assets/*` 文件必须存在（`check` 会校验）；
- 不写入 `hooks`（D7）：宿主 `hooks.json` 用的是宿主专有格式（`onBlock`、`persistAfterInterrupt`，工具名为 `write_file`/`execute`），只写在根清单里。

## 3. 看板配置 board_config.json

`board_core/board_config.json` 是插件对 DevClaw 的固定看板接口。运行框架的状态规则不从这里读取，而是读取 `runtime/config/flow.json`（§5.2）；两者由同一份中间表示生成，`check` 会校验二者一致。

### 3.1 顶层键

| 键 | 必有 | 来源 |
|---|---|---|
| `apiVersion` | 是 | 固定为 `1` |
| `inspectCommands` | 是 | §3.2 |
| `workflow` | 是 | §3.3 |
| `checkpointSuffixState` | 是 | `in_progress`、`done` 两项；有终态节点时加 `archived`（input-config.md §6） |
| `boardEvents` | 是 | 固定为 `{"protocol": "autobiz.board-events.v1"}`，表示插件会推送看板事件（interfaces.md §3.5） |
| `knowledge_config` | 看板能力 `knowledgeSedimentation` | §7.3 |
| `artifact_sync` | 产物同步模块且 `artifactSync.entry.enabled` | §7.2 |
| `supported_deploy_units` | 知识模块 | §7.1；声明 `knowledge.source` 时运行期回写 |
| `agentsRepo` | 声明 `knowledge.source` | §7.1 |

### 3.2 inspectCommands

每个平台（darwin/linux/win32）一组。令 `{py}` 为 `board.target.python.posix`（win32 用 `python.win32`），`utf8Mode` 为 true 时再追加 ` -X utf8`。

| 键 | 值模板 | 条件 |
|---|---|---|
| `project_status` | `{py} "${pluginPath}/runtime/adapters/inspect_state.py" --mode project --workspace "${pluginWorkspace}" --projects ${projectDirs...}` | 必有 |
| `feature_status` | `{py} "${pluginPath}/runtime/adapters/inspect_state.py" --mode run --workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}"` | 必有 |
| `create_project` | `{py} "${pluginPath}/runtime/adapters/init_workspace.py" --workspace "${pluginWorkspace}" --project "${projectDir}"` | 必有 |
| `create_feature` | `{py} "${pluginPath}/runtime/adapters/init_feature.py" --workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}" --selected-deployUnit ${selectedDeployUnits}` | 必有 |
| `dynamic_workflow` | `{py} "${pluginPath}/runtime/adapters/inspect_workflow_templates.py"` | 必有 |
| `plugin_dir_hook` | `${pluginWorkspace}/${projectDir}` | 必有 |
| `dialog_tips` | `board.display.dialogTips` | 必有 |
| `system_prompt_inject` | `board.display.systemPromptInject` | 必有 |
| `session_context_inject` | `{py} "${pluginPath}/runtime/session/render_session_context.py" --platform <platform> --plugin-workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}" --selected-deployUnit ${selectedDeployUnits} --session-workspace-path "${sessionWorkspacePath}"` | 必有 |
| `knowledge_path` | `${pluginPath}/<knowledge.root>` | 知识模块；声明 `source` 时运行期回写 |
| `deploy_units` | `{py} "${pluginPath}/runtime/knowledge/inspect_deploy_units.py"` | 知识模块；键名待与 DevClaw 确认（README §9） |
| `pull_knowledge` | `{py} "${pluginPath}/runtime/knowledge/sync_knowledge.py" --write-board-config` | 声明 `knowledge.source` |
| `skip_node` | `{py} "${pluginPath}/runtime/adapters/skip_node.py" --workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}" --node "${nodeId}"` | 开启 `rules.skip` |

引号规则（D2）：单值占位符一律写成 `"${pluginPath}"` 这样放在双引号内；`${projectDirs...}`（多参数展开）和 `${selectedDeployUnits}`（JSON 数组）不加引号，由宿主当作参数整体转义。

关闭知识模块时，`knowledge_path`、`deploy_units`、`pull_knowledge` 三个键直接不生成（D1），不会输出空值。

### 3.3 workflow

```jsonc
{
  "templates": { "standard": { "kind": "profile", "label": "…", "description": "…" } },
  "skipPolicy": { "lockedNodes": [] },                       // 开启 rules.skip 时
  "dynamicStages": [ /* 有动态阶段时，见下 */ ],
  "checkpoints": {
    "initial": ["<P0>_in_progress"],
    "transitions": {
      "<P0>_in_progress": ["<P0>_done"], "<P0>_done": ["<P1>_in_progress"], "…": [],
      "<Pk-1>_done": ["archived"], "archived": []              // 有终态节点时；否则 "<Pk>_done": []
    },
    "stageLabels": { "<P0>_in_progress": "{name}进行中", "<P0>_done": "{name}完成", "archived": "已归档" }
  },
  "nodes": [ /* §3.4 */ ],
  "transitions": [ { "id": "<Pi>-to-<Pi+1>", "from": { "nodeId": "…", "state": "done" }, "to": { "nodeId": "…", "state": "in_progress" } } ]
}
```

动态阶段（`rules.dynamicStages`，input-config.md §2.7）：

```json
{
  "id": "detail_design_before_code", "phase": "Dev", "label": "详细设计", "description": "…", "order": 45,
  "choiceCheckpoint": "plan_done", "defaultDecision": "pending", "insertAfter": "dev.plan",
  "enableTargetCheckpoint": "detail_design_in_progress", "skipTargetCheckpoint": "code_in_progress",
  "enableLabel": "…", "skipLabel": "…", "enableDescription": "…", "skipDescription": "…",
  "nodes": [ { "id": "dev.detail_design", "phase": "Dev", "checkpointPrefix": "detail_design", "…": "其余字段同 §3.4" } ]
}
```

`checkpoints.transitions` 只描述主干。动态阶段的流转由 `choiceCheckpoint`、`enableTargetCheckpoint`、`skipTargetCheckpoint` 表达：执行时 `choiceCheckpoint → 阶段节点依次推进 → skipTargetCheckpoint`，跳过时 `choiceCheckpoint → skipTargetCheckpoint`。

### 3.4 节点

```jsonc
{
  "id": "dev.plan",
  "label": "任务计划",
  "group": "Dev",
  "skill": "autodev-plan",
  "runtimePolicy": { "agentMode": "multi", "subagentConfig": { … } },  // 可选，来自 session.policies.nodes
  "description": "…",
  "checkpoints": ["plan_in_progress", "plan_done"],
  "states": [
    { "nodeStatus": "not_started", "label": "未开始", "nextAction": { "slashSkill": "…", "userMessage": "…", "dialogTips": "…" } },
    { "nodeStatus": "in_progress", "label": "进行中", "nextAction": { … } },
    { "nodeStatus": "done",        "label": "已完成", "nextAction": { … } }
  ],
  "artifacts": { "inputs": [ /* §3.5 */ ], "outputs": [ /* §3.5 */ ] },
  "validators": []
}
```

`states` 必须按 not_started、in_progress、done 的顺序给出这三项；终态节点只有 not_started、archived 两项，`checkpoints` 为 `["archived"]`。`skipped` 是运行期状态，由 `feature_status` 给出，不在 `states` 中列出。`nextAction.slashSkill` 为空字符串表示流程结束，没有下一步。`validators` 固定为空数组：节点的校验命令由运行框架执行（§4.4），不交给 DevClaw。

### 3.5 产物定义

```json
{ "id": "plan", "label": "实施计划", "artifactType": "file", "path": "plan.md", "required": true }
{ "id": "spec_bundle", "label": "proposal.md", "artifactType": "file", "path": "proposal.md",
  "paths": ["proposal.md", "specs/*/spec.md"], "required": true }
{ "id": "prd", "label": "PRD文档", "artifactType": "file", "path": "PRD.md", "required": false }
{ "id": "code", "label": "代码提交", "artifactType": "git", "required": true,
  "git": { "repos": "deployUnits", "branch": "current", "require": ["commits", "clean", "merged"] } }
```

| 字段 | 必有 | 语义 |
|---|---|---|
| `id` / `artifactType` / `required` | 是 | 文件产物的 `artifactType` 按扩展名推断为 `file` 或 `json`，代码提交为 `git`；`required` 为核心配置中 `optional` 的反面 |
| `path` | 文件产物 | 核心配置中路径为数组时取首项，保证只认 `path` 的旧版宿主仍能工作。git 产物没有 `path` |
| `label` | 是 | 取 `board.display.artifacts[id]`，未配置时为第一个路径，git 产物为产物 id |
| `paths` | 否 | 仅在核心配置中路径为数组时输出，给出全部项 |
| `git` | git 产物 | 填好默认值的 `{repos, branch, require}`（input-config.md §2.9） |

完成判定见 §4.4。

### 3.6 运行期回写字段

只在声明了 `knowledge.source` 时存在：

| 字段 | 写入方 | 说明 |
|---|---|---|
| `supported_deploy_units` | `runtime/knowledge/sync_knowledge.py --write-board-config` | 来自同步后的知识清单 |
| `inspectCommands.<当前平台>.knowledge_path` | 同上 | 同步后的知识目录 |

运行期写入方只能改动上述字段。`build` 保留这两个字段的当前值，`package` 将其重置为输入值或模板默认值。

## 4. 运行期数据

### 4.1 目录布局

所有业务状态写在项目目录下，不得写入插件安装目录（运行框架会拒绝）。每个插件只读写自己的元数据目录 `{metaDir}`（D3，设计说明见 README §6.5）：

| `runtime.layout` | `{metaDir}`（相对项目目录） | 用途 |
|---|---|---|
| `isolated`（默认） | `<metaRoot>/<pluginId>` | 新插件；同一项目可以安装多个插件 |
| `legacy` | `<metaRoot>` | 迁移已有插件（例如 lite），保证其已有项目可用 |

`<metaRoot>` 是元数据根目录，取 `runtime.metaRoot`，默认 `.autobizdevops`（input-config.md §3.4）。

```text
<pluginWorkspace>/<projectDir>/{metaDir}/
├── state.json                 # 本插件的唯一事实源
├── .state.lock                # 跨进程锁
└── features/<feature>/
    ├── <产物…>                 # 按产物定义的 path
    ├── hooks.ndjson           # 变更日志
    ├── sync-status.json       # 产物同步能力
    └── ARTIFACT_CATALOG.json  # 产物同步能力
```

- `{metaDir}` 由运行框架根据 `runtime/config/runtime.json` 中的 `metaRoot`、`layout`、`pluginId` 推导。框架入口和模块通过 `runtime.common.query` 的 `metadata_dir()` / `feature_dir()` 获取，不得自行拼接；开发者的校验器通过 `${featureDir}` 占位符获取；
- isolated 布局下，`plugin.id` 不得是元数据根目录下的保留目录名：`features`、`archive`、`issues`、`reviews`、`logs`、`plugins`；
- `<feature>` 必须是安全的路径分量：非空，不是 `.` 或 `..`，不含 `/`、`\`、NUL。不同插件可以有同名 Feature。

### 4.2 state.json

位于 `{metaDir}/state.json`，只由 `engine.py` 写入：

```json
{
  "schemaVersion": 1,
  "pluginId": "autodev-planning-kanban",
  "boardSeq": 12,
  "features": {
    "example-feature": {
      "feature": "example-feature",
      "owner": "—",
      "iteration": "—",
      "checkpoint": "plan_in_progress",
      "stage": "任务计划进行中",
      "workflowProfile": "standard",
      "workflowTemplate": "standard",
      "workflowDecisions": { "detail_design_before_code": "enabled" },
      "workflowSkippedNodes": [],
      "deployUnits": [ { "deployUnitId": "LF39.18_wg_flow", "localRepoPath": "/Users/u/code/wg_flow" } ],
      "git": {
        "dev.code": {
          "LF39.18_wg_flow": {
            "path": "/Users/u/code/wg_flow", "branch": "feature/f1", "base": "a1b2c3d",
            "worktrees": ["/Users/u/code/wg_flow"], "done": null
          }
        }
      },
      "updated_at": "2026-10-14T03:00:00.000000+00:00"
    }
  }
}
```

流程规则和 git 产物相关的字段（只在用到时写入）：

| 字段 | 说明 |
|---|---|
| `workflowDecisions` | 动态阶段 id → `enabled` / `skipped`；尚未选择的阶段不出现 |
| `workflowSkippedNodes` | 被跳过的节点 id |
| `deployUnits` | 所选发布单元 `[{deployUnitId, localRepoPath}]`，`create_feature` 时由宿主传入（interfaces.md §3.3.2）。`localRepoPath` 是本机绝对路径，属于运行期数据，只出现在项目目录下的 `state.json` 中 |
| `git` | 节点 id → 仓库键 → 基线：`path`（仓库或子目录的绝对路径）、`branch`（基线分支）、`base`（节点开始时基线分支的 HEAD）、`worktrees`（节点开始时已有的工作树）、`done`（完成时的 HEAD，未完成为 `null`）。仓库键在 `repos` 为 `deployUnits` 时是发布单元 id，否则是相对项目目录的路径（`project` 为 `.`）。重开时保留 `base`、清空 `done` |

规则：

- 必须记录 `pluginId`（D3）。`pluginId` 与本插件不符时，拒绝读写，原文件保持不变（防止目录被拷贝或误放）；
- `schemaVersion` 不符、`checkpoint` 不在当前配置中、或 key 与 `feature` 字段不一致时，拒绝写入，原文件保持不变；
- `boardSeq` 是看板事件序号（interfaces.md §3.5），非负整数，缺省视为 0。engine 每次提交时在锁内加 1，其他写入方不得修改它；
- 记录中的未知字段原样保留（允许技能存放自定义元数据）；
- 不保存历史，事件写入 `hooks.ndjson`；读到旧版的 `history` 字段时，在下一次写入时移除；
- 写入必须在 `.state.lock` 内完成“读取 → 校验 → 原子替换”的完整事务。

### 4.3 hooks.ndjson（变更日志）简化事件内容，变更到mods，移动本身文件到.autobizdevops同级

文件名沿用现有宿主的 `hookLogRefs` 约定。每行一个 JSON 对象，所有写入方共用以下信封：

| 字段 | 必有 | 说明 |
|---|---|---|
| `ts` | 是 | ISO 8601，带时区 |
| `source` | 是 | `hook`（运行框架）/ `skill` / `module:<id>` |
| `pluginId` | 是 | 取自配置，禁止硬编码（目前产物同步写死为 `AUTOBIZDEVOPS-PLUGIN`，迁移时改掉） |
| `sessionId` | 是 | 环境变量 `SESSION_ID`，没有则为空字符串 |
| `featureId` | 是 | — |
| `eventId` | 是 | 事件类型，见下表 |
| `eventStatus` | 是 | `success` / `failed` / `skipped` / … |
| `message` | 是 | 给人看的说明 |

运行框架写入的事件：

| `eventId` | 写入时机 | 附加字段 |
|---|---|---|
| `update-state` | 状态推进或重开成功 | `from`、`to`、`nodeId`、`reopen`；做出动态阶段选择时另有 `decision: {stageId, value}` |
| `skip-node` | 跳过节点成功 | `nodeIds`、`from`、`to`（落地的 checkpoint，未变化时与 `from` 相同）、`reason` |
| `node-validate` | 执行节点校验命令后（无论是否通过；`--dry-run` 时不写） | `nodeId`、`exitCode`（超时为 `null`）、`durationMs`、`timedOut` |

### 4.4 完成判定

| 层次 | 负责方 | 内容 |
|---|---|---|
| 存在性（最小校验） | 运行框架 `engine.py` | 产物路径的每一项至少匹配一个普通文件。空文件也算存在。glob 不匹配目录 |
| 代码提交（git 产物） | 运行框架 `engine.py` | 按节点开始时记录的基线查仓库：基线分支上有新提交、没有未提交的改动、没有未合并回来的工作树分支（input-config.md §2.9） |
| 业务校验 | 开发者的校验命令 | 空文件、格式、内容是否合格，由节点 `validate` 命令判断（D13、D14） |

推进规则：

- 推进到 `<prefix>_in_progress`：检查本节点的必需输入是否存在；本节点有 git 产物时记录基线（重开时沿用原基线）；
- 推进到 `<prefix>_done`：检查必需输入和必需输出是否存在，git 产物按齐全条件检查，全部满足后再执行节点的 `validate` 命令，退出码为 0 才写入，同时记下各仓库的 `done`；
- 推进到 `archived`（终态节点）：检查终态节点的必需输入是否存在，不执行校验命令。

输入和输出默认是必需的；标了 `optional` 的不检查。git 产物作为输入时，看上游节点记录的提交范围 `base..done` 是否非空。生产者被跳过、或生产者是未执行的动态阶段节点时，依赖它的必需输入也不检查（input-config.md §2.3）。

查询（`feature_status`）只报告存在性：产物显示为已生成，不代表节点已完成。git 产物在查询时按同样的条件实时检查仓库（每个仓库几条只读 git 命令），只报告结果，不写记录。节点状态只由 `state.json` 中的 checkpoint 决定。

## 5. 内部配置 runtime/config/

编译后的内部配置，只给运行框架读取，DevClaw 不读。`engine.py` 只依赖这里的配置和 `state.json`；适配入口（`adapters/`、`session/`）在拼装宿主数据时，可以额外读取 `board_config.json` 中的展示字段（标签、`nextAction` 文案）。

### 5.1 runtime.json

```json
{
  "schema": "autobiz.runtime.v1",
  "pluginId": "doc-review",
  "metaRoot": ".autobizdevops",
  "layout": "isolated",
  "validateTimeoutSec": 120
}
```

`pluginId`、`metaRoot` 和 `layout` 在插件发布后不得修改：改了之后，已有项目的状态会找不到或被拒绝读取。`build` 发现它们与 build-manifest 中记录的不一致时报错（`PLUGIN_ID_CHANGED`、`LAYOUT_CHANGED`）。

### 5.2 flow.json（流程契约及状态规则）

核心流程 `workflow.json` 只写决策，`flow.json` 是它的编译结果，插件运行时只读这一份（D19）。编译时填好全部默认值：从节点 id 算出 checkpoint，从 `outputs` 汇总产物表并记下生产者，按扩展名推断产物类型，从 `board.display` 取显示名。

最小示例（input-config.md §8）编译后：

```jsonc
{
  "schema": "autobiz.flow.v1",
  "source": { "workflow.json": "sha256:…" },        // 用于检测编译配置是否过期（BUILD_STALE）
  "stages": ["Doc-Review-Kanban"],
  "artifacts": {
    "draft":  { "label": "DRAFT.md",  "type": "file", "paths": ["DRAFT.md"],  "producer": "draft" },
    "review": { "label": "REVIEW.md", "type": "file", "paths": ["REVIEW.md"], "producer": "review" }
  },
  "nodes": [
    { "id": "draft", "name": "起草", "stage": "Doc-Review-Kanban", "skill": "doc-draft", "skillDir": "skills/doc-draft",
      "order": 10, "terminal": false,
      "checkpoints": ["draft_in_progress", "draft_done"],
      "inputs": [], "outputs": [ { "id": "draft", "required": true } ],
      "validate": null },
    { "id": "review", "name": "评审", "stage": "Doc-Review-Kanban", "skill": "doc-review", "skillDir": "skills/doc-review",
      "order": 20, "terminal": false,
      "checkpoints": ["review_in_progress", "review_done"],
      "inputs": [ { "id": "draft", "required": true } ], "outputs": [ { "id": "review", "required": true } ],
      "validate": "${python} ${skillPath}/scripts/check_review.py --feature-dir ${featureDir}" }
  ],
  "dynamicStages": [],
  "skip": null,
  "checkpoints": {
    "chain": ["draft_in_progress", "draft_done", "review_in_progress", "review_done"],
    "initial": "draft_in_progress",
    "labels": { "draft_in_progress": "起草进行中", "draft_done": "起草完成", "review_in_progress": "评审进行中", "review_done": "评审完成" }
  }
}
```

文件产物的 `paths` 总是数组：核心配置中为字符串时只有一项。git 产物没有 `paths`，改为 `"type": "git"` 加填好默认值的 `git`，例如 `"code": {"label": "代码提交", "type": "git", "git": {"repos": "deployUnits", "branch": "current", "require": ["commits", "clean", "merged"]}, "producer": "dev.code"}`。节点的 `inputs`、`outputs` 都写成 `{id, required}`。`skillDir` 是按 input-config.md §5 查找到的技能目录。`validate` 未声明时为 `null`，命令中的占位符保持原样，执行时才替换。`flow.json` 不需要人阅读或修改，被手改时 `check` 报 `DRIFT_GENERATED`。

用到流程规则时，相关字段的形态：

```jsonc
{
  "nodes": [ …, { "id": "ops.archive", "terminal": true, "checkpoints": ["archived"], "outputs": [], "validate": null, "…": "…" } ],
  "dynamicStages": [
    { "id": "detail_design_before_code", "name": "详细设计", "insertAfter": "dev.plan", "defaultDecision": "pending",
      "choiceCheckpoint": "plan_done", "enableTarget": "detail_design_in_progress", "skipTarget": "code_in_progress",
      "nodes": [ { "id": "dev.detail_design", "checkpoints": ["detail_design_in_progress", "detail_design_done"], "…": "同主干节点" } ] }
  ],
  "skip": { "locked": [] },                                  // 未开启 rules.skip 时为 null
  "checkpoints": {
    "chain": [ "…", "cicd_done", "archived" ],                // 只含主干
    "initial": "prd_in_progress",
    "labels": { "…": "…", "detail_design_in_progress": "详细设计进行中", "archived": "已归档" }
  }
}
```

运行框架加载时必须校验以下不变量（沿用 lite 的 `load_config`）：

- 节点非空，主干与动态阶段的节点 id 合起来唯一，checkpoint 全局唯一；
- 非终态节点恰好有 2 个 checkpoint；终态节点最多一个，是最后一个主干节点，只有 `archived`；
- `initial` 恰好是首个节点的开始 checkpoint，`chain` 与主干节点顺序严格一致；
- 每个动态阶段的 `choiceCheckpoint` 在 `chain` 中，`skipTarget` 是 `choiceCheckpoint` 在 `chain` 中的后继；
- `skip.locked` 引用的节点都存在；
- `labels` 覆盖全部 checkpoint（含动态阶段节点、`archived`）；
- 每个节点的 `<skillDir>/SKILL.md` 存在；
- 产物路径均为安全的相对路径。

### 5.3 session.json

```json
{
  "schema": "autobiz.session.v1",
  "policies": {
    "default": { "agentMode": "solo" },
    "nodes": { "dev.plan": { "agentMode": "multi", "subagentConfig": { "customSubagentFiles": ["agents/explore.md"] } } }
  },
  "knowledgeAssembly": { "script": "runtime/knowledge/render_collected_session_context.py", "timeoutSec": 30 }
}
```

`knowledgeAssembly` 由知识模块在 `assembler = plugin` 时写入（interfaces.md §2.4）：`script` 固定为内置组装脚本，`timeoutSec` 取 `knowledge.assembly.timeoutSec`；未启用知识模块或 `assembler = devclaw` 时为 `null`。

### 5.4 knowledge.json（知识模块）

```json
{
  "schema": "autobiz.knowledge.v1",
  "root": "sys",
  "manifest": { "format": "agents-manifest-v1", "path": "agents.manifest.json" },
  "assembly": { "enabled": true, "assembler": "plugin", "timeoutSec": 30 },
  "source": { "type": "git", "url": "…", "sshUrl": "…", "ref": "master" }
}
```

未声明 `source` 时该键为 `null`。

## 6. 技能规范

### 6.1 SKILL.md append进skill.md（待讨论）

```markdown
---
name: autodev-plan
description: 将工作拆解为有序任务。当你已有规格说明……时使用。
---

# 任务计划

<!-- scaffold:begin state -->
## 技能状态维护

> 由脚手架生成，请勿手改；节点、checkpoint 或校验命令变化后执行 `autobiz-plugin build` 更新。

- 技能开始执行：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint plan_in_progress
  ```
- 本节点必需产物全部写入 `FEATURE_DIR` 后：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint plan_done
  ```
  推进时框架会检查必需产物是否存在，并执行本节点的校验命令 `${python} ${skillPath}/scripts/check_plan.py --feature-dir ${featureDir}`。未通过时按返回的错误修正产物后重试，不需要自己调用校验命令。
- 需要修改已完成阶段时：`--checkpoint plan_in_progress --reopen --reason "<原因>"`
<!-- scaffold:end state -->


（以下为开发者编写的技能正文）
```

`state` 片段就是“状态接入说明”。用到流程规则时，片段按节点追加对应的说明：

| 条件 | 追加内容 |
|---|---|
| 本节点是动态阶段的选择点 | 完成后询问用户是否执行该阶段（附两个选项的文案），按选择推进到 `<阶段首节点>_in_progress` 或 `<下一主干节点>_in_progress` |
| 开启 `rules.skip` 且本节点未被锁定 | 用户明确要求跳过本节点时：`--skip-node <nodeId> --reason "<原因>"` |
| 终态节点 | 不写 `_in_progress`/`_done` 两条，改为前一节点完成后推进到 `archived` |

要求：

- frontmatter 遵循 Codex 技能规则：只允许 `name`、`description`、`license`、`allowed-tools`、`metadata` 五个键。`name` 等于目录名和节点的 `skill`；`description` 必填，不超过 1024 字符，不含 `<` `>`。版本号等自定义信息放在 `metadata` 下（例如 `metadata: {version: "v3.0"}`）。现有插件中有 19 个技能把 `version` 写在顶层、2 个写了 `author`。DevClaw 不依赖这两个字段（D8），导入技能（`add skill --from`）时会自动把它们迁到 `metadata`；
- `description` 是技能的触发依据，“什么时候用”要写在这里，而不是正文：正文只有在技能被触发后才会加载。桩文件的 description 预置为 `[TODO: 做什么；在什么情况下使用]`；
- 技能的详细要求写在正文中。正文建议不超过 500 行，细节放到 `references/`，并在正文中写明什么时候读哪个文件（渐进式加载）；
- 必须包含 `state` 托管片段，片段内容必须与推导结果一致（`check` 会校验）；
- `artifacts` 托管片段是可选的，删除后 build 不会再加回来（build-manifest 中会记录 `optOut`）；
- 技能只能在本节点必需产物全部写好之后，才推进 `<prefix>_done`；运行框架会检查存在性并执行校验命令，不通过则拒绝推进；
- 技能私有的脚本放在技能目录的 `scripts/` 下（技能目录可能在分组下，见 input-config.md §5），校验命令中用 `${skillPath}/scripts/…` 引用。技能不需要、也不应该导入 `runtime/` 下的模块（interfaces.md §4.6）。


### 6.3 业务校验器

| 资源 | 建议位置 | 规则 |
|---|---|---|
| 业务校验器 | `skills/<skill>/scripts/` | 由节点 `validate` 命令调用，契约见 interfaces.md §4.4。脚手架不生成校验器；初始化向导可以按开发者要求创建骨架（带 `[TODO]`，`package` 前必须补全） |

技能用的模板由技能自己维护：放在技能目录下（例如 `templates/`），在技能正文中引用。脚手架不登记、不检查、不生成，`flow.json` 和会话上下文中也没有模板信息（D29）。

## 7. 模块输出

### 7.1 知识模块

文件（归属 `module`）：

| 文件 | 来源 | 条件 | 作用 |
|---|---|---|---|
| `runtime/knowledge/inspect_deploy_units.py` | lite `agents_repo.py` | 启用即生成 | 按 `manifest.format` 解析知识清单，输出支持的系统和发布单元（interfaces.md §3.3.8） |
| `runtime/knowledge/render_collected_session_context.py` | 全栈版 `render_collected_session_context.py`，去掉流程上下文和运行策略部分 | `assembler = plugin` | 内置组装脚本（interfaces.md §4.5）：调用 `collect-knowledge.js` 按所选发布单元组装知识；collector 不可用或单元未命中时按清单映射加载，最后回退 `<localRepoPath>/AGENTS.md`；始终读取 `<sessionWorkspacePath>/AGENTS.md`。插件可以替换这个文件，被替换后 build 和 upgrade 保留插件的版本（README §4） |
| `runtime/knowledge/collect-knowledge.js` | 全栈版 `collect-knowledge.js` | `assembler = plugin` | collector：列出支持的发布单元、按单元恢复知识，依赖 Node 和 `gray-matter` |
| `runtime/knowledge/sync_knowledge.py` | lite `sync_agents.py` | 声明 `source` | 克隆知识仓库到 `root`：先在临时目录克隆并校验清单，成功后再替换；HTTPS 失败时回退 SSH；回写 §3.6 字段 |

board_config 中的配置：

```json
"agentsRepo": { "url": "…", "sshUrl": "…", "ref": "master" },
"supported_deploy_units": []
```

`agentsRepo` 只在声明 `source` 时输出。另外会在 `inspectCommands` 中加入 `knowledge_path`、`deploy_units`（声明 `source` 时再加 `pull_knowledge`），生成 `runtime/config/knowledge.json`，在 `session.json` 中写入 `knowledgeAssembly`（仅 `assembler = plugin`，§5.3）。声明 `source` 时还会在 `.gitignore` 中追加 `<root>/`、`.knowledge.lock`、`.knowledge-sync-*`。

### 7.2 产物同步模块（modules/artifactSync.json）

```text
skills/<skillName>/
├── SKILL.md                         # module（文案中的技能名、路径会按 skillName 渲染）
├── config/artifact-sync.json        # generated（由节点输出推导）
├── references/sync-runtime.md       # module
├── references/feature-api-detail.md # module
└── scripts/sync_artifacts.py  scripts/artifact_sync_utils.py   # module
```

`config/artifact-sync.json` v2 格式：

```json
{
  "schemaVersion": 2,
  "allowedCheckpoints": ["plan_done", "code_in_progress", "code_done"],
  "uploadUrl": "https://…/file/upload",
  "maxFileSizeMiB": 5,
  "stages": {
    "Biz": { "biz.prd":   { "PRD.md": "结构化需求。" } },
    "Dev": { "dev.specs": { "proposal.md": "变更提案。", "specs/*/spec.md": "行为规格。", "design.md": "技术设计。" },
             "dev.plan":  { "plan.md": "实施计划。" } }
  }
}
```

推导规则：

- `stages[阶段名][nodeId][path] = 简述`，阶段名取节点的 `stage`（未写时为默认分组名）；按流程顺序（动态阶段节点在插入位置）遍历每个节点的 `outputs`，只取 `artifacts` 中列出的产物；简述取 `artifacts[产物 id]`。`path` 为数组的产物，每一项各占一个条目，简述相同；
- 每个产物只登记到第一个产出它的节点下；
- 再合并 `extraPaths`；
- `allowedCheckpoints` 优先用显式列表；否则取主干 checkpoint 链（含 `archived`，不含动态阶段节点）上 `allowedFrom` 及之后的全部 checkpoint，再去掉 `excludeCheckpoints`；
- 没有任何可同步路径的节点和阶段不输出。

看板入口（`entry.enabled` 时生成）：

```json
"artifact_sync": {
  "sync_type": "invoke_session",
  "nextAction": { "slashSkill": "<skillName>", "userMessage": "请针对${projectCode}项目的${feature}特性发起产物同步", "dialogTips": "发起产物同步" }
}
```

同步脚本属于框架模块，与运行框架同版本发布，通过 `runtime.common.query` 定位 Feature 目录和状态，因此同时支持 isolated 和 legacy 布局。上传路径（`{PROJECT_CODE}/DEV/Features/{feature}/{employeeId}/`）是否加入 `pluginId`，见 README §9。

脚本相对全栈版的改动见 [README.md §6.3](README.md)。v1 配置（无 `schemaVersion`、`stages` 只有 biz/dev）仍需能读取，以兼容全栈版现有插件。

### 7.3 知识沉淀入口（看板可选能力 knowledgeSedimentation）

只生成 board_config 中的配置，不带脚本：

```json
"knowledge_config": {
  "sync_type": "invoke_session",
  "nextAction": { "slashSkill": "knowledge-sync", "userMessage": "请针对${projectCode}项目发起知识沉淀，这个是 token：${leanToken}", "dialogTips": "发起知识沉淀" }
}
```

## 8. runtime/build-manifest.json

记录生成文件及构建信息，随插件发布。脚手架靠它判断哪些文件被手改过、能否安全升级：

```json
{
  "schema": "autobiz.build-manifest.v1",
  "scaffoldVersion": "1.0.0",
  "coreVersion": "1.0.0",
  "pluginId": "autodev-planning-kanban",
  "layout": "legacy",
  "metaRoot": ".autobizdevops",
  "modules": { "board": "1.0.0", "session": "1.0.0", "knowledge": "1.0.0", "artifactSync": "1.0.0" },
  "inputs": { "plugin.scaffold.json": "sha256:…", "workflow.json": "sha256:…",
              "modules/board.json": "sha256:…", "modules/session.json": "sha256:…", "modules/knowledge.json": "sha256:…",
              "modules/artifactSync.json": "sha256:…" },
  "files": {
    "runtime/common/engine.py": { "ownership": "managed", "sha256": "…" },
    "board_core/board_config.json": { "ownership": "generated", "sha256": "…", "runtimeFields": ["supported_deploy_units", "inspectCommands.*.knowledge_path"] },
    "skills/autodev-plan/SKILL.md": { "ownership": "seeded", "regions": { "state": "sha256:…", "artifacts": "optOut" } }
  }
}
```

不记录构建时间，保证同样的输入构建出同样的文件。build-manifest 应纳入版本控制。
