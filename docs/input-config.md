# 用户输入配置规范 v1

## 1. 输入总览

### 1.1 输入分类

插件开发者的输入分为两份配置文件和若干资源目录，都放在插件根目录。初始化向导（`autobiz-plugin new` 或插件开发技能，interfaces.md §1.4、§1.6）负责收集信息并生成骨架：

| 输入类别 | 位置 | 用户需要提供什么 | 哪些由初始化向导完成 | 最终生成什么 |
|---|---|---|---|---|
| 插件基础信息 | `plugin.scaffold.json` → `plugin` | 名称、版本、描述 | 收集信息，生成基础配置 | 插件清单 `plugin.json`、工程结构 |
| 核心流程 | `workflow.json` | 节点、技能绑定、执行顺序、输入输出、模板引用、可选校验命令 | 创建配置骨架，辅助选择已有技能 | 编译后的流程契约及状态规则 `runtime/config/flow.json` |
| 技能资源 | `skills/<skill>/` | 技能正文、模板、执行脚本、业务校验器 | 导入已有资源或创建空骨架 | 带状态接入说明的交付技能及资源 |
| 看板模块配置 | `plugin.scaffold.json` → `board` | 目标平台、展示设置、可选能力 | 生成接入脚本和平台命令映射 | 看板 adapter `runtime/adapters/*`、固定看板配置 `board_core/board_config.json` |
| 会话与 Agent 配置 | `plugin.scaffold.json` → `session`；`agents/` | 可选的自定义会话入口、运行策略、外挂资源 | 提供默认会话入口及配置骨架 | 会话模块 `runtime/session/*`、策略配置 `runtime/config/session.json`、资源引用 |
| 知识模块配置 | `plugin.scaffold.json` → `knowledge` | 清单解析方式、知识组装能力及组装方选择 | 引导启用和选择 | `runtime/knowledge/*`：清单解析、发布单元查询及组装接入 |
| 自定义扩展 | `hooks/` 等 | 开发者自己的 hooks 等资源 | 创建对应目录 | 原样交付的扩展资源 |

两份配置的结构分别由 [workflow.schema.json](../schemas/workflow.schema.json) 和 [plugin-scaffold.schema.json](../schemas/plugin-scaffold.schema.json) 约束，语义规则见 §6。两份配置都不随插件发布，运行期只读取编译结果（output-spec.md §5）。

### 1.2 设计原则

- **核心流程只表达业务骨架**：`workflow.json` 只写阶段、节点、技能绑定、产物、模板引用和校验命令。看板接入、知识配置、外挂技能管理和技能内部实现都不写在这里，分别放到 `plugin.scaffold.json` 的对应模块和技能正文中（D11）。
- **技能细节写在技能正文**：节点的 `description` 只写一句话，技能的详细要求写在 `SKILL.md` 正文中。
- **运行上下文不进配置**：项目路径、Feature、所选发布单元、会话工作区等由 DevClaw 在运行时传入（interfaces.md §3.2、§3.4），配置中不得写死（D15）。
- **只写决策**：checkpoint、状态流转、三平台命令、提示文案默认值都由脚手架推导，配置里不写。
- **产物先注册，后引用**：所有产物登记在 `artifacts` 中，节点通过 id 引用，避免同一路径重复定义。
- **默认值 + 局部覆写**：每个可推导的字段都有默认值，覆写只影响该字段本身。
- **JSON + Schema**：零依赖；在文件头写 `"$schema"`，IDEA/VS Code 就能补全和提示。（不用 YAML，因为 Python 标准库不能解析它。）

## 2. 核心流程 workflow.json

### 2.1 顶层结构

```jsonc
{
  "$schema": "./.scaffold/workflow.schema.json",
  "workflowVersion": 1,        // 必填，流程配置格式主版本
  "stages":    [ ... ],        // 必填，阶段（业务分组）
  "artifacts": { ... },        // 必填，产物注册表
  "nodes":     [ ... ]         // 必填，节点；数组顺序即执行顺序
}
```

### 2.2 stages

```json
"stages": [ { "id": "biz", "label": "Biz" }, { "id": "dev", "label": "Dev" } ]
```

