# AutoBiz 看板插件脚手架：整体设计（v1 草案）

## 1. 目标与三方职责

| 参与方 | 职责 |
|---|---|
| 插件开发者 | 定义流程，提供技能、模板、业务校验器和自定义扩展 |
| 脚手架与运行框架 | 生成固定入口、编译配置，提供流程查询、状态管理及宿主适配 |
| DevClaw | 展示看板、发起会话、传入运行上下文、调用插件入口 |

下文的“宿主”均指 DevClaw；`board.*`、`session.*`、`knowledge.*` 分别指 `modules/board.json`、`modules/session.json`、`modules/knowledge.json` 中的字段。

插件开发者只做两件事：

1. 写核心配置：`workflow.json`（核心流程，只写节点、技能绑定、执行顺序、输入输出、校验命令和按需开启的流程规则）、入口文件 `plugin.scaffold.json`（插件基础信息和对模块配置的引用），以及 `modules/` 下按需拆分的看板、会话与 Agent、知识、产物同步模块配置（D18）。核心配置只写决策，插件运行时使用的是由它编译出来的配置（D19）；不需要改默认值的模块不用写文件，所以新插件的入口文件只有几行。这些配置都可以由初始化向导问答生成，修改后会被自动检测（D20）；
2. 提供技能资源：技能正文、模板、执行脚本、业务校验器，以及 `hooks/` 等自定义扩展。

固定入口（`runtime/` 下的脚本）、编译后的内部配置、宿主接口 `board_core/`（`board_config.json` 中的三平台宿主命令、`modules.json` 中的模块与看板入口）、状态机、技能中的状态接入说明，以及知识、产物同步等模块，都由脚手架生成或托管。输入分类与生成内容的对应关系见 [input-config.md §1.1](input-config.md)。

v1 范围：

- 工作流：节点顺序即主干执行顺序，每个节点有 `<prefix>_in_progress`、`<prefix>_done` 两个 checkpoint；可以有一个终态节点；`rules` 中按需开启的流程规则：动态阶段、跳过节点（D22）；
- 节点输入和输出都可以标可选；
- 节点完成判定：框架检查产物是否存在，再执行开发者提供的单行校验命令（§6.6）；
- 看板可选能力：**知识沉淀入口**（`knowledgeSedimentation`）；
- 可选的**产物同步模块**（`modules/artifactSync.json`，D30）：把产物上传到外部服务，并在看板上生成同步入口；
- 可选的**知识模块**：清单解析、发布单元查询、知识组装（默认由插件用内置的 collector 组装脚本完成，插件可以直接替换这个脚本，也可以交给 DevClaw）；
- 初始化向导与插件开发技能 `autobiz-plugin-creator`：开发者用问答或对话描述流程，由向导或 agent 写配置并调用 CLI；
- 同一项目可以安装多个插件，各插件的状态和产物按 `pluginId` 隔离；
- 看板事件推送（P0，D21）：插件在状态提交后把看板数据推送给 DevClaw 的本机服务，DevClaw 不再为刷新看板反复启动 Python 进程；

- 运行时只依赖 Python 3.9+ 标准库（知识仓库同步另需 Git；内置知识组装脚本优先用 Node 调用 collector，没有 Node 时退回纯 Python 的清单映射加载）。

脚手架位于独立仓库 `autobizdevops_plugin_creator`（即本仓库，结构见 §3.1）。§8 汇总了已经确认的决策，§10 列出本次相对初稿的调整。

两个参考插件是 lite（仓库 `autobizdevops_lite`）和全栈版（仓库 `autobiz_kanban`）。全栈版用到的流程能力除回流修复（`needs_fix`）外都在 v1 中支持，样例见 [examples/fullstack/](../examples/fullstack/)；它自有的校验与钩子配置（声明式校验器清单、编译守卫、人工确认关卡、回滚归档清单）留在插件自己的文件中（§6.8，D23）。回流修复、模板子集和 collector 知识组装预留到 v2（§7）。

文档索引：

| 文档 | 内容 |
|---|---|
| [input-config.md](input-config.md) | 用户输入：输入分类、`workflow.json`、入口文件与模块配置文件的字段、默认值、推导规则、校验规则 |
| [output-spec.md](output-spec.md) | 插件标准化输出：目录、清单、宿主接口 board_core、内部配置、运行期数据、技能格式 |
| [interfaces.md](interfaces.md) | 接口：CLI 与初始化向导、模块契约、宿主命令协议、看板事件推送、运行框架入口与内部库 |
| [diagrams.md](diagrams.md) | 框架图与核心机制图（Mermaid）：整体架构、运行期调用、配置分层、构建、自动检测、状态推进、会话组成、知识模块、多插件隔离 |
| [mods.md](mods.md) | 草案：DevClaw mods 机制下的插件初始化与热更新（开发 mod、运行 mod、变更等级、状态迁移） |
| [rpc.md](rpc.md) | 草案：DevClaw 与插件的 JSON-RPC 双向通信（常驻进程、握手与鉴权、方法、降级） |
| [schemas/workflow.schema.json](../schemas/workflow.schema.json) | 核心流程 JSON Schema |
| [schemas/plugin-scaffold.schema.json](../schemas/plugin-scaffold.schema.json) | 入口文件 JSON Schema |
| [schemas/modules/](../schemas/modules/) | 看板、会话、知识模块配置的 JSON Schema |
| [examples/lite/](../examples/lite/) | 复刻 autobizdevops_lite 的完整输入样例 |
| [examples/fullstack/](../examples/fullstack/) | 按全栈版（autobiz_kanban）编写的完整输入样例，用到全部流程规则（input-config.md §9.2） |
| [examples/minimal/](../examples/minimal/) | 两个节点、没有模块配置文件的最小样例（input-config.md §8） |

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

初稿已用临时编译原型验证：单文件输入约 110 行（使用 `layout: legacy`），编译结果与 lite 现有配置逐字段一致。差异只有三处：

- 两处是运行期回写字段。其中 win32 的 `knowledge_path` 已被本地同步写成个人机器路径 `C:\Users\80319167\...` 并提交进了仓库。v1 不再回写任何配置文件（§6.1）；
- 一处是样例额外启用的产物同步带来的 `artifact_sync` 入口（lite 本身没有这个能力）。

本次调整后，输入拆成 [examples/lite/](../examples/lite/) 下的五个文件（入口、流程、三个模块配置），内容基本不变，只是换了位置；`plan.md` 对旧文件名 `PLAN.md` 的回退不再表达（interfaces.md §5）。框架入口迁到 `runtime/` 后，`inspectCommands` 中的脚本路径不再与 lite 一致，金样测试改为比对 `inspectCommands` 脚本路径以外的部分（§3.1）。

这些推导结果原来写在 `board_config.json` 中，一份文件同时给 DevClaw 和插件脚本读。v1 把两者分开（D31）：`board_config.json` 只剩宿主命令，流程和文案编译进 `runtime/config/`，由命令输出给 DevClaw。

### 2.2 两个插件的差异与标准化取舍

