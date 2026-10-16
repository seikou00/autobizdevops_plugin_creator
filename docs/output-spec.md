# 插件标准化输出规范 v1

本文规定脚手架生成的插件**静态形态**：目录、清单、看板配置、运行期数据格式、技能格式。宿主命令的调用参数与返回 JSON 等**行为接口**见 [interfaces.md](interfaces.md)。

文中“必须/应当/可以”按 RFC 2119 的含义理解。

## 1. 目录结构

```text
<plugin>/
├── plugin.scaffold.json              # developer  输入配置（唯一事实源）
├── plugin.json                       # generated  根清单（看板宿主只读这一份）
├── .codex-plugin/plugin.json         # generated  Codex 清单（可选，plugin.codexManifest）
├── board.json                        # generated  board_config.json 的导出副本
├── inspect_state.py                  # managed    feature_status / project_status 入口
├── board_core/
│   ├── board_config.json             # generated  看板配置（运行期回写字段见 §3.6）
│   ├── __init__.py  runtime.py  inspect.py  cli.py                       # managed  内部实现
│   ├── api.py  extensions.py  policy.py                                  # managed  对外 API / Provider 协议 / 策略解析
│   ├── runtime.json                  # generated  pluginId、目录布局、Provider 注册表
│   └── VERSION                       # managed    内核版本
├── hooks/
│   ├── init_workspace.py             # managed    create_project / create_feature
│   ├── update_state.py               # managed    技能推进 checkpoint
│   ├── update_checkpoint.py          # managed    update_state 别名（兼容）
│   ├── inspect_workflow_templates.py # managed    dynamic_workflow
│   ├── render_session_context.py     # managed    session_context_inject
│   ├── export_board.py               # managed    board.json 导出与一致性检查
│   ├── sync_agents.py  agents_repo.py  knowledge_context.py  paths.py   # module: knowledge
│   └── hooks.json                    # developer  宿主工具钩子（可选，经 plugin.hooks 透传）
├── skills/
│   ├── <node-skill>/SKILL.md         # seeded     每个节点一个
│   ├── <node-skill>/agents/openai.yaml  # seeded  Codex 技能展示信息（可选）
│   ├── <node-skill>/references/…     # developer
│   └── <sync-skill>/…                # module: artifactSync（目录结构见 §7.2）
├── agents/*.md                       # developer  自定义子代理（runtimePolicy 引用）
├── references/workflow.md            # generated  状态接入约定（给技能和 agent 读）
├── tests/test_plugin_contract.py     # generated  契约测试
├── .scaffold/
│   ├── lock.json                     # generated  文件归属与哈希
│   └── plugin-scaffold.schema.json   # managed    输入配置 Schema
└── .gitignore                        # seeded     含 sys/、.knowledge.lock 等
```

打包产物（`autobiz-plugin package`）包含：根 `plugin.json`（开启时另含 `.codex-plugin/plugin.json`）、`board.json`、`inspect_state.py`、`board_core/`、`hooks/`、`skills/`、`agents/`、`references/`，以及清单中引用的 `.mcp.json`。不包含 `plugin.scaffold.json`、`.scaffold/`、`tests/`、`sys/`、`__pycache__/`。

## 2. 插件清单

看板宿主只读取根目录的 `plugin.json`（D5）。`.codex-plugin/plugin.json` 只在 `plugin.codexManifest: true` 时生成，用于兼容 Codex。`marketplace.json` 不生成。

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

### 3.1 顶层键

| 键 | 必有 | 来源 |
|---|---|---|
| `apiVersion` | 是 | 固定为 `1` |
| `inspectCommands` | 是 | §3.2 |
| `workflow` | 是 | §3.3 |
| `checkpointSuffixState` | 是 | `in_progress`、`done` 两项 |
| `agentsRepo` | 知识模块 | §7.1 |
| `knowledge_config` | 知识模块且 `sedimentation.enabled` | §7.1 |
| `supported_deploy_units` | 知识模块 | §7.1，运行期回写 |
| `artifact_sync` | 产物同步模块且 `entry.enabled` | §7.2 |

`board.json` 必须与 `board_config.json` 字节一致，由 `hooks/export_board.py` 维护，`--check` 用于校验。

### 3.2 inspectCommands

每个平台（darwin/linux/win32）一组。令 `{py}` 为 `runtime.python.posix`（win32 用 `runtime.python.win32`），`utf8Mode` 为 true 时再追加 ` -X utf8`。

