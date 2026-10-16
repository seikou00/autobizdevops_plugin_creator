# 用户输入配置规范（plugin.scaffold.json v1）

插件开发者唯一需要手写的配置文件，放在插件根目录。结构由 [JSON Schema](../schemas/plugin-scaffold.schema.json) 约束，语义规则见 §5。

## 1. 设计原则

- **只写决策**：checkpoint、状态流转、三平台命令、提示文案默认值都由脚手架推导，配置里不写。
- **产物先注册，后引用**：所有产物登记在 `artifacts` 中，节点通过 id 引用，避免同一路径重复定义。
- **默认值 + 局部覆写**：每个可推导的字段都有默认值，覆写只影响该字段本身。
- **JSON + Schema**：零依赖；在文件头写 `"$schema"`，IDEA/VS Code 就能补全和提示。（不用 YAML，因为 Python 标准库不能解析它。）

## 2. 顶层结构

```jsonc
{
  "$schema": "./.scaffold/plugin-scaffold.schema.json",
  "scaffoldVersion": 1,        // 必填，输入格式主版本
  "plugin":    { ... },        // 必填，插件信息 → 清单
  "runtime":   { ... },        // 可选，解释器与平台
  "board":     { ... },        // 可选，看板级文案
  "stages":    [ ... ],        // 必填，阶段（看板分组）
  "artifacts": { ... },        // 必填，产物注册表
  "nodes":     [ ... ],        // 必填，节点（顺序即流转顺序）
  "modules":   { ... }         // 可选，模块勾选与参数
}
```

## 3. 字段说明

### 3.1 plugin

| 字段 | 必填 | 说明 | 输出位置 |
|---|---|---|---|
| `id` | 是 | 稳定 ID，小写连字符，不超过 64 字符，同时也是安装目录名和隔离布局下的元数据目录名（`.autobizdevops/<id>/`）。不得使用保留名 `features`、`archive`、`issues`、`reviews`、`logs`、`plugins`。**发布后不可修改**，否则已有项目的状态无法找到或会被拒绝读取 | `state.json.pluginId`、hooks.ndjson `pluginId`、元数据目录名、`.codex-plugin/plugin.json.name` |
| `name` | 是 | 看板宿主沿用的插件名，可含大写（例如 `AutoBizDevOps-Plugin-Lite`） | 根 `plugin.json.name` |
| `version` | 是 | semver | 两份清单的 `version` |
| `description` | 是 | — | 两份清单的 `description` |
| `author` / `homepage` / `repository` / `license` / `keywords` | 否 | — | 两份清单 |
| `mcpServers` | 否 | 透传路径，以 `./` 开头，文件由开发者维护 | 两份清单的 `mcpServers` |
| `hooks` | 否 | 透传路径（宿主工具钩子），以 `./` 开头，文件由开发者维护 | 只写入根 `plugin.json.hooks`，不写入 Codex 清单（D7） |
| `codexManifest` | 否 | 默认 `false`。看板宿主只读根 `plugin.json`（D5），需要兼容 Codex 时再开启 | 是否生成 `.codex-plugin/plugin.json` |
| `interface` | 否 | 仅在 `codexManifest: true` 时使用。Codex 展示信息：`displayName`（缺省取 `name`）、`shortDescription`（缺省取 `description`）、`longDescription`、`developerName`、`category`、`capabilities`、`defaultPrompt`（最多 3 条，每条不超过 128 字符）、`brandColor`、`composerIcon`/`logo`/`screenshots`（放在 `./assets/` 下，截图必须是 PNG）、三个 URL | `.codex-plugin/plugin.json.interface` |

`new` 命令会像 Codex plugin-creator 那样规范化用户输入的名称：转小写，非字母数字字符改为 `-`，合并连续的 `-`，去掉首尾的 `-`（`My Plugin` → `my-plugin`），并提示规范化后的结果。

### 3.2 runtime

| 字段 | 默认值 | 说明 |
|---|---|---|
| `python.posix` | `python3` | darwin/linux 的解释器 |
| `python.win32` | `python` | win32 的解释器 |
| `utf8Mode` | `true` | 是否加 `-X utf8`（kanban 的约定）。lite 复刻样例设为 `false` |
| `layout` | `isolated` | 元数据与产物目录布局（README §6.5）。`isolated`：`.autobizdevops/<plugin.id>/`，同一项目可以装多个插件；`legacy`：`.autobizdevops/` 根目录，只用于迁移已有插件（例如 lite），保证其已有项目可用 |
| `platforms` | 三平台全部 | 生成哪些 `inspectCommands.<platform>` |