| 方面 | lite | 全栈版 | 脚手架标准 |
|---|---|---|---|
| 清单 | 根目录 `plugin.json`（`skills: ./skills/`） | 根目录 `plugin.json` + skills/mcpServers/hooks | DevClaw 只读根 `plugin.json`；`.codex-plugin/plugin.json` 可选（D5） |
| 状态内核 | `board_core/runtime.py` 单文件，约 15KB | workflow_compiler 等 9 个模块，约 125KB | 以 lite 为基础泛化，拆成只读的 `query.py` 和负责变更的 `engine.py` 两个内部库（D17） |
| 入口位置 | `hooks/` 下的脚本 + 根目录 `inspect_state.py` | `hooks/` 下的脚本 | 框架入口统一放在 `runtime/`；`hooks/` 只放开发者扩展（D16） |
| 宿主命令 | 无 `-X utf8`，路径加引号 | 有 `-X utf8`，路径不加引号 | 默认 `-X utf8`；单值占位符一律写成 `"${pluginPath}"` 形式（D2） |
| 元数据目录 | `.autobizdevops/state.json`（带 `pluginId`） | `.autobizdevops/state.json`（`autobizdevops.state.v3`，不带 `pluginId`） | 默认 `.autobizdevops/<pluginId>/`，同一项目可装多个插件（D3）；`legacy` 布局仅用于迁移已有插件 |
| 状态脚本 | `update_state.py`，另有 `update_checkpoint.py` 别名 | `update_checkpoint.py` | `runtime/workflow/update_state.py` 为唯一入口，不再保留别名 |
| 完成判定 | 必需产物存在且非空 | validators / guards | 框架只检查存在性，内容由节点校验命令判断（D13、D14） |
| 会话上下文 | `render_session_context.py`（读 manifest，纯 Python） | `render_collected_session_context.py` + `collect-knowledge.js`（需要 Node） | 默认会话入口输出流程上下文、运行策略和知识组装结果。知识组装默认用全栈版的 collector（内置组装脚本 `render_collected_session_context.py`），lite 也改用它；插件可以直接替换这个脚本，组装方也可以选 DevClaw（§6.2，D26） |
| 运行策略下发 | 经 `session_context_inject` 的 `agentConfig` | 同左 | 由会话模块负责（`session.policies`），不依赖知识模块是否启用 |
| 产物同步 | 无 | `stages` 键写死为 `biz`/`dev`，只认 `.autobizdevops/state.json` | 改为可选模块 `artifactSync`（`modules/artifactSync.json`，D30），`stages` 由节点生成 |
| Feature 名 | 不校验（定义了 `SLUG` 但没用） | `validate_path_component` | 强制路径安全 |
| 错误输出 | `{"ok":false,"errors":[...]}`，退出码 1 | 混合（有纯文本输出） | 统一为 JSON（interfaces.md §3.1） |
| 流程规则 | 纯线性 | 动态阶段、`needs_fix` 回流、`skip_node`、归档终态节点；模板子集已下架 | 动态阶段、跳过节点写在 `workflow.json` 的 `rules` 中，终态节点写在节点上，checkpoint 由 build 推导（D22）；`needs_fix` 回流和模板子集预留到 v2 |
| 输入输出 | 全部必需 | `required: false` 与 `extract.degrade`，可选输入另起 id（如 `prd_optional`） | `inputs` 中的 `{id, optional}`、`outputs` 中的 `{path, optional}`，引用同一个产物 id；不再输出 `extract.degrade`，输入缺失时怎么做写在技能正文中 |
| 代码产物 | `dev.code` 没有输出 | `dev.code` 只输出证据流，代码是否提交由技能和 `stage_gate.py` 自己判断 | `outputs` 中的 git 产物 `{git: {repos, branch, require}}`：节点开始时记录各仓库基线，完成时查仓库状态（D25） |
| 技能目录 | `skills/<skill>/` | `skills/<分组>/<skill>/` | 两种都支持，build 只找这两层（input-config.md §5） |

### 2.3 借鉴 Codex plugin-creator / skill-creator

参考来源：`Open-ai_skills/skills/.system/plugin-creator`（以及它引用的 `skill-creator`）。它只生成 Codex 清单骨架和空目录，不涉及工作流、看板和状态，所以不能替代本脚手架。下面几点可以直接借鉴：

| 借鉴点 | 做法 | 落到本设计 |
|---|---|---|
| **脚手架以技能形式交付**（v1，D9） | 一份 SKILL.md 讲清流程和规则，确定性工作交给脚本；agent 先问清位置等关键信息再执行 | 除了 `autobiz-plugin` CLI 和初始化向导，再提供插件开发技能 `autobiz-plugin-creator`（interfaces.md §1.6）：agent 与开发者对话，梳理阶段、节点、产物和校验，写出 `workflow.json`、入口文件和需要的模块配置，再调用 `build`/`check`；技能的 `short_description` 等文案也由 agent 读完 SKILL.md 后生成。开发者可以只描述流程，不用自己写 JSON |
| Codex 清单完整字段 | `references/plugin-json-spec.md` | 开启 `plugin.codexManifest` 时，`.codex-plugin/plugin.json` 按该规范生成，`interface` 来自输入（output-spec.md §2.2）。DevClaw 不读这份清单（D5），默认不生成 |
| 名称规范化 | 小写连字符、不超过 64 字符；目录名等于清单 `name` | `plugin.id` 同时作为安装目录名和元数据目录名；技能名禁止下划线；初始化向导自动规范化并提示 |
| 技能 frontmatter 校验 | `quick_validate.py`：五个允许的键、name/description 约束 | 新增 `SKILL_FRONTMATTER` 规则；DevClaw 不依赖顶层 `version`（D8），导入技能时自动迁到 `metadata` |
| `agents/openai.yaml` 约束 | `short_description` 25–64 字符，`default_prompt` 必须带 `$skill`，可声明 MCP 依赖 | output-spec.md §6.2 |
| `[TODO: …]` 占位 | 桩文件里用显式占位提示待填项 | `check` 对残留占位报 warning，`package` 报 error |
| 不随意覆盖 | 默认不覆盖已有文件，需要 `--force`；已有的桩文件跳过 | 与 §4 的归属模型一致 |

不照搬的地方：

- plugin-creator 把清单所有字段都填上 `[TODO]`，补全前清单就是无效的。本脚手架只输出已声明的字段和有默认值的字段；
- 它的 `quick_validate.py` 依赖 PyYAML，写 JSON 时没有指定 `encoding` 和 `ensure_ascii=False`。本脚手架只用标准库，frontmatter 用受限解析器读取（只支持上面五个键的简单形态），所有文件都按 UTF-8 写入，避免中文被转义或在 Windows 上按 GBK 写入。

## 3. 总体架构