| 键 | 值模板 | 条件 |
|---|---|---|
| `project_status` | `{py} "${pluginPath}/inspect_state.py" --mode project --workspace "${pluginWorkspace}" --projects ${projectDirs...}` | 必有 |
| `feature_status` | `{py} "${pluginPath}/inspect_state.py" --mode run --workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}"` | 必有 |
| `create_project` | `{py} "${pluginPath}/hooks/init_workspace.py" --mode createProject --workspace "${pluginWorkspace}" --project "${projectDir}"` | 必有 |
| `create_feature` | `{py} "${pluginPath}/hooks/init_workspace.py" --mode createFeature --workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}" --selected-deployUnit ${selectedDeployUnits}` | 必有 |
| `dynamic_workflow` | `{py} "${pluginPath}/hooks/inspect_workflow_templates.py"` | 必有 |
| `plugin_dir_hook` | `${pluginWorkspace}/${projectDir}` | 必有 |
| `dialog_tips` | `board.dialogTips` | 必有 |
| `system_prompt_inject` | `board.systemPromptInject` | 必有 |
| `session_context_inject` | `{py} "${pluginPath}/hooks/render_session_context.py" --platform <platform> --plugin-workspace "${pluginWorkspace}" --project "${projectDir}" --feature "${feature}" --selected-deployUnit ${selectedDeployUnits} --session-workspace-path "${sessionWorkspacePath}"` | 必有 |
| `knowledge_path` | `${pluginPath}/sys` | 知识模块；运行期回写 |
| `pull_knowledge` | `{py} "${pluginPath}/hooks/sync_agents.py" --write-board-config` | 知识模块 |

引号规则（D2）：单值占位符一律写成 `"${pluginPath}"` 这样放在双引号内；`${projectDirs...}`（多参数展开）和 `${selectedDeployUnits}`（JSON 数组）不加引号，由宿主当作参数整体转义。

关闭知识模块时，`knowledge_path` 和 `pull_knowledge` 两个键直接不生成（D1），不会输出空值。

### 3.3 workflow

```jsonc
{
  "templates": { "standard": { "kind": "profile", "label": "…", "description": "…" } },
  "checkpoints": {
    "initial": ["<P0>_in_progress"],
    "transitions": { "<P0>_in_progress": ["<P0>_done"], "<P0>_done": ["<P1>_in_progress"], "…": [], "<Pk>_done": [] },
    "stageLabels": { "<P0>_in_progress": "{label}进行中", "<P0>_done": "{label}完成" }
  },
  "nodes": [ /* §3.4 */ ],
  "transitions": [ { "id": "<Pi>-to-<Pi+1>", "from": { "nodeId": "…", "state": "done" }, "to": { "nodeId": "…", "state": "in_progress" } } ]
}
```

内核加载配置时必须校验以下不变量（沿用 lite 的 `load_config`）：

- 节点非空，节点 id 唯一，checkpoint 全局唯一；
- 每个节点恰好有 2 个 checkpoint；
- `initial` 恰好是首个节点的开始 checkpoint；
- `transitions` 与节点顺序严格一致，末节点完成后为空数组；
- `stageLabels` 覆盖全部 checkpoint；
- 每个节点的 `skills/<skill>/SKILL.md` 存在；
- 产物路径均为安全的相对路径。

### 3.4 节点

```jsonc
{
  "id": "dev.plan",
  "label": "任务计划",
  "group": "Dev",
  "skill": "autodev-plan",
  "order": 30,
  "runtimePolicy": { "agentMode": "multi", "toolCustomConfig": { "task": { "enabled": true } }, "subagentConfig": { … } },  // 可选
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

`states` 必须按 not_started、in_progress、done 的顺序给出这三项。`nextAction.slashSkill` 为空字符串表示流程结束，没有下一步。

### 3.5 产物定义

```json
{ "id": "plan", "label": "实施计划", "artifactType": "file", "path": "plan.md", "required": true,
  "legacyPaths": ["PLAN.md"], "extract": { "degrade": "…" } }
