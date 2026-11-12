# 用户输入配置规范 v1

## 1. 输入总览

### 1.1 输入分类

插件开发者的输入包括一个入口文件、一份核心流程、按模块拆分的配置文件，以及若干资源目录，都放在插件根目录下。初始化向导（`autobiz-plugin new` 或骨架引导技能，interfaces.md §1.4、§1.6）负责收集信息并生成骨架：

| 输入类别 | 位置 | 用户需要提供什么 | 哪些由初始化向导完成 | 最终生成什么 |
|---|---|---|---|---|
| 插件基础信息 | `plugin.scaffold.json` | 名称、版本、描述 | 收集信息，生成基础配置 | 插件清单 `plugin.json`、工程结构 |
| 核心流程 | `workflow.json` | 按 `biz`、`dev`、`ops` 分组的节点、编排顺序 `seq`、技能绑定、输出、终态节点 | 创建配置骨架，辅助选择已有技能 | 编译后的流程契约及状态规则 `runtime/config/flow.json` |
| 技能资源 | `skills/<skill>/` 或 `skills/<分组>/<skill>/` | 技能正文、模板、执行脚本、业务校验器；可以不提供 | 导入已有资源，或生成空白 `SKILL.md` | 开头带状态维护片段的交付技能及资源（output-spec.md §6.1） |
| 看板模块配置 | `modules/board.json` | 目标平台、展示设置、可选能力 | 生成接入脚本和平台命令映射 | 看板 adapter `runtime/adapters/*`、宿主接口 `board_core/board_config.json`、`board_core/modules.json`，看板文案 `runtime/config/board.json` |
| 运行策略 | `modules/session.json`、`agents/` | 默认与逐节点运行方式、子代理、工具开关 | 询问是否自定义 | `runtime/config/session.json` 中的 `policies`、子代理资源引用 |
| 发布单元知识 | `modules/knowledge.json` | 知识来源、清单和组装方 | 询问是否按发布单元带入知识 | `runtime/knowledge/*`、发布单元查询和知识组装配置 |
| 产物同步模块配置 | `modules/artifactSync.json` | 允许同步的阶段、要上传的产物 | 引导启用 | 同步技能 `skills/<skillName>/`、看板同步入口 `artifact_sync` |
| 自定义扩展 | `hooks/` 等 | 开发者自己的 hooks 等资源 | 创建对应目录 | 原样交付的扩展资源 |

每个配置文件都有自己的 JSON Schema：[workflow.schema.json](../booter/schemas/workflow.schema.json)、[plugin-scaffold.schema.json](../booter/schemas/plugin-scaffold.schema.json)，以及 [schemas/modules/](../booter/schemas/modules/) 下的各模块 Schema。

### 1.2 设计原则

**核心配置与编译配置分开**（D19）。开发者和 agent 共同维护的是一组尽量短的核心配置，插件运行时使用的是由它们生成的编译配置：

| | 核心配置 | 编译配置 |
|---|---|---|
| 文件 | `workflow.json`、`plugin.scaffold.json`、`modules/*.json` | `runtime/config/*.json`、`board_core/*.json` |
| 谁写 | 开发者与 agent 共同维护 | 只由 build 流水线写入（`autobiz-plugin doctor`、`new`） |
| 内容 | 只写决策；能推导或有默认值的都不写 | 填好全部默认值，展开引用，算出 checkpoint、标签、产物类型 |
| 谁读 | 脚手架 | 运行框架与 DevClaw |
| 是否随插件发布 | 否 | 是 |
| 如何保证正确 | 编辑、提交、构建、合并时自动检测（§7.1，D20） | 只能由通过检测的核心配置生成；运行框架加载时再校验不变量 |

其余原则：

- **核心流程只表达业务骨架**：`workflow.json` 只写按阶段分组的节点、编排顺序、技能绑定、输出和终态节点。输入、校验命令和流程规则（动态阶段、跳过节点）不由用户配置，编译配置中保留这些字段并取默认值（§2.5）。看板接入、知识配置、外挂技能管理和技能内部实现都不写在这里（D11），见 §2.4。
- **配置按模块拆分**：入口文件 `plugin.scaffold.json` 只放基础信息和对各模块配置文件的引用，每个模块的配置放在 `modules/` 下自己的文件里。没有引用的模块使用默认值或不启用，所以新插件的入口文件只有几行（D18）。
- **Schema 只管结构和默认值**：JSON Schema 只检查字段名、类型和必填项，并给出常量默认值，让 IDE 能补全和即时提示；引用、顺序、路径安全、命令格式等语义规则交给 `autobiz-plugin lint`（§7.2），避免 Schema 本身变得难以维护。
- **默认值只有一个来源**（D27）：常量默认值只写在 Schema 的 `default` 中。lint 和 build 读入核心配置后先按它补全缺省字段，对象只有在 Schema 写了 `default: {}` 时才会在缺省时被创建，所以 `source`、`knowledgeSedimentation` 这类按需开启的块不会被补出来；编译配置里是补全后的值，运行框架只读编译配置，不再保留自己的默认值。由其他字段推导的默认值（例如 `workflowLabel` 取 `plugin.name`）不写进 Schema 的 `default`，由 build 计算，规则写在本文档中。本文档各表“默认值”列中的字面量必须与 Schema 一致，由 `tests/check_schema_defaults.py` 检查；
- **技能细节写在技能正文**：技能的详细要求写在 `SKILL.md` 正文中，配置里不写。技能用的模板也由技能自己维护，脚手架不登记、不检查、不生成（D29）。
- **运行上下文不进配置**：项目路径、Feature、所选发布单元、会话工作区等由 DevClaw 在运行时传入（interfaces.md §3.2、§3.4），配置中不得写死（D15）。
- **JSON + Schema**：零依赖；在文件头写 `"$schema"`，IDEA/VS Code 就能补全和提示。（不用 YAML，因为 Python 标准库不能解析它。）

## 2. 核心流程 workflow.json

### 2.1 结构

```json
{
  "$schema": "./.scaffold/workflow.schema.json",
  "nodes": {
    "biz": [
      { "id": "prd", "seq": 1, "name": "需求清洗", "skill": "autobiz-prd", "outputs": ["PRD.md"] }
    ],
    "dev": [
      { "id": "plan", "seq": 2, "name": "任务计划", "skill": "autodev-plan", "outputs": ["plan.md"] }
    ]
  }
}
```

顶层只有 `nodes` 一个字段，按阶段分组。阶段固定为 `biz`、`dev`、`ops` 三个，只用于分组，没有 `seq`；节点的编排顺序由每个节点手动填写的 `seq` 决定（§2.2），不看数组顺序。用不到的阶段不写，但至少要写一个：

| 字段 | 必填 | 说明 |
|---|---|---|
| `nodes.biz` | 否 | Biz 阶段的节点（§2.2），看板分组名 `Biz` |
| `nodes.dev` | 否 | Dev 阶段的节点，看板分组名 `Dev` |
| `nodes.ops` | 否 | Ops 阶段的节点，看板分组名 `Ops` |

主干就是全部节点按 `seq` 从小到大排列的结果，流程是纯线性的。

文件格式随入口文件的 `scaffoldVersion` 一起演进，不单独标版本。

### 2.2 节点字段

每个节点对象从 `id` 开始写：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 小写字母开头，只含小写字母、数字和 `_`（`^[a-z][a-z0-9_]*$`）。阶段已经由所在分组表达，id 不加阶段前缀：写 `plan`，不写 `dev.plan`。id 直接作为 checkpoint 前缀：`plan` → `plan_in_progress`、`plan_done`，所以各分组的节点 id 合起来不能重复 |
| `seq` | 是 | 编排顺序，手动填写的正整数。全部节点按 `seq` 从小到大执行，规则见下文 |
| `name` | 是 | 节点显示名 |
| `skill` | 是 | 绑定的技能名，小写连字符，不超过 64 字符。一个技能只能绑定一个节点，因为技能的 `SKILL.md` 中写着本节点的 checkpoint（output-spec.md §6.1）。技能目录可以是 `skills/<skill>/`，也可以放在一层分组目录下 `skills/<分组>/<skill>/`（§5）。初始化向导会列出已有技能供选择；build 时找不到会在 `skills/<skill>/` 生成空白 `SKILL.md` |
| `outputs` | 否 | 本节点产出的产物，写成文件名（相对 `FEATURE_DIR` 的路径）列表，不写产物 id；可选输出写成 `{path, optional: true}`，见 §2.3。代码提交不作为产物，编码节点通常不写 `outputs`（§2.9） |
| `terminal` | 否 | 终态节点，见 §2.6 |

