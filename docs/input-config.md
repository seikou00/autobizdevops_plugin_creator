# 用户输入配置规范 v1

## 1. 输入总览

### 1.1 输入分类

插件开发者的输入包括一个入口文件、一份核心流程、按模块拆分的配置文件，以及若干资源目录，都放在插件根目录下。初始化向导（`autobiz-plugin new` 或插件开发技能，interfaces.md §1.4、§1.6）负责收集信息并生成骨架：

| 输入类别 | 位置 | 用户需要提供什么 | 哪些由初始化向导完成 | 最终生成什么 |
|---|---|---|---|---|
| 插件基础信息 | `plugin.scaffold.json` | 名称、版本、描述 | 收集信息，生成基础配置 | 插件清单 `plugin.json`、工程结构 |
| 核心流程 | `workflow.json` | 节点、技能绑定、执行顺序、输入输出、可选校验命令、终态节点；`rules` 中按需开启的流程规则（动态阶段、跳过节点） | 创建配置骨架，辅助选择已有技能 | 编译后的流程契约及状态规则 `runtime/config/flow.json` |
| 技能资源 | `skills/<skill>/` 或 `skills/<分组>/<skill>/` | 技能正文、模板、执行脚本、业务校验器 | 导入已有资源或创建空骨架 | 带状态接入说明的交付技能及资源 |
| 看板模块配置 | `modules/board.json` | 目标平台、展示设置、可选能力 | 生成接入脚本和平台命令映射 | 看板 adapter `runtime/adapters/*`、固定看板配置 `board_core/board_config.json` |
| 会话与 Agent 配置 | `modules/session.json`；`agents/` | 运行策略、外挂资源 | 提供默认会话入口及配置骨架 | 会话模块 `runtime/session/*`、策略配置 `runtime/config/session.json`、资源引用 |
| 知识模块配置 | `modules/knowledge.json` | 清单解析方式、组装方选择 | 引导启用和选择 | `runtime/knowledge/*`：清单解析、发布单元查询、内置组装脚本 |
| 产物同步模块配置 | `modules/artifactSync.json` | 允许同步的阶段、要上传的产物 | 引导启用 | 同步技能 `skills/<skillName>/`、看板同步入口 `artifact_sync` |
| 自定义扩展 | `hooks/` 等 | 开发者自己的 hooks 等资源 | 创建对应目录 | 原样交付的扩展资源 |

每个配置文件都有自己的 JSON Schema：[workflow.schema.json](../schemas/workflow.schema.json)、[plugin-scaffold.schema.json](../schemas/plugin-scaffold.schema.json)，以及 [schemas/modules/](../schemas/modules/) 下的各模块 Schema。

### 1.2 设计原则

**核心配置与编译配置分开**（D19）。开发者和 agent 共同维护的是一组尽量短的核心配置，插件运行时使用的是由它们生成的编译配置：

| | 核心配置 | 编译配置 |
|---|---|---|
| 文件 | `workflow.json`、`plugin.scaffold.json`、`modules/*.json` | `runtime/config/*.json`、`board_core/board_config.json` |
| 谁写 | 开发者与 agent 共同维护 | 只由 `autobiz-plugin build` 写入 |
| 内容 | 只写决策；能推导或有默认值的都不写 | 填好全部默认值，展开引用，算出 checkpoint、标签、产物类型 |
| 谁读 | 脚手架 | 运行框架与 DevClaw |
| 是否随插件发布 | 否 | 是 |
| 如何保证正确 | 编辑、提交、构建、合并时自动检测（§7.1，D20） | 只能由通过检测的核心配置生成；运行框架加载时再校验不变量 |

其余原则：