```

| 字段 | 必有 | 语义 |
|---|---|---|
| `id` / `label` / `artifactType` / `path` / `required` | 是 | — |
| `legacyPaths` | 否 | 仅当 `path` 无匹配时回退；`path` 存在但为空时**不**回退 |
| `extract.degrade` | 否 | 仅用于输入产物：缺失时的降级说明，给技能读 |

完成判定：`required` 产物的每个匹配文件都存在且去除空白后非空。glob 产物要求至少匹配一个文件。

### 3.6 运行期回写字段

| 字段 | 写入方 | 说明 |
|---|---|---|
| `supported_deploy_units` | `hooks/sync_agents.py --write-board-config` | 来自 `sys/agents.manifest.json` |
| `inspectCommands.<当前平台>.knowledge_path` | 同上 | 同步后的知识目录 |

运行期写入方必须同时写 `board_config.json` 和 `board.json`，并且只能改动上述字段。`build` 保留这两个字段的当前值，`package` 将其重置为输入值或模板默认值。

### 3.7 board_core/runtime.json

内核自身需要、但宿主不需要读的信息，单独生成一份，避免往 `board_config.json` 里加宿主不认识的键：

```json
{
  "schema": "autobiz.runtime.v1",
  "pluginId": "doc-review",
  "layout": "isolated",
  "sessionContextProviders": ["hooks.knowledge_context:provide"]
}
```

`pluginId` 和 `layout` 在插件发布后不得修改：改了之后，已有项目的状态会找不到或被拒绝读取。`build` 发现这两项与 lock 中记录的不一致时报错（`PLUGIN_ID_CHANGED`、`LAYOUT_CHANGED`）。

## 4. 运行期数据

### 4.1 目录布局

所有业务状态写在项目目录下，不得写入插件安装目录（内核会拒绝）。每个插件只读写自己的元数据目录 `{metaDir}`（D3，设计说明见 README §6.5）：

| `runtime.layout` | `{metaDir}`（相对项目目录） | 用途 |
|---|---|---|
| `isolated`（默认） | `.autobizdevops/<pluginId>` | 新插件；同一项目可以安装多个插件 |
| `legacy` | `.autobizdevops` | 迁移已有插件（例如 lite），保证其已有项目可用 |

```text
<pluginWorkspace>/<projectDir>/{metaDir}/
├── state.json                 # 本插件的唯一事实源
├── .state.lock                # 跨进程锁
└── features/<feature>/
    ├── <产物…>                 # 按 board_config 的 path
    ├── hooks.ndjson           # 事件日志
    ├── sync-status.json       # artifactSync 模块
    └── ARTIFACT_CATALOG.json  # artifactSync 模块
```

- `.autobizdevops` 是协议常量；`{metaDir}` 由内核根据 `board_core/runtime.json` 推导，模块和技能脚本必须通过 `board_core.api.metadata_dir()` / `feature_dir()` 获取，不得自行拼接；
- isolated 布局下，`plugin.id` 不得是 `.autobizdevops` 下的保留目录名：`features`、`archive`、`issues`、`reviews`、`logs`、`plugins`；
- `<feature>` 必须是安全的路径分量：非空，不是 `.` 或 `..`，不含 `/`、`\`、NUL。不同插件可以有同名 Feature。

### 4.2 state.json

位于 `{metaDir}/state.json`：

```json
{
  "schemaVersion": 1,
  "pluginId": "autodev-planning-kanban",
  "features": {
    "example-feature": {
      "feature": "example-feature",
      "owner": "—",
      "iteration": "—",
      "checkpoint": "plan_in_progress",
      "stage": "任务计划进行中",
      "workflowProfile": "standard",
      "workflowTemplate": "standard",
      "updated_at": "2026-10-14T03:00:00.000000+00:00"
    }
  }
}
```

规则：

- 必须记录 `pluginId`（D3）。`pluginId` 与本插件不符时，拒绝读写，原文件保持不变（防止目录被拷贝或误放）；
- `schemaVersion` 不符、`checkpoint` 不在当前配置中、或 key 与 `feature` 字段不一致时，拒绝写入，原文件保持不变；
- 记录中的未知字段原样保留（允许技能存放自定义元数据）；
- 不保存历史，事件写入 `hooks.ndjson`；读到旧版的 `history` 字段时，在下一次写入时移除；
- 写入必须在 `.state.lock` 内完成“读取 → 校验 → 原子替换”的完整事务。

### 4.3 hooks.ndjson

每行一个 JSON 对象，所有写入方共用以下信封：

| 字段 | 必有 | 说明 |
|---|---|---|
| `ts` | 是 | ISO 8601，带时区 |
| `source` | 是 | `hook`（内核）/ `skill` / `module:<id>` |
| `pluginId` | 是 | 取自配置，禁止硬编码（目前产物同步写死为 `AUTOBIZDEVOPS-PLUGIN`，迁移时改掉） |
| `sessionId` | 是 | 环境变量 `SESSION_ID`，没有则为空字符串 |
| `featureId` | 是 | — |
| `eventId` | 是 | 事件类型，例如 `update-state`、`artifact-sync` |
| `eventStatus` | 是 | `success` / `failed` / `skipped` / … |
| `message` | 是 | 给人看的说明 |

内核的 `update-state` 事件另有 `from`、`to`、`nodeId`、`reopen` 字段。模块应通过 `board_core.api.append_event` 写日志（interfaces.md §4）。

## 5. references/workflow.md（生成）

给技能和 agent 读的状态接入约定，内容由配置生成，包括：checkpoint 链、各节点的输入/输出产物表、状态更新命令、重开方式、`FEATURE_DIR` 的定位方式。技能托管片段会链接到这份文件。

## 6. 技能规范

### 6.1 SKILL.md

```markdown
---
name: autodev-plan
description: 将工作拆解为有序任务。当你已有规格说明……时使用。
---