节点不写 `stage`，所属阶段由它所在的分组决定。`inputs`、`validate` 不能写（§2.5）。

输出默认是必需的：推进到 `_done` 时，框架会检查它们是否存在且非空（§2.3）。

**编排顺序 `seq`**：只有节点有 `seq`，阶段分组没有。

- 全部节点（各分组合起来）按 `seq` 从小到大执行，组内数组怎么排不影响顺序。数组顺序与 `seq` 不一致时文件不好读，建议保持一致；
- 不能重复（`SEQ_DUP`），可以跳号：写 `1, 2, 3` 或 `10, 20, 30` 都可以，跳号方便以后在中间插入节点；
- 要与阶段先后一致：`biz` 中所有节点的 `seq` 小于 `dev` 中的，`dev` 的小于 `ops` 的（`SEQ_STAGE_ORDER`）；
- 终态节点必须是 `seq` 最大的节点（§2.6）；
- `seq` 只决定顺序，不进入 checkpoint 名。编译配置中节点按 `seq` 排列，`order` 仍按排列后的位置算（§6），所以只改号、不改先后时，编译结果中只有 `seq` 变化；调整了先后时，已有 Feature 的推进顺序随之改变，修改后要执行 `doctor` 重新生成插件（interfaces.md §1.7）。

```json
"nodes": {
  "biz": [ { "id": "prd",   "seq": 1, "name": "需求清洗", "skill": "autobiz-prd",  "outputs": ["PRD.md"] } ],
  "dev": [ { "id": "specs", "seq": 2, "name": "规格生成", "skill": "autodev-sepc", "outputs": ["proposal.md"] },
           { "id": "plan",  "seq": 3, "name": "任务计划", "skill": "autodev-plan", "outputs": ["plan.md"] } ]
}
```

### 2.3 产物与路径

```json
"outputs": [
  "PLAN.md",
  "plan.json",
  "specs/**/*.md",
  { "path": "PR_BODY.md", "optional": true }
]
```

- `outputs` 是列表，每一项是一个产物，写它的文件名：相对 `FEATURE_DIR` 的 POSIX 路径，可以含 glob。用户不写产物 id；
- 其他配置引用产物时直接写这个路径（`artifactSync.artifacts` 的 key，§4.5）；
- 产物不需要起名：编译配置和看板数据中产物的 `label`（DevClaw 产物卡片的标题）就是这里写的路径（§6，D39）；
- 输出写成 `{path, optional: true}` 表示可选输出，完成时不检查它是否存在；
- 节点要读哪些上游产物写在技能正文中，核心配置不表达（编译配置中节点的 `inputs` 为 `[]`，§2.5）；
- 后面的节点可以再次输出同一个路径（例如在后续阶段更新它），视为同一个产物，以第一个输出它的节点为生产者；
- 框架只做最小校验：至少匹配一个普通文件，并且匹配到的每个文件去掉首尾空白后都不为空。空文件不算存在；
- 产物类型按扩展名推断：`.json` 为 `json`，其余为 `file`；
- 保留路径不可使用：`state.json`、`hooks.ndjson`、`sync-status.json`、`ARTIFACT_CATALOG.json`。

**产物 id 的推导**：编译配置（`flow.json` 的 `artifacts`、节点的 `outputs`）和看板数据仍按产物 id 引用产物，id 由 build 从路径推导：

1. 按 `/` 拆分路径，取最后一个不含 glob 字符（`*`、`?`、`[`）的段；
2. 转小写，去掉结尾的 `.md`；
3. 连续的非 `[a-z0-9]` 字符替换为一个 `_`，再去掉首尾的 `_`。

例如 `PRD.md` → `prd`，`plan.json` → `plan_json`，`UI_CONTEXT.json` → `ui_context_json`，`specs/**/*.md` → `specs`，`.design-contract.lock.json` → `design_contract_lock_json`，`evidence/EVIDENCE.jsonl` → `evidence_jsonl`。推导结果不符合 `^[a-z][a-z0-9_]*$`，或两个不同路径推导出同一个 id 时，lint 报 `ARTIFACT_ID_INVALID` / `ARTIFACT_ID_CONFLICT`，改文件名即可。

### 2.4 不在核心流程里的内容

| 内容 | 去向 |
|---|---|
| 看板提示文案 | `modules/board.json` 的 `display`（§4.1.2） |
| 产物显示名 | 不配置，编译时取路径本身（§6，D39） |
| 产物同步设置 | `modules/artifactSync.json`（§4.5） |
| 运行策略 | `modules/session.json` 的 `policies`（§4.2） |
| checkpoint 名、阶段标签、节点描述与 `nextAction`、状态流转、产物类型 | 由脚手架推导，写入编译配置（§6） |
| 节点输入、校验命令、流程规则（动态阶段、跳过节点） | 不由用户配置；编译配置 `flow.json` 保留这些字段并取默认值（§2.5） |
| 插件自有的校验与钩子配置：声明式校验器清单、编译守卫、人工确认关卡、回滚时归档的文件 | 插件自己的文件：校验器清单由读取它的脚本自己维护；人工确认关卡写在 `hooks/hooks.json`；回滚清单由回滚技能自己读取（README §6.8） |
| 外部输入、旧文件名回退、checkpoint 前缀覆写 | v1 不支持，预留到 v2（README §7） |
| 技能的详细要求 | 技能正文 |
| 技能用的模板 | 技能自己维护：放在技能目录下，由技能正文引用，脚手架不登记、不检查、不生成（D29） |

### 2.5 编译配置中保留、用户不配置的字段

`workflow.json` 不能写节点的 `inputs`、`validate`，也不能写流程规则（动态阶段、跳过节点）。编译配置 `flow.json` 保留这些字段，build 写入下表的默认值；运行框架照常执行 `inputs`、`validate`，`dynamicStages`、`skip` 出现非默认值时拒绝加载（D59）。字段留着是为了让运行框架的契约保持不变，以后需要开放配置时不用改 `flow.json` 的格式：

| `flow.json` 字段 | build 写入的值 | 含义 |
|---|---|---|
| `nodes[i].inputs` | `[]` | 推进时不检查输入 |
| `nodes[i].validate` | `null` | 节点完成时只做产物存在性检查，不执行校验命令 |
| `dynamicStages` | `[]` | 没有动态阶段（§2.7） |
| `skip` | `null` | 不允许跳过节点（§2.8） |

`validate` 不为 `null` 时，运行框架按下面的约定执行（D14）：

- 只在推进到 `<prefix>_done` 时执行，并且在框架的存在性检查通过之后才执行。推进到 `_in_progress`、重开、查询都不执行；
- 命令是单行，不经过 shell：先按 POSIX shell 规则拆分参数，再逐个参数替换占位符，不支持管道、重定向和 `&&`；
- 退出码 `0` 表示通过；非 `0` 或超时表示不通过，此时拒绝推进，`state.json` 不变，命令输出的末尾部分返回给模型；
- 格式、内容是否合格都由校验器自己判断，框架只检查非空。

可用占位符由运行框架在执行时替换（与 DevClaw 的宿主占位符无关）：

| 占位符 | 值 |
|---|---|
| `${python}` | 运行框架当前使用的 Python 解释器，三个平台通用 |
| `${pluginPath}` | 插件安装目录 |
| `${skillPath}` | 本节点的技能目录，即 `${pluginPath}/skills/<skill>` 或 `${pluginPath}/skills/<分组>/<skill>`（§5） |
| `${projectPath}` | 项目目录，即 `<pluginWorkspace>/<projectDir>` |
| `${featureDir}` | 当前 Feature 的产物目录（按目录布局推导） |
| `${feature}` | 当前 Feature |
| `${nodeId}` | 当前节点 id |

执行细节（工作目录、环境变量、超时、输出截取）见 interfaces.md §4.3、§4.4。

### 2.6 终态节点 terminal

```json
"ops": [
  …,
  { "id": "archive", "seq": 7, "name": "归档", "skill": "autoops-archive", "terminal": true }
]
```

- 只能是最后一个主干节点（`seq` 最大的节点），最多一个；
- 只有一个 checkpoint `archived`（固定名称），没有 `_in_progress`/`_done`。前一个节点完成后推进到 `archived`；
- 不能写 `outputs`，也不能被跳过或重开；到达 `archived` 后流程结束；
- 看板上只有“未开始”和“已归档”（`board.display.stateLabels.archived`）两种状态。

### 2.7 动态阶段 dynamicStages

v1 不由用户配置，`flow.json` 的 `dynamicStages` 固定为 `[]`（§2.5）。字段保留给 v2，v1 运行框架不实现，不为 `[]` 时拒绝加载（D59）。v2 中数组的每一项是插在某个主干节点之后、到达时由用户决定执行还是跳过的一组节点，选择记录在 Feature 的 `workflowDecisions` 中（output-spec.md §5.2）。为 `[]` 时没有选择点，流程按主干线性推进。

