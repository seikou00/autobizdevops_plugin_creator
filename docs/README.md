# AutoBiz 看板插件脚手架：整体设计（v1 草案）

## 1. 目标

插件开发者只做两件事：

1. 在 `plugin.scaffold.json` 中填写**阶段、节点、产物**，勾选可选模块；
2. 编写每个节点的技能（`skills/<skill>/SKILL.md` 及其 references、templates）。

看板配置 `board_core/board_config.json`、三平台宿主命令、状态机、看板 JSON 协议、插件清单、技能中的状态维护片段，以及知识、产物同步模块，都由脚手架生成或托管。

v1 范围：

- 线性工作流：节点顺序即流转顺序，每个节点有 `<prefix>_in_progress`、`<prefix>_done` 两个 checkpoint；
- 两个可选模块：**知识沉淀与解析**（`knowledge`）、**产物同步**（`artifactSync`）；
- 插件开发技能 `autobiz-plugin-creator`：开发者用对话描述流程，由 agent 写配置并调用 CLI；
- 同一项目可以安装多个插件，各插件的状态和产物按 `pluginId` 隔离；
- 运行时只依赖 Python 3.9+ 标准库（知识同步另需 Git）。

脚手架位于独立仓库 `autobizdevops_plugin_creator`（即本仓库，结构见 §3.1）。§8 汇总了已经确认的决策。

kanban 全栈版的模板子集（lean）、动态阶段、needs_fix 回流、skip_node、归档终态节点、validators/guards 不进 v1，见 §7。

文档索引：

| 文档 | 内容 |
|---|---|
| [input-config.md](input-config.md) | 用户输入配置规范：字段、默认值、推导规则、校验规则 |
| [output-spec.md](output-spec.md) | 插件标准化输出规范：目录、清单、board_config、运行期数据、技能格式 |
| [interfaces.md](interfaces.md) | 接口定义：脚手架 CLI、模块契约、宿主命令协议、运行时 API |
| [schemas/plugin-scaffold.schema.json](../schemas/plugin-scaffold.schema.json) | 输入配置 JSON Schema（IDE 补全与结构校验） |
| [examples/lite.plugin.scaffold.json](../examples/lite.plugin.scaffold.json) | 复刻 autobizdevops_lite 的完整输入样例 |
| [examples/minimal.plugin.scaffold.json](../examples/minimal.plugin.scaffold.json) | 两个节点、不启用模块的最小样例（input-config.md §6） |

## 2. 从两个参考插件中提取的结论

### 2.1 可推导内容占了看板配置的大部分

lite 版 `board_config.json` 有 509 行，开发者真正做出的决策只有：4 个节点各自的名称、技能、输入/输出产物，加上 3 处提示文案覆写和运行策略。其余都可以推导：

| 内容 | 推导来源 |
|---|---|
| `workflow.checkpoints`（initial / transitions / stageLabels） | 节点顺序 + 节点 label（lite 的 `load_config` 已强制要求二者一致） |
| 每个节点的 3 个 `states` 与 `nextAction` | 本节点技能、下一节点技能，加上可选覆写 |
| `workflow.transitions` | 相邻节点 |
| 三平台 `inspectCommands` | 一份命令模板，仅解释器名和 `--platform` 不同 |
| 输入产物的完整定义 | 引用前序节点的输出（lite 中 `PRD.md` 的定义重复了 4 次） |

已用临时编译原型验证：[样例输入](../examples/lite.plugin.scaffold.json) 约 110 行（使用 `layout: legacy`），编译结果与 lite 现有配置逐字段一致。差异只有三处：

- 两处是运行期回写字段（§6.1）。其中 win32 的 `knowledge_path` 已被本地同步写成个人机器路径 `C:\Users\80319167\...` 并提交进了仓库，所以脚手架要明确哪些字段归运行期，打包时重置；
- 一处是样例额外启用的产物同步模块带来的 `artifact_sync` 入口（lite 本身没有这个模块）。

### 2.2 两个插件的差异与标准化取舍