```text
 插件开发者                             脚手架（开发期工具，不随插件发布）
 ┌──────────────────────┐             ┌─────────────────────────────────────────────┐
 │ plugin.scaffold.json  │──┐          │ 初始化向导 / autobiz-plugin-creator          │
 │ workflow.json         │──┤          │ load → normalize → validate → compile(IR)   │
 │ modules/*.json        │──┤          │   → modules.contribute → emit → manifest    │
 │ skills/ agents/ hooks/│──┘          └──────────────────────┬──────────────────────┘
 └──────────────────────┘                                     │
                                                              ▼
 插件（随包发布，见 output-spec.md）
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ plugin.json  board_core/board_config.json  modules.json      ← generated      │
 │ runtime/adapters/*  runtime/session/*                        ← 宿主适配入口    │
 │ runtime/workflow/update_state.py                             ← 模型入口        │
 │ runtime/common/query.py  engine.py                           ← 内部库          │
 │ runtime/knowledge/*                                          ← 知识模块        │
 │ runtime/config/*  runtime/build-manifest.json                ← generated      │
 │ skills/*（含状态接入片段）  hooks/  agents/                    ← 开发者资源      │
 └───────────┬───────────────────────────────────┬───────────────────────────────┘
             │ inspectCommands（命令 + JSON 协议） │ update_state.py
             ▼                                   │
     DevClaw（看板 / 会话）──── 拉起会话 ────▶  模型（执行技能）
```

运行期的调用关系：

```text
DevClaw ─▶ runtime/adapters/inspect_*.py、runtime/session/render_session_context.py ─import─▶ common/query.py（只读）
DevClaw ─▶ runtime/adapters/init_workspace.py、init_feature.py ──────────────────────import─▶ common/engine.py（初始化）
模型    ─▶ runtime/workflow/update_state.py ─import─▶ common/engine.py ─执行─▶ 节点校验命令（开发者）
知识模块接入方 ─▶ runtime/knowledge/inspect_deploy_units.py
写入口（init_workspace.py、init_feature.py、update_state.py）─提交后推送─▶ DevClaw 看板事件服务（board/changed）
默认会话入口 ─执行─▶ 知识组装脚本 runtime/knowledge/render_collected_session_context.py（内置，插件可替换）
```

整体分三层：

1. **脚手架**：开发期 CLI `autobiz-plugin`，负责初始化、生成、校验、模拟、升级、打包，不随插件发布。初始化向导和插件开发技能 `autobiz-plugin-creator` 位于这一层之上：它们只负责问答和编写输入配置，生成工作全部交给 CLI。
2. **运行框架**（`runtime/`）：固定入口 + 内部库 `query.py`/`engine.py` + 编译配置。从 lite 运行时泛化而来，完全由配置驱动，不含任何插件专属名称；随插件发布，按版本托管。
3. **模块**：核心模块 `board`（看板接入）和 `session`（会话与 Agent）始终启用；`knowledge`（知识）和 `artifactSync`（产物同步）按配置启用。各模块声明要拷贝的文件、要补充的配置和宿主命令（interfaces.md §2）。

### 3.1 仓库结构（autobizdevops_plugin_creator）

```text
autobizdevops_plugin_creator/
├── scaffold/                       # CLI、初始化向导与构建流水线：cli wizard normalize validate compile emit manifest simulate
│   └── modules/
│       ├── board/                  # 看板模块：adapters 模板、命令映射、知识沉淀入口
│       ├── session/                # 会话模块：默认会话入口、策略
│       ├── knowledge/              # module.json  module.py  options.schema.json  files/
│       └── artifact_sync/
├── runtime/                        # 运行框架模板：workflow/  adapters/  session/  common/
├── skills/autobiz-plugin-creator/  # 插件开发技能：SKILL.md  agents/openai.yaml  references/
├── schemas/                        # workflow.schema.json、plugin-scaffold.schema.json、modules/*.schema.json
├── examples/                       # lite/、fullstack/、minimal/
├── docs/                           # 设计文档
└── tests/
    ├── golden/                     # 以 lite、全栈版为基线：命令输出的看板数据与其 board_config 中对应内容比对（inspectCommands 脚本路径及 input-config.md §9.2 列出的差异除外）
    ├── contract/                   # 在临时工作区模拟宿主调用
    └── modules/
```

运行框架以 lite 的 `board_core` 为起点，产物同步模块以全栈版的 `autobizdevops-artifact-sync` 最新提交为起点，知识模块以 lite 的 `hooks/` 为起点。三者都带着各自已有的测试迁入。

## 4. 文件归属

每个输出文件都有明确的归属。归属决定了 build 和 upgrade 时脚手架会怎么处理这个文件，归属关系记录在 `runtime/build-manifest.json`。

| 归属 | 示例 | build 时 | 开发者能否修改 |
|---|---|---|---|
| `generated` | `plugin.json`、`.codex-plugin/plugin.json`（可选）、`board_core/board_config.json`、`board_core/modules.json`、`runtime/config/*`、`runtime/build-manifest.json` | 每次重写 | 不能，改输入后重新 build |
| `managed` | `runtime/workflow/*`、`runtime/adapters/*`、`runtime/session/*`、`runtime/common/*` | 仅在运行框架版本变化时替换；哈希与 build-manifest 不符时拒绝覆盖 | 不能；确需修改请提 issue 给脚手架 |
| `module` | `runtime/knowledge/*`、`skills/<sync-skill>/**` | 同 managed，跟随模块版本。例外：内置知识组装脚本 `runtime/knowledge/render_collected_session_context.py` 与记录不一致时视为插件的替换，保留不动，不报 drift | 同 managed，内置知识组装脚本除外：插件可以整个替换它（input-config.md §4.4）；模块配置文件由输入生成 |
| `seeded` | `skills/<skill>/SKILL.md`、`agents/openai.yaml`、`.githooks/pre-commit`、`.gitignore` | 缺失时创建；已存在时只更新托管片段 | 可以，托管片段以外随意修改 |
| `developer` | `plugin.scaffold.json`、`workflow.json`、`modules/*.json`、`skills/<skill>/scripts/**`、`references/**`、`hooks/**`、`agents/*.md`、`.mcp.json` | 不读写（配置文件只读） | 可以 |

**托管片段**：`SKILL.md` 中用 HTML 注释界定的区域（`<!-- scaffold:begin state -->` … `<!-- scaffold:end state -->`），由脚手架维护，也就是交付技能中的“状态接入说明”。节点改名、改 checkpoint 前缀、改产物、改模板或校验命令后，build 会同步更新片段，开发者写的正文不受影响（output-spec.md §6）。

## 5. 构建流水线