### 3.3 board

| 字段 | 默认值 |
|---|---|
| `workflowLabel` | `plugin.name` |
| `workflowDescription` | `{节点 label 以 " → " 连接}。` |
| `dialogTips` | `当前为{workflowLabel}插件：{节点 label 以 " → " 连接}。请描述目标与验收标准。` |
| `systemPromptInject` | `当前 Feature 为 ${feature}。产物目录 FEATURE_DIR=${pluginWorkspace}/${projectDir}/{metaDir}/features/${feature}。插件根目录 PLUGIN_ROOT=${pluginPath}。`，其中 `{metaDir}` 在构建时替换：`isolated` 布局为 `.autobizdevops/<plugin.id>`，`legacy` 布局为 `.autobizdevops` |
| `stateLabels` | `{"not_started":"未开始","in_progress":"进行中","done":"已完成"}` |

文案中只能使用该命令键允许的占位符（interfaces.md §3.2），否则报 `PLACEHOLDER_UNKNOWN`。覆写 `systemPromptInject` 时如果去掉了 `FEATURE_DIR`，会报 `FEATURE_DIR_MISSING` 警告，因为技能依赖这个变量定位产物目录。

### 3.4 stages

```json
"stages": [ { "id": "biz", "label": "Biz" }, { "id": "dev", "label": "Dev" } ]
```

- `id`：小写字母开头的字母数字，用作节点 id 前缀，也是产物同步配置的分组键；
- `label`：看板分组名，写入每个节点的 `group`；
- 数组顺序即分组顺序。节点必须按阶段连续排列（不允许 biz → dev → biz 交错）。

### 3.5 artifacts