| 方面 | lite | kanban | 脚手架标准 |
|---|---|---|---|
| 清单 | 根目录 `plugin.json`（`skills: ./skills/`） | 根目录 `plugin.json` + skills/mcpServers/hooks | 宿主只读根 `plugin.json`；`.codex-plugin/plugin.json` 可选（D5） |
| 状态内核 | `board_core/runtime.py` 单文件，约 15KB | workflow_compiler 等 9 个模块，约 125KB | 以 lite 为基础泛化，作为托管内核 |
| 宿主命令 | 无 `-X utf8`，路径加引号 | 有 `-X utf8`，路径不加引号 | 默认 `-X utf8`；单值占位符一律写成 `"${pluginPath}"` 形式（D2） |
| 元数据目录 | `.autobizdevops/state.json`（带 `pluginId`） | `.autobizdevops/state.json`（`autobizdevops.state.v3`，不带 `pluginId`） | 默认 `.autobizdevops/<pluginId>/`，同一项目可装多个插件（D3）；`legacy` 布局仅用于迁移已有插件 |
| 状态脚本 | `update_state.py`，另有 `update_checkpoint.py` 别名 | `update_checkpoint.py` | `update_state.py` 为正式入口，保留别名 |
| 会话上下文 | `render_session_context.py`（读 manifest，纯 Python） | `render_collected_session_context.py` + `collect-knowledge.js`（需要 Node） | v1 使用 manifest 加载器 |
| 运行策略下发 | 经 `session_context_inject` 的 `agentConfig` | 同左 | 由内核负责，不依赖知识模块是否启用 |
| 产物同步 | 无 | `stages` 键写死为 `biz`/`dev`，只认 `.autobizdevops/state.json` | 改为模块，`stages` 由节点生成 |
| Feature 名 | 不校验（定义了 `SLUG` 但没用） | `validate_path_component` | 强制路径安全 |
| 错误输出 | `{"ok":false,"errors":[...]}`，退出码 1 | 混合（有纯文本输出） | 统一为 JSON（interfaces.md §3.1） |

### 2.3 借鉴 Codex plugin-creator / skill-creator

参考来源：`Open-ai_skills/skills/.system/plugin-creator`（以及它引用的 `skill-creator`）。它只生成 Codex 清单骨架和空目录，不涉及工作流、看板和状态，所以不能替代本脚手架。下面几点可以直接借鉴：

| 借鉴点 | 做法 | 落到本设计 |
|---|---|---|
| **脚手架以技能形式交付**（v1，D9） | 一份 SKILL.md 讲清流程和规则，确定性工作交给脚本；agent 先问清位置等关键信息再执行 | 除了 `autobiz-plugin` CLI，再提供插件开发技能 `autobiz-plugin-creator`（interfaces.md §1.6）：agent 与开发者对话，梳理阶段、节点、产物，写出 `plugin.scaffold.json`，再调用 `build`/`check`；技能的 `short_description` 等文案也由 agent 读完 SKILL.md 后生成。开发者可以只描述流程，不用自己写 JSON |
| Codex 清单完整字段 | `references/plugin-json-spec.md` | 开启 `plugin.codexManifest` 时，`.codex-plugin/plugin.json` 按该规范生成，`interface` 来自输入（output-spec.md §2.2）。宿主不读这份清单（D5），默认不生成 |
| 名称规范化 | 小写连字符、不超过 64 字符；目录名等于清单 `name` | `plugin.id` 同时作为安装目录名和元数据目录名；技能名禁止下划线；`new` 自动规范化并提示 |
| 技能 frontmatter 校验 | `quick_validate.py`：五个允许的键、name/description 约束 | 新增 `SKILL_FRONTMATTER` 规则；宿主不依赖顶层 `version`（D8），`import` 时自动迁到 `metadata` |
| `agents/openai.yaml` 约束 | `short_description` 25–64 字符，`default_prompt` 必须带 `$skill`，可声明 MCP 依赖 | output-spec.md §6.2 |
| `[TODO: …]` 占位 | 桩文件里用显式占位提示待填项 | `check` 对残留占位报 warning，`package` 报 error |
| 不随意覆盖 | 默认不覆盖已有文件，需要 `--force`；已有的桩文件跳过 | 与 §4 的归属模型一致 |

不照搬的地方：

- plugin-creator 把清单所有字段都填上 `[TODO]`，补全前清单就是无效的。本脚手架只输出已声明的字段和有默认值的字段；
- 它的 `quick_validate.py` 依赖 PyYAML，写 JSON 时没有指定 `encoding` 和 `ensure_ascii=False`。本脚手架只用标准库，frontmatter 用受限解析器读取（只支持上面五个键的简单形态），所有文件都按 UTF-8 写入，避免中文被转义或在 Windows 上按 GBK 写入。