| 步骤 | 做什么 | 失败时 |
|---|---|---|
| load | 读入口文件 `plugin.scaffold.json`，再读它引用的 `workflow.json` 和 `modules/*.json`，各自按 Schema 校验结构 | 报 `INPUT_SCHEMA` 或 `MODULE_FILE_MISSING`，指出文件和 JSON Pointer |
| normalize | 按 Schema 的 `default` 补全缺省字段（默认值的唯一来源，D27），再计算推导值；从 `outputs` 汇总产物表，统一产物路径为数组，推断产物类型，计算 checkpoint、order、文案 | — |
| validate | 语义校验：引用、顺序、唯一性、路径安全、技能文件、命令格式、占位符（input-config.md §7） | 汇总全部问题后退出码 1，不写任何文件 |
| compile | 生成内部表示 `PluginIR`（节点、产物、checkpoint 序列、策略、命令模板） | — |
| contribute | 每个模块基于 IR 产出 `Contribution`（文件、配置补丁、内部配置、命令） | 模块报错，例如 `MODULE_OPTION` |
| emit | 合并运行框架与模块输出，按归属规则写文件；写之前检查 managed 文件是否漂移 | 漂移时报 `DRIFT_MANAGED`，可用 `--force` 覆盖 |
| manifest | 写 `runtime/build-manifest.json`：脚手架版本、运行框架版本、模块版本、输入摘要、各文件哈希 | — |

load、normalize、validate 前三步单独执行就是 `autobiz-plugin lint`，它也用于提交前钩子和 agent 的每轮修改之后（§6.7）。

`check` 命令在 lint 之外再做两件事：一是 `--check` 模式重放 build 并比较结果，发现生成文件被手改即报错，同时校验 `runtime/config/` 下各文件引用的节点、产物一致；二是在临时工作区跑一遍契约测试（建项目 → 建 Feature → 逐个 checkpoint 推进 → 查看板 JSON，跳过节点校验命令）。

## 6. 关键设计点

### 6.1 宿主接口与内部配置分开

全栈版和 lite 的 `board_config.json` 有两个读者：DevClaw 读 `inspectCommands` 和看板入口，插件自己的脚本再从同一份文件读流程、标签和 `nextAction`，以复用配置。按模块拆分后，每个模块都有自己的编译配置，脚本读固定的那几份即可，不需要再借道 board_config（D31）：

| 文件 | 读者 | 内容 |
|---|---|---|
| `board_core/board_config.json` | DevClaw | `apiVersion`、`inspectCommands` |
| `board_core/modules.json` | DevClaw | 开启了哪些模块、`boardEvents`、看板入口 `knowledge_config`、`artifact_sync` |
| `runtime/config/*.json` | 运行框架、adapter、模块脚本 | 流程（`flow.json`）、看板文案（`board.json`）、运行策略（`session.json`）、知识（`knowledge.json`） |

DevClaw 看板上的流程数据全部来自命令输出（interfaces.md §3.3）。`board_core/` 只由 build 写入，运行期不回写：原来回写的 `supported_deploy_units` 改由 `deploy_units` 命令给出，`knowledge_path` 固定为 `${pluginPath}/<knowledge.root>`，同步脚本只更新知识目录。这样也就不存在“把本机路径带进发布包”的问题，build 和 package 不需要保留或重置任何字段。

### 6.2 会话内容的组成

DevClaw 通过 `session_context_inject` 拿到会话内容。默认会话入口 `runtime/session/render_session_context.py` 由会话模块提供，始终生成，按顺序拼装：

| 部分 | 来源 | 条件 |
|---|---|---|
| 流程上下文 | `query.py`：产物目录、当前节点与状态、策略目标节点的技能、输入输出及存在情况、下一节点 | 始终 |
| `agentConfig` | `session.policies`：按“nextAction 目标节点 → 当前节点 → 全局默认”三级降级 | 始终 |
| 知识组装结果 | 组装脚本 `render_collected_session_context.py` 的输出：默认为内置版本，插件替换后为插件的版本（interfaces.md §4.5） | 知识模块启用且 `assembler = plugin` |

因此：

- 运行策略由会话模块负责，与知识模块是否启用无关；
- 组装方为 `devclaw` 时，插件只通过 `inspect_deploy_units.py` 提供清单解析结果，知识段由 DevClaw 自己组装；
- 组装脚本只负责知识段，插件替换它也一样：流程上下文和 `agentConfig` 始终由默认入口给出，组装脚本不能改写；
- 内置组装脚本兜底读取 `<localRepoPath>/AGENTS.md` 和 `<sessionWorkspacePath>/AGENTS.md`，知识仓库中没有 collector 知识的插件也能直接用它。

这需要把 lite 中 1100 多行的 `render_session_context.py` 和全栈版的 `render_collected_session_context.py` 拆开：策略解析和流程上下文留在会话模块，清单解析放进 `inspect_deploy_units.py`，知识组装放进知识模块的内置组装脚本。lite 和全栈版都改用 collector 组装。

### 6.3 模块从全栈版剥离时要做的改造

**产物同步**（来源：`autobiz_kanban/skills/autobizdevops-artifact-sync`，改为可选模块 `artifactSync`，配置在 `modules/artifactSync.json`）：

- `load_config` 不再要求 `stages` 恰好是 `{biz, dev}`，改为接受输入中声明的任意阶段 id；
- 上传地址 `UPLOAD_URL` 和 5 MiB 上限改为从模块配置读取；
- 用 `runtime.common.query` 定位工作区、Feature 目录和状态，不再写死 `.autobizdevops/state.json` 和 `.autobizdevops/features/`，也不再从 `hooks.paths` 导入。这样隔离布局和 legacy 布局都能用；
- hooks.ndjson 中的 `pluginId` 取自配置（目前写死为 `AUTOBIZDEVOPS-PLUGIN`）；
- 同步配置 `config/artifact-sync.json` 按 `artifacts` 中列出的产物生成（路径和归属节点从节点输出推导），`allowedCheckpoints` 由 `allowedFrom` 推导；
- 看板入口：全栈版在 `9411fc3` 新增了顶层键 `artifact_sync`（与 `knowledge_config` 同构，用于在看板上带出同步技能），改由模块生成，写入 `board_core/modules.json`，对应子选项 `entry`；
- 工号确认（`--employee-id`，上传路径为 `{PROJECT_CODE}/DEV/Features/{feature}/{employeeId}/`）也在 `9411fc3` 中加入。模块以该提交为起点，照搬这套确认流程。

**知识模块**（来源：lite 的 `sync_agents.py`、`agents_repo.py`、`paths.py`；全栈版的 `render_collected_session_context.py`、`collect-knowledge.js`）：

- `agents_repo.py` 的清单解析改为 `inspect_deploy_units.py`，按 `manifest.format` 选择解析方式（v1 只有 `agents-manifest-v1`）；
- 全栈版的 `render_collected_session_context.py` + `collect-knowledge.js` 成为内置组装脚本，只保留知识段的组装，流程上下文和运行策略交给会话模块；`assembler = plugin` 时生成并使用，插件可以直接替换这个文件（D26）；
- `sync_agents.py` 改为可选的 `sync_knowledge.py`，只在声明 `source` 时生成；不再回写任何配置文件（§6.1）；
- 知识沉淀（`knowledge_config.nextAction`，即宿主的 `knowledge-sync`）移到看板可选能力 `knowledgeSedimentation`，只在 `modules.json` 中生成入口，不带脚本，也不再依赖知识模块。

### 6.4 运行框架从 lite 泛化时要做的改造