# 任务计划

<!-- scaffold:begin state -->
## 技能状态维护

> 由脚手架生成，请勿手改；节点或 checkpoint 变化后执行 `autobiz-plugin build` 更新。

- 技能开始执行：
  ```
  python -X utf8 "${pluginPath}/hooks/update_state.py" --feature "${feature}" --checkpoint plan_in_progress
  ```
- 本节点必需产物全部写入 `FEATURE_DIR` 后：
  ```
  python -X utf8 "${pluginPath}/hooks/update_state.py" --feature "${feature}" --checkpoint plan_done
  ```
- 需要修改已完成阶段时：`--checkpoint plan_in_progress --reopen --reason "<原因>"`
<!-- scaffold:end state -->

<!-- scaffold:begin artifacts -->
## 输入与产物

| 方向 | 产物 | 路径（相对 FEATURE_DIR） | 必需 | 缺失时 |
|---|---|---|---|---|
| 输入 | 结构化需求 | `PRD.md` | 是 | — |
| 输出 | 实施计划 | `plan.md` | 是 | — |
<!-- scaffold:end artifacts -->

（以下为开发者编写的技能正文）
```

要求：

- frontmatter 遵循 Codex 技能规则：只允许 `name`、`description`、`license`、`allowed-tools`、`metadata` 五个键。`name` 等于目录名和节点的 `skill`；`description` 必填，不超过 1024 字符，不含 `<` `>`。版本号等自定义信息放在 `metadata` 下（例如 `metadata: {version: "v3.0"}`）。现有插件中有 19 个技能把 `version` 写在顶层、2 个写了 `author`。宿主不依赖这两个字段（D8），`import` 时会自动把它们迁到 `metadata`；
- `description` 是技能的触发依据，“什么时候用”要写在这里，而不是正文：正文只有在技能被触发后才会加载。桩文件的 description 预置为 `[TODO: 做什么；在什么情况下使用]`；
- 正文建议不超过 500 行，细节放到 `references/`，并在正文中写明什么时候读哪个文件（渐进式加载）；
- 必须包含 `state` 托管片段，片段内容必须与推导结果一致（`check` 会校验）；
- `artifacts` 托管片段是可选的，删除后 build 不会再加回来（lock 中会记录 `optOut`）；
- 技能只能在本节点必需产物全部写好之后，才推进 `<prefix>_done`；内核会再校验一次，校验不过则拒绝推进；
- 技能私有的脚本放在 `skills/<skill>/scripts/`，通过 `${pluginPath}/skills/<skill>/scripts/…` 调用；需要状态或路径时，使用 `board_core.api`（interfaces.md §4）。

### 6.2 agents/openai.yaml（可选，seeded）

格式遵循 Codex skill-creator 的 `references/openai_yaml.md`：

```yaml
interface:
  display_name: "任务计划"
  short_description: "把规格拆成带依赖和验收标准的任务计划"
  default_prompt: "使用 $autodev-plan 为当前 Feature 生成实施计划。"
dependencies:
  tools:
    - type: "mcp"
      value: "mcp-arch"
      description: "架构知识 MCP"