## 3. 总体架构

```text
 开发者手写                         脚手架（开发期工具，不随插件发布）
 ┌─────────────────────┐          ┌───────────────────────────────────────────┐
 │ plugin.scaffold.json│────┐     │ load → normalize → validate → compile(IR) │
 │ skills/*/SKILL.md   │────┼────▶│   → modules.contribute → emit → lock      │
 │ agents/*.md         │────┘     └──────────────────┬────────────────────────┘
 └─────────────────────┘                             │
                                                     ▼
 标准化输出（随插件发布，见 output-spec.md）
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ plugin.json（宿主读取）  .codex-plugin/plugin.json（可选）                │
 │ board_core/board_config.json  board.json        ← 生成                   │
 │ board_core/*.py  hooks/*.py  inspect_state.py   ← 托管内核（运行时）      │
 │ hooks/sync_agents.py …  skills/<sync-skill>/    ← 模块（按勾选拷贝）      │
 │ skills/<skill>/SKILL.md（含托管片段）            ← 开发者 + 托管片段       │
 └───────────────────────────────┬──────────────────────────────────────────┘
                                 │ inspectCommands（命令 + JSON 协议，见 interfaces.md §3）
                                 ▼
                         宿主看板 UI / Agent 会话
```

整体分三层：

1. **脚手架**：开发期 CLI `autobiz-plugin`，负责生成、校验、模拟、升级、打包，不随插件发布。
2. **运行时内核**（`board_core` + 宿主入口脚本）：从 lite 运行时泛化而来，完全由配置驱动，不含任何插件专属名称；随插件发布，按版本托管。
3. **模块**：可勾选的能力包，各自声明要拷贝的文件、要补充的配置键和宿主命令（interfaces.md §2）。

插件开发技能 `autobiz-plugin-creator` 位于第 1 层之上：它只负责对话和编写输入配置，生成工作全部交给 CLI。

### 3.1 仓库结构（autobizdevops_plugin_creator）

```text
autobizdevops_plugin_creator/
├── scaffold/                       # CLI 与构建流水线：cli normalize validate compile emit lock simulate
│   └── modules/
│       ├── knowledge/              # module.json  module.py  options.schema.json  files/
│       └── artifact_sync/
├── runtime/                        # 内核模板：board_core/、hooks/ 入口脚本、inspect_state.py
├── skills/autobiz-plugin-creator/  # 插件开发技能：SKILL.md  agents/openai.yaml  references/
├── schemas/                        # plugin-scaffold.schema.json 等
├── examples/                       # lite.plugin.scaffold.json、minimal
├── docs/                           # 设计文档
└── tests/
    ├── golden/                     # 以 lite 为基线：编译结果与其 board_config 比对
    ├── contract/                   # 在临时工作区模拟宿主调用
    └── modules/
```

内核以 lite 的 `board_core` 为起点，产物同步模块以 kanban 的 `autobizdevops-artifact-sync` 最新提交为起点，知识模块以 lite 的 `hooks/` 为起点。三者都带着各自已有的测试迁入。

## 4. 文件归属

每个输出文件都有明确的归属。归属决定了 build 和 upgrade 时脚手架会怎么处理这个文件，归属关系记录在 `.scaffold/lock.json`。

| 归属 | 示例 | build 时 | 开发者能否修改 |
|---|---|---|---|
| `generated` | `board_config.json`、`board.json`、`board_core/runtime.json`、`plugin.json`、`.codex-plugin/plugin.json`（可选） | 每次重写（运行期回写字段按 §6.1 处理） | 不能，改输入后重新 build |
| `managed` | `board_core/*.py`、`hooks/init_workspace.py`、`inspect_state.py` | 仅在内核版本变化时替换；哈希与 lock 不符时拒绝覆盖 | 不能；确需修改请提 issue 给脚手架 |
| `module` | `hooks/sync_agents.py`、`skills/<sync-skill>/**` | 同 managed，跟随模块版本 | 同 managed；模块配置文件由输入生成 |
| `seeded` | `skills/<skill>/SKILL.md`、`agents/openai.yaml` | 缺失时创建；已存在时只更新托管片段 | 可以，托管片段以外随意修改 |
| `developer` | `references/**`、`agents/*.md`、`hooks/hooks.json`、`.mcp.json` | 不读写 | 可以 |