- `id`：小写字母开头的字母数字，用作节点 id 前缀，也是产物同步配置的分组键；
- `label`：阶段名，写入看板节点的 `group`；
- 数组顺序即分组顺序。节点必须按阶段连续排列（不允许 biz → dev → biz 交错）。

### 2.3 artifacts

```json
"artifacts": {
  "plan": { "label": "实施计划", "path": "plan.md", "legacyPaths": ["PLAN.md"] },
  "spec_bundle": { "label": "规格包", "path": ["proposal.md", "specs/*/spec.md"] },
  "plan_json": { "label": "计划机器事实源", "path": "plan.json", "type": "json" }
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| key | — | 产物 id，格式 `^[a-z][a-z0-9_]*$` |
| `label` | 必填 | 看板显示名 |
| `path` | 必填 | 字符串或字符串数组（D12）。每一项都是相对 `FEATURE_DIR` 的 POSIX 路径，可含 glob（`specs/*/spec.md`）。数组表示该产物由多项组成，每一项都要存在 |
| `type` | `file` | `file` / `json`，写入 `artifactType` |
| `legacyPaths` | `[]` | 兼容旧文件名，只在 `path` 没有匹配时回退使用。只能和字符串形式的 `path` 一起使用 |

存在性由框架检查，只做最小校验：`path` 的每一项至少匹配一个普通文件即视为存在，空文件也算存在。空文件和产物是否合格由节点的业务校验决定（§2.5，D13）。

保留路径不可使用：`state.json`、`hooks.ndjson`、`sync-status.json`、`ARTIFACT_CATALOG.json`。

产物是否参与产物同步、同步目录中的简述，属于看板可选能力，配置在 `board.capabilities.artifactSync`（§3.4.4），不写在这里。

### 2.4 nodes

```json
{
  "id": "dev.plan",
  "label": "任务计划",
  "skill": "autodev-plan",
  "checkpointPrefix": "plan",
  "description": "任务计划；产物：plan.md",
  "inputs": ["requirements", { "ref": "design", "required": false, "degrade": "无 design 时基于现有代码模式拆分任务" }],
  "outputs": ["plan", { "ref": "plan_json", "required": true }],
  "templates": ["skills/autodev-plan/templates/plan.md"],
  "validate": "${python} ${pluginPath}/skills/autodev-plan/scripts/check_plan.py --feature-dir ${featureDir}"
}
```

| 字段 | 必填 | 默认值 / 说明 |
|---|---|---|
| `id` | 是 | `<stageId>.<name>`；stageId 必须已在 `stages` 中声明 |
| `label` | 是 | 节点显示名 |
| `skill` | 是 | 技能绑定。小写连字符，不超过 64 字符（Codex 技能命名规则，不允许下划线），对应 `skills/<skill>/SKILL.md`。初始化向导会列出已有技能供选择；build 时文件不存在会自动生成桩文件，check 时必须存在 |
| `checkpointPrefix` | 否 | 取 id 中 `.` 之后的部分；生成 `<prefix>_in_progress`、`<prefix>_done` |
| `description` | 否 | 一句话说明，默认 `{label}；产物：{输出路径以 "、" 连接}`。详细要求写在技能正文中 |
| `inputs` | 否 | 产物 id，或 `{ref, required=true, degrade?, external=false}` |
| `outputs` | 否 | 产物 id，或 `{ref, required=true}`。可以为空数组（例如编码节点） |
| `templates` | 否 | 模板引用：相对插件根目录的路径，必须位于 `skills/` 下。写入技能的托管片段和会话的流程上下文；build 时文件不存在会生成桩文件 |
| `validate` | 否 | 节点完成时执行的业务校验命令，见 §2.5 |

节点数组的顺序就是执行顺序，状态只能按这个顺序线性推进（v1）。

运行策略（`runtimePolicy`）和看板提示文案覆写（`nextAction`）不属于业务骨架，分别移到 `session.policies`（§3.5）和 `board.display.nodes`（§3.4.2）。

### 2.5 校验命令 validate

自定义校验采用**完整的单行命令**，**仅在节点完成时执行**（D14）：

- 只在推进到 `<prefix>_done` 时执行，并且在框架的存在性检查通过之后才执行。推进到 `_in_progress`、重开、查询都不执行；
- 命令不得含换行，也不经过 shell：先按 POSIX shell 规则拆分参数，再逐个参数替换占位符。所以路径含空格也不需要加引号，三个平台的行为一致，但不支持管道、重定向和 `&&`；
- 退出码 `0` 表示通过；非 `0` 或超时表示不通过，此时拒绝推进，`state.json` 不变，命令输出的末尾部分返回给模型，方便修正产物后重试；
- 空文件、格式、内容是否合格都由校验器自己判断，框架不做内容检查。

可用占位符由运行框架在执行时替换（与 DevClaw 的宿主占位符无关）：

| 占位符 | 值 |
|---|---|
| `${python}` | 运行框架当前使用的 Python 解释器，三个平台通用 |
| `${pluginPath}` | 插件安装目录 |
| `${projectPath}` | 项目目录，即 `<pluginWorkspace>/<projectDir>` |
| `${featureDir}` | 当前 Feature 的产物目录（按目录布局推导） |
| `${feature}` | 当前 Feature |
| `${nodeId}` | 当前节点 id |

执行细节（工作目录、环境变量、超时、输出截取）见 interfaces.md §4.3、§4.4。校验器脚本建议放在 `skills/<skill>/scripts/` 下。

## 3. 工程配置 plugin.scaffold.json

### 3.1 顶层结构

```jsonc
{
  "$schema": "./.scaffold/plugin-scaffold.schema.json",
  "scaffoldVersion": 1,          // 必填，工程配置格式主版本
  "workflow": "./workflow.json", // 可选，核心流程文件位置，默认即此值
  "plugin":    { ... },          // 必填，插件基础信息 → 清单
  "runtime":   { ... },          // 可选，状态目录布局与校验超时
  "board":     { ... },          // 可选，看板模块：目标平台、展示设置、可选能力
  "session":   { ... },          // 可选，会话与 Agent：自定义会话入口、运行策略
  "knowledge": { ... }           // 可选，知识模块：清单解析、知识组装
}
```

### 3.2 plugin

| 字段 | 必填 | 说明 | 输出位置 |
|---|---|---|---|
| `id` | 是 | 稳定 ID，小写连字符，不超过 64 字符，同时也是安装目录名和隔离布局下的元数据目录名（`.autobizdevops/<id>/`）。不得使用保留名 `features`、`archive`、`issues`、`reviews`、`logs`、`plugins`。**发布后不可修改**，否则已有项目的状态无法找到或会被拒绝读取 | `state.json.pluginId`、hooks.ndjson `pluginId`、元数据目录名、`.codex-plugin/plugin.json.name` |
| `name` | 是 | DevClaw 沿用的插件名，可含大写（例如 `AutoBizDevOps-Plugin-Lite`） | 根 `plugin.json.name` |
| `version` | 是 | semver | 两份清单的 `version` |
| `description` | 是 | — | 两份清单的 `description` |
| `author` / `homepage` / `repository` / `license` / `keywords` | 否 | — | 两份清单 |
| `mcpServers` | 否 | 透传路径，以 `./` 开头，文件由开发者维护 | 两份清单的 `mcpServers` |
| `hooks` | 否 | 透传路径（宿主工具钩子，属于自定义扩展），以 `./` 开头，文件由开发者维护 | 只写入根 `plugin.json.hooks`，不写入 Codex 清单（D7） |
| `codexManifest` | 否 | 默认 `false`。DevClaw 只读根 `plugin.json`（D5），需要兼容 Codex 时再开启 | 是否生成 `.codex-plugin/plugin.json` |
| `interface` | 否 | 仅在 `codexManifest: true` 时使用。Codex 展示信息：`displayName`（缺省取 `name`）、`shortDescription`（缺省取 `description`）、`longDescription`、`developerName`、`category`、`capabilities`、`defaultPrompt`（最多 3 条，每条不超过 128 字符）、`brandColor`、`composerIcon`/`logo`/`screenshots`（放在 `./assets/` 下，截图必须是 PNG）、三个 URL | `.codex-plugin/plugin.json.interface` |

初始化向导会像 Codex plugin-creator 那样规范化用户输入的名称：转小写，非字母数字字符改为 `-`，合并连续的 `-`，去掉首尾的 `-`（`My Plugin` → `my-plugin`），并提示规范化后的结果。

### 3.3 runtime

| 字段 | 默认值 | 说明 |
|---|---|---|
| `layout` | `isolated` | 元数据与产物目录布局（README §6.5）。`isolated`：`.autobizdevops/<plugin.id>/`，同一项目可以装多个插件；`legacy`：`.autobizdevops/` 根目录，只用于迁移已有插件（例如 lite），保证其已有项目可用 |
| `validateTimeoutSec` | `120` | 节点校验命令的超时秒数 |

### 3.4 board（看板模块）

#### 3.4.1 target：目标平台

| 字段 | 默认值 | 说明 |
|---|---|---|
| `platforms` | 三平台全部 | 生成哪些 `inspectCommands.<platform>` |
| `python.posix` | `python3` | darwin/linux 的解释器 |
| `python.win32` | `python` | win32 的解释器 |
| `utf8Mode` | `true` | 是否加 `-X utf8`（kanban 的约定）。lite 复刻样例设为 `false` |

#### 3.4.2 display：展示设置

| 字段 | 默认值 |
|---|---|
| `workflowLabel` | `plugin.name` |
| `workflowDescription` | `{节点 label 以 " → " 连接}。` |
| `dialogTips` | `当前为{workflowLabel}插件：{节点 label 以 " → " 连接}。请描述目标与验收标准。` |
| `systemPromptInject` | `当前 Feature 为 ${feature}。产物目录 FEATURE_DIR=${pluginWorkspace}/${projectDir}/{metaDir}/features/${feature}。插件根目录 PLUGIN_ROOT=${pluginPath}。`，其中 `{metaDir}` 在构建时替换：`isolated` 布局为 `.autobizdevops/<plugin.id>`，`legacy` 布局为 `.autobizdevops` |
| `stateLabels` | `{"not_started":"未开始","in_progress":"进行中","done":"已完成"}` |
| `nodes.<nodeId>.nextAction.active` | 覆写该节点 not_started 和 in_progress 状态的 `slashSkill`/`userMessage`/`dialogTips` |
| `nodes.<nodeId>.nextAction.done` | 覆写该节点完成后的提示，默认指向下一个节点 |

文案中只能使用该命令键允许的占位符（interfaces.md §3.2），否则报 `PLACEHOLDER_UNKNOWN`。覆写 `systemPromptInject` 时如果去掉了 `FEATURE_DIR`，会报 `FEATURE_DIR_MISSING` 警告，因为技能依赖这个变量定位产物目录。

`slashSkill` 的作用是让看板**带出**对应技能，方便用户直接发起（D6），所以写不带命名空间前缀的技能名。覆写时如果写的既不是节点技能也不是模块技能，会报 `SLASH_SKILL_UNKNOWN` 警告；DevClaw 提供的技能可以写，警告可以忽略。设为空字符串表示不带出任何技能。

#### 3.4.3 capabilities.knowledgeSedimentation：知识沉淀入口

在看板上生成知识沉淀入口（board_config 顶层 `knowledge_config`），带出 DevClaw 提供的 `knowledge-sync` 技能。它只是看板入口，不依赖知识模块是否启用。

```json
"knowledgeSedimentation": { "enabled": true }
```

| 字段 | 默认值 |
|---|---|
| `enabled` | 必填 |
| `syncType` | `invoke_session` |
| `slashSkill` | `knowledge-sync` |
| `userMessage` | `请针对${projectCode}项目发起知识沉淀，这个是 token：${leanToken}` |
| `dialogTips` | `发起知识沉淀` |

#### 3.4.4 capabilities.artifactSync：产物同步

```json
"artifactSync": {
  "enabled": true,
  "allowedFrom": "dev.plan:done",
  "excludeCheckpoints": ["code_in_progress"],
  "exclude": ["plan_json"],
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
| `exclude` | `[]` | 不上传的产物 id |
| `descriptions` | `{}` | 产物 id → 同步目录中的简述，缺省为 `label + "。"` |
| `uploadUrl` | 模块内置地址 | 上传服务地址 |
| `maxFileSizeMiB` | `5` | 超过上限的文件跳过并报告 |
| `apiDetail.enabled` / `.node` | — | 是否按实际代码生成 `FEATURE_API_DETAIL.md`，以及它归属哪个节点 |
| `extraPaths` | `{}` | 不属于任何节点输出、但需要同步的路径 |

### 3.5 session（会话与 Agent）

```json
"session": {
  "customEntry": { "command": "${python} ${pluginPath}/hooks/session_extra.py" },
  "policies": {
    "default": { "agentMode": "solo", "toolCustomConfig": { "task": { "enabled": true } } },
    "nodes": {
      "dev.plan": {
        "agentMode": "multi",
        "toolCustomConfig": { "task": { "enabled": true } },
        "subagentConfig": { "disabledBuiltinSubagents": ["Explore"], "customSubagentFiles": ["agents/explore.md"] }
      }
    }
  }
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `customEntry.command` | 不声明 | 可选的自定义会话入口：完整的单行命令，拆分和占位符规则同 §2.5。默认会话入口生成流程上下文和知识组装结果后调用它，把它的输出并入 `sessionContext`。它不会替换默认入口（README §9） |
| `customEntry.timeoutSec` | `30` | 超时后忽略该入口的输出，并在 `message` 中说明 |
| `policies.default` | `{"agentMode":"solo","toolCustomConfig":{"task":{"enabled":true}}}` | 全局默认运行策略 |
| `policies.nodes.<nodeId>` | — | 节点运行策略，原样写入 board_config 中对应节点的 `runtimePolicy` |

不声明 `session` 时，使用默认会话入口和默认策略。

运行策略字段：

| 字段 | 取值 |
|---|---|
| `agentMode` | `solo` / `multi` / `agent_team` / `workflow` |
| `toolCustomConfig.task.enabled` | bool |
| `subagentConfig.disabledBuiltinSubagents` | 禁用的内置子代理名，例如 `["Explore","critic"]` |
| `subagentConfig.customSubagentFiles` | 外挂资源：插件内相对路径 `agents/*.md`，文件必须存在 |

### 3.6 knowledge（知识模块）

```json
"knowledge": {
  "enabled": true,
  "manifest": { "format": "agents-manifest-v1", "path": "agents.manifest.json" },
  "assembly": { "enabled": true, "assembler": "plugin" },
  "source": { "type": "git", "url": "https://…/Knowledge.git", "sshUrl": "git@…:…/Knowledge.git", "ref": "master" }
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enabled` | — | 必填 |
| `root` | `sys` | 知识目录，相对插件根目录。知识模块入口和会话入口另接受 `--knowledge-path` 参数临时覆盖它（用于本地调试，或由自行管理知识目录的调用方传入），生成的宿主命令不带这个参数 |
| `manifest.format` | `agents-manifest-v1` | 清单解析方式。v1 只支持 lite 的 `agents.manifest.json` 格式 |
| `manifest.path` | `agents.manifest.json` | 清单文件，相对 `root` |
| `assembly.enabled` | `true` | 是否组装知识上下文 |
| `assembly.assembler` | `plugin` | 组装方。`plugin`：由插件会话模块内置的组装器组装（系统级、单元级、会话工作区、领域词汇表四层），结果并入 `sessionContext`；`devclaw`：由 DevClaw 组装，插件只通过 `inspect_deploy_units.py` 提供清单解析结果，`sessionContext` 中不含知识段 |
| `source` | 不声明 | 可选：由插件自己拉取知识仓库。声明后生成 `runtime/knowledge/sync_knowledge.py` 和 `pull_knowledge` 命令（README §9） |
| `source.type` | `git` | v1 只支持 git |
| `source.url` | 声明 `source` 时必填 | 知识仓库 HTTPS 地址 |
| `source.sshUrl` | `""` | HTTPS 克隆失败时回退的 SSH 地址 |
| `source.ref` | `main` | 分支、标签或 commit |
| `supportedDeployUnits` | `[]` | board_config `supported_deploy_units` 的初始值。声明 `source` 时，运行期由 `pull_knowledge` 回写，打包时重置为此值 |

## 4. 资源目录

| 目录 | 内容 | 初始化向导 | 交付方式 |
|---|---|---|---|
| `skills/<skill>/` | `SKILL.md` 正文、`templates/` 模板、`scripts/` 执行脚本与业务校验器、`references/` | 导入已有技能目录，或创建空骨架（SKILL.md 桩、`templates/`、`scripts/`） | SKILL.md 加上状态接入托管片段，其余原样交付（output-spec.md §6） |
| `agents/` | 自定义子代理等外挂资源，由会话策略引用 | 按需创建 | 原样交付 |
| `hooks/` | 开发者自定义扩展，例如宿主工具钩子 `hooks.json`、自定义会话入口脚本 | 创建目录 | 原样交付，脚手架不读写 |

技能私有的脚本和校验器不需要、也不应该导入 `runtime/` 下的任何模块。它们需要的路径来自会话上下文（`FEATURE_DIR`）或校验命令占位符（§2.5）。

## 5. 推导规则（输入 → board_config.json）

下表是规范性规则。设节点按数组顺序为 `N[0..k]`，`P[i]` 为 `N[i]` 的 checkpointPrefix。`runtime/config/` 下的内部配置由同一份中间表示生成（output-spec.md §5）。

| 输出字段 | 规则 |
|---|---|
| `apiVersion` | `1` |
| `inspectCommands.<platform>` | 见 output-spec.md §3.2 的命令模板，平台与解释器取自 `board.target` |
| `workflow.templates.standard` | `{kind:"profile", label: workflowLabel, description: workflowDescription}` |
| `workflow.checkpoints.initial` | `[P[0]_in_progress]` |
| `workflow.checkpoints.transitions` | 按 `P[0]_in_progress → P[0]_done → P[1]_in_progress → … → P[k]_done → []` 线性排列 |
| `workflow.checkpoints.stageLabels` | `P[i]_in_progress: "{label}进行中"`，`P[i]_done: "{label}完成"` |
| `nodes[i].group` | `N[i]` 所属阶段的 `label` |
| `nodes[i].order` | `(i + 1) * 10` |
| `nodes[i].runtimePolicy` | `session.policies.nodes[N[i].id]`；未配置时不输出 |
| `nodes[i].checkpoints` | `[P[i]_in_progress, P[i]_done]` |
| `nodes[i].states[not_started/in_progress].nextAction` | `slashSkill = N[i].skill`；`userMessage = "请使用 /{skill} 处理当前 Feature，先读取现有状态和产物。"`；`dialogTips = "当前阶段：{label}。"`；再合并 `board.display.nodes[N[i].id].nextAction.active` |
| `nodes[i].states[done].nextAction`（i < k） | `slashSkill = N[i+1].skill`；`userMessage` 同上，但用 `N[i+1].skill`；`dialogTips = "下一阶段：{N[i+1].label}。"`；再合并 `nextAction.done` |
| `nodes[k].states[done].nextAction` | `{slashSkill:"", userMessage:"", dialogTips:"{label}已完成。"}`，再合并 `nextAction.done` |
| `nodes[i].artifacts.inputs/outputs[]` | `{id, label, artifactType, path, required[, paths][, legacyPaths][, extract:{degrade}]}`。`path` 为数组时，`path` 取首项，`paths` 给出全部（output-spec.md §3.5） |
| `nodes[i].validators` | `[]`（v1 固定）。节点的 `validate` 命令只写入 `runtime/config/flow.json`，由运行框架执行，DevClaw 不执行 |
| `workflow.transitions[i]` | `{id:"P[i]-to-P[i+1]", from:{nodeId:N[i].id, state:"done"}, to:{nodeId:N[i+1].id, state:"in_progress"}}` |
| `checkpointSuffixState` | `in_progress`、`done` 两项，label 取 `stateLabels` |
| `knowledge_config` | 仅在 `board.capabilities.knowledgeSedimentation.enabled` 时生成（output-spec.md §7.3） |
| `artifact_sync` | 仅在 `board.capabilities.artifactSync.enabled` 且 `entry.enabled` 时生成（output-spec.md §7.2） |
| `supported_deploy_units` | 仅在知识模块启用时生成（output-spec.md §7.1） |
| `agentsRepo` | 仅在声明 `knowledge.source` 时生成 |
| `inspectCommands.*.knowledge_path` / `deploy_units` | 仅在知识模块启用时生成；关闭时直接不生成（D1） |
| `inspectCommands.*.pull_knowledge` | 仅在声明 `knowledge.source` 时生成 |

## 6. 校验规则

`validate` 阶段会收集全部问题后一次性输出（格式见 interfaces.md §1.3）。`error` 会阻止 build；`warning` 只提示，加 `--strict` 后视为 error。问题出在哪份配置，由 Issue 的 `file` 字段标明。

| code | 级别 | 规则 |
|---|---|---|
| `INPUT_SCHEMA` | error | `workflow.json` 或 `plugin.scaffold.json` 不符合各自的 JSON Schema |
| `STAGE_DUP` / `NODE_DUP` / `ARTIFACT_DUP` | error | id 重复 |
| `NODE_STAGE_UNKNOWN` | error | 节点 id 前缀不在 `stages` 中 |
| `NODE_STAGE_ORDER` | error | 节点没有按阶段连续排列，或排列顺序与 `stages` 不一致 |
| `STAGE_EMPTY` | warning | 阶段下没有节点 |
| `CHECKPOINT_DUP` | error | 推导出的 checkpoint 重复（前缀冲突） |
| `ARTIFACT_REF_UNKNOWN` | error | `inputs`/`outputs`，或 `artifactSync.exclude`/`descriptions` 引用了未注册的产物 |
| `INPUT_REF_FORWARD` | error | 输入产物不是由前序节点产出，且未声明 `external: true` |
| `ARTIFACT_UNUSED` | warning | 产物已注册但没有节点引用 |
| `ARTIFACT_MULTI_PRODUCER` | warning | 多个节点输出同一产物（允许，用于后续阶段更新产物；以第一个节点为生产者） |
| `PATH_UNSAFE` | error | 产物路径（数组中的每一项）、模板路径或知识目录为绝对路径，含 `..`、`\`、`:`，或与保留文件名冲突 |
| `PATH_ARRAY_LEGACY` | error | `path` 为数组时声明了 `legacyPaths` |
| `SKILL_MISSING` | error（check）/ 自动生成桩（build） | `skills/<skill>/SKILL.md` 不存在 |
| `SKILL_NAME_MISMATCH` | error | SKILL.md frontmatter 中的 `name` 与 `skill` 不一致 |
| `SKILL_FRONTMATTER` | error | frontmatter 不符合 Codex 规则：只允许 `name`、`description`、`license`、`allowed-tools`、`metadata` 五个键；`description` 必填、不超过 1024 字符、不含 `<` `>`。版本号等自定义信息放进 `metadata`（例如 `metadata.version`）。DevClaw 不依赖顶层 `version`（D8），`import` 时会自动迁移 |
| `SKILL_TOO_LONG` | warning | SKILL.md 超过 500 行，应把细节拆到 `references/` |
| `OPENAI_YAML` | error | `agents/openai.yaml` 不符合约束：`short_description` 应为 25–64 字符，`default_prompt` 必须以 `$<skill>` 形式提及技能 |
| `TODO_PLACEHOLDER` | warning（check）/ error（package） | 桩文件、骨架文件或清单中还有未填写的 `[TODO: …]` |
| `SKILL_STATE_BLOCK` | error | SKILL.md 缺少 `state` 托管片段，或片段内容与推导结果不一致 |
| `SKILL_SHARED` | warning | 多个节点共用同一个技能（看板能用，但技能需要自行区分 checkpoint） |
| `LEGACY_ENTRY_REF` | warning | 技能正文（托管片段以外）仍引用旧入口路径：`hooks/update_state.py`、`hooks/update_checkpoint.py`、`hooks/init_workspace.py`、根目录 `inspect_state.py` |
| `TEMPLATE_MISSING` | error（check）/ 自动生成桩（build） | `templates` 引用的文件不存在 |
| `COMMAND_INVALID` | error | `validate` 或 `session.customEntry.command` 为空、含换行、无法按 POSIX 规则拆分，或使用了 §2.5 以外的占位符 |
| `COMMAND_SCRIPT_MISSING` | warning | 命令中以 `${pluginPath}/` 开头的参数指向的文件不存在 |
| `BOARD_NODE_UNKNOWN` | error | `board.display.nodes` 的 key 不是 workflow 中的节点 |
| `POLICY_NODE_UNKNOWN` | error | `session.policies.nodes` 的 key 不是 workflow 中的节点 |
| `SUBAGENT_FILE_MISSING` | error | `customSubagentFiles` 指向的文件不存在 |
| `PLACEHOLDER_UNKNOWN` | error | 看板文案中使用了该命令键不允许的占位符 |
| `SLASH_SKILL_UNKNOWN` | warning | `nextAction` 覆写的 `slashSkill` 既不是节点技能也不是模块技能 |
| `PLUGIN_ID_RESERVED` | error | `plugin.id` 是保留目录名 |
| `INTERFACE_UNUSED` | warning | 声明了 `plugin.interface`，但 `codexManifest` 为 `false` |
| `LAYOUT_LEGACY` | warning | 使用了 `legacy` 布局：该插件不能与另一个 legacy 插件（例如 kanban）装在同一个项目中 |
| `FEATURE_DIR_MISSING` | warning | 覆写后的 `systemPromptInject` 不含 `FEATURE_DIR` |
| `MODULE_OPTION` | error | 模块或可选能力的参数非法，例如 `allowedFrom` 指向不存在的节点，或 `apiDetail.node` 不存在 |
| `MODULE_SKILL_CONFLICT` | error | 模块技能名与某个节点的技能名冲突 |
| `PLUGIN_ID_CHANGED` | error | `plugin.id` 与 `runtime/build-manifest.json` 中记录的不一致（需加 `--allow-id-change`） |
| `LAYOUT_CHANGED` | error | `runtime.layout` 与 build-manifest 中记录的不一致：已有项目的状态会找不到（需加 `--allow-layout-change`） |

## 7. 最小示例

两个节点，不启用知识模块和看板可选能力（文件见 [examples/minimal/](../examples/minimal/)）。

`workflow.json`：

```json
{
  "$schema": "./.scaffold/workflow.schema.json",
  "workflowVersion": 1,
  "stages": [ { "id": "biz", "label": "Biz" } ],
  "artifacts": {
    "draft": { "label": "文档初稿", "path": "DRAFT.md" },
    "review": { "label": "评审意见", "path": "REVIEW.md" }
  },
  "nodes": [
    { "id": "biz.draft", "label": "起草", "skill": "doc-draft", "outputs": ["draft"],
      "templates": ["skills/doc-draft/templates/DRAFT.md"] },
    { "id": "biz.review", "label": "评审", "skill": "doc-review", "inputs": ["draft"], "outputs": ["review"],
      "validate": "${python} ${pluginPath}/skills/doc-review/scripts/check_review.py --feature-dir ${featureDir}" }
  ]
}
```

`plugin.scaffold.json`：

```json
{
  "$schema": "./.scaffold/plugin-scaffold.schema.json",
  "scaffoldVersion": 1,
  "plugin": { "id": "doc-review", "name": "Doc-Review-Kanban", "version": "0.1.0", "description": "文档起草与评审" }
}
```

生成结果：

- checkpoint 链为 `draft_in_progress → draft_done → review_in_progress → review_done`，产物目录为 `.autobizdevops/doc-review/features/<feature>/`；
- 生成两个技能桩文件，各自带好状态接入片段；生成模板桩 `skills/doc-draft/templates/DRAFT.md`；
- 推进到 `review_done` 时，框架先检查 `DRAFT.md`、`REVIEW.md` 存在，再执行 `check_review.py`，退出码为 0 才放行。脚本尚未编写时，`check` 报 `COMMAND_SCRIPT_MISSING`；
- `inspectCommands` 中不含 `knowledge_path`、`deploy_units`、`pull_knowledge`；board_config 中没有 `knowledge_config` 和 `artifact_sync`；
- `session_context_inject` 返回流程上下文和默认策略的 `agentConfig`，不含知识段；
- 不生成 `.codex-plugin/plugin.json`。

## 8. 完整示例

[examples/lite/](../examples/lite/)：复刻 autobizdevops_lite。`workflow.json` 只有阶段、5 个产物和 4 个节点；`plugin.scaffold.json` 中写 `layout: legacy`（保证 lite 已有项目可用）、`nextAction` 覆写、节点运行策略、知识模块（含仓库同步），以及知识沉淀入口和产物同步两项看板可选能力。产物同步是样例额外启用的，lite 本身没有这个能力。