- 状态内核拆成两个内部库（D17）：`query.py` 只读，负责读取编译配置和状态、查询节点与产物存在情况；`engine.py` 负责初始化、状态转移、存在性检查、执行校验命令、提交状态和变更日志。所有入口都通过 import 使用它们；
- `engine.py` 只读 `runtime/config/` 和 `state.json`，不读看板配置；看板文案的拼装留在 `adapters/` 和 `session/`；
- `PLUGIN_ID` 和目录布局从生成的 `runtime/config/runtime.json` 读取（目前 `PLUGIN_ID` 写死为 `autodev-planning-kanban`，元数据目录写死为 `.autobizdevops`）。之所以不放进 `board_config.json`，是为了不给宿主读取的配置增加未知键；
- 所有路径都通过 `query.metadata_dir()` 推导，不得在其他地方拼接 `.autobizdevops`；
- `resolve_feature` 增加路径安全校验；
- `load_config` 中“技能必须存在”的校验保留，改为对 `flow.json` 执行，按 `skillDir` 检查，支持一层分组目录下的技能；
- `engine.py` 增加流程规则：动态阶段的选择与决定记录、跳过节点、终态节点。规则参照全栈版 `board_core/workflow.py`、`hooks/update_checkpoint.py` 的现有行为（input-config.md §2.6–§2.8），但只读 `flow.json`；新增入口 `runtime/adapters/skip_node.py`；
- 完成判定去掉“非空”检查，改为“存在性 + 校验命令”（§6.6）；
- `init_workspace.py` 拆成 `init_workspace.py`（项目）和 `init_feature.py`（Feature），不再用 `--mode` 区分；
- 删除未被引用的 `board_core/context.py`（引用了不存在的 `references/workflow.md` 和旧技能名 `autodev-onlycode`），由技能托管片段和会话流程上下文替代。

### 6.5 同一项目安装多个插件

现状：lite 和全栈版都把状态写在 `<project>/.autobizdevops/state.json`，而且格式不兼容（lite 是 `schemaVersion: 1` 并带 `pluginId`，全栈版是 `autobizdevops.state.v3` 且不带 `pluginId`），产物也都放在 `.autobizdevops/features/<feature>/`。两个插件装到同一个项目就会冲突。

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
| 元数据根目录可配置 | 图中的 `.autobizdevops` 是 `runtime.metaRoot` 的默认值，插件可以换成别的相对路径（D28）。它和 `layout` 一样是插件级静态配置，发布后不能改；不同根目录的插件天然互不干扰，同一根目录下仍按上面的规则隔离 |
| 每个插件只读写自己的命名空间 | 不维护跨插件共享的 state.json：各插件只认识自己的 checkpoint，共享文件意味着要互相校验对方的数据，而且多版本运行框架并存时容易互相破坏 |
| state.json 仍记录 `pluginId` 并校验 | 防止目录被拷贝或误放；不匹配时拒绝读写 |
| 保留目录名 | `plugin.id` 不得是 `features`、`archive`、`issues`、`reviews`、`logs`、`plugins`，以免与 legacy 布局和全栈版现有目录冲突 |
| 同名 Feature | 不同插件可以有同名 Feature，彼此互不影响 |
| legacy 布局 | 只为迁移已有插件（例如 lite、全栈版）而保留，保证它们已有的项目不受影响。项目里最多只能有一个 legacy 插件，但它可以和任意多个 isolated 插件共存 |
| 迁移 | 运行框架不会自动搬迁目录。v1 不提供迁移命令；如果确实需要，以后再提供显式的 `migrate-layout`，见 §9 |

受影响的输出：`system_prompt_inject` 中的 `FEATURE_DIR`、`feature_status` 返回的 `path`/`watchRefs`/`hookLogRefs`、`create_*` 返回的 `statePath`/`featureDir`、校验命令的 `${featureDir}`、产物同步读取的 Feature 目录。所有这些都由 `query.metadata_dir()` 统一推导。

### 6.6 节点完成判定

| 层次 | 负责方 | 做什么 |
|---|---|---|
| 存在性（最小校验） | 运行框架 `engine.py` | 必需产物的 `path` 每一项至少匹配一个文件；空文件也算存在 |
| 业务校验 | 开发者的校验命令 | 空文件、格式、内容是否合格 |

- 校验命令是写在 `workflow.json` 节点 `validate` 中的完整单行命令，只在推进到 `_done` 时、存在性检查通过之后执行（D14）；
- 命令不经过 shell：先按 POSIX 规则拆分参数，再替换 `${python}`、`${featureDir}` 等框架占位符。这样三个平台行为一致，路径含空格也不需要加引号（interfaces.md §4.3）；
- 退出码 0 才放行；不通过时状态不变，命令输出的末尾部分返回给模型，模型修正产物后重试；
- `query.py` 和 `feature_status` 只报告存在性。产物已生成不代表节点已完成，节点状态只由 `state.json` 决定；
- DevClaw 不执行校验命令，看板数据中不再输出 `validators`。全栈版按节点列出的声明式校验器，改由节点校验命令调用的脚本自己读取（§6.8）。

### 6.7 核心配置、编译配置与自动检测

配置分两层（D19）：

- **核心配置**（`workflow.json`、`plugin.scaffold.json`、`modules/*.json`）由人和 agent 共同维护，只写决策，字段尽量少。`workflow.json` 的顶层只有 `nodes` 和可选的流程规则 `rules`（`dynamicStages`、`skip`），每个节点最多 9 个字段，产物直接在 `outputs` 中以 `{id: 路径}` 定义，不再有单独的阶段表和产物表；
- **编译配置**（`runtime/config/*.json`、`board_core/*.json`）只由 build 生成，补全全部默认值，插件运行时只读它。

因为核心配置会被多人和 agent 修改，正确性靠自动检测保证，而不是靠人记得运行命令（D20，input-config.md §7.1）：编辑时 IDE 按 Schema 提示；agent 每次修改后运行 `lint`；提交前 `.githooks/pre-commit` 运行 `lint`；build 前同样检查，有 error 不写编译配置；CI 运行 `check --strict` 作为最后一道；运行框架加载 `flow.json` 时再校验不变量。

Schema 只检查结构，引用、顺序、路径安全、命令格式等语义规则都在 `lint` 中实现，这样 Schema 可以保持简短。`lint` 还会比较核心配置与 build-manifest 中记录的摘要，发现“改了核心配置却没重新 build”时报 `BUILD_STALE`。

### 6.8 全栈版迁入

全栈版（仓库 `autobiz_kanban`）用到的流程能力都能在核心配置中表达，样例见 [examples/fullstack/](../examples/fullstack/)（input-config.md §9.2）。对应关系：