**托管片段**：`SKILL.md` 中用 HTML 注释界定的区域（`<!-- scaffold:begin state -->` … `<!-- scaffold:end state -->`），由脚手架维护。节点改名、改 checkpoint 前缀或改产物后，build 会同步更新片段，开发者写的正文不受影响（output-spec.md §6）。

## 5. 构建流水线

| 步骤 | 做什么 | 失败时 |
|---|---|---|
| load | 读 `plugin.scaffold.json`，按 Schema 校验结构 | 报 `INPUT_SCHEMA`，指出 JSON Pointer |
| normalize | 填默认值，展开 `inputs`/`outputs` 引用，计算 checkpoint、order、文案 | — |
| validate | 语义校验：引用、顺序、唯一性、路径安全、技能文件、占位符（input-config.md §5） | 汇总全部问题后退出码 1，不写任何文件 |
| compile | 生成内部表示 `PluginIR`（节点、产物、checkpoint 序列、命令模板） | — |
| contribute | 每个已启用模块基于 IR 产出 `Contribution`（文件、配置补丁、命令） | 模块报错，例如 `MODULE_OPTION` |
| emit | 合并内核与模块输出，按归属规则写文件；写之前检查 managed 文件是否漂移 | 漂移时报 `DRIFT_MANAGED`，可用 `--force` 覆盖 |
| lock | 写 `.scaffold/lock.json`：脚手架版本、内核版本、模块版本、输入摘要、各文件哈希 | — |

`check` 命令额外做两件事：一是 `--check` 模式重放 build 并比较结果，发现生成文件被手改即报错；二是在临时工作区跑一遍契约测试（建项目 → 建 Feature → 逐个 checkpoint 推进 → 查看板 JSON）。

## 6. 关键设计点

### 6.1 运行期回写字段

`pull_knowledge` 会把同步结果写回 `board_config.json` 和 `board.json`。以下字段归运行期所有：

| 字段 | 写入方 | `build` | `package` |
|---|---|---|---|
| `supported_deploy_units` | `hooks/sync_agents.py` | 保留当前值 | 重置为输入中的 `supportedDeployUnits` |
| `inspectCommands.<platform>.knowledge_path` | `hooks/sync_agents.py` | 保留当前值 | 重置为 `${pluginPath}/sys` |

打包时重置，可以避免把本机路径和本地同步结果带进发布包。

### 6.2 运行策略和知识注入解耦

宿主通过 `session_context_inject` 的返回值拿到当前节点的 `agentConfig`（来自 `runtimePolicy`），这和知识注入走的是同一个命令。因此：

- 内核始终提供 `hooks/render_session_context.py`，负责解析策略节点（与宿主 nextAction 同源，按“nextAction 目标节点 → 当前节点 → 全局默认”三级降级），输出 `agentConfig`；
- 知识模块以 **Provider** 形式注册，负责生成 `sessionContext` 与 `agentmdLoadStatus`（interfaces.md §2.4）；
- 未启用知识模块时，`sessionContext` 为空字符串，`agentConfig` 照常返回。

这需要把 lite 中 1100 多行的 `render_session_context.py` 拆成两部分：内核保留策略解析，知识模块承担其余加载逻辑。

### 6.3 模块从全栈版剥离时要做的改造

**产物同步**（来源：`autobiz_kanban/skills/autobizdevops-artifact-sync`）：

- `load_config` 不再要求 `stages` 恰好是 `{biz, dev}`，改为接受输入中声明的任意阶段 id；
- 上传地址 `UPLOAD_URL` 和 5 MiB 上限改为从模块配置读取；
- 用 `board_core.api` 定位工作区、Feature 目录和状态，不再写死 `.autobizdevops/state.json` 和 `.autobizdevops/features/`，也不再从 `hooks.paths` 导入。这样隔离布局和 legacy 布局都能用；
- hooks.ndjson 中的 `pluginId` 取自配置（目前写死为 `AUTOBIZDEVOPS-PLUGIN`）；
- 同步配置 `config/artifact-sync.json` 由节点输出自动生成（`sync: false` 的产物除外），`allowedCheckpoints` 由 `allowedFrom` 推导；
- `FEATURE_API_DETAIL.md` 的生成降为子选项 `apiDetail`，只对含编码节点的插件开启；
- 看板入口：kanban 在 `9411fc3` 新增了顶层键 `artifact_sync`（与 `knowledge_config` 同构，用于在看板上带出同步技能），改由模块生成，对应子选项 `entry`；
- 工号确认（`--employee-id`，上传路径为 `{PROJECT_CODE}/DEV/Features/{feature}/{employeeId}/`）也在 `9411fc3` 中加入。模块以该提交为起点，照搬这套确认流程。