- **核心流程只表达业务骨架**：`workflow.json` 只写节点、技能绑定、执行顺序、输入输出、校验命令、终态节点，以及 `rules` 中改变状态流转的流程规则（动态阶段、跳过节点）。看板接入、知识配置、外挂技能管理和技能内部实现都不写在这里（D11），见 §2.4。
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
  "nodes": [
    {
      "id": "dev.plan",
      "name": "任务计划",
      "stage": "Dev",
      "skill": "autodev-plan",
      "inputs": ["requirements", "design"],
      "outputs": { "plan": "plan.md" },
      "validate": "${python} ${skillPath}/scripts/check_plan.py --feature-dir ${featureDir}"
    }
  ]
}
```

顶层只有两个字段。`nodes` 的数组顺序就是主干的执行顺序；`rules` 放改变线性推进方式的流程规则，不写时流程就是纯线性的：

| 字段 | 必填 | 说明 |
|---|---|---|
| `nodes` | 是 | 主干节点（§2.2） |
| `rules.dynamicStages` | 否 | 动态阶段：插在某个主干节点之后、由用户决定是否执行的一组节点（§2.7） |
| `rules.skip` | 否 | 跳过节点：允许在看板或会话中跳过尚未完成的节点（§2.8） |

```json
"rules": {
  "dynamicStages": [ … ],
  "skip": true
}
```

文件格式随入口文件的 `scaffoldVersion` 一起演进，不单独标版本。

### 2.2 节点字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 小写字母开头，可以用 `.` 分段（例如 `dev.plan`）。最后一段作为 checkpoint 前缀：`dev.plan` → `plan_in_progress`、`plan_done`，所以各节点 id 的最后一段不能重复（包括动态阶段中的节点） |
| `name` | 是 | 节点显示名 |
| `skill` | 是 | 绑定的技能名，小写连字符，不超过 64 字符。技能目录可以是 `skills/<skill>/`，也可以放在一层分组目录下 `skills/<分组>/<skill>/`（§5）。初始化向导会列出已有技能供选择；build 时找不到会在 `skills/<skill>/` 生成桩文件 |
| `stage` | 否 | 所属阶段名，例如 `Biz`、`Dev`，用作看板分组。同一阶段的节点必须连续排列。不写时归入默认分组，分组名取 `board.display.workflowLabel` |
| `inputs` | 否 | 本节点读取的产物，必须由前面的节点输出。写产物 id，或写成 `{id, optional}`，见 §2.3 |
| `outputs` | 否 | 本节点产出的产物，写成 `{产物 id: 路径}`；可选输出写成 `{产物 id: {path, optional: true}}`，见 §2.3；代码提交写成 `{产物 id: {git: {…}}}`，见 §2.9 |
| `validate` | 否 | 节点完成时执行的业务校验命令，见 §2.5 |
| `terminal` | 否 | 终态节点，见 §2.6 |

输入和输出默认都是必需的：推进状态时，框架会检查它们是否存在。

### 2.3 产物与路径

```json
"inputs": [
  "proposal",
  { "id": "prd", "optional": true },
  "design"
],
"outputs": {
  "plan": "plan.md",
  "spec_bundle": ["proposal.md", "specs/*/spec.md"],
  "pr_body": { "path": "PR_BODY.md", "optional": true }
}
```

- 产物在第一个输出它的节点中定义，后面的节点通过 id 把它列为输入。产物 id 格式为 `^[a-z][a-z0-9_]*$`；
- 路径是字符串或字符串数组（D12）。每一项都是相对 `FEATURE_DIR` 的 POSIX 路径，可以含 glob。数组表示该产物由多项组成，每一项都要存在；
- 输入写成对象时：`optional: true` 表示推进时不检查它是否存在。输入缺失时技能怎么做，写在技能正文中，核心配置不表达；
- 输出写成 `{path, optional: true}` 表示可选输出，完成时不检查它是否存在；
- 生产者被跳过（§2.8），或生产者是未执行的动态阶段节点（§2.7）时，依赖它的必需输入按可选处理，缺失时怎么做由技能正文说明；
- 后面的节点可以再次输出同一个产物（例如在后续阶段更新它），但路径必须与第一次声明的一致；
- 存在性由框架检查，只做最小校验：每一项至少匹配一个普通文件即视为存在，空文件也算存在。空文件和产物是否合格由节点的校验命令判断（§2.5，D13）；
- 产物类型按扩展名推断：`.json` 为 `json`，其余为 `file`；
- 保留路径不可使用：`state.json`、`hooks.ndjson`、`sync-status.json`、`ARTIFACT_CATALOG.json`。

### 2.4 不在核心流程里的内容

| 内容 | 去向 |
|---|---|
| 节点描述、产物显示名、看板提示文案、动态阶段的选择文案、阶段标签覆写 | `modules/board.json` 的 `display`（§4.1.2） |
| 产物同步设置 | `modules/artifactSync.json`（§4.5） |
| 运行策略 | `modules/session.json` 的 `policies`（§4.2） |
| checkpoint 名、默认阶段标签、状态流转、产物类型 | 由脚手架推导，写入编译配置（§6） |
| 插件自有的校验与钩子配置：声明式校验器清单、编译守卫、人工确认关卡、回滚时归档的文件 | 插件自己的文件：校验器清单由节点 `validate` 调用的脚本自己读取；人工确认关卡写在 `hooks/hooks.json`；回滚清单由回滚技能自己读取（README §6.8） |
| 外部输入、旧文件名回退、checkpoint 前缀覆写 | v1 不支持，预留到 v2（README §7） |
| 技能的详细要求 | 技能正文 |
| 技能用的模板 | 技能自己维护：放在技能目录下，由技能正文引用，脚手架不登记、不检查、不生成（D29） |

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
| `${skillPath}` | 本节点的技能目录，即 `${pluginPath}/skills/<skill>` 或 `${pluginPath}/skills/<分组>/<skill>`（§5） |
| `${projectPath}` | 项目目录，即 `<pluginWorkspace>/<projectDir>` |
| `${featureDir}` | 当前 Feature 的产物目录（按目录布局推导） |
| `${feature}` | 当前 Feature |
| `${nodeId}` | 当前节点 id |
| `${repos}` | 本节点 git 产物涉及的仓库（或子目录）绝对路径，JSON 数组；没有 git 产物时为 `[]` |
| `${gitRanges}` | 本节点每个仓库的提交范围，JSON 对象，例如 `{"LF39.18_wg_flow": "a1b2c3d..9f8e7d6"}`；没有 git 产物时为 `{}` |

执行细节（工作目录、环境变量、超时、输出截取）见 interfaces.md §4.3、§4.4。校验器脚本建议放在 `skills/<skill>/scripts/` 下，用 `${skillPath}/scripts/…` 引用。

### 2.6 终态节点 terminal

```json
{ "id": "ops.archive", "name": "归档", "stage": "Ops", "skill": "autoops-archive", "terminal": true, "inputs": ["cicd_checklist"] }
```

- 只能是最后一个主干节点，最多一个；
- 只有一个 checkpoint `archived`（固定名称），没有 `_in_progress`/`_done`。前一个节点完成后推进到 `archived`，进入时检查本节点的必需输入；
- 不能写 `outputs` 和 `validate`，也不能被跳过或重开；到达 `archived` 后流程结束；
- 看板上只有“未开始”和“已归档”（`board.display.stateLabels.archived`）两种状态。

### 2.7 动态阶段 rules.dynamicStages

```json
"rules": {
  "dynamicStages": [
    {
      "id": "detail_design_before_code",
      "name": "详细设计",
      "insertAfter": "dev.plan",
      "defaultDecision": "pending",
      "nodes": [
        { "id": "dev.detail_design", "name": "详细设计", "stage": "Dev", "skill": "autodev-detail-design",
          "inputs": ["proposal", "specs", "design", "plan_json"],
          "outputs": { "detail_design": "DETAIL_DESIGN.md" } }
      ]
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 动态阶段 id，`^[a-z][a-z0-9_]*$`，记录在 Feature 的 `workflowDecisions` 中 |
| `name` | 是 | 阶段显示名 |
| `insertAfter` | 是 | 插在哪个主干节点之后。该节点后面必须还有非终态的主干节点；同一个节点后面只能插一个动态阶段 |
| `defaultDecision` | 否 | `pending`（默认）：到达时由用户选择；`enabled` / `skipped`：默认执行或跳过，看板提示按默认值给出，用户仍可改选 |
| `nodes` | 是 | 本阶段的节点，字段与主干节点相同（§2.2），不能是终态节点 |

规则：

- **选择点**是 `insertAfter` 节点的 `_done`。从这里推进到阶段第一个节点的 `_in_progress`，即记为执行（`enabled`）；推进到下一个主干节点的 `_in_progress`，即记为跳过（`skipped`）。决定写入 Feature 记录的 `workflowDecisions`；
- 执行时，阶段内节点依次推进，最后一个节点完成后进入下一个主干节点；
- 重开到选择点之前的节点时，该阶段的决定清除，下次到达选择点时重新选择；
- 阶段内节点的 `stage` 必须让同一阶段的节点保持连续（与 `insertAfter` 节点或下一个主干节点相同）；
- 阶段内节点可以读取 `insertAfter` 及之前节点的产物；后面的主干节点也可以读取阶段内节点的产物，阶段被跳过时这些输入按可选处理（§2.3），建议同时标 `optional`；
- 选择文案（阶段描述、执行与跳过两个选项的标题和说明）写在 `board.display.dynamicStages`（§4.1.2）。

### 2.8 跳过节点 rules.skip

```json
"rules": { "skip": true }
```

或者锁定部分节点：`"rules": { "skip": { "locked": ["dev.code"] } }`。

- 开启后，用户可以在看板上跳过节点（宿主命令 `skip_node`，interfaces.md §3.3.10），模型也可以通过 `update_state.py --skip-node` 跳过；
- 只能跳过当前处于 `_in_progress` 的节点，或尚未开始的节点；`locked` 中的节点、终态节点不可跳过；
- 跳过当前节点时，Feature 落到后面第一个未被跳过的节点的 `_in_progress`；后面没有可落地的节点时拒绝跳过；
- 被跳过的节点记录在 Feature 的 `workflowSkippedNodes` 中，看板上显示为“已跳过”（`board.display.stateLabels.skipped`）；依赖它产物的必需输入按可选处理（§2.3）；
- 重开到被跳过节点之前时，被跳过节点恢复为未开始。

### 2.9 代码提交产物 git

代码节点的成果是仓库里的提交，不是 `FEATURE_DIR` 下的文件，所以 `outputs` 中可以声明 git 类型的产物。它与文件产物并列，全部齐全才能推进到 `_done`：

```json
"outputs": {
  "code": { "git": { "repos": "deployUnits" } },
  "evidence_stream": "evidence/EVIDENCE.jsonl"
}
```

`git` 对象的字段都可以省略，上例等同于 `{ "repos": "deployUnits", "branch": "current", "require": ["commits", "clean", "merged"] }`：

| 字段 | 默认 | 说明 |
|---|---|---|
| `repos` | `"deployUnits"` | 看哪些仓库。`"deployUnits"`：本 Feature 所选发布单元的 `localRepoPath`，由宿主在建 Feature 时传入并记在 Feature 记录中（interfaces.md §3.3.2）；看板要有发布单元可选，需要启用知识模块。`"project"`：项目目录本身就是仓库。也可以写相对项目目录的路径数组。不写绝对路径（D15） |
| `branch` | `"current"` | 基线分支。`"current"`：节点开始时各仓库检出的分支；也可以写分支名，可用 `${feature}`，例如 `"feature/${feature}"` |
| `require` | `["commits", "clean", "merged"]` | 齐全条件，取下表的子集；`"pushed"` 默认不要求 |

**基线**：推进到本节点的 `_in_progress` 时，engine 为每个仓库记下基线分支、它当时的 HEAD 和已有的工作树，写进 Feature 记录的 `git`（output-spec.md §4.2）。找不到仓库（没有所选发布单元、路径不存在或不是 git 仓库）时拒绝推进，并说明原因。重开节点时保留原来的基线，所以重开之前的提交仍然算数。

**齐全条件**：推进到 `_done` 时，在检查文件产物之后、执行校验命令之前检查：

| 条件 | engine 怎么查 | 不满足时给出的原因 |
|---|---|---|
| `commits` | `git rev-list --count <base>..<branch>`，至少一个仓库大于 0 | 还没有新提交 |
| `clean` | `git status --porcelain` 为空，`.gitignore` 忽略的文件不算 | 列出未提交的文件，最多 20 个 |
| `merged` | 基线之后新增的工作树（例如子代理的独立工作树），其分支上不能有不在 `<branch>` 上的提交（`git rev-list <branch>..<工作树分支>` 为空） | 列出未合并的工作树和分支 |
| `pushed` | `git rev-list @{u}..<branch>` 为空 | 有 N 个提交未推送 |

- **看结果，不看过程**：engine 直接查仓库状态，不拦截 `git commit`。主会话、子代理和用户在终端里的提交都算，`amend`、`rebase` 之后也照样能判断；
- 仓库当前检出的分支与基线分支不同时，原因中会提示（例如“wg_flow 当前在 fix-log，开始时在 feature/f1”），因为提交可能落在了别的分支上；
- `localRepoPath` 是某个仓库的子目录时（单仓库多模块），`commits` 和 `clean` 只看这个子目录；
- 只改了部分发布单元也能完成：`commits` 只要求至少一个仓库有新提交，其余条件每个仓库都要满足；
- 完成时 engine 记下各仓库当时的 HEAD，`<base>..<done>` 就是本节点的提交范围。校验命令通过 `${repos}`、`${gitRanges}` 拿到仓库和提交范围（§2.5），可以只检查改动部分；
- 后面的节点可以把 git 产物列为输入（例如评审节点 `"inputs": ["code"]`），存在与否看上游节点记录的提交范围是否非空；
- git 产物不能加入产物同步（§4.5）。

## 3. 入口文件 plugin.scaffold.json

### 3.1 文件组织

```text
<plugin>/
├── plugin.scaffold.json     # 入口：基础信息、目录布局、对流程和模块配置的引用
├── workflow.json            # 核心流程（§2）
└── modules/
    ├── board.json           # 看板模块（可选；不引用时全部取默认值）
    ├── session.json         # 会话与 Agent（可选；不引用时全部取默认值）
    └── knowledge.json       # 知识模块（可选；不引用即不启用）
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
    "artifactSync": "./modules/artifactSync.json"
  }
}
```

`modules` 的键：

| 键 | 不引用时 | 配置内容 |
|---|---|---|
| `board` | 全部取默认值 | 看板模块：目标平台、展示设置、可选能力（§4.1） |
| `session` | 全部取默认值 | 会话与 Agent：运行策略（§4.2） |
| `knowledge` | 不启用知识模块 | 清单解析、知识组装、可选的知识仓库同步（§4.3）。引用即启用 |
| `artifactSync` | 不启用产物同步 | 上传产物到外部服务、看板上的同步入口（§4.5）。引用即启用 |

引用规则：

- 值是相对插件根目录的路径，以 `./` 开头、以 `.json` 结尾，不得含 `..`。建议使用 `./modules/<键>.json`；
- 引用的文件必须存在，否则报 `MODULE_FILE_MISSING`；
- 各模块文件按各自的 Schema 校验（`schemas/modules/<键>.schema.json`）；
- 关闭知识模块时去掉 `knowledge` 引用即可，文件可以保留，下次启用时再引用回来（`module disable` / `module enable` 就是这样做的）。

### 3.3 plugin

| 字段 | 必填 | 说明 | 输出位置 |
|---|---|---|---|
| `id` | 是 | 稳定 ID，小写连字符，不超过 64 字符，同时也是安装目录名和隔离布局下的元数据目录名（`<metaRoot>/<id>/`，§3.4）。不得使用保留名 `features`、`archive`、`issues`、`reviews`、`logs`、`plugins`。**发布后不可修改**，否则已有项目的状态无法找到或会被拒绝读取 | `state.json.pluginId`、hooks.ndjson `pluginId`、元数据目录名、`.codex-plugin/plugin.json.name` |
| `name` | 是 | DevClaw 沿用的插件名，可含大写（例如 `AutoBizDevOps-Plugin-Lite`） | 根 `plugin.json.name` |
| `version` | 是 | semver | 两份清单的 `version` |
| `description` | 是 | — | 两份清单的 `description` |
| `author` / `homepage` / `repository` / `license` / `keywords` | 否 | — | 两份清单 |
| `mcpServers` | 否 | 透传路径，以 `./` 开头，文件由开发者维护 | 两份清单的 `mcpServers` |
| `hooks` | 否 | 透传路径（宿主工具钩子，属于自定义扩展），以 `./` 开头，文件由开发者维护 | 只写入根 `plugin.json.hooks`，不写入 Codex 清单（D7） |
| `codexManifest` | 否 | 默认 `false`。DevClaw 只读根 `plugin.json`（D5），需要兼容 Codex 时再开启 | 是否生成 `.codex-plugin/plugin.json` |
| `interface` | 否 | 仅在 `codexManifest: true` 时使用。Codex 展示信息：`displayName`（缺省取 `name`）、`shortDescription`（缺省取 `description`）、`longDescription`、`developerName`、`category`、`capabilities`、`defaultPrompt`（最多 3 条，每条不超过 128 字符）、`brandColor`、`composerIcon`/`logo`/`screenshots`（放在 `./assets/` 下，截图必须是 PNG）、三个 URL | `.codex-plugin/plugin.json.interface` |

初始化向导会像 Codex plugin-creator 那样规范化用户输入的名称：转小写，非字母数字字符改为 `-`，合并连续的 `-`，去掉首尾的 `-`（`My Plugin` → `my-plugin`），并提示规范化后的结果。

### 3.4 runtime

| 字段 | 默认值 | 说明 |
|---|---|---|
| `metaRoot` | `.autobizdevops` | 元数据根目录，相对项目目录，状态和产物都在它下面。可以写多级相对路径（例如 `docs/autobiz`），不能是绝对路径，不能含 `..`、`\`、`:`，不能是 `.git` 或在 `.git` 下 |
| `layout` | `isolated` | 元数据与产物目录布局（README §6.5）。`isolated`：`<metaRoot>/<plugin.id>/`，同一项目可以装多个插件；`legacy`：`<metaRoot>/` 本身，只用于迁移已有插件（例如 lite），保证其已有项目可用 |
| `validateTimeoutSec` | `120` | 节点校验命令的超时秒数 |

`metaRoot` 和 `layout` 一起决定 Feature 产物目录 `FEATURE_DIR`：isolated 为 `<项目目录>/<metaRoot>/<plugin.id>/features/<feature>/`，legacy 为 `<项目目录>/<metaRoot>/features/<feature>/`。两者发布后都不可修改，否则已有项目的状态和产物找不到，所以留在入口文件中，不放进模块配置。迁移 lite、全栈版时 `metaRoot` 保持默认值。覆写 `board.display.systemPromptInject` 时，其中写的产物目录要与它们一致。

## 4. 模块配置文件

下文 `board.*`、`session.*`、`knowledge.*`、`artifactSync.*` 分别指 `modules/board.json`、`modules/session.json`、`modules/knowledge.json`、`modules/artifactSync.json` 中的字段。

### 4.1 modules/board.json（看板模块）

```jsonc
{
  "$schema": "../.scaffold/modules/board.schema.json",
  "target":       { ... },   // 目标平台
  "display":      { ... },   // 展示设置
  "capabilities": { ... }    // 可选能力
}
```

#### 4.1.1 target：目标平台

| 字段 | 默认值 | 说明 |
|---|---|---|
| `platforms` | `["darwin", "linux", "win32"]` | 生成哪些 `inspectCommands.<platform>` |
| `python.posix` | `python3` | darwin/linux 的解释器 |
| `python.win32` | `python` | win32 的解释器 |
| `utf8Mode` | `true` | 是否加 `-X utf8`（全栈版的约定）。lite 复刻样例设为 `false` |

#### 4.1.2 display：展示设置

| 字段 | 默认值 |
|---|---|
| `workflowLabel` | `plugin.name` |
| `workflowDescription` | `{节点 name 以 " → " 连接}。` |
| `dialogTips` | `当前为{workflowLabel}插件：{节点 name 以 " → " 连接}。请描述目标与验收标准。` |
| `systemPromptInject` | `当前 Feature 为 ${feature}。产物目录 FEATURE_DIR=${pluginWorkspace}/${projectDir}/{metaDir}/features/${feature}。插件根目录 PLUGIN_ROOT=${pluginPath}。`，其中 `{metaDir}` 在构建时替换：`isolated` 布局为 `.autobizdevops/<plugin.id>`，`legacy` 布局为 `.autobizdevops` |
| `stateLabels` | `{"not_started":"未开始","in_progress":"进行中","done":"已完成","skipped":"已跳过","archived":"已归档"}`；后两项只在开启 `rules.skip` 或有终态节点时使用 |
| `checkpointLabels.<checkpoint>` | 覆写看板阶段标签（board_config 的 `stageLabels`）。默认 `_in_progress` 为 `{name}进行中`、`_done` 为 `{name}完成`、`archived` 为 `stateLabels.archived` |
| `artifacts.<产物 id>` | 产物显示名；默认取该产物的第一个路径（例如 `PRD.md`），git 产物默认为产物 id |
| `nodes.<nodeId>.description` | 节点描述；默认 `{name}；产物：{输出路径以 "、" 连接}`。key 可以是动态阶段中的节点 |
| `nodes.<nodeId>.nextAction.active` | 覆写该节点 not_started 和 in_progress 状态的 `slashSkill`/`userMessage`/`dialogTips` |
| `nodes.<nodeId>.nextAction.done` | 覆写该节点完成后的提示，默认指向下一个节点；终态节点作用于 `archived` 状态 |
| `dynamicStages.<阶段 id>.description` | 动态阶段描述；默认 `在{下一主干节点 name}之前执行{name}。` |
| `dynamicStages.<阶段 id>.enable` / `.skip` | 选择点上两个选项的 `label` 和 `description`。默认执行为 `需要，执行{name}` / `先执行{阶段节点 name 以 " → " 连接}，再进入{下一主干节点 name}。`，跳过为 `不需要，直接进入{下一主干节点 name}` / `不执行{name}，直接进入{下一主干节点 name}。` |

文案中只能使用该命令键允许的占位符（interfaces.md §3.2），否则报 `PLACEHOLDER_UNKNOWN`。覆写 `systemPromptInject` 时如果去掉了 `FEATURE_DIR`，会报 `FEATURE_DIR_MISSING` 警告，因为技能依赖这个变量定位产物目录。

`slashSkill` 的作用是让看板**带出**对应技能，方便用户直接发起（D6），所以写不带命名空间前缀的技能名。覆写时如果写的既不是节点技能也不是模块技能，会报 `SLASH_SKILL_UNKNOWN` 警告；DevClaw 提供的技能可以写，警告可以忽略。设为空字符串表示不带出任何技能。

#### 4.1.3 capabilities.knowledgeSedimentation：知识沉淀入口

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

### 4.2 modules/session.json（会话与 Agent）

```json
{
  "$schema": "../.scaffold/modules/session.schema.json",
  "policies": {
    "default": { "agentMode": "solo" },
    "nodes": {
      "dev.plan": {
        "agentMode": "multi",
        "subagentConfig": { "disabledBuiltinSubagents": ["Explore"], "customSubagentFiles": ["agents/explore.md"] }
      }
    }
  }
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `policies.default` | `{"agentMode":"solo"}` | 全局默认运行策略 |
| `policies.nodes.<nodeId>` | — | 节点运行策略，原样写入 board_config 中对应节点的 `runtimePolicy` |

运行策略字段：

| 字段 | 取值 |
|---|---|
| `agentMode` | `solo` / `multi` / `agent_team` / `workflow` |
| `subagentConfig.disabledBuiltinSubagents` | 禁用的内置子代理名，例如 `["Explore","critic"]` |
| `subagentConfig.customSubagentFiles` | 外挂资源：插件内相对路径 `agents/*.md`。`agents/` 目录是可选的，文件可以稍后再补：lint 报 `SUBAGENT_FILE_MISSING`（warning），会话入口下发 `agentConfig` 时跳过不存在的文件 |
| `toolCustomConfig` | 宿主工具的定制开关，例如 `{"task": {"enabled": true}}`。脚手架不解释其内容，原样写入 `runtimePolicy` 和 `agentConfig` |

### 4.3 modules/knowledge.json（知识模块）

入口文件引用了这个文件即表示启用知识模块。

```json
{
  "$schema": "../.scaffold/modules/knowledge.schema.json",
  "manifest": { "format": "agents-manifest-v1", "path": "agents.manifest.json" },
  "assembly": { "enabled": true, "assembler": "plugin" },
  "source": { "type": "git", "url": "https://…/Knowledge.git", "sshUrl": "git@…:…/Knowledge.git", "ref": "master" }
}
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `root` | `sys` | 知识目录，相对插件根目录。知识模块入口和会话入口另接受 `--knowledge-path` 参数临时覆盖它（用于本地调试，或由自行管理知识目录的调用方传入），生成的宿主命令不带这个参数 |
| `manifest.format` | `agents-manifest-v1` | 清单解析方式。v1 只支持 lite 的 `agents.manifest.json` 格式 |
| `manifest.path` | `agents.manifest.json` | 清单文件，相对 `root` |
| `assembly.enabled` | `true` | 是否组装知识上下文 |
| `assembly.assembler` | `plugin` | 组装方。`plugin`：由插件执行组装脚本 `runtime/knowledge/render_collected_session_context.py`（§4.4），结果并入 `sessionContext`；`devclaw`：由 DevClaw 组装，插件只通过 `inspect_deploy_units.py` 提供清单解析结果，`sessionContext` 中不含知识段 |
| `assembly.timeoutSec` | `30` | 组装脚本的超时秒数。超时、退出码非 0 或输出不是合法 JSON 时，本次会话不含知识段，并在 `message` 中说明 |
| `source` | 不声明 | 可选：由插件自己拉取知识仓库。声明后生成 `runtime/knowledge/sync_knowledge.py` 和 `pull_knowledge` 命令（README §9） |
| `source.type` | `git` | v1 只支持 git |
| `source.url` | 声明 `source` 时必填 | 知识仓库 HTTPS 地址 |
| `source.sshUrl` | `""` | HTTPS 克隆失败时回退的 SSH 地址 |
| `source.ref` | `main` | 分支、标签或 commit |
| `supportedDeployUnits` | `[]` | board_config `supported_deploy_units` 的初始值。声明 `source` 时，运行期由 `pull_knowledge` 回写，打包时重置为此值 |

文件内容可以只有 `$schema`：此时清单解析、组装方都取默认值，用内置组装脚本组装知识，也不拉取知识仓库。

### 4.4 内置组装脚本

`assembler = plugin` 时，知识由 `runtime/knowledge/render_collected_session_context.py` 组装，它和 `collect-knowledge.js` 都来自全栈版，lite 和全栈版都直接使用：

- 调用 `collect-knowledge.js`（collector，需要 Node）按所选发布单元组装知识；collector 不可用或单元不在它的列表中时，按清单映射加载，最后回退 `<localRepoPath>/AGENTS.md`；
- 无论选没选发布单元，都读取会话工作区的 `<sessionWorkspacePath>/AGENTS.md` 作为会话工作区指令。

所以知识仓库里没有 collector 知识的插件，也能直接用它从各仓库和工作区的 `AGENTS.md` 取到上下文。

没有配置项可以换掉它。插件需要不同的组装方式时，直接替换这个文件：新文件放在同一路径，按 interfaces.md §4.5 的协议从 stdin 读请求、向 stdout 输出知识段即可。build 和 upgrade 发现它与构建记录不一致时，当作插件的替换保留，不报 `DRIFT_MANAGED`（README §4）。

### 4.5 modules/artifactSync.json（产物同步模块）

把产物上传到外部服务，并在看板上生成同步入口。入口文件的 `modules.artifactSync` 引用了这个文件即表示启用，不引用即不启用，文件中没有 `enabled`（D30）。

```json
{
  "$schema": "../.scaffold/modules/artifactSync.schema.json",
  "allowedFrom": "dev.plan:done",
  "excludeCheckpoints": ["code_in_progress"],
  "artifacts": {
    "prd": "正式产品需求文档。",
    "plan": "开发执行计划。"
  },
  "extraPaths": { "biz.prd": { "prd_original/**/*": "原始需求文档或参考材料。" } }
}
```

同步会把文件上传到外部服务，所以要上传的产物用 `artifacts` 显式列出：没列出的产物不上传，节点新增输出也不会自动加入同步。产物的路径和归属节点从 `workflow.json` 的 `outputs` 推导，这里不用重复写。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `skillName` | `autobizdevops-artifact-sync` | 生成的技能目录名和技能名 |
| `entry.enabled` | `true` | 是否在看板上生成产物同步入口（board_config 顶层 `artifact_sync`，`slashSkill` 为 `skillName`） |
| `entry.syncType` / `entry.userMessage` / `entry.dialogTips` | `invoke_session` / `请针对${projectCode}项目的${feature}特性发起产物同步` / `发起产物同步` | 入口文案 |
| `allowedFrom` | 与 `allowedCheckpoints` 二选一 | `<nodeId>:<in_progress\|done>` 或 checkpoint 名；从这里到流程末尾都允许同步。只沿主干 checkpoint 链推导（含 `archived`），动态阶段节点的 checkpoint 不在其中，需要时写进 `allowedCheckpoints` |
| `excludeCheckpoints` | `[]` | 从 `allowedFrom` 推导出的列表中再剔除的 checkpoint |
| `allowedCheckpoints` | — | 显式列表 |
| `artifacts` | — | 必填。要上传的产物：产物 id → 同步目录中的简述。产物必须由某个节点（含动态阶段节点）以文件路径输出，git 产物不能同步 |
| `uploadUrl` | `https://tscode-cos-plugin.paasuat.cmbchina.cn/file/upload` | 上传服务地址，默认值取自全栈版 `sync_artifacts.py` |
| `maxFileSizeMiB` | `5` | 超过上限的文件跳过并报告 |
| `extraPaths` | `{}` | 不属于任何节点输出、但需要同步的路径：`{nodeId: {路径模式: 简述}}` |

## 5. 资源目录

| 目录 | 内容 | 初始化向导 | 交付方式 |
|---|---|---|---|
| `skills/<skill>/` 或 `skills/<分组>/<skill>/` | `SKILL.md` 正文、`scripts/` 执行脚本与业务校验器、`references/`，以及技能自己维护的模板等资源 | 导入已有技能目录，或创建空骨架（SKILL.md 桩、`scripts/`） | SKILL.md 加上状态接入托管片段，其余原样交付（output-spec.md §6） |
| `agents/`（可选） | 自定义子代理等外挂资源，由会话策略引用 | 不创建，需要时由开发者创建 | 存在时原样交付 |
| `hooks/` | 开发者自定义扩展，例如宿主工具钩子 `hooks.json`、节点校验脚本及其配置 | 创建目录 | 原样交付，脚手架不读写 |

技能目录的查找规则：build 按节点的 `skill` 在 `skills/<skill>/` 和 `skills/*/<skill>/` 两处查找含 `SKILL.md` 的目录，只找这两层。两处都有、或在多个分组下都有时报 `SKILL_AMBIGUOUS`；都没有时在 `skills/<skill>/` 生成桩文件。找到的目录就是该节点的技能目录，`${skillPath}` 指向它。分组目录自己的 `SKILL.md`（例如 `skills/autodev/SKILL.md`）和分组下不被节点绑定的技能（例如回滚、评审等辅助技能）都按开发者资源原样交付。

技能私有的脚本和校验器不需要、也不应该导入 `runtime/` 下的任何模块。它们需要的路径来自会话上下文（`FEATURE_DIR`）或校验命令占位符（§2.5）。

## 6. 编译规则（核心配置 → 编译配置）

build 把核心配置编译成 `runtime/config/flow.json`（output-spec.md §5.2）和 `board_core/board_config.json`。两者来自同一份中间表示，下表以 board_config 为例。设主干节点按数组顺序为 `N[0..k]`，`P[i]` 为 `N[i].id` 的最后一段；“下一节点”指流程上紧随其后的节点（动态阶段默认执行时为阶段第一个节点，阶段最后一个节点的下一节点是 `insertAfter` 之后的主干节点）；未引用的模块按默认值计算。

| 输出字段 | 规则 |
|---|---|
| `apiVersion` | `1` |
| `inspectCommands.<platform>` | 见 output-spec.md §3.2 的命令模板，平台与解释器取自 `board.target` |
| `workflow.templates.standard` | `{kind:"profile", label: workflowLabel, description: workflowDescription}` |
| `workflow.checkpoints.initial` | `[P[0]_in_progress]` |
| `workflow.checkpoints.transitions` | 主干按 `P[0]_in_progress → P[0]_done → P[1]_in_progress → …` 线性排列。最后一个主干节点是终态节点时，前一个节点的 `_done → archived`，`archived: []`；否则 `P[k]_done: []`。动态阶段的流转见 `workflow.dynamicStages` |
| `workflow.checkpoints.stageLabels` | 全部 checkpoint（含动态阶段节点、`archived`）的默认标签（§4.1.2 `checkpointLabels`），再合并 `board.display.checkpointLabels` |
| `workflow.dynamicStages[]` | `rules.dynamicStages` 中每个动态阶段一项：`{id, phase, label, description, order, choiceCheckpoint, defaultDecision, insertAfter, enableTargetCheckpoint, skipTargetCheckpoint, enableLabel, skipLabel, enableDescription, skipDescription, nodes}`。`phase` 取阶段第一个节点的 `stage`；`label` 取 `name`；`order` 为 `insertAfter` 节点的 `order + 5`；`choiceCheckpoint` 为 `insertAfter` 节点的 `_done`；`enableTargetCheckpoint` 为阶段第一个节点的 `_in_progress`；`skipTargetCheckpoint` 为下一个主干节点的 `_in_progress`；描述和选项文案来自 `board.display.dynamicStages`（§4.1.2）；`nodes[]` 与主干节点同形，另加 `phase`（即 `group`）和 `checkpointPrefix` |
| `workflow.skipPolicy` | 开启 `rules.skip` 时为 `{lockedNodes: rules.skip.locked}`（写 `true` 时为 `[]`）；未开启时不输出 |
| `nodes[i].label` | `N[i].name` |
| `nodes[i].group` | `N[i].stage`；未写时取 `board.display.workflowLabel` |
| `nodes[i].order` | `(i + 1) * 10` |
| `nodes[i].description` | `board.display.nodes[N[i].id].description`，未配置时为 `{name}；产物：{输出路径以 "、" 连接}`，没有输出时为 `{name}` |
| `nodes[i].runtimePolicy` | `session.policies.nodes[N[i].id]`；未配置时不输出 |
| `nodes[i].checkpoints` | `[P[i]_in_progress, P[i]_done]`；终态节点为 `["archived"]` |
| `nodes[i].states[not_started/in_progress].nextAction` | `slashSkill = N[i].skill`；`userMessage = "请使用 /{skill} 处理当前 Feature，先读取现有状态和产物。"`；`dialogTips = "当前阶段：{name}。"`；再合并 `board.display.nodes[N[i].id].nextAction.active`。终态节点只有 `not_started` 这一项 |
| `nodes[i].states[done].nextAction` | 有下一节点时：`slashSkill` 为下一节点的技能；`userMessage` 同上，但用下一节点的技能；`dialogTips = "下一阶段：{下一节点 name}。"`。没有下一节点时：`{slashSkill:"", userMessage:"", dialogTips:"{name}已完成。"}`。再合并 `nextAction.done` |
| 终态节点的 `states[archived].nextAction` | `{slashSkill: skill, userMessage: "请使用 /{skill} 查看当前 Feature 的归档状态。", dialogTips: "{name}已完成。"}`，再合并 `nextAction.done` |
| `nodes[i].artifacts.inputs/outputs[]` | 文件产物为 `{id, label, artifactType, path, required[, paths]}`。`label` 取 `board.display.artifacts[id]`，缺省为第一个路径；`artifactType` 按扩展名推断；`required` 为非 `optional`；路径为数组时 `path` 取首项，`paths` 给出全部。git 产物为 `{id, label, artifactType: "git", required, git: {repos, branch, require}}`，没有 `path`，`git` 填好默认值（output-spec.md §3.5） |
| `nodes[i].validators` | `[]`（固定）。节点的 `validate` 命令只写入 `flow.json`，由运行框架执行，DevClaw 不执行 |
| `workflow.transitions[i]` | 主干相邻节点：`{id:"P[i]-to-P[i+1]", from:{nodeId:N[i].id, state:"done"}, to:{nodeId:N[i+1].id, state:"in_progress"}}`；`N[i+1]` 是终态节点时 `to.state` 为 `"archived"` |
| `checkpointSuffixState` | `in_progress`、`done` 两项，label 取 `stateLabels`；有终态节点时加 `archived: {nodeStatus:"archived", label: stateLabels.archived}` |
| `inspectCommands.*.skip_node` | 仅在开启 `rules.skip` 时生成 |
| `knowledge_config` | 仅在 `board.capabilities.knowledgeSedimentation.enabled` 时生成（output-spec.md §7.3） |
| `artifact_sync` | 仅在引用了产物同步模块且 `artifactSync.entry.enabled` 时生成（output-spec.md §7.2） |
| `supported_deploy_units` | 仅在引用了知识模块时生成（output-spec.md §7.1） |
| `agentsRepo` | 仅在知识模块声明 `source` 时生成 |
| `inspectCommands.*.knowledge_path` / `deploy_units` | 仅在引用了知识模块时生成；未引用时直接不生成（D1） |
| `inspectCommands.*.pull_knowledge` | 仅在知识模块声明 `source` 时生成 |

## 7. 自动检测

### 7.1 检测时机

核心配置由人和 agent 一起修改，所以在每个可能引入错误的环节都自动检测，而不是依赖人记得去跑（D20）：

| 时机 | 怎么触发 | 检查什么 | 发现问题时 |
|---|---|---|---|
| 编辑时 | IDE 读取文件头的 `$schema` | 字段名、类型、必填项 | 编辑器里即时标红 |
| agent 修改后 | 插件开发技能每次改完配置都运行 `autobiz-plugin lint`（interfaces.md §1.6） | §7.2 全部规则 | agent 按 Issue 修正后再继续 |
| 提交时 | 仓库内的 `.githooks/pre-commit` 运行 `autobiz-plugin lint`；每个协作者执行一次 `autobiz-plugin git-hook install` 启用 | §7.2 全部规则，包括编译配置是否过期 | 阻止提交 |
| 构建时 | `autobiz-plugin build` 先执行同样的检查 | §7.2 全部规则 | 不写任何编译配置 |
| 合并时 | CI 运行 `autobiz-plugin check --strict`（本地钩子可能被 `--no-verify` 跳过，CI 是最后一道） | §7.2、§7.3 全部规则，加契约测试 | 阻止合并 |
| 运行时 | 运行框架加载 `flow.json` | 编译配置自身的不变量（output-spec.md §5.2） | 拒绝执行并报错 |

`lint` 只读、不联网，只看配置文件和它们引用的文件是否存在，通常在 1 秒内完成，适合放进钩子和 agent 的每轮修改之后。`check` 在 `lint` 的基础上再检查技能内容、生成文件漂移并跑契约测试。

编译配置是否过期：build 把每份核心配置的摘要写进 `runtime/build-manifest.json`，并在 `flow.json` 中记录 `workflow.json` 的摘要。`lint` 发现当前文件与记录不一致时报 `BUILD_STALE`，提示先执行 `build`，避免提交了新的核心配置却带着旧的编译配置。

### 7.2 配置规则（lint，build 前同样执行）

问题汇总后一次性输出（格式见 interfaces.md §1.3），由 Issue 的 `file` 字段标明出在哪个文件。`error` 会阻止提交和 build；`warning` 只提示，加 `--strict` 后视为 error。

| code | 级别 | 规则 |
|---|---|---|
| `INPUT_SCHEMA` | error | 入口文件、`workflow.json` 或某个模块配置文件不符合各自的 JSON Schema |
| `MODULE_FILE_MISSING` | error | `modules` 引用的文件不存在 |
| `NODE_DUP` | error | 节点 id 重复（主干节点与动态阶段节点一起算） |
| `CHECKPOINT_DUP` | error | 两个节点 id 的最后一段相同，推导出的 checkpoint 重复（终态节点不参与，它只有 `archived`） |
| `STAGE_ORDER` | error | 同一 `stage` 的节点没有连续排列（动态阶段节点按插入位置计算） |
| `TERMINAL_INVALID` | error | 终态节点不是最后一个主干节点、出现多个、出现在动态阶段中，或写了 `outputs`/`validate` |
| `DYNAMIC_STAGE_INVALID` | error | 动态阶段 id 重复；`insertAfter` 不是主干节点，或后面没有非终态的主干节点；同一节点后面插了多个动态阶段 |
| `FLOW_NODE_UNKNOWN` | error | `rules.skip.locked` 引用了不存在的节点 |
| `INPUT_UNKNOWN` | error | 输入的产物 id 没有任何节点输出过 |
| `INPUT_FORWARD` | error | 输入的产物只由本节点或后面的节点输出（动态阶段节点按插入位置计算） |
| `OUTPUT_PATH_CONFLICT` | error | 同一产物 id 在不同节点输出时路径不一致 |
| `OUTPUT_REDECLARED` | warning | 同一产物被多个节点输出（允许，用于后续阶段更新产物；以第一个节点为生产者） |
| `PATH_UNSAFE` | error | 产物路径（数组中的每一项）、git 产物 `repos` 中的路径或知识目录为绝对路径，含 `..`、`\`、`:`，或与保留文件名冲突 |
| `GIT_OUTPUT_INVALID` | error | git 产物的 `repos` 为 `"deployUnits"`（含默认值），但没有启用知识模块，看板上没有发布单元可选；或 `branch` 使用了 `${feature}` 以外的占位符；或同一个 git 产物 id 在不同节点的 `git` 设置不一致 |
| `COMMAND_INVALID` | error | 节点 `validate` 含换行、无法按 POSIX 规则拆分，或使用了 §2.5 以外的占位符 |
| `SKILL_MISSING` | warning（lint）/ error（check） | `skills/<skill>/SKILL.md` 和 `skills/*/<skill>/SKILL.md` 都不存在；build 会在 `skills/<skill>/` 生成桩文件 |
| `SKILL_AMBIGUOUS` | error | 同名技能目录出现在多处（§5），无法确定节点的技能目录 |
| `COMMAND_SCRIPT_MISSING` | warning | 命令中以 `${pluginPath}/` 或 `${skillPath}/` 开头的参数指向的文件不存在 |
| `SUBAGENT_FILE_MISSING` | warning | `customSubagentFiles` 指向的文件不存在；会话入口下发 `agentConfig` 时跳过该文件 |
| `BOARD_NODE_UNKNOWN` | error | `board.display.nodes` 的 key 不是 workflow 中的节点（含动态阶段节点），或 `board.display.dynamicStages` 的 key 不是动态阶段 |
| `CHECKPOINT_LABEL_UNKNOWN` | error | `board.display.checkpointLabels` 的 key 不是推导出的 checkpoint |
| `POLICY_NODE_UNKNOWN` | error | `session.policies.nodes` 的 key 不是 workflow 中的节点（含动态阶段节点） |
| `ARTIFACT_REF_UNKNOWN` | error | `board.display.artifacts`、`artifactSync.artifacts` 引用了没有任何节点输出的产物，或 `artifactSync.artifacts` 中列了 git 产物 |
| `PLACEHOLDER_UNKNOWN` | error | 看板文案中使用了该命令键不允许的占位符 |
| `SLASH_SKILL_UNKNOWN` | warning | `nextAction` 覆写的 `slashSkill` 既不是节点技能也不是模块技能 |
| `FEATURE_DIR_MISSING` | warning | 覆写后的 `systemPromptInject` 不含 `FEATURE_DIR` |
| `MODULE_OPTION` | error | 模块或可选能力的参数非法，例如 `allowedFrom` 指向不存在的节点 |
| `MODULE_SKILL_CONFLICT` | error | 模块技能名与某个节点的技能名冲突 |
| `PLUGIN_ID_RESERVED` | error | `plugin.id` 是保留目录名 |
| `INTERFACE_UNUSED` | warning | 声明了 `plugin.interface`，但 `codexManifest` 为 `false` |
| `LAYOUT_LEGACY` | warning | 使用了 `legacy` 布局：该插件不能与另一个 legacy 插件（例如 lite 与全栈版）装在同一个项目中 |
| `PLUGIN_ID_CHANGED` | error | `plugin.id` 与 `runtime/build-manifest.json` 中记录的不一致（需加 `--allow-id-change`） |
| `LAYOUT_CHANGED` | error | `runtime.layout` 或 `runtime.metaRoot` 与 build-manifest 中记录的不一致：已有项目的状态会找不到（需加 `--allow-layout-change`） |
| `BUILD_STALE` | error | 核心配置的摘要与 build-manifest 中记录的不一致：配置改了但没有重新 build（从未 build 过时不报） |

### 7.3 资源与构建规则（check）

| code | 级别 | 规则 |
|---|---|---|
| `SKILL_NAME_MISMATCH` | error | SKILL.md frontmatter 中的 `name` 与 `skill` 不一致 |
| `SKILL_FRONTMATTER` | error | frontmatter 不符合 Codex 规则：只允许 `name`、`description`、`license`、`allowed-tools`、`metadata` 五个键；`description` 必填、不超过 1024 字符、不含 `<` `>`。版本号等自定义信息放进 `metadata`（例如 `metadata.version`）。DevClaw 不依赖顶层 `version`（D8），导入技能（`add skill --from`）时会自动迁移 |
| `SKILL_TOO_LONG` | warning | SKILL.md 超过 500 行，应把细节拆到 `references/` |
| `SKILL_STATE_BLOCK` | error | SKILL.md 缺少 `state` 托管片段，或片段内容与推导结果不一致 |
| `SKILL_SHARED` | warning | 多个节点共用同一个技能（看板能用，但技能需要自行区分 checkpoint） |
| `LEGACY_ENTRY_REF` | warning | 技能正文（托管片段以外）仍引用旧入口路径：`hooks/update_state.py`、`hooks/update_checkpoint.py`、`hooks/route_checkpoint.py`、`hooks/skip_node.py`、`hooks/init_workspace.py`、根目录 `inspect_state.py` |
| `OPENAI_YAML` | error | `agents/openai.yaml` 不符合约束：`short_description` 应为 25–64 字符，`default_prompt` 必须以 `$<skill>` 形式提及技能 |
| `TODO_PLACEHOLDER` | warning（check）/ error（package） | 桩文件、骨架文件或清单中还有未填写的 `[TODO: …]` |
| `DRIFT_GENERATED` / `DRIFT_MANAGED` | error | 生成或托管的文件被手改过（内置知识组装脚本除外，插件可以替换它，§4.4） |
| `CONTRACT_TEST` | error | 在临时工作区模拟宿主调用失败（interfaces.md §1.5） |

## 8. 最小示例

两个节点，不写任何模块配置文件：看板和会话全部取默认值，不启用知识模块（文件见 [examples/minimal/](../examples/minimal/)）。

`workflow.json`：

```json
{
  "$schema": "./.scaffold/workflow.schema.json",
  "nodes": [
    { "id": "draft", "name": "起草", "skill": "doc-draft",
      "outputs": { "draft": "DRAFT.md" } },
    { "id": "review", "name": "评审", "skill": "doc-review",
      "inputs": ["draft"], "outputs": { "review": "REVIEW.md" },
      "validate": "${python} ${skillPath}/scripts/check_review.py --feature-dir ${featureDir}" }
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

编译结果：

- checkpoint 链为 `draft_in_progress → draft_done → review_in_progress → review_done`，产物目录为 `.autobizdevops/doc-review/features/<feature>/`；两个节点都在默认分组 `Doc-Review-Kanban` 下，产物显示名为 `DRAFT.md`、`REVIEW.md`。完整的 `flow.json` 见 output-spec.md §5.2；
- 生成两个技能桩文件，各自带好状态接入片段；
- 推进到 `review_done` 时，框架先检查 `DRAFT.md`、`REVIEW.md` 存在，再执行 `skills/doc-review/scripts/check_review.py`，退出码为 0 才放行。脚本尚未编写时，`lint` 报 `COMMAND_SCRIPT_MISSING`；
- `inspectCommands` 中不含 `knowledge_path`、`deploy_units`、`pull_knowledge`；board_config 中没有 `knowledge_config` 和 `artifact_sync`；
- `session_context_inject` 返回流程上下文和默认策略的 `agentConfig`，不含知识段；
- 不生成 `.codex-plugin/plugin.json`。

以后需要给产物起中文显示名或调整看板文案时，新建 `modules/board.json` 并在入口文件的 `modules.board` 中引用即可，`workflow.json` 不用动。

## 9. 完整示例

### 9.1 lite

[examples/lite/](../examples/lite/)：复刻 autobizdevops_lite，共六个配置文件：

| 文件 | 内容 |
|---|---|
| `plugin.scaffold.json` | 插件信息、`layout: legacy`（保证 lite 已有项目可用）、对四个模块文件的引用 |
| `workflow.json` | 4 个节点，分属 `Biz`、`Dev` 两个阶段，产物在 `outputs` 中定义 |
| `modules/board.json` | 关闭 `-X utf8`、`workflowLabel`、5 个产物的显示名、两个节点的描述和 `nextAction` 覆写，以及知识沉淀入口 |
| `modules/session.json` | 三个节点的运行策略 |
| `modules/knowledge.json` | 内置组装器和知识仓库同步 |
| `modules/artifactSync.json` | 从 `dev.plan` 完成起同步 5 个文档产物 |

产物同步是样例额外启用的，lite 本身没有这个能力。lite 中 `plan.md` 对旧文件名 `PLAN.md` 的回退在 v1 核心配置中不再表达（interfaces.md §5）。

### 9.2 全栈版

[examples/fullstack/](../examples/fullstack/)：按全栈版插件（仓库 `autobiz_kanban`）的现有内容编写，用到了 v1 的全部流程规则：

| 文件 | 内容 |
|---|---|
| `plugin.scaffold.json` | 插件信息、宿主钩子与 MCP 配置的透传路径、`layout: legacy`（保证全栈版已有项目可用）、对四个模块文件的引用 |
| `workflow.json` | 7 个主干节点，分属 `Biz`、`Dev`、`Ops` 三个阶段，最后的归档是终态节点；`dev.code` 的代码提交产物 `code`（git，看所选发布单元的仓库）；可选输入和可选输出 `PR_BODY.md`；`rules` 中是 `dev.plan` 之后的动态阶段“详细设计”和跳过节点。前五个节点的校验命令调用插件自己的 `hooks/stage_gate.py` |
| `modules/board.json` | 工作流名称与描述、对话提示、系统提示注入、12 个阶段标签、12 个产物的显示名、节点描述与 3 处 `nextAction` 覆写、详细设计的选择文案，以及知识沉淀入口 |
| `modules/session.json` | 五个节点的运行策略（含子代理替换和 `toolCustomConfig`） |
| `modules/knowledge.json` | 内置组装器和知识仓库同步 |
| `modules/artifactSync.json` | 从 `dev.plan` 完成起同步（编码进行中除外）6 个文档产物，以及 `biz.prd` 的原始材料 |

与全栈版现有 `board_config.json` 的差异：

- 声明式校验器清单（`validators`）、编译守卫（`guards`）、`hookDefinitions` 和回滚归档清单（`rollback.archive`）不在核心配置中，留在插件自己的文件里（README §6.8）；人工确认关卡仍是 `hooks/hooks.json` 中的宿主钩子；
- 回流修复（`needs_fix` checkpoint 和“已阻断”状态）暂不支持，预留到 v2（README §7）；
- 已下架的精简路线、自定义节点子集和遗留的 `profiles` 不再表达，新建 Feature 只从第一个节点开始（全栈版的 `initial` 中其余 4 个 checkpoint 只服务于已下架的模板）；
- 通用的 `userMessage`、`dialogTips` 使用脚手架默认文案，只保留有业务含义的覆写；
- 节点输入不再单独起 id（全栈版的 `prd_optional`、`detail_design_optional`、`design_optional`），统一引用产物 id 并标 `optional`；同一产物在不同节点的显示名统一取 `board.display.artifacts`；
- 知识组装沿用全栈版的 `render_collected_session_context.py` 与 `collect-knowledge.js`，它们成为知识模块的内置组装脚本（README §6.3），会话入口的流程上下文和运行策略改由会话模块给出。