| 全栈版现有形态 | 迁入后 |
|---|---|
| `workflow.dynamicStages[]`，`choiceCheckpoint`、`enableTargetCheckpoint` 等字段手写 | `workflow.json` 的 `rules.dynamicStages`，只写 `id`、`name`、`insertAfter`、`defaultDecision` 和节点；checkpoint 由 build 推导，选择文案写在 `board.display.dynamicStages` |
| `needs_fix` checkpoint 与 `checkpoints.transitions.needs_fix` | 暂不支持，预留到 v2（§7） |
| `skip_node` 命令与 `skipPolicy.lockedNodes` | `"rules": {"skip": true}`，或 `{"locked": […]}` 锁定部分节点；入口改为 `runtime/adapters/skip_node.py` |
| `ops.archive` 只有 `archived` | 节点上写 `"terminal": true` |
| 产物 `required: false`、`extract.degrade`，以及 `prd_optional` 这类单独的输入 id | `inputs` 中的 `{id, optional}`、`outputs` 中的 `{path, optional}`；`extract.degrade` 的内容移到技能正文 |
| `checkpoints.stageLabels` | 默认推导；不同的写在 `board.display.checkpointLabels` |
| `runtimePolicy.toolCustomConfig` | `session.policies.nodes.<id>.toolCustomConfig` |
| `skills/<分组>/<skill>/` | 原样保留，build 按 input-config.md §5 查找 |
| `validators`、`guards`（`hooks/stage_gate.py` 从 board_config 读取后执行） | 节点 `validate` 调用 `stage_gate.py`；校验器清单和守卫改由 `stage_gate.py` 从插件自己的配置文件读取（例如 `hooks/stage_gate.json`，按节点 id 列出），不再读 board_config |
| `hookDefinitions` | 说明性元数据，不再输出；需要时写进上面的配置文件 |
| 技术设计完成前的人工确认（`hooks/human_gate_design_done.py`） | 仍是 `hooks/hooks.json` 中的 PreToolUse 钩子；匹配的命令改为 `runtime/workflow/update_state.py --checkpoint design_done` |
| `rollback.archive`（回滚技能读取） | 回滚技能 `autobizdevops-rollback` 从自己的配置文件读取各节点要归档的文件（例如 `skills/autobizdevops-rollback/config/rollback.json`） |
| `templates`/`profiles`（精简路线、自定义节点子集，均已下架）及 `initial` 中只服务于它们的 checkpoint | 不迁入；`dynamic_workflow` 只返回 `standard`，新 Feature 从第一个节点开始。模板子集预留到 v2（§7） |
| `render_collected_session_context.py` + `collect-knowledge.js` | 流程上下文和运行策略归默认会话入口；知识组装部分成为知识模块的内置组装脚本（`assembler = plugin` 时默认使用，D26） |
| `hooks/update_checkpoint.py`、`route_checkpoint.py`、`skip_node.py`、根目录 `inspect_state.py` | 由 `runtime/` 下的框架入口和会话流程上下文替代；技能正文中残留的旧路径由 `check` 报 `LEGACY_ENTRY_REF` |

校验器清单、人工确认关卡、回滚清单都是插件自己的业务规则：脚手架不解释它们，也不检查它们与流程是否一致，节点 id 或 checkpoint 改名后由开发者自己同步（D23）。

## 7. v2 扩展预留

以下字段名在 v1 的 Schema 中先不开放，运行框架配置和看板数据中对应的键也暂不生成，但命名已对齐全栈版，避免日后破坏兼容：

| 能力 | 全栈版中的形态 | 预留输入字段 |
|---|---|---|
| 回流修复 | `needs_fix` checkpoint、`blocked`（已阻断）状态、`needsFixFromCheckpoint` | `workflow.json` 的 `rules.needsFix` |
| 模板子集（精简路线、自定义节点子集） | `workflow.templates.<id>.kind = nodeSubset / custom`（均已下架） | `workflow.json` 顶层的 `profiles[]`（不用 `templates`，以免与节点的模板引用混淆） |
| 模块自带宿主钩子 | `hooks/hooks.json` 片段 | `module.json` 中的 `contributes.hooks` |
| 外部输入（用户直接提供的文件） | — | `inputs` 中的 `{id, path, external: true}` |
| 旧文件名回退 | lite 的 `legacyPaths` | `outputs` 中的 `{path, legacyPaths}` |
| checkpoint 前缀覆写 | — | 节点的 `checkpointPrefix` |

后三项是精简核心流程时移出的字段，需要时以对象形式扩展 `inputs`/`outputs` 和节点，现有写法保持不变。

## 8. 已确认决策（2026-10-16；D22–D24 为 2026-10-26；D31 为 2026-10-28）