**知识沉淀与解析**（来源：lite 的 `sync_agents.py`、`agents_repo.py`、`render_session_context.py`、`paths.py`）：

- `sync_agents.write_board_config` 改为只写 §6.1 列出的字段；
- 加载逻辑改为 Provider；
- 知识沉淀（`knowledge_config.nextAction`，即宿主的 `knowledge-sync`）作为子选项 `sedimentation`，只生成配置，不带脚本。

### 6.4 内核从 lite 泛化时要做的改造

- `PLUGIN_ID` 和目录布局从生成的 `board_core/runtime.json` 读取（目前 `PLUGIN_ID` 写死为 `autodev-planning-kanban`，元数据目录写死为 `.autobizdevops`）。之所以不放进 `board_config.json`，是为了不给宿主读取的配置增加未知键；
- 所有路径都通过 `metadata_dir()` 推导，不得在其他地方拼接 `.autobizdevops`；
- `resolve_feature` 增加路径安全校验；
- `load_config` 中“技能必须存在”的校验保留，同时支持输入中声明嵌套技能路径（v2）；
- 删除未被引用的 `board_core/context.py`（引用了不存在的 `references/workflow.md` 和旧技能名 `autodev-onlycode`），由生成的 `references/workflow.md` 和技能托管片段替代；
- 新增 `board_core/api.py`，作为给技能脚本和模块使用的稳定 API（interfaces.md §4）。

### 6.5 同一项目安装多个插件

现状：lite 和 kanban 都把状态写在 `<project>/.autobizdevops/state.json`，而且格式不兼容（lite 是 `schemaVersion: 1` 并带 `pluginId`，kanban 是 `autobizdevops.state.v3` 且不带 `pluginId`），产物也都放在 `.autobizdevops/features/<feature>/`。两个插件装到同一个项目就会冲突。

方案：按 `pluginId` 划分命名空间，每个插件拥有独立的状态文件、锁和产物目录。

```text
<pluginWorkspace>/<projectDir>/.autobizdevops/
├── doc-review/                    # isolated 布局（新插件默认）
│   ├── state.json                 # { "schemaVersion": 1, "pluginId": "doc-review", "features": {…} }
│   ├── .state.lock
│   └── features/<feature>/…
├── another-plugin/…
├── state.json                     # legacy 布局：已有插件（lite）沿用
└── features/<feature>/…
```

| 规则 | 说明 |
|---|---|
| 布局是插件级的静态配置 | `runtime.layout`：`isolated`（默认）或 `legacy`。不能按项目自动判断，因为 `system_prompt_inject` 中的 `FEATURE_DIR` 是静态模板 |
| 每个插件只读写自己的命名空间 | 不维护跨插件共享的 state.json：各插件只认识自己的 checkpoint，共享文件意味着要互相校验对方的数据，而且多版本内核并存时容易互相破坏 |
| state.json 仍记录 `pluginId` 并校验 | 防止目录被拷贝或误放；不匹配时拒绝读写 |
| 保留目录名 | `plugin.id` 不得是 `features`、`archive`、`issues`、`reviews`、`logs`、`plugins`，以免与 legacy 布局和 kanban 现有目录冲突 |
| 同名 Feature | 不同插件可以有同名 Feature，彼此互不影响 |
| legacy 布局 | 只为迁移已有插件（例如 lite）而保留，保证它们已有的项目不受影响。`import` 发现源插件使用根目录布局时自动设为 `legacy`。项目里最多只能有一个 legacy 插件，但它可以和任意多个 isolated 插件共存 |
| 迁移 | 内核不会自动搬迁目录。v1 不提供迁移命令；如果确实需要，以后再提供显式的 `migrate-layout`，见 §9 |