```json
"artifacts": {
  "plan": { "label": "实施计划", "path": "plan.md", "legacyPaths": ["PLAN.md"] },
  "plan_json": { "label": "计划机器事实源", "path": "plan.json", "type": "json", "sync": false }
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| key | — | 产物 id，格式 `^[a-z][a-z0-9_]*$` |
| `label` | 必填 | 看板显示名 |
| `path` | 必填 | 相对 `FEATURE_DIR` 的 POSIX 路径，可含 glob（`specs/*/spec.md`）。glob 产物要求每个匹配文件都非空 |
| `type` | `file` | `file` / `json`，写入 `artifactType` |
| `legacyPaths` | `[]` | 兼容旧文件名，只在 `path` 没有匹配时回退使用 |
| `sync` | `true` | 产物同步模块是否上传 |
| `syncDescription` | `label + "。"` | 产物同步目录中的简述 |

保留路径不可使用：`state.json`、`hooks.ndjson`、`sync-status.json`、`ARTIFACT_CATALOG.json`。

### 3.6 nodes

```json
{
  "id": "dev.plan",
  "label": "任务计划",
  "skill": "autodev-plan",
  "checkpointPrefix": "plan",
  "description": "任务计划；产物：plan.md",
  "inputs": ["requirements", { "ref": "design", "required": false, "degrade": "无 design 时基于现有代码模式拆分任务" }],
  "outputs": ["plan", { "ref": "plan_json", "required": true }],
  "runtimePolicy": { "agentMode": "multi", "toolCustomConfig": { "task": { "enabled": true } } },
  "nextAction": { "done": { "userMessage": "实现当前feature" } }
}
```

| 字段 | 必填 | 默认值 / 说明 |
|---|---|---|
| `id` | 是 | `<stageId>.<name>`；stageId 必须已在 `stages` 中声明 |
| `label` | 是 | 节点显示名 |
| `skill` | 是 | 小写连字符，不超过 64 字符（Codex 技能命名规则，不允许下划线），对应 `skills/<skill>/SKILL.md`。build 时文件不存在会自动生成桩文件，check 时必须存在 |
| `checkpointPrefix` | 否 | 取 id 中 `.` 之后的部分；生成 `<prefix>_in_progress`、`<prefix>_done` |
| `description` | 否 | `{label}；产物：{输出路径以 "、" 连接}` |
| `inputs` | 否 | 产物 id，或 `{ref, required=true, degrade?, external=false}` |
| `outputs` | 否 | 产物 id，或 `{ref, required=true}`。可以为空数组（例如编码节点） |
| `runtimePolicy` | 否 | 原样写入节点。省略时宿主按 `solo` + task 开启处理 |
| `nextAction.active` | 否 | 覆写 not_started 和 in_progress 的 `slashSkill`/`userMessage`/`dialogTips` |
| `nextAction.done` | 否 | 覆写本节点完成后的提示，默认指向下一个节点 |

`slashSkill` 的作用是让看板**带出**对应技能，方便用户直接发起（D6），所以写不带命名空间前缀的技能名。覆写时如果写的既不是节点技能也不是模块技能，会报 `SLASH_SKILL_UNKNOWN` 警告；宿主提供的技能可以写，警告可以忽略。设为空字符串表示不带出任何技能。

`runtimePolicy` 字段：

| 字段 | 取值 |
|---|---|
| `agentMode` | `solo` / `multi` / `agent_team` / `workflow` |
| `toolCustomConfig.task.enabled` | bool |
| `subagentConfig.disabledBuiltinSubagents` | 禁用的内置子代理名，例如 `["Explore","critic"]` |
| `subagentConfig.customSubagentFiles` | 插件内相对路径 `agents/*.md`，文件必须存在 |

### 3.7 modules.knowledge（知识沉淀与解析）

```json
"knowledge": {
  "enabled": true,
  "agentsRepo": { "url": "https://…/Knowledge.git", "sshUrl": "git@…:…/Knowledge.git", "ref": "master" },
  "sedimentation": { "enabled": true },
  "supportedDeployUnits": []
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enabled` | — | 必填 |
| `loader` | `manifest` | v1 只支持 `agents.manifest.json` 加载器 |
| `agentsRepo.url` | 启用时必填 | 知识仓库 HTTPS 地址 |
| `agentsRepo.sshUrl` | `""` | HTTPS 克隆失败时回退的 SSH 地址 |
| `agentsRepo.ref` | `main` | 分支、标签或 commit |
| `sedimentation.enabled` | `true` | 是否生成 `knowledge_config`（宿主知识沉淀入口） |
| `sedimentation.syncType` | `invoke_session` | — |
| `sedimentation.slashSkill` | `knowledge-sync` | 宿主提供的技能 |
| `sedimentation.userMessage` | `请针对${projectCode}项目发起知识沉淀，这个是 token：${leanToken}` | — |
| `sedimentation.dialogTips` | `发起知识沉淀` | — |
| `supportedDeployUnits` | `[]` | 初始部署单元列表。运行期由 `pull_knowledge` 回写，打包时重置为此值 |

### 3.8 modules.artifactSync（产物同步）

```json
"artifactSync": {
  "enabled": true,
  "allowedFrom": "dev.plan:done",
  "excludeCheckpoints": ["code_in_progress"],
  "apiDetail": { "enabled": true, "node": "dev.code" },
  "extraPaths": { "biz.prd": { "prd_original/**/*": "原始需求文档或参考材料。" } }
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enabled` | — | 必填 |
| `skillName` | `autobizdevops-artifact-sync` | 生成的技能目录名和技能名 |
| `entry.enabled` | `true` | 是否在看板上生成产物同步入口（board_config 顶层 `artifact_sync`，`slashSkill` 为 `skillName`） |
| `entry.syncType` / `entry.userMessage` / `entry.dialogTips` | `invoke_session` / `请针对${projectCode}项目的${feature}特性发起产物同步` / `发起产物同步` | 入口文案 |
| `allowedFrom` | 与 `allowedCheckpoints` 二选一 | `<nodeId>:<in_progress\|done>` 或 checkpoint 名；从这里到流程末尾都允许同步 |
| `excludeCheckpoints` | `[]` | 从 `allowedFrom` 推导出的列表中再剔除的 checkpoint |
| `allowedCheckpoints` | — | 显式列表 |
| `uploadUrl` | 模块内置地址 | 上传服务地址 |
| `maxFileSizeMiB` | `5` | 超过上限的文件跳过并报告 |
| `apiDetail.enabled` / `.node` | — | 是否按实际代码生成 `FEATURE_API_DETAIL.md`，以及它归属哪个节点 |
| `extraPaths` | `{}` | 不属于任何节点输出、但需要同步的路径 |

## 4. 推导规则（输入 → board_config.json）

下表是规范性规则。已用 [lite 样例](../examples/lite.plugin.scaffold.json) 验证，编译结果与 autobizdevops_lite 的 `board_config.json` 逐字段一致（运行期回写字段除外）。

设节点按数组顺序为 `N[0..k]`，`P[i]` 为 `N[i]` 的 checkpointPrefix。

| 输出字段 | 规则 |
|---|---|
| `apiVersion` | `1` |
| `inspectCommands.<platform>` | 见 output-spec.md §3.2 的命令模板 |
| `workflow.templates.standard` | `{kind:"profile", label: workflowLabel, description: workflowDescription}` |
| `workflow.checkpoints.initial` | `[P[0]_in_progress]` |
| `workflow.checkpoints.transitions` | 按 `P[0]_in_progress → P[0]_done → P[1]_in_progress → … → P[k]_done → []` 线性排列 |
| `workflow.checkpoints.stageLabels` | `P[i]_in_progress: "{label}进行中"`，`P[i]_done: "{label}完成"` |
| `nodes[i].group` | `N[i]` 所属阶段的 `label` |
| `nodes[i].order` | `(i + 1) * 10` |
| `nodes[i].checkpoints` | `[P[i]_in_progress, P[i]_done]` |
| `nodes[i].states[not_started/in_progress].nextAction` | `slashSkill = N[i].skill`；`userMessage = "请使用 /{skill} 处理当前 Feature，先读取现有状态和产物。"`；`dialogTips = "当前阶段：{label}。"`；再合并 `nextAction.active` |
| `nodes[i].states[done].nextAction`（i < k） | `slashSkill = N[i+1].skill`；`userMessage` 同上，但用 `N[i+1].skill`；`dialogTips = "下一阶段：{N[i+1].label}。"`；再合并 `nextAction.done` |
| `nodes[k].states[done].nextAction` | `{slashSkill:"", userMessage:"", dialogTips:"{label}已完成。"}`，再合并 `nextAction.done` |
| `nodes[i].artifacts.inputs/outputs[]` | `{id, label, artifactType, path, required[, legacyPaths][, extract:{degrade}]}` |
| `nodes[i].validators` | `[]`（v1 固定） |
| `workflow.transitions[i]` | `{id:"P[i]-to-P[i+1]", from:{nodeId:N[i].id, state:"done"}, to:{nodeId:N[i+1].id, state:"in_progress"}}` |
| `checkpointSuffixState` | `in_progress`、`done` 两项，label 取 `stateLabels` |
| `agentsRepo` / `knowledge_config` / `supported_deploy_units` | 仅在知识模块启用时生成（output-spec.md §7.1） |
| `artifact_sync` | 仅在产物同步模块启用且 `entry.enabled` 时生成（output-spec.md §7.2） |
| `inspectCommands.*.knowledge_path` / `pull_knowledge` | 仅在知识模块启用时生成；关闭时直接不生成（D1） |

## 5. 校验规则

`validate` 阶段会收集全部问题后一次性输出（格式见 interfaces.md §1.3）。`error` 会阻止 build；`warning` 只提示，加 `--strict` 后视为 error。

| code | 级别 | 规则 |
|---|---|---|
| `INPUT_SCHEMA` | error | 不符合 JSON Schema |
| `STAGE_DUP` / `NODE_DUP` / `ARTIFACT_DUP` | error | id 重复 |
| `NODE_STAGE_UNKNOWN` | error | 节点 id 前缀不在 `stages` 中 |
| `NODE_STAGE_ORDER` | error | 节点没有按阶段连续排列，或排列顺序与 `stages` 不一致 |
| `STAGE_EMPTY` | warning | 阶段下没有节点 |
| `CHECKPOINT_DUP` | error | 推导出的 checkpoint 重复（前缀冲突） |
| `ARTIFACT_REF_UNKNOWN` | error | `inputs`/`outputs` 引用了未注册的产物 |
| `INPUT_REF_FORWARD` | error | 输入产物不是由前序节点产出，且未声明 `external: true` |
| `ARTIFACT_UNUSED` | warning | 产物已注册但没有节点引用 |
| `ARTIFACT_MULTI_PRODUCER` | warning | 多个节点输出同一产物（允许，用于后续阶段更新产物；以第一个节点为生产者） |
| `PATH_UNSAFE` | error | 路径为绝对路径、含 `..`、`\`、`:`，或与保留文件名冲突 |
| `SKILL_MISSING` | error（check）/ 自动生成桩（build） | `skills/<skill>/SKILL.md` 不存在 |
| `SKILL_NAME_MISMATCH` | error | SKILL.md frontmatter 中的 `name` 与 `skill` 不一致 |
| `SKILL_FRONTMATTER` | error | frontmatter 不符合 Codex 规则：只允许 `name`、`description`、`license`、`allowed-tools`、`metadata` 五个键；`description` 必填、不超过 1024 字符、不含 `<` `>`。版本号等自定义信息放进 `metadata`（例如 `metadata.version`）。宿主不依赖顶层 `version`（D8），`import` 时会自动迁移 |
| `SKILL_TOO_LONG` | warning | SKILL.md 超过 500 行，应把细节拆到 `references/` |
| `OPENAI_YAML` | error | `agents/openai.yaml` 不符合约束：`short_description` 应为 25–64 字符，`default_prompt` 必须以 `$<skill>` 形式提及技能 |
| `TODO_PLACEHOLDER` | warning（check）/ error（package） | 桩文件或清单中还有未填写的 `[TODO: …]` |
| `SKILL_STATE_BLOCK` | error | SKILL.md 缺少 `state` 托管片段，或片段内容与推导结果不一致 |
| `SKILL_SHARED` | warning | 多个节点共用同一个技能（看板能用，但技能需要自行区分 checkpoint） |
| `SUBAGENT_FILE_MISSING` | error | `customSubagentFiles` 指向的文件不存在 |
| `PLACEHOLDER_UNKNOWN` | error | 文案中使用了该命令键不允许的占位符 |
| `SLASH_SKILL_UNKNOWN` | warning | `nextAction` 覆写的 `slashSkill` 既不是节点技能也不是模块技能 |
| `PLUGIN_ID_RESERVED` | error | `plugin.id` 是保留目录名 |
| `INTERFACE_UNUSED` | warning | 声明了 `plugin.interface`，但 `codexManifest` 为 `false` |
| `LAYOUT_LEGACY` | warning | 使用了 `legacy` 布局：该插件不能与另一个 legacy 插件（例如 kanban）装在同一个项目中 |
| `FEATURE_DIR_MISSING` | warning | 覆写后的 `systemPromptInject` 不含 `FEATURE_DIR` |
| `MODULE_OPTION` | error | 模块参数非法，例如 `allowedFrom` 指向不存在的节点，或 `apiDetail.node` 不存在 |
| `MODULE_SKILL_CONFLICT` | error | 模块技能名与某个节点的技能名冲突 |
| `PLUGIN_ID_CHANGED` | error | `plugin.id` 与 `.scaffold/lock.json` 中记录的不一致（需加 `--allow-id-change`） |
| `LAYOUT_CHANGED` | error | `runtime.layout` 与 lock 中记录的不一致：已有项目的状态会找不到（需加 `--allow-layout-change`） |

## 6. 最小示例

两个节点，不启用模块（文件见 [examples/minimal.plugin.scaffold.json](../examples/minimal.plugin.scaffold.json)）：

```json
{
  "$schema": "./.scaffold/plugin-scaffold.schema.json",
  "scaffoldVersion": 1,
  "plugin": { "id": "doc-review", "name": "Doc-Review-Kanban", "version": "0.1.0", "description": "文档起草与评审" },
  "stages": [ { "id": "biz", "label": "Biz" } ],
  "artifacts": {
    "draft": { "label": "文档初稿", "path": "DRAFT.md" },
    "review": { "label": "评审意见", "path": "REVIEW.md" }
  },
  "nodes": [
    { "id": "biz.draft", "label": "起草", "skill": "doc-draft", "outputs": ["draft"] },
    { "id": "biz.review", "label": "评审", "skill": "doc-review", "inputs": ["draft"], "outputs": ["review"] }
  ]
}
```

生成结果：checkpoint 链为 `draft_in_progress → draft_done → review_in_progress → review_done`；产物目录为 `.autobizdevops/doc-review/features/<feature>/`；生成两个技能桩文件，各自带好状态维护片段；`inspectCommands` 中不含 `knowledge_path` 和 `pull_knowledge`；`session_context_inject` 只返回 `agentConfig`；不生成 `.codex-plugin/plugin.json`。

## 7. 完整示例

[examples/lite.plugin.scaffold.json](../examples/lite.plugin.scaffold.json)：约 110 行，复刻 autobizdevops_lite 的 509 行 `board_config.json`（使用 `layout: legacy`，保证 lite 已有项目可用），同时演示 `nextAction` 覆写、`legacyPaths`、`runtimePolicy`，以及两个模块的勾选。