| # | 决策 | 落到 |
|---|---|---|
| D1 | 关闭知识模块时，`knowledge_path`、`deploy_units`、`pull_knowledge` 直接不生成；`pull_knowledge` 另外只在声明 `knowledge.source` 时生成 | output-spec.md §3.2；interfaces.md §2.3 |
| D2 | 宿主命令中的单值占位符一律写成 `"${pluginPath}"` 形式（加双引号）；`${projectDirs...}` 和 `${selectedDeployUnits}` 由宿主整体转义，不加引号 | output-spec.md §3.2 |
| D3 | state.json 记录 `pluginId`；同一项目使用多个插件时，按 `pluginId` 隔离插件产物目录 | §6.5；output-spec.md §4；interfaces.md §3、§4.6 |
| D4 | 脚手架建独立仓库 | §3.1 |
| D5 | DevClaw 读取根目录 `plugin.json`。`.codex-plugin/plugin.json` 改为可选输出（`plugin.codexManifest`），不生成 `marketplace.json` | output-spec.md §2 |
| D6 | 看板 `slashSkill` 用于带出技能，写不带命名空间的技能名；不受 Codex 命名空间影响 | input-config.md §4.1.2 |
| D7 | 宿主 `hooks.json` 只写入根 `plugin.json`，不写入 Codex 清单 | output-spec.md §2 |
| D8 | DevClaw 不依赖技能 frontmatter 中的 `version`。`SKILL_FRONTMATTER` 定为 error，导入技能时自动把 `version`、`author` 迁到 `metadata` | input-config.md §7；output-spec.md §6.1 |
| D9 | 插件开发技能 `autobiz-plugin-creator` 进入 v1 | §2.3；interfaces.md §1.6 |
| D10 | 三方职责：插件开发者定义流程并提供技能、模板、业务校验器和自定义扩展；脚手架与运行框架生成固定入口和编译配置，提供流程查询、状态管理及宿主适配；DevClaw 展示看板、发起会话、传入运行上下文、调用插件入口 | §1 |
| D11 | 核心流程配置 `workflow.json` 只表达业务骨架，不包含看板接入、知识配置、外挂技能管理和技能内部实现；其余配置放在模块配置文件中（D18） | input-config.md §1.2、§2、§4 |
| D12 | 产物路径支持字符串或字符串数组 | input-config.md §2.3；interfaces.md §3.3.3 |
| D13 | 产物存在性由框架检查，只做最小校验；空文件以及产物是否合格由业务校验决定 | §6.6；output-spec.md §4.4 |
| D14 | 自定义校验采用完整的单行命令，仅在节点完成时执行 | input-config.md §2.5；interfaces.md §4.3、§4.4 |
| D15 | 项目路径、Feature、所选发布单元和会话工作区等，由宿主在运行时传入，配置中不写 | input-config.md §1.2；interfaces.md §3.2、§3.4 |
| D16 | 输出目录：框架入口统一放在 `runtime/`（`workflow/`、`adapters/`、`session/`、`knowledge/`），`hooks/` 只放开发者自定义扩展，`board_core/` 只放 DevClaw 读取的 `board_config.json` 和 `modules.json`（D31）；构建记录为 `runtime/build-manifest.json` | output-spec.md §1 |
| D17 | `query.py`（只读查询）与 `engine.py`（初始化与状态变更）是内部库，由框架入口通过 Python import 使用，不注册为宿主命令，也不要求用户技能调用 | §6.4；interfaces.md §4.6 |
| D18 | 工程配置按模块拆分：入口文件 `plugin.scaffold.json` 只放插件基础信息、目录布局和引用；看板、会话与 Agent、知识、产物同步的配置分别放在 `modules/board.json`、`modules/session.json`、`modules/knowledge.json`、`modules/artifactSync.json`。前两个不引用时取默认值，知识和产物同步模块引用即启用（D30） | input-config.md §3、§4 |
| D19 | 核心配置与编译配置分开：`workflow.json` 只保留节点、技能绑定、执行顺序、输入输出、校验命令、可选的阶段名和流程规则（D22），产物在 `outputs` 中就地定义；其余内容由 build 推导，写入编译配置 `runtime/config/*.json` 和 `board_core/*.json`，插件运行时只读编译配置 | §6.7；input-config.md §1.2、§2；output-spec.md §5.2 |
| D20 | 核心配置自动检测：Schema 只管结构，语义规则由 `autobiz-plugin lint` 检查；lint 在 agent 修改后、提交前（`.githooks/pre-commit`）和 build 前自动执行，CI 运行 `check --strict`；改了核心配置未重新 build 时报 `BUILD_STALE` | §6.7；input-config.md §7 |
| D22 | 全栈版用到的流程规则进入 v1：终态节点、动态阶段、跳过节点、可选输入、可选输出；动态阶段和跳过节点统一写在 `workflow.json` 的 `rules` 中；技能目录支持一层分组。回流修复（`needs_fix`）暂不支持 | input-config.md §2；output-spec.md §3、§4、§5.2；interfaces.md §3.3、§4.2 |
| D23 | 插件自有的校验与钩子配置（声明式校验器清单、编译守卫、`hookDefinitions`、人工确认关卡、回滚归档清单）不进脚手架输入，留在插件自己的文件中 | §6.8；input-config.md §2.4 |
| D24 | 不提供从已有插件反推核心配置的命令；迁移 lite、全栈版时以 `examples/` 下的样例为起点（`new --from`） | interfaces.md §1.1、§1.4 |
| D25 | 代码提交作为 git 类型的产物：节点开始时 engine 记录各仓库的基线分支和 HEAD；基线分支上有新提交、没有未提交的改动、没有未合并回来的工作树分支，才算齐全。直接查仓库，不拦截 `git commit`；仓库取 Feature 所选发布单元的 `localRepoPath`，建 Feature 时记入 `state.json` | input-config.md §2.9；output-spec.md §4.2、§4.4；interfaces.md §3.3.3；interfaces.md §3.3.2、§3.3.4、§4.2、§4.3 |
| D21 | 看板数据改为插件推送（P0）：DevClaw 启动时在 `127.0.0.1` 上开一个 JSON-RPC 2.0 服务，通过 `AUTOBIZ_BOARD_ENDPOINT` 告诉插件；插件的写入口提交后发送 `board/changed`，内容与读取命令的输出相同，按 `boardSeq` 排序；DevClaw 缓存并展示，读取命令只用于冷启动和兜底。鉴权、产物实时刷新、静态结果预生成放到后续 | interfaces.md §3.5；output-spec.md §3.1、§4.2 |
| D26 | 知识组装默认由插件完成（`assembler = plugin`），内置组装脚本取自全栈版的 `render_collected_session_context.py` + `collect-knowledge.js`，lite 和全栈版都使用它；内置脚本兜底读取各仓库和会话工作区的 `AGENTS.md`，没有 collector 知识的插件也能直接用。插件需要不同的组装方式时直接替换这个文件（协议不变，只负责知识段，build 和 upgrade 不覆盖），不设组装脚本的配置项；去掉 `session.customEntry` | input-config.md §4.3；interfaces.md §2.4、§4.5 |
| D27 | 默认值只有一个来源：常量默认值只写在 Schema 的 `default` 中，lint 和 build 按它补全核心配置（对象要写 `default: {}` 才会在缺省时创建），编译配置里是补全后的值，运行框架不保留自己的默认值；推导出来的默认值由 build 计算。input-config.md 中的默认值列由 `tests/check_schema_defaults.py` 与 Schema 比对 | input-config.md §1.2；§5 |
| D28 | 元数据根目录 `.autobizdevops` 改为可配置的 `runtime.metaRoot`（默认不变，相对项目目录，不能是 `.git`）；`{metaDir}` 由 `metaRoot`、`layout`、`pluginId` 推导，三者发布后都不能改，`metaRoot` 变化同样报 `LAYOUT_CHANGED`。迁移 lite、全栈版时保持默认值 | input-config.md §3.4；output-spec.md §4.1、§5.1 |
| D29 | 节点模板由技能自己维护：`workflow.json` 不再有 `templates` 字段，模板放在技能目录下、由技能正文引用；脚手架不登记、不检查、不生成模板，`flow.json`、会话上下文和初始化向导中都不再出现模板，去掉 `TEMPLATE_MISSING` | input-config.md §2.4；output-spec.md §6.3 |
| D30 | 产物同步是独立的可选模块：配置放在 `modules/artifactSync.json`（Schema `schemas/modules/artifactSync.schema.json`），入口文件 `modules.artifactSync` 引用即启用，不再有 `enabled`；看板模块只保留知识沉淀入口一项可选能力。看板上的同步入口 `artifact_sync` 仍由产物同步模块生成 | input-config.md §3.2、§4.5；output-spec.md §7.2 |
| D31 | DevClaw 与插件只通过 `board_core/` 交互：`board_config.json` 只放 `apiVersion` 和 `inspectCommands`；新增 `modules.json` 列出四个模块的开启情况，并放 `boardEvents` 与看板入口 `knowledge_config`、`artifact_sync`。流程、标签、`nextAction`、产物定义编译进 `runtime/config/`（新增 `board.json`），由 adapter 在命令输出中给出。去掉 `supported_deploy_units`、`agentsRepo` 和全部运行期回写 | §6.1；output-spec.md §3、§5.3；interfaces.md §3.3 |

## 9. 遗留问题