受影响的输出：`system_prompt_inject` 中的 `FEATURE_DIR`、`feature_status` 返回的 `path`/`watchRefs`/`hookLogRefs`、`create_*` 返回的 `statePath`/`featureDir`、产物同步模块读取的 Feature 目录。所有这些都由 `board_core.api.metadata_dir()` 统一推导。

## 7. v2 扩展预留

以下字段名在 v1 的 Schema 中先不开放，内核和 board_config 中对应的键也暂不生成，但命名已对齐 kanban，避免日后破坏兼容：

| 能力 | kanban 中的形态 | 预留输入字段 |
|---|---|---|
| 模板子集（精简路线） | `workflow.templates.<id>.kind = nodeSubset` | `templates[]` |
| 动态阶段（例如详细设计） | `workflow.dynamicStages[]` | `dynamicStages[]` |
| 回流修复 | `needs_fix` checkpoint、`blocked` 状态 | `nodes[].reopenTargets` |
| 跳过节点 | `skip_node` 命令、`skipPolicy` | `board.skipPolicy` |
| 归档终态节点 | `ops.archive` 只有 `archived` 一个 checkpoint | `nodes[].terminal` |
| 声明式校验 | `validators`、`guards`、`hookDefinitions` | `nodes[].validators` |
| collector 知识加载 | `collect-knowledge.js` | `modules.knowledge.loader = "collector"` |
| 模块自带宿主钩子 | `hooks/hooks.json` 片段 | `module.json` 中的 `contributes.hooks` |

## 8. 已确认决策（2026-10-16）

| # | 决策 | 落到 |
|---|---|---|
| D1 | 关闭知识模块时，`knowledge_path` 和 `pull_knowledge` 直接不生成 | output-spec.md §3.2；interfaces.md §2.3 |
| D2 | 宿主命令中的单值占位符一律写成 `"${pluginPath}"` 形式（加双引号）；`${projectDirs...}` 和 `${selectedDeployUnits}` 由宿主整体转义，不加引号 | output-spec.md §3.2 |
| D3 | state.json 记录 `pluginId`；同一项目使用多个插件时，按 `pluginId` 隔离插件产物目录 | §6.5；output-spec.md §4；interfaces.md §3、§4 |
| D4 | 脚手架建独立仓库 | §3.1 |
| D5 | 宿主读取根目录 `plugin.json`。`.codex-plugin/plugin.json` 改为可选输出（`plugin.codexManifest`），不生成 `marketplace.json` | output-spec.md §2 |
| D6 | 看板 `slashSkill` 用于带出技能，写不带命名空间的技能名；不受 Codex 命名空间影响 | input-config.md §3.6 |
| D7 | 宿主 `hooks.json` 只写入根 `plugin.json`，不写入 Codex 清单 | output-spec.md §2 |
| D8 | 宿主不依赖技能 frontmatter 中的 `version`。`SKILL_FRONTMATTER` 定为 error，`import` 自动把 `version`、`author` 迁到 `metadata` | input-config.md §5；output-spec.md §6.1 |
| D9 | 插件开发技能 `autobiz-plugin-creator` 进入 v1 | §2.3；interfaces.md §1.6 |

## 9. 遗留问题

1. **产物同步的服务端路径不含 `pluginId`**：上传路径是 `{PROJECT_CODE}/DEV/Features/{feature}/{employeeId}/`。D3 之后，同一项目中两个插件可以有同名 Feature，上传时会互相覆盖。是否在路径中加入 `pluginId`（例如 `{PROJECT_CODE}/DEV/Features/{pluginId}/{feature}/{employeeId}/`）？这需要和服务端约定，也会影响 kanban 已上传数据的位置。
2. **legacy 项目是否需要迁移**：按目前设计，lite 迁入脚手架后继续使用 legacy 布局，已有项目不受影响。是否需要提供 `migrate-layout` 命令，把旧项目搬到 `.autobizdevops/<pluginId>/`？如果需要，还要确认宿主侧是否缓存了旧路径（例如已打开的产物链接）。
3. **kanban 是否也迁入脚手架**：kanban 依赖的模板子集、动态阶段、needs_fix 等能力在 v2 才会支持，v1 只覆盖 lite 这一类线性插件。kanban 现有的 state.json 不带 `pluginId`，在 v2 之前，它与 legacy 插件不能装在同一个项目里，但可以和 isolated 插件共存。