### 2.8 跳过节点 skip

v1 不由用户配置，`flow.json` 的 `skip` 固定为 `null`（§2.5），看板不提供跳过入口，`board_config.json` 不生成 `skip_node` 命令。字段保留给 v2，v1 运行框架不实现，不为 `null` 时拒绝加载（D59）。v2 中不为 `null` 时写作 `{locked: [节点 id]}`，允许跳过 `locked` 以外的非终态节点，被跳过的节点记录在 Feature 的 `workflowSkippedNodes` 中。

### 2.9 编码节点

脚手架不把代码提交作为产物，也不检查仓库状态（D37）。编码节点通常不写 `outputs`，与其他节点一样按技能 `SKILL.md` 开头的状态维护片段推进：技能开始时推进到 `_in_progress`，技能完成时推进到 `_done`（output-spec.md §6.1）。需要按提交、构建或测试判断完成时，把要求写在技能正文中，例如“代码提交、测试通过后再执行完成命令”。

## 3. 入口文件 plugin.scaffold.json

### 3.1 文件组织

```text
<plugin>/
├── plugin.scaffold.json     # 入口：基础信息、目录布局、对流程和模块配置的引用
├── workflow.json            # 核心流程（§2）
└── modules/
    ├── board.json           # 看板模块（可选；不引用时全部取默认值）
    ├── session.json         # 运行策略（省略时使用默认值）
    └── knowledge.json       # 发布单元知识（可选）
```

脚手架从入口文件出发，读取它引用的 `workflow.json` 和各模块配置文件。模块配置文件只写本模块的内容，不再引用其他文件。

### 3.2 顶层结构

```jsonc
{
  "$schema": "./.scaffold/plugin-scaffold.schema.json",
  "scaffoldVersion": 1,            // 必填，入口文件格式主版本
  "plugin":   { ... },             // 必填，插件基础信息 → 清单
  "runtime":  { ... },             // 可选，状态目录布局与校验超时
  "workflow": "./workflow.json",   // 可选，核心流程文件，默认即此值
  "modules": {                     // 可选，模块配置文件引用
    "board":     "./modules/board.json",
    "session":   "./modules/session.json",
    "knowledge": "./modules/knowledge.json",
    "artifactSync": "./modules/artifactSync.json",
    "globalHooks": "./modules/globalHooks.json"
  }
}
```

`modules` 的键：

| 键 | 不引用时 | 配置内容 |
|---|---|---|
| `board` | 全部取默认值 | 看板模块：目标平台、展示设置、可选能力（§4.1） |
| `session` | 全部取默认值 | 运行策略（§4.2） |
| `knowledge` | 不启用发布单元知识 | 清单解析、发布单元查询和知识组装（§4.3）。引用即启用 |
| `artifactSync` | 不启用产物同步 | 上传产物到外部服务、看板上的同步入口（§4.5）。引用即启用 |
| `globalHooks` | 只有产物检查钩子 | 全局钩子模块暂停开放。构建兼容已有插件的配置（§4.6） |

引用规则：

- 值是相对插件根目录的路径，以 `./` 开头、以 `.json` 结尾，不得含 `..`。建议使用 `./modules/<键>.json`；
- 引用的文件必须存在，否则报 `MODULE_FILE_MISSING`；
- 各模块文件按各自的 Schema 校验（`schemas/modules/<键>.schema.json`）；
- 关闭知识模块时去掉 `knowledge` 引用即可，文件可以保留，下次启用时再引用回来（`module disable` / `module enable` 就是这样做的）。

### 3.3 plugin

| 字段 | 必填 | 说明 | 输出位置 |
|---|---|---|---|
| `id` | 是 | 稳定 ID，只含英文字母、数字、短横线和下划线（`^[A-Za-z0-9_-]+$`），不超过 64 字符（D65），同时也是安装目录名（`package` 生成的 zip 以它为顶层目录，D57）。**发布后不可修改**，否则已有项目 state.json 中记录的 `pluginId` 对不上，会被拒绝读取 | `state.json.pluginId`、hooks.ndjson `pluginId` |
| `name` | 是 | DevClaw 沿用的插件名，可含大写（例如 `AutoBizDevOps-Plugin-Lite`） | 根 `plugin.json.name` |
| `version` | 是 | semver | 根 `plugin.json.version` |
| `description` | 是 | — | 根 `plugin.json.description` |
| `author` / `homepage` / `repository` / `license` / `keywords` | 否 | — | 根 `plugin.json` |
| `mcpServers` | 否 | 透传路径，以 `./` 开头，文件由开发者维护 | 根 `plugin.json.mcpServers` |
| `hooks` | 否 | 宿主钩子配置，固定为 `./hooks/hooks.json`，可以不写；写了其他路径报 `PLUGIN_HOOKS_PATH`。`hooks/hooks.json` 由脚手架和开发者共用：脚手架只维护自己的条目——命令指向 `hooks/artifact_guard.py` 或 `hooks/<全局钩子 id>/` 下脚本的条目，每次重新生成都排在各事件的最前面并按当前配置重写；其他条目是开发者的，按原顺序原样保留。生成的条目也是给开发者打样的写法 | 根 `plugin.json.hooks` 固定为 `./hooks/hooks.json`（D7、D61，interfaces.md §4.7） |


初始化向导会规范化用户输入的插件 ID：英文字母、数字、短横线和下划线以外的字符改为 `-`，合并连续的 `-`，去掉首尾的 `-`，保留大小写（`My Plugin` → `My-Plugin`），并提示规范化后的结果（D65）。

### 3.4 runtime