```

| 字段 | 生成规则 |
|---|---|
| `display_name` | 节点 `label` |
| `short_description` | 25–64 字符；由开发者填写，或由插件开发技能（README §2.3）读完 SKILL.md 后生成。不能截取 description，因为长度和语气都不对 |
| `default_prompt` | 一句话，必须以 `$<skill>` 形式提及技能 |
| `dependencies.tools` | 可选，声明技能依赖的 MCP 服务（`type` 目前只支持 `mcp`），对应插件 `.mcp.json` 中的服务 |

所有字符串值都加引号。`icon_small`、`icon_large`、`brand_color` 只在开发者提供时输出。

## 7. 模块输出

### 7.1 knowledge（知识沉淀与解析）

文件（归属 `module`）：

| 文件 | 来源 | 作用 |
|---|---|---|
| `hooks/sync_agents.py` | lite | 克隆知识仓库到 `sys/`：先在临时目录克隆并校验清单，成功后再替换；HTTPS 失败时回退 SSH；回写 §3.6 字段 |
| `hooks/agents_repo.py` | lite | `agents.manifest.json` 的解析、校验与路径助手 |
| `hooks/knowledge_context.py` | 从 lite `render_session_context.py` 拆出 | Provider：系统级、单元级、会话工作区、领域词汇表四层上下文 |
| `hooks/paths.py` | lite | 路径助手 |

board_config 中的配置：

```json
"agentsRepo": { "url": "…", "sshUrl": "…", "ref": "master" },
"knowledge_config": {
  "sync_type": "invoke_session",
  "nextAction": { "slashSkill": "knowledge-sync", "userMessage": "请针对${projectCode}项目发起知识沉淀，这个是 token：${leanToken}", "dialogTips": "发起知识沉淀" }
},
"supported_deploy_units": []
```

另外会在 `inspectCommands` 中加入 `knowledge_path`、`pull_knowledge`，在 `board_core/runtime.json` 的 `sessionContextProviders` 中注册 `hooks.knowledge_context:provide`，并在 `.gitignore` 中追加 `sys/`、`.knowledge.lock`、`.knowledge-sync-*`。

### 7.2 artifactSync（产物同步）

```text
skills/<skillName>/
├── SKILL.md                         # module（文案中的技能名、路径会按 skillName 渲染）
├── config/artifact-sync.json        # generated（由节点输出推导）
├── references/sync-runtime.md       # module
├── references/feature-api-detail.md # module，仅 apiDetail.enabled 时拷贝
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
    "biz": { "biz.prd":   { "PRD.md": "结构化需求。" } },
    "dev": { "dev.specs": { "proposal.md": "变更提案。", "specs/*/spec.md": "行为规格。", "design.md": "技术设计。" },
             "dev.plan":  { "plan.md": "实施计划。" },
             "dev.code":  { "FEATURE_API_DETAIL.md": "当前 Feature 涉及接口的详细说明。" } }
  }
}
```

推导规则：

- `stages[stageId][nodeId][path] = syncDescription`，按节点顺序遍历每个节点的 `outputs`，跳过 `sync: false` 的产物；
- 每个产物只登记到第一个产出它的节点下；
- 再合并 `extraPaths`；`apiDetail.enabled` 时，在 `apiDetail.node` 下加入 `FEATURE_API_DETAIL.md`；
- `allowedCheckpoints` 优先用显式列表；否则取 checkpoint 链上 `allowedFrom` 及之后的全部 checkpoint，再去掉 `excludeCheckpoints`；
- 没有任何可同步路径的节点和阶段不输出。

看板入口（`entry.enabled` 时生成；与 kanban `9411fc3` 新增的同名键同构）：

```json
"artifact_sync": {
  "sync_type": "invoke_session",
  "nextAction": { "slashSkill": "<skillName>", "userMessage": "请针对${projectCode}项目的${feature}特性发起产物同步", "dialogTips": "发起产物同步" }
}
```

脚本通过 `board_core.api.feature_dir()` 定位 Feature 目录，因此同时支持 isolated 和 legacy 布局。上传路径（`{PROJECT_CODE}/DEV/Features/{feature}/{employeeId}/`）是否加入 `pluginId`，见 README §9。

脚本相对全栈版的改动见 [README.md §6.3](README.md)。v1 配置（无 `schemaVersion`、`stages` 只有 biz/dev）仍需能读取，以兼容 kanban 现有插件。

## 8. .scaffold/lock.json

```json
{
  "schema": "autobiz.scaffold.lock.v1",
  "scaffoldVersion": "1.0.0",
  "coreVersion": "1.0.0",
  "pluginId": "autodev-planning-kanban",
  "layout": "legacy",
  "modules": { "knowledge": "1.0.0", "artifactSync": "1.0.0" },
  "inputDigest": "sha256:…",
  "files": {
    "board_core/runtime.py": { "ownership": "managed", "sha256": "…" },
    "board_core/board_config.json": { "ownership": "generated", "sha256": "…", "runtimeFields": ["supported_deploy_units", "inspectCommands.*.knowledge_path"] },
    "skills/autodev-plan/SKILL.md": { "ownership": "seeded", "regions": { "state": "sha256:…", "artifacts": "optOut" } }
  }
}
```

lock 文件应纳入版本控制，脚手架靠它判断哪些文件被手改过、能否安全升级。