1. **产物同步的服务端路径不含 `pluginId`**：上传路径是 `{PROJECT_CODE}/DEV/Features/{feature}/{employeeId}/`。D3 之后，同一项目中两个插件可以有同名 Feature，上传时会互相覆盖。是否在路径中加入 `pluginId`（例如 `{PROJECT_CODE}/DEV/Features/{pluginId}/{feature}/{employeeId}/`）？这需要和服务端约定，也会影响全栈版已上传数据的位置。
2. **legacy 项目是否需要迁移**：按目前设计，lite 迁入脚手架后继续使用 legacy 布局，已有项目不受影响。是否需要提供 `migrate-layout` 命令，把旧项目搬到 `.autobizdevops/<pluginId>/`？如果需要，还要确认宿主侧是否缓存了旧路径（例如已打开的产物链接）。
3. **全栈版已有项目的状态如何接续**：全栈版的 state.json 是 `autobizdevops.state.v3`，不带 `pluginId`，记录中还有 `workflowProfile`、`workflowNodes`，部分 Feature 的 `workflowTemplate` 是已下架的 `lean`、`custom`。运行框架是否读取 v3 并在首次写入时升级为 `schemaVersion: 1` 加 `pluginId`？用 `lean`/`custom` 创建的 Feature 按 `standard` 继续，还是保持只读？
4. **产物同步放在哪里**（已定）：作为独立的可选模块，配置在 `modules/artifactSync.json`，入口文件引用即启用，由脚手架生成同步配置和技能（D30）。
5. **知识仓库由谁同步**：新目录结构中 `runtime/knowledge/` 只列出 `inspect_deploy_units.py`。本稿把 lite 的仓库同步保留为可选项 `knowledge.source`（生成 `sync_knowledge.py` 和 `pull_knowledge`）。如果改由 DevClaw 统一拉取知识，去掉该项即可。
6. **`inspect_deploy_units.py` 如何暴露给 DevClaw**：本稿在 `inspectCommands` 中暂定键名 `deploy_units`，并已去掉静态的 `supported_deploy_units`（D31），DevClaw 需要改为调用它获取发布单元。键名待确认。
7. **内置组装脚本的 Node 依赖**：collector 需要 Node 和 `gray-matter`。全栈版的做法是缺依赖时在会话入口里执行 `npm install`，这要联网，耗时可能超过 `assembly.timeoutSec`，也违反了 `session_context_inject` 不写文件的约定（interfaces.md §3.1）。是否改为 build 或 package 时安装、随包带上 `node_modules`？没有 Node 的机器上退回清单映射和本地 `AGENTS.md`，需要确认这样加载的知识是否够用。
8. **去掉的输出**：根目录 `board.json` 副本、`references/workflow.md`、`hooks/update_checkpoint.py` 别名、插件内的 `tests/` 都不在新目录结构中，本稿已经去掉。需要确认 DevClaw 不读取 `board.json`。
9. **产物路径数组在看板数据中的表达**：本稿输出 `path`（取首项）加 `paths`（全部），只认 `path` 的旧版 DevClaw 仍能工作，但只会看到首项。需要 DevClaw 确认能否读取 `paths`。
10. **看板事件推送需要 DevClaw 配合的部分**（D21）：一是启动本机服务并实现 interfaces.md §3.5.5 的缓存与拉取规则；二是在执行 inspectCommands 和发起会话时注入 `AUTOBIZ_BOARD_ENDPOINT`；三是从新增的 `board_core/modules.json` 读取 `boardEvents`。后续做产物实时刷新时，还需要 DevClaw 能拿到会话中模型写文件的工具调用事件。
11. **git 产物需要 DevClaw 确认的部分**（D25）：一是看板数据中 git 产物没有 `path`，只有 `artifactType: "git"` 和 `git`，旧版 DevClaw 能否接受；二是 Feature 创建后用户改选发布单元时，DevClaw 是否会再次调用 `create_feature` 更新 `deployUnits`，否则节点基线仍按建 Feature 时的选择记录；三是子代理的独立工作树建在哪里、分支怎么命名，`merged` 条件靠 `git worktree list` 发现它们。

## 10. 本次调整（相对初稿 2c713e4）

按三方职责和“输入类别 → 生成内容”的对应关系调整：

| 方面 | 初稿 | 本稿 |
|---|---|---|
| 参与方 | “宿主” | 明确为插件开发者、脚手架与运行框架、DevClaw 三方（D10） |
| 输入 | 单个 `plugin.scaffold.json` | `workflow.json`（业务骨架）+ 入口 `plugin.scaffold.json`（基础信息与引用）+ 按需存在的 `modules/board.json`、`session.json`、`knowledge.json`、`artifactSync.json`；`runtimePolicy` 移到 `session.policies`，`nextAction` 覆写移到 `board.display.nodes`，产物的 `sync`/`syncDescription` 合并为 `artifactSync.artifacts`（显式列出要上传的产物及简述）（D11、D18） |
| 核心流程 | 阶段表 + 产物注册表 + 节点（约 10 个字段，输入输出各有两种写法） | 只有 `nodes`；节点最多 8 个字段，产物在 `outputs` 中就地定义；新增 `validate`；模板由技能自己维护，不在核心流程中登记（D29）；编译后的 `flow.json` 供运行时使用（D14、D19） |
| 产物 | `path` 为字符串，要求非空 | `path` 可为数组（D12）；框架只查存在性（D13） |
| 模块 | 知识、产物同步两个可选模块 | 核心模块看板、会话；知识模块（清单解析、发布单元查询、组装方可选）；知识沉淀入口改为看板可选能力；产物同步仍是独立的可选模块，配置在 `modules/artifactSync.json`（D30） |
| 目录 | 入口散在 `hooks/`、`board_core/`、根目录 | 入口统一到 `runtime/`，`hooks/` 归开发者，`board_core/` 只放 DevClaw 读取的命令与模块清单（D31），`.scaffold/lock.json` 改为 `runtime/build-manifest.json`（D16） |
| 内核 | `board_core` + 对外稳定 API `board_core.api` | 内部库 `query.py` / `engine.py`，不对开发者代码开放（D17） |
| 会话 | 只有策略和知识 | 增加流程上下文段；知识组装默认用全栈版的 collector，插件可以直接替换组装脚本（D26） |
| 初始化 | `new` 问答 | 初始化向导按七类输入问答，可导入已有技能资源；以 lite、全栈版样例为起点，不从已有插件反推（D24） |
| 流程规则 | 只有线性流程 | 终态节点、动态阶段、跳过节点、可选输入输出进 v1，流程规则收在 `rules` 中；插件自有的校验与钩子配置留在插件文件中（D22、D23） |
| 代码产物 | 代码节点没有产物 | git 类型的产物，按仓库状态判断是否齐全（D25） |
| 检测 | `build` / `check` 手动执行 | 新增 `lint`，在 agent 修改后、提交前、build 前自动执行，CI 运行 `check`；检测编译配置是否过期（D20） |
| 宿主交互 | DevClaw 每次刷新看板都执行读取命令 | 新增看板事件推送 P0：插件在提交后把看板数据推给 DevClaw 的本机服务，读取命令只用于冷启动和兜底（D21） |