| 字段 | 默认值 | 说明 |
|---|---|---|
| `metaRoot` | `.autobizdevops` | 元数据根目录，相对项目目录，状态和产物都在它下面。可以写多级相对路径（例如 `docs/autobiz`），不能是绝对路径，不能含 `..`、`\`、`:`，不能是 `.git` 或在 `.git` 下 |
| `validateTimeoutSec` | `120` | 节点校验命令的超时秒数 |

`metaRoot` 决定 Feature 产物目录 `FEATURE_DIR`：`<项目目录>/<metaRoot>/features/<feature>/`。同一项目安装多个插件时，各插件要配置不同的 `metaRoot`（D48）。它发布后不可修改，否则已有项目的状态和产物找不到，所以留在入口文件中，不放进模块配置。迁移 lite、全栈版时保持默认值。覆写 `board.display.systemPromptInject` 时，其中写的产物目录要与它一致。

## 4. 模块配置文件

下文 `board.*`、`session.*`、`knowledge.*`、`artifactSync.*` 分别指 `modules/board.json`、`modules/session.json`、`modules/knowledge.json`、`modules/artifactSync.json` 中的字段。

### 4.1 modules/board.json（看板模块）

```jsonc
{
  "$schema": "../.scaffold/modules/board.schema.json",
  "target":  { ... },   // 目标平台
  "display": { ... }    // 展示设置
}
```

节点的看板文案（描述、`nextAction`）和看板能力（知识沉淀入口）不在这里配置：节点文案全部由 build 推导（§6），知识沉淀入口固定开启（§4.1.3）。

#### 4.1.1 target：目标平台

| 字段 | 默认值 | 说明 |
|---|---|---|
| `platforms` | `["darwin", "linux", "win32"]` | 生成哪些 `inspectCommands.<platform>` |
| `python.posix` | `python3` | darwin/linux 的解释器 |
| `python.win32` | `python` | win32 的解释器 |

宿主命令和技能状态维护片段中的命令一律加 `-X utf8`，不能关闭（D40）。

#### 4.1.2 display：展示设置

| 字段 | 默认值 |
|---|---|
| `workflowLabel` | `plugin.name` |
| `workflowDescription` | `{节点 name 以 " → " 连接}。` |
| `dialogTips` | `当前为{workflowLabel}插件：{节点 name 以 " → " 连接}。请描述目标与验收标准。` |
| `systemPromptInject` | `当前 Feature 为 ${feature}。产物目录 FEATURE_DIR=${pluginWorkspace}/${projectDir}/{metaDir}/features/${feature}。插件根目录 PLUGIN_ROOT=${pluginPath}。`，其中 `{metaDir}` 在构建时替换为 `runtime.metaRoot`（D28、D48） |
| `stateLabels` | `{"not_started":"未开始","in_progress":"进行中","done":"已完成","skipped":"已跳过","archived":"已归档"}`；`skipped` 只在 `flow.json` 的 `skip` 不为 `null` 时使用（v1 不会出现），`archived` 只在有终态节点时使用 |

文案中只能使用该命令键允许的占位符（interfaces.md §3.2），否则报 `PLACEHOLDER_UNKNOWN`。覆写 `systemPromptInject` 时如果去掉了 `FEATURE_DIR`，会报 `FEATURE_DIR_MISSING` 警告，因为技能依赖这个变量定位产物目录。


#### 4.1.3 知识沉淀入口（固定开启）

看板能力不由用户选择，全部默认开启。v1 只有知识沉淀入口一项：build 总是在 `board_core/modules.json` 顶层生成 `knowledge_config`，带出 DevClaw 提供的 `knowledge-sync` 技能。它只是看板入口，不依赖知识模块是否启用。入口内容是 DevClaw 协议常量：

| 字段 | 值 |
|---|---|
| `sync_type` | `invoke_session` |
| `nextAction.slashSkill` | `knowledge-sync` |
| `nextAction.userMessage` | `请针对${projectCode}项目发起知识沉淀，这个是 token：${leanToken}` |
| `nextAction.dialogTips` | `发起知识沉淀` |

### 4.2 modules/session.json（运行策略）

自定义节点怎么运行时填写此文件。框架自动提供会话入口，发布单元知识在 `modules/knowledge.json` 中配置。

```json
{
  "$schema": "../.scaffold/modules/session.schema.json",
  "policies": {
    "default": { "agentMode": "multi" },
    "nodes": {
      "dev": [
        { "id": "plan", "agentMode": "multi",
          "subagentConfig": { "disabledBuiltinSubagents": ["Explore"], "customSubagentFiles": ["agents/explore.md"] } }
      ]
    }
  }
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `policies.default` | `{"agentMode":"multi"}` | 全局默认运行策略 |
| `policies.nodes.biz` / `.dev` / `.ops` | — | 节点运行策略，与 `workflow.json` 一样按阶段分组，组内每项从 `id` 开始，`id` 必须是 `workflow.json` 同一分组中的节点；只写需要单独配置的节点。原样写入 `runtime/config/session.json`，看板数据中对应节点的 `runtimePolicy` 即该项去掉 `id` 后的内容 |

运行策略字段：

| 字段 | 取值 |
|---|---|
| `agentMode` | `solo` / `multi` / `agent_team` / `workflow` |
| `subagentConfig.disabledBuiltinSubagents` | 禁用的内置子代理名，例如 `["Explore","critic"]` |
| `subagentConfig.customSubagentFiles` | 外挂资源：插件内相对路径 `agents/*.md`。`agents/` 目录是可选的，文件可以稍后再补：lint 报 `SUBAGENT_FILE_MISSING`（warning），会话入口下发 `agentConfig` 时跳过不存在的文件 |
| `toolCustomConfig` | 宿主工具的定制开关，例如 `{"task": {"enabled": true}}`。脚手架不解释其内容，原样写入 `runtimePolicy` 和 `agentConfig` |

### 4.3 modules/knowledge.json（发布单元知识）

入口文件引用了这个文件即表示启用知识模块。

```json
{
  "$schema": "../.scaffold/modules/knowledge.schema.json",
  "manifest": { "format": "agents-manifest-v1", "path": "agents.manifest.json" },
  "assembly": { "enabled": true, "assembler": "plugin" },
  "source": { "type": "git", "url": "https://…/Knowledge.git", "sshUrl": "git@…:…/Knowledge.git", "ref": "master" }
}
```

知识目录固定为插件根目录下的 `sys/`，不由用户配置（D53）。由 DevClaw 自己维护知识时，目录由 DevClaw 通过会话入口的 `--knowledge-path-platform` 传入（interfaces.md §3.3.7）。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `manifest.format` | `agents-manifest-v1` | 清单解析方式。v1 只支持 lite 的 `agents.manifest.json` 格式 |
| `manifest.path` | `agents.manifest.json` | 清单文件，相对知识目录 |
| `assembly.enabled` | `true` | 是否组装知识上下文 |
| `assembly.assembler` | `plugin` | 组装方。`plugin`：由插件执行组装脚本 `runtime/knowledge/render_collected_session_context.py`（§4.4），结果并入 `sessionContext`；`devclaw`：由 DevClaw 组装，插件只通过 `inspect_deploy_units.py` 提供清单解析结果，`sessionContext` 中不含知识段 |
| `assembly.timeoutSec` | `30` | 组装脚本的超时秒数。超时、退出码非 0 或输出不是合法 JSON 时，本次会话不含知识段，并在 `message` 中说明 |
| `source` | 不声明 | 可选：由插件自己拉取知识仓库。声明后生成 `runtime/knowledge/sync_knowledge.py` 和 `pull_knowledge` 命令（README §9）。`doctor` 写盘后，`sys/` 中还没有清单时执行一次 `sync_knowledge.py`，供 check、simulate 的契约测试读取清单；失败报 `KNOWLEDGE_PULL` warning。`sys/` 不随包带上 |
| `source.type` | `git` | v1 只支持 git |
| `source.url` | 声明 `source` 时必填 | 知识仓库 HTTPS 地址 |
| `source.sshUrl` | `""` | HTTPS 克隆失败时回退的 SSH 地址 |
| `source.ref` | `master` | 分支、标签或 commit |

文件内容可以只有 `$schema`：此时清单解析、组装方都取默认值，用内置组装脚本组装知识，也不拉取知识仓库。

### 4.4 内置组装脚本

`assembler = plugin` 时，知识由 `runtime/knowledge/render_collected_session_context.py` 组装，它和 `collect-knowledge.js` 都来自全栈版，lite 和全栈版都直接使用：

- 调用 `collect-knowledge.js`（collector，需要 Node）按所选发布单元组装知识；collector 不可用或单元不在它的列表中时，按清单映射加载，最后回退 `<localRepoPath>/AGENTS.md`；
- 无论选没选发布单元，都读取会话工作区的 `<sessionWorkspacePath>/AGENTS.md` 作为会话工作区指令；
- 未取得任何非空单元内容时，读取项目元数据目录中的 `CONTEXT.md` 作为领域词汇表，默认路径为项目下的 `.autobizdevops/CONTEXT.md`。

所以知识仓库里没有 collector 知识的插件，也能直接用它从各仓库和工作区的 `AGENTS.md` 取到上下文。

没有配置项可以换掉它。插件需要不同的组装方式时，直接替换这个文件：新文件放在同一路径，按 interfaces.md §4.5 的协议从 stdin 读请求、向 stdout 输出知识段即可。doctor 发现它与构建记录不一致时，当作插件的替换保留，不报 `DRIFT_MANAGED`；脚手架更新后替换运行框架时也保留它（README §4）。

### 4.5 modules/artifactSync.json（产物同步模块）

把产物上传到外部服务，并在看板上生成同步入口。入口文件的 `modules.artifactSync` 引用了这个文件即表示启用，不引用即不启用，文件中没有 `enabled`（D30）。

```json
{
  "$schema": "../.scaffold/modules/artifactSync.schema.json",
  "allowedFrom": "plan:done",
  "excludeCheckpoints": ["code_in_progress"],
  "artifacts": {
    "PRD.md": "正式产品需求文档。",
    "PLAN.md": "开发执行计划。"
  },
  "extraPaths": { "prd_original/**/*": "原始需求文档或参考材料。" }
}
```

同步会把文件上传到外部服务，所以要上传的产物用 `artifacts` 显式列出：没列出的产物不上传，节点新增输出也不会自动加入同步。key 直接写 `workflow.json` 中 `outputs` 的路径，归属节点从 `outputs` 推导。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `skillName` | `autobizdevops-artifact-sync` | 生成的技能目录名和技能名 |
| `entry.enabled` | `true` | 是否在看板上生成产物同步入口（`board_core/modules.json` 顶层 `artifact_sync`，`slashSkill` 为 `skillName`） |
| `entry.syncType` / `entry.userMessage` / `entry.dialogTips` | `invoke_session` / `请针对${projectCode}项目的${feature}特性发起产物同步` / `发起产物同步` | 入口文案 |
| `allowedFrom` | 与 `allowedCheckpoints` 二选一 | `<nodeId>:<in_progress\|done>` 或 checkpoint 名；从这里到流程末尾都允许同步。只沿主干 checkpoint 链推导（含 `archived`），动态阶段节点的 checkpoint 不在其中，需要时写进 `allowedCheckpoints` |
| `excludeCheckpoints` | `[]` | 从 `allowedFrom` 推导出的列表中再剔除的 checkpoint |
| `allowedCheckpoints` | — | 显式列表 |
| `artifacts` | — | 必填。要上传的产物：产物路径 → 同步目录中的简述。路径必须出现在某个节点的 `outputs` 中 |
| `uploadUrl` | `https://tscode-cos-plugin.paasuat.cmbchina.cn/file/upload` | 上传服务地址，默认值取自全栈版 `sync_artifacts.py` |
| `maxFileSizeMiB` | `5` | 超过上限的文件跳过并报告 |
| `extraPaths` | `{}` | 不属于任何节点输出、但需要同步的路径：`{路径模式: 简述}`，路径相对 `FEATURE_DIR`，不记录阶段和节点。同步技能生成的 `FEATURE_API_DETAIL.md` 总会同步：没有作为节点输出列进 `artifacts`、这里也没写时，生成的同步配置自动追加（D66）；要改它的简述就写在这里 |

### 4.6 modules/globalHooks.json（插件全局钩子模块）

全局钩子模块暂停开放。本节说明已有插件中 `modules.globalHooks` 引用的配置文件。

```json
{
  "$schema": "../.scaffold/modules/globalHooks.schema.json",
  "hooks": ["secrets-check", "performance-check"]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `hooks` | 是 | 要启用的钩子 id，按顺序写进 `hooks/hooks.json`。包括 `secrets-check`（明文密码检查）和 `performance-check`（前端性能检查），说明见 interfaces.md §4.8 |

- 生成：每个钩子的脚本拷到插件根目录的 `hooks/<id>/`（module），条目写进 `hooks/hooks.json`：产物检查钩子在最前，其次是这里列出的钩子，开发者在同一文件中自己写的条目在最后（interfaces.md §4.7）；
- 产物检查钩子由框架始终注册，不需要、也不能在这里列出；
- id 不存在报 `GLOBAL_HOOK_UNKNOWN`，重复报 `GLOBAL_HOOK_DUP`；
- 从 `hooks` 中去掉某个钩子，或关闭模块（去掉入口文件的引用）后，以前生成的脚本在 build-manifest 中标为 `inactive`，不再打包；

## 5. 资源目录

| 目录 | 内容 | 初始化向导 | 交付方式 |
|---|---|---|---|
| `skills/<skill>/` 或 `skills/<分组>/<skill>/` | `SKILL.md` 正文、`scripts/` 执行脚本与业务校验器、`references/`，以及技能自己维护的模板等资源 | 导入已有技能目录；开发者没有提供时不创建，由 build 生成空白 `SKILL.md` | `SKILL.md` 开头由 build 写入状态维护片段，其余原样交付（output-spec.md §6.1） |
| `skills/` 下的共享资源 | 技能集合根目录和分组目录自己的 `SKILL.md`、`references/`、`hooks/` 等，供多个技能引用 | 不创建；`add skills` 导入技能集合时按原路径拷入 | 原样交付 |
| `agents/`（可选） | 自定义子代理等外挂资源，由会话策略引用 | 不创建，需要时由开发者创建，或用 `add skills --agents`、`new --answers` 的 `agents` 拷入 | 存在时原样交付 |
| `hooks/` | 宿主钩子与开发者自定义扩展，例如节点校验脚本及其配置 | 创建目录，生成 `hooks.json`、`artifact_guard.py` | `hooks.json` 中脚手架维护的条目、`artifact_guard.py` 和全局钩子脚本由 build 维护，其余原样交付（D61、D62） |

技能目录的查找规则：build 按节点的 `skill` 在 `skills/<skill>/` 和 `skills/*/<skill>/` 两处查找含 `SKILL.md` 的目录，只找这两层。两处都有、或在多个分组下都有时报 `SKILL_AMBIGUOUS`。

节点技能按节点所属阶段放进分组目录（D64）：biz 节点的技能在 `skills/autobiz/<skill>/`，dev 在 `skills/autodev/<skill>/`，ops 在 `skills/autoops/<skill>/`，与技能名无关。都没找到时在这个分组目录生成空白 `SKILL.md`；找到的目录不在这里时（平铺在 `skills/<skill>/`、在别的分组下，或节点换了阶段），lint 报 `SKILL_LAYOUT` warning，doctor 先把整个技能目录挪过去，并把 `skills/` 下开发者文件中对旧目录的引用（例如 `${pluginPath}/skills/<skill>/references/…`）改成新目录，再生成；目标目录已经存在时报 `SKILL_LAYOUT_CONFLICT`，什么都不写。挪动结果在 doctor 的 `changes.skills.moved` 中列出。不绑定节点的辅助技能和模块生成的技能（例如产物同步的 `autobizdevops-artifact-sync`）不分组，按原位置交付。

找到的目录就是该节点的技能目录，`${skillPath}` 指向它。找到的目录就是该节点的技能目录，`${skillPath}` 指向它。分组目录自己的 `SKILL.md`（例如 `skills/autodev/SKILL.md`）和分组下不被节点绑定的技能（例如回滚、评审等辅助技能）都按开发者资源原样交付，不写状态维护片段。

开发者创建插件时可以带上自己的 `SKILL.md`，也可以不带：

| 情况 | build 怎么做 |
|---|---|
| 提供了 `SKILL.md` | 在 frontmatter 之后插入状态维护片段，正文不动；已有片段时只更新片段内容 |
| 没有提供 | 生成空白 `SKILL.md`：只有 frontmatter（`name` 为技能名，`description` 为 `[TODO: …]` 占位）和状态维护片段，正文由开发者自己填写 |

片段的内容、位置和更新规则见 output-spec.md §6.1。

技能私有的脚本和校验器不需要、也不应该导入 `runtime/` 下的任何模块。它们需要的路径来自会话上下文（`FEATURE_DIR`）或校验命令占位符（§2.5）。

## 6. 编译规则（核心配置 → 编译配置）

build 把核心配置编译成两类文件（output-spec.md §3、§5），都来自同一份中间表示：

| 文件 | 谁读 | 内容 |
|---|---|---|
| `board_core/board_config.json` | DevClaw | `apiVersion`、`inspectCommands` |
| `board_core/modules.json` | DevClaw | 已开启的模块、`boardEvents`、看板入口 |
| `runtime/config/flow.json` | 运行框架 | 流程、checkpoint、产物、阶段标签 |
| `runtime/config/board.json` | adapter | 看板文案：模板、状态名、按 biz/dev/ops 分组的节点描述与 `nextAction` |
| `runtime/config/session.json`、`knowledge.json`、`runtime.json` | 运行框架、模块脚本 | output-spec.md §5 |

看板上的流程数据（节点、状态、`nextAction`、产物定义、checkpoint 流转）不写进 `board_core/`，由 adapter 读取 `flow.json`、`board.json`、`session.json` 后在 `project_status`、`feature_status`、`dynamic_workflow` 中输出（interfaces.md §3.3.3、§3.3.5）。

设全部主干节点按 `seq` 从小到大排列为 `N[0..k]`，`P[i]` 为 `N[i].id`；“下一节点”指流程上紧随其后的节点（动态阶段默认执行时为阶段第一个节点，阶段最后一个节点的下一节点是 `insertAfter` 之后的主干节点）；未引用的模块按默认值计算。

**board_core/**：

| 输出字段 | 规则 |
|---|---|
| `apiVersion` | `1`，两个文件相同 |
| `inspectCommands.<platform>` | 见 output-spec.md §3.2 的命令模板，平台与解释器取自 `board.target` |
| `inspectCommands.*.knowledge_path` / `deploy_units` | 仅在引用了知识模块时生成；未引用时直接不生成（D1） |
| `inspectCommands.*.pull_knowledge` | 仅在知识模块声明 `source` 时生成 |
| `inspectCommands.*.skip_node` | 仅在 `flow.json` 的 `skip` 不为 `null` 时生成，v1 不生成 |
| `modules.<id>` | 四个模块都列出：引用了的为 `{enabled: true, version, …}`，未引用的为 `{enabled: false}`（`board`、`session` 始终开启） |
| `boardEvents` | 固定 `{protocol: "autobiz.board-events.v1"}` |
| `knowledge_config` | 总是生成，内容固定（§4.1.3，output-spec.md §7.3） |
| `artifact_sync` | 仅在引用了产物同步模块且 `artifactSync.entry.enabled` 时生成（output-spec.md §7.2） |

**flow.json**（字段形态见 output-spec.md §5.2）：

| 输出字段 | 规则 |
|---|---|
| `nodes[i]` | 全部节点按 `seq` 从小到大排列后的第 i 个节点 |
| `stages` | 写了的分组，按 biz → dev → ops 排列，取 `Biz`、`Dev`、`Ops` |
| `nodes[i].stage` | 节点所在分组：`biz` → `Biz`、`dev` → `Dev`、`ops` → `Ops` |
| `nodes[i].seq` | 原样取自 `workflow.json` |
| `nodes[i].inputs` | `[]`（§2.5） |
| `nodes[i].validate` | `null`（§2.5） |
| `nodes[i].order` | `(i + 1) * 10`，即按 `seq` 排列后的位置，与 `seq` 是否跳号无关 |
| `nodes[i].checkpoints` | `[P[i]_in_progress, P[i]_done]`；终态节点为 `["archived"]` |
| `artifacts.<id>` | id 按 §2.3 从路径推导；第一个输出它的节点为 `producer`；`label` 为路径本身（用户不配置产物名称，D39）；`paths` 为 `[路径]`；`type` 按扩展名推断 |
| `nodes[i].outputs` | 按 `outputs` 顺序列出 `{id: 推导出的产物 id, required}`，可选输出 `required` 为 `false` |
| `checkpoints.chain` | 主干按 `P[0]_in_progress → P[0]_done → P[1]_in_progress → …` 线性排列；最后一个主干节点是终态节点时以 `archived` 结尾 |
| `checkpoints.labels` | 全部 checkpoint（含 `archived`）的标签，不由用户配置：`_in_progress` 为 `{name}进行中`，`_done` 为 `{name}完成`，`archived` 为终态节点的 id（D49）。DevClaw 不读这些标签，插件内部用于 Feature 记录的 `stage` 字段和回滚时按名称匹配节点 |
| `dynamicStages` | `[]`（§2.7） |
| `skip` | `null`（§2.8） |

**board.json**（字段形态见 output-spec.md §5.3）：

| 输出字段 | 规则 |
|---|---|
| `template` | `{id: "standard", label: workflowLabel, description: workflowDescription}` |
| `stateLabels` | `board.display.stateLabels`；`skipped` 仅在 `skip` 不为 `null` 时输出（v1 不输出），`archived` 仅在有终态节点时输出 |
| `nodes` | 按 `workflow.json` 的分组输出 `{biz: [...], dev: [...], ops: [...]}`，组内按 `seq` 排列，每项从 `id` 开始：`{id, description, nextAction}` |
| `nodes.<组>[i].description` | 节点技能 `SKILL.md` frontmatter 中的 `description`；技能不存在（build 生成空白 `SKILL.md`）或仍是 `[TODO: …]` 占位文字时，为 `{name}；产物：{输出路径以 "、" 连接}`，没有输出时为 `{name}` |
| `nodes.<组>[i].nextAction.not_started/in_progress` | `slashSkill = skill`；`userMessage = "请使用 /{skill} 处理当前 Feature，先读取现有状态和产物。"`；`dialogTips = "当前阶段：{name}。"`。终态节点只有 `not_started` |
| `nodes.<组>[i].nextAction.done` | 有下一节点时：`slashSkill` 为下一节点的技能；`userMessage` 同上，但用下一节点的技能；`dialogTips = "下一阶段：{下一节点 name}。"`。没有下一节点时：`{slashSkill:"", userMessage:"", dialogTips:"{name}已完成。"}` |
| 终态节点的 `nextAction.archived` | `{slashSkill: skill, userMessage: "请使用 /{skill} 查看当前 Feature 的归档状态。", dialogTips: "{name}已完成。"}` |
| `dynamicStages` | `{}` |

adapter 输出看板数据时的拼装：`WorkflowNode` 的 `label`、`group`、`order`、`skill`、`checkpoints` 取自 `flow.json`，`description`、`states[].nextAction` 取自 `board.json`，`states[].label` 取 `board.json` 的 `stateLabels`，`runtimePolicy` 取 `session.policies.nodes` 分组中 `id` 相同的那一项、去掉 `id`（未配置时不输出），`artifacts` 由 `flow.json` 的节点输入输出和产物表展开成 `ArtifactDef`（interfaces.md §3.3.3）；`dynamic_workflow` 的 `checkpoints.transitions` 由 `chain` 逐项连接得到，`stageLabels` 即 `checkpoints.labels`。

**技能 SKILL.md 的状态维护片段**（格式与更新规则见 output-spec.md §6.1）：

| 输出 | 规则 |
|---|---|
| 节点 `N[i]` 所绑定技能的片段 | 开始命令 `--checkpoint P[i]_in_progress`，完成命令 `--checkpoint P[i]_done`；终态节点只有完成命令 `--checkpoint archived` |
| 命令中的解释器 | 固定为 `python -X utf8`（D40） |
| 不再绑定任何节点的技能 | 删掉 build-manifest 记录的上次写入的片段，正文不动 |

## 7. 自动检测

### 7.1 检测时机

核心配置由人和 agent 一起修改，下面这些环节会检测（D20、D41）。脚手架生成的插件是成品，不假设插件仓库用 git 管理，所以没有提交前钩子和 CI 这类自动检测，`lint`、`check` 由开发者手动执行：

| 时机 | 怎么触发 | 检查什么 | 发现问题时 |
|---|---|---|---|
| 编辑时 | IDE 读取文件头的 `$schema` | 字段名、类型、必填项 | 编辑器里即时标红 |
| agent 修改后 | 骨架引导技能每次改完配置都运行 `autobiz-plugin lint`（interfaces.md §1.6） | §7.2 全部规则 | agent 按 Issue 修正后再继续 |
| 重新生成时 | `autobiz-plugin doctor`（以及它调用的 `build`）先执行同样的检查 | §7.2 全部规则（`BUILD_STALE`、`SCAFFOLD_VERSION_CHANGED` 除外，过期和可升级正是要重新生成的原因） | 不写任何编译配置和技能文件 |
| 手动 | 开发者执行 `autobiz-plugin lint` 或 `autobiz-plugin check` | `lint`：§7.2 全部规则，包括编译配置是否过期；`check`：再加 §7.3 全部规则和契约测试 | 按 Issue 修正 |
| 运行时 | 运行框架加载 `flow.json` | 编译配置自身的不变量（output-spec.md §5.2） | 拒绝执行并报错 |

`lint` 只读、不联网，只看配置文件和它们引用的文件是否存在，通常在 1 秒内完成，适合在 agent 的每轮修改之后和开发者改完配置时执行。`check` 在 `lint` 的基础上再检查技能内容、生成文件漂移并跑契约测试。

编译配置是否过期：build 把每份核心配置的摘要，以及每个节点技能 SKILL.md 中 `description` 的摘要（节点描述由它编译进 `board.json`，D49）写进 `runtime/build-manifest.json`，并在 `flow.json` 中记录 `workflow.json` 的摘要。`lint` 发现当前文件与记录不一致时报 `BUILD_STALE`，提示执行 `autobiz-plugin doctor`，避免核心配置改了，编译配置和技能状态片段还是旧的。

**修改核心配置后重新生成插件**：开发者或 agent 改了 `workflow.json`、`modules/*.json` 或入口文件之后，执行 `autobiz-plugin doctor`。它先 lint，再与上次构建比较、列出影响，然后重新生成编译配置，并同步各技能 `SKILL.md` 中的状态维护片段（interfaces.md §1.7）。`build` 仍是底层流水线，供 `new` 和 doctor 调用。

### 7.2 配置规则（lint，build 前同样执行）

问题分两段汇总输出（格式见 interfaces.md §1.3）：先检查核心规则，没有 error 时再检查各模块的配置（D47）。由 Issue 的 `file` 字段标明出在哪个文件。`error` 会阻止 build；`warning` 只提示，加 `--strict` 后视为 error。`--strict` 只供手动使用，`package` 不使用它（D47）。

| code | 级别 | 规则 |
|---|---|---|
| `INPUT_SCHEMA` | error | 入口文件、`workflow.json` 或某个模块配置文件不是合法 JSON（包括出现重复的键，D46），或不符合各自的 JSON Schema |
| `MODULE_FILE_MISSING` | error | `modules` 引用的文件不存在 |
| `NODE_DUP` | error | 节点 id 重复（各分组的节点一起算），推导出的 checkpoint 会重复（终态节点只有 `archived`，不参与 checkpoint 比较） |
| `SEQ_DUP` | error | 两个节点的 `seq` 相同（各分组的节点一起算），无法确定先后（§2.2） |
| `SEQ_STAGE_ORDER` | error | `seq` 与阶段先后不一致：某个 `dev` 节点的 `seq` 小于某个 `biz` 节点的，或某个 `ops` 节点的 `seq` 小于某个 `biz`、`dev` 节点的（§2.2） |
| `TERMINAL_INVALID` | error | 终态节点不是 `seq` 最大的节点、出现多个，或写了 `outputs` |
| `SKILL_SHARED` | error | 多个节点绑定同一个技能：一份 `SKILL.md` 只能写一个节点的状态维护片段（§2.2） |
| `ARTIFACT_ID_INVALID` | error | 从输出路径推导出的产物 id 不符合 `^[a-z][a-z0-9_]*$`（§2.3） |
| `ARTIFACT_ID_CONFLICT` | error | 两个不同的输出路径推导出同一个产物 id（§2.3） |
| `OUTPUT_REDECLARED` | warning | 同一路径被多个节点输出（允许，用于后续阶段更新产物；以第一个节点为生产者） |
| `PATH_UNSAFE` | error | 产物路径（数组中的每一项）为绝对路径，含 `..`、`\`、`:`，或与保留文件名冲突。知识目录的同类检查由 Schema 完成（D47） |
| `SKILL_MISSING` | warning（lint）/ error（check） | `skills/<skill>/SKILL.md` 和 `skills/*/<skill>/SKILL.md` 都不存在；build 会在节点阶段对应的分组目录 `skills/autobiz\|autodev\|autoops/<skill>/` 生成空白 `SKILL.md`（D64） |
| `SKILL_LAYOUT` | warning | 节点技能不在节点阶段对应的分组目录（§5）；doctor 会挪过去并改掉 `skills/` 下对旧目录的引用（D64） |
| `SKILL_LAYOUT_CONFLICT` | error | 要把技能挪进分组目录，但目标目录已经存在；doctor 不写任何文件（D64） |
| `SKILL_AMBIGUOUS` | error | 同名技能目录出现在多处（§5），无法确定节点的技能目录 |
| `SUBAGENT_FILE_MISSING` | warning | `customSubagentFiles` 指向的文件不存在；会话入口下发 `agentConfig` 时跳过该文件 |
| `POLICY_NODE_UNKNOWN` | error | `session.policies.nodes` 某一项的 `id` 不是 workflow 中的节点、不在 workflow 的同一分组中，或同一节点出现多次 |
| `ARTIFACT_REF_UNKNOWN` | error | `artifactSync.artifacts` 的 key 不是任何节点 `outputs` 中的路径 |
| `PLACEHOLDER_UNKNOWN` | error | 看板文案中使用了该命令键不允许的占位符 |
| `FEATURE_DIR_MISSING` | warning | 覆写后的 `systemPromptInject` 不含 `FEATURE_DIR` |
| `MODULE_OPTION` | error | 模块或可选能力的参数非法，例如 `allowedFrom` 指向不存在的节点 |
| `MODULE_SKILL_CONFLICT` | error | 模块技能名与某个节点的技能名冲突 |
| `MODULE_INACTIVE_FILES` | warning | 有模块已关闭，它以前生成的文件还在插件目录中（build-manifest 中标为 `inactive`）。这些文件不再生效、不会打包，可以删除（D52） |
| `PLUGIN_ID_CHANGED` | error | `plugin.id` 与 `runtime/build-manifest.json` 中记录的不一致。确认要改时执行 `doctor --allow-id-change`（D47） |
| `LAYOUT_CHANGED` | error | `runtime.metaRoot` 与 build-manifest 中记录的不一致：已有项目的状态会找不到。确认要改时执行 `doctor --allow-layout-change`（D47） |
| `GLOBAL_HOOK_UNKNOWN` | error | `modules/globalHooks.json` 的 `hooks` 中的 id 不是脚手架自带的全局钩子（D62） |
| `GLOBAL_HOOK_DUP` | error | `modules/globalHooks.json` 的 `hooks` 中同一个 id 出现了多次 |
| `PLUGIN_HOOKS_INVALID` | error | `hooks/hooks.json` 的结构不对：要求“事件名 → 条目对象数组”，可以包在 `{"hooks": {…}}` 下（D61） |
| `PLUGIN_HOOKS_PATH` | error | 入口文件的 `plugin.hooks` 不是 `./hooks/hooks.json`：钩子配置固定在这个文件（D61） |
| `PLUGIN_REF_MISSING` | error | `plugin.mcpServers` 引用的文件不存在；`package` 按实际路径打包这个文件（D57） |
| `SCAFFOLD_OUTDATED` | error | 当前脚手架、运行框架或某个模块的版本低于 build-manifest 中的记录，或入口文件的 `scaffoldVersion` 比脚手架支持的高：继续生成会把插件降级，doctor 拒绝执行，应先更新脚手架（D57） |
| `CORE_MAJOR_CHANGED` | error | 当前运行框架的主版本与 build-manifest 记录的 `coreVersion` 不同。确认要跨主版本升级时执行 `doctor --allow-major-upgrade`（D57） |
| `SCAFFOLD_VERSION_CHANGED` | warning | 当前脚手架、运行框架或某个模块的版本高于 build-manifest 中的记录（主版本不变）。执行 doctor 即可替换 managed、module 文件（D57） |
| `BUILD_STALE` | error（lint、check）/ warning（simulate） | 核心配置或节点技能 `description` 的摘要与 build-manifest 中记录的不一致：改了但没有重新生成（从未 build 过时不报，D49）。执行 `autobiz-plugin doctor` 即可消除。simulate 只报 warning，照常运行上次生成的插件（D55） |

### 7.3 资源与构建规则（check）

| code | 级别 | 规则 |
|---|---|---|
| `SKILL_NAME_MISMATCH` | error | SKILL.md frontmatter 中的 `name` 与 `skill` 不一致 |
| `SKILL_FRONTMATTER` | error | frontmatter 不符合 Codex 规则：只允许 `name`、`description`、`license`、`allowed-tools`、`metadata` 五个键；`description` 必填、不超过 1024 字符、不含 `<` `>`。版本号等自定义信息放进 `metadata`（例如 `metadata.version`）。DevClaw 不依赖顶层 `version`（D8），导入技能（`add skill --from`）时会自动迁移。写法只支持单行 `键: 值` 和 `metadata:` 下一层缩进的 `键: 值`（D45） |
| `SKILL_TOO_LONG` | warning | SKILL.md 超过 500 行，应把细节拆到 `references/` |
| `SKILL_STATE_BLOCK` | error | 节点技能的 `SKILL.md` 缺少状态维护片段，片段内容与推导结果不一致（例如被手改，或改了节点却没有重新生成），或不再绑定节点的技能还留着片段。执行 `doctor` 即可修复（output-spec.md §6.1） |
| `LEGACY_ENTRY_REF` | error | 技能正文（跳过 frontmatter 和状态维护片段）逐行检查，命中一行报一条，`message` 写明行号和所在小节（D51）：节点技能中出现 `update_state.py`、`update_checkpoint.py`、`route_checkpoint.py`（节点状态只由状态维护片段维护）；所有技能中出现旧入口路径 `hooks/update_state.py`、`hooks/update_checkpoint.py`、`hooks/route_checkpoint.py`、`hooks/skip_node.py`、`hooks/init_workspace.py`、`${pluginPath}/inspect_state.py`（新目录结构中已不存在）。提示：删掉这一行；整节只剩状态命令时连同小节标题一起删；这一行前面有校验等步骤时，改写成“执行完成命令之前先……”。`add skill --from` 导入时同样检查，但只报 warning、照样导入（D56）。旧版的 `scaffold:begin state` 片段由 build 直接替换成新片段，不报 |
| `SKILL_REF_DANGLING` | warning | 悬空引用（D71）：`skills/` 下全部 `SKILL.md`（集合根目录、分组、技能，以及技能目录里更深层的子技能；模块生成的技能除外）正文逐行检查，跳过 frontmatter 和状态维护片段，引用的文件或目录在插件中不存在时，每个引用报一条，`message` 写明行号、所在小节和找过的路径。检查两类路径：`${pluginPath}/…`（相对插件根目录，不限目录）；以 `templates/`、`references/`、`scripts/`、`hooks/`、`agents/`、`assets/` 开头的相对路径（可带 `./`、`../`），不带 `../` 时依次在技能目录、分组目录、`skills/`、插件根目录下找，任何一处有就算存在，带 `../` 时只按技能目录解析；以 `skills/` 开头的相对路径按插件根目录解析。不检查 URL、含占位符或通配符的路径（`<feature>`、`${var}`、`*`、`...`）、单独一个目录名（`scripts/`），以及 `LEGACY_ENTRY_REF` 负责的旧入口路径。`doctor`（含 `add skill(s)`）、`check`、`package` 都报，doctor 把这次将要生成的文件也算作存在。只报 warning：正文也可能写到用户工程里的同名目录 |
| `SKILL_REF_ABSOLUTE` | warning | 写死的绝对路径（D71）：与 `SKILL_REF_DANGLING` 检查同一批 `SKILL.md`。正文中的 `/…`、`~/…`、`C:/…`、`C:\…`，路径里含 `skills` 或资源目录（`templates`、`references`、`scripts`、`hooks`、`agents`、`assets`）一段时报出：这是某台机器上的插件或技能位置，换个环境就找不到。提示改成 `${pluginPath}/…` 或相对技能目录的路径；插件的 `skills/`、`hooks/`、`agents/` 下有末两段相同的文件时，在提示中列出（最多 3 个）。不含这些目录的绝对路径（接口路由、斜杠命令等）、URL、含占位符的路径不报 |
| `TODO_FIELD` | error / warning | 核心配置中还有没填写的 `[TODO: …]` 占位（`new --skeleton` 的骨架、手写的占位），每个占位报一条，`pointer` 指出位置，对象的键也检查。默认是 error，doctor 不生成；`artifactSync` 的 `artifacts`、`extraPaths` 中的简述是 warning，打包前由 `TODO_PLACEHOLDER` 拦下。占位所在位置不再另报 `INPUT_SCHEMA`（D63） |
| `TODO_PLACEHOLDER` | warning（check）/ error（package） | 空白 `SKILL.md`、骨架文件或清单中还有未填写的 `[TODO: …]`，包括 `module enable artifactSync` 预填在 `modules/artifactSync.json` 的 `artifacts` 中的简述（D56），以及开发者改过的文字字段（D70）：它们不再跟随技能的 `description` 更新，占位要开发者自己填 |
| `DRIFT_GENERATED` / `DRIFT_MANAGED` | error | 生成或托管的文件被手改过（内置知识组装脚本除外，插件可以替换它，§4.4）。按磁盘内容与 build-manifest 的记录是否一致判断：与记录一致、只是与当前脚手架重放的结果不同时，报 `SCAFFOLD_VERSION_CHANGED`（§7.2），不算漂移（D57）。`plugin.json`、`board_core/board_config.json`、`runtime/config/board.json` 中列出的文字字段可以改，改动超出这些字段时才报（按 `structure` 记录判断）；doctor 把这类改动按核心配置重写，报同一个 code 的 warning（D70） |
| `CUSTOMIZED_INVALID` | error | `plugin.json`、`board_core/board_config.json`、`runtime/config/board.json` 被改成了非法的 JSON 或顶层不是对象，doctor 无法合并其中改过的文字。修好它，或删掉文件由 doctor 重新生成（D70） |
| `CUSTOMIZED_STALE` | warning | 开发者改过的文字字段，这次生成的值也变了（例如默认 `dialog_tips` 含节点链，改了节点名），doctor 保留开发者的值，`message` 列出这些字段，只在发生变化的那次报。要改用生成的文字，删掉文件再执行 doctor（该文件的手改全部恢复为生成内容，D70） |
| `CONTRACT_TEST` | error | 在临时目录中模拟宿主调用失败，每个失败的步骤报一条；`simulate` 报同一个 code（interfaces.md §1.5）。lint 或漂移检查有 error 时不跑契约测试（D55） |

## 8. 最小示例

两个节点，使用默认看板和运行策略。输入见 [examples/minimal/input/](../booter/examples/minimal/input/)。

`workflow.json`：

```json
{
  "$schema": "./.scaffold/workflow.schema.json",
  "nodes": {
    "biz": [
      { "id": "draft", "seq": 1, "name": "起草", "skill": "doc-draft", "outputs": ["DRAFT.md"] },
      { "id": "review", "seq": 2, "name": "评审", "skill": "doc-review", "outputs": ["REVIEW.md"] }
    ]
  }
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

编译结果：

- checkpoint 链为 `draft_in_progress → draft_done → review_in_progress → review_done`，产物目录为项目下的 `.autobizdevops/features/<feature>/`。两个节点都在 `Biz` 分组下，产物的 `label` 为 `DRAFT.md`、`REVIEW.md`。完整的 `flow.json` 见 output-spec.md §5.2；
- 没有提供技能，生成两个空白 `SKILL.md`：只有 frontmatter 和状态维护片段（`draft_in_progress`/`draft_done`、`review_in_progress`/`review_done`），正文由开发者填写；
- 推进到 `review_done` 时，框架检查 `REVIEW.md` 存在即放行；两个节点的 `inputs` 为 `[]`、`validate` 为 `null`；
- `inspectCommands` 中不含 `knowledge_path`、`deploy_units`、`pull_knowledge`；`modules.json` 中 `knowledge`、`artifactSync` 为 `{"enabled": false}`，只有固定的 `knowledge_config`，没有 `artifact_sync`；
- `session_context_inject` 返回流程上下文和默认策略的 `agentConfig`，不含知识段；

生成结果预览见 [examples/minimal/output/](../booter/examples/minimal/output/)。

以后需要调整看板文案时，新建 `modules/board.json` 并在入口文件的 `modules.board` 中引用即可，`workflow.json` 不用动。

## 9. 完整示例

### 9.1 lite

[fixtures/lite/](../fixtures/lite/)：复刻 autobizdevops_lite，共六个配置文件（只供测试，不随 booter 分发，D67）：

| 文件 | 内容 |
|---|---|
| `plugin.scaffold.json` | 插件信息、对四个模块文件的引用 |
| `workflow.json` | 4 个节点，分在 `biz`、`dev` 两组，`seq` 为 1–4，产物在 `outputs` 中定义 |
| `modules/board.json` | `workflowLabel` |
| `modules/session.json` | 三个节点的运行策略 |
| `modules/knowledge.json` | 内置组装器和知识仓库同步 |
| `modules/artifactSync.json` | 从 `plan` 完成起同步 5 个文档产物 |

生成内容见 [fixtures/lite/output/](../fixtures/lite/output/)。产物同步是样例额外启用的，lite 本身没有这个能力。lite 中 `plan.md` 对旧文件名 `PLAN.md` 的回退在 v1 核心配置中不再表达（interfaces.md §5）。

### 9.2 全栈版

[fixtures/fullstack/](../fixtures/fullstack/)：按全栈版插件（仓库 `autobiz_kanban`）的现有内容编写（只供测试，不随 booter 分发，D67）：

| 文件 | 内容 |
|---|---|
| `plugin.scaffold.json` | 插件信息、宿主钩子与 MCP 配置的透传路径、对四个模块文件的引用 |
| `workflow.json` | 7 个主干节点，分在 `biz`、`dev`、`ops` 三组，`seq` 为 1–7，最后的归档是终态节点；`code` 只输出证据流 `evidence/EVIDENCE.jsonl`；可选输出 `PR_BODY.md` |
| `modules/board.json` | 工作流名称与描述、对话提示、系统提示注入 |
| `modules/session.json` | 五个节点的运行策略（含子代理替换和 `toolCustomConfig`） |
| `modules/knowledge.json` | 内置组装器和知识仓库同步 |
| `modules/artifactSync.json` | 从 `plan` 完成起同步（编码进行中除外）5 个文档产物，以及 `prd` 的原始材料 |

生成内容见 [fixtures/fullstack/output/](../fixtures/fullstack/output/)。

与全栈版现有 `board_config.json` 的差异：

- `board_config.json` 只保留 `apiVersion` 和 `inspectCommands`；`workflow`、`checkpointSuffixState` 由命令输出，`knowledge_config` 移到 `modules.json`，`supported_deploy_units`、`agentsRepo` 不再生成（output-spec.md §3）；
- 声明式校验器清单（`validators`）、编译守卫（`guards`）、`hookDefinitions` 和回滚归档清单（`rollback.archive`）不在核心配置中，留在插件自己的文件里（README §6.8）；人工确认关卡仍是 `hooks/hooks.json` 中的宿主钩子；
- 回流修复（`needs_fix` checkpoint 和“已阻断”状态）暂不支持，预留到 v2（README §7）；
- 已下架的精简路线、自定义节点子集和遗留的 `profiles` 不再表达，新建 Feature 只从第一个节点开始（全栈版的 `initial` 中其余 4 个 checkpoint 只服务于已下架的模板）；
- 节点描述和 `nextAction` 不再覆写，全部按推导规则生成（§6）：描述取技能的 `description`，提示文案使用脚手架默认文案；
- 节点输入、`stage_gate.py` 校验命令、详细设计动态阶段和跳过节点不在核心配置中表达（§2.5），`flow.json` 中对应字段取默认值；全栈版的 `autodev-detail-design` 技能不再挂在流程上；产物显示名不再配置，统一取路径（全栈版的“PRD文档”等名称不再保留）；
- 发布单元知识沿用全栈版的 `render_collected_session_context.py` 与 `collect-knowledge.js`。框架的会话入口生成流程上下文，读取运行策略，再追加知识组装结果。
