# 框架图与核心机制图

本文用 Mermaid 绘制，GitHub、IDEA、VS Code 都能直接渲染。图只是概览，规则以各设计文档为准，图中标注了对应章节。

| 类别 | 图 |
|---|---|
| 框架图 | [1. 三方职责与整体架构](#1-三方职责与整体架构) · [2. 运行期调用关系](#2-运行期调用关系) · [3. 核心配置与编译配置](#3-核心配置与编译配置) |
| 核心机制图 | [4. 构建流水线](#4-构建流水线) · [5. 自动检测](#5-自动检测) · [6. 状态推进与完成判定](#6-状态推进与完成判定) · [7. checkpoint 状态机](#7-checkpoint-状态机) · [8. 会话内容组成](#8-会话内容组成) · [9. 知识模块](#9-知识模块) · [10. 多插件隔离](#10-多插件隔离) · [11. 看板事件推送](#11-看板事件推送) |

---

## 一、框架图

### 1. 三方职责与整体架构

上面一行是开发期：插件开发者写核心配置和技能资源，脚手架检测并编译，生成插件。下面一行是运行期：DevClaw 读取看板配置、调用插件入口、拉起会话，模型执行技能并通过 `update_state.py` 提交状态。两条线汇合到同一个插件。见 [README §1、§3](README.md)。

```mermaid
flowchart LR
  subgraph DEV["插件开发者：定义流程，提供技能、模板、校验器和扩展"]
    direction TB
    D1["workflow.json<br/>核心流程"]
    D2["plugin.scaffold.json<br/>基础信息与引用"]
    D3["modules/*.json<br/>看板 · 会话 · 知识"]
    D4["skills/ · agents/ · hooks/<br/>技能资源与扩展"]
  end

  subgraph SCF["脚手架（开发期，不随插件发布）"]
    direction TB
    W["初始化向导<br/>autobiz-plugin-creator"]
    L["lint<br/>结构 + 语义检测"]
    B["build<br/>编译 · 生成 · 托管"]
    W --> L --> B
  end

  subgraph HOST["DevClaw：展示看板、发起会话、传入运行上下文、调用插件入口"]
    direction TB
    H1["看板"]
    H2["会话"]
  end

  M["模型<br/>执行技能"]

  subgraph PLG["插件（随包发布）"]
    direction TB
    P1["plugin.json<br/>board_core/board_config.json"]
    P2["runtime/<br/>固定入口 · query/engine · 编译配置"]
    P3["skills/（含状态接入说明）<br/>hooks/ · agents/"]
  end

  DEV -->|"核心配置与技能资源"| SCF
  SCF -->|"生成与托管"| PLG
  HOST -->|"读取看板配置<br/>调用插件入口"| PLG
  PLG -.->|"看板事件推送"| HOST
  HOST -->|"拉起会话"| M
  M -->|"读取技能<br/>update_state.py"| PLG
```

### 2. 运行期调用关系

DevClaw 只调用 `runtime/` 下的固定入口；入口通过 import 使用内部库 `query.py`（只读）和 `engine.py`（初始化与状态变更）；模型通过 `update_state.py` 提交状态变更；三个写入口提交后把看板事件推送给 DevClaw（虚线，见图 11）。会话入口内部如何组装知识和调用自定义入口见图 8。见 [interfaces.md §4](interfaces.md)。

```mermaid
flowchart LR
  subgraph HOST["DevClaw"]
    direction TB
    C1["create_project"]
    C2["create_feature"]
    C3["project_status<br/>feature_status"]
    C4["dynamic_workflow"]
    C5["session_context_inject"]
    C6["deploy_units"]
    EV["看板事件服务<br/>127.0.0.1"]
  end

  MODEL["模型"]

  subgraph RT["runtime/ 固定入口"]
    direction TB
    A1["adapters/init_workspace.py"]
    A2["adapters/init_feature.py"]
    A3["adapters/inspect_state.py"]
    A4["adapters/inspect_workflow_templates.py"]
    S1["session/render_session_context.py"]
    K1["knowledge/inspect_deploy_units.py"]
    WF["workflow/update_state.py"]
  end

  subgraph CM["runtime/common/ 内部库"]
    direction TB
    Q["query.py<br/>只读查询"]
    E["engine.py<br/>初始化与状态变更"]
  end

  subgraph DATA["数据"]
    direction TB
    CFG[("runtime/config/<br/>编译配置")]
    ST[("项目目录<br/>state.json · 产物 · hooks.ndjson")]
  end

  VAL["节点校验命令<br/>（开发者）"]

  C1 --> A1
  C2 --> A2
  C3 --> A3
  C4 --> A4
  C5 --> S1
  C6 --> K1
  MODEL --> WF
  A3 & A4 & S1 --> Q
  A1 & A2 & WF --> E
  Q -->|"只读"| CFG & ST
  E -->|"读配置 · 加锁写状态"| CFG & ST
  E -->|"完成时执行"| VAL
  A1 & A2 & WF -.->|"board/changed"| EV
```

### 3. 核心配置与编译配置

人和 agent 只维护左边的核心配置；右边的编译配置只由 build 写入，插件运行时只读它们。build-manifest 记录各核心配置的摘要，lint 发现核心配置改了却没重新 build 时报 `BUILD_STALE`（见图 5）。见 [input-config.md §1.2、§6](input-config.md)、[output-spec.md §5](output-spec.md)。

```mermaid
flowchart LR
  subgraph CORE["核心配置（人与 agent 维护，不发布）"]
    direction TB
    I1["plugin.scaffold.json"]
    I2["workflow.json"]
    I3["modules/board.json"]
    I4["modules/session.json"]
    I5["modules/knowledge.json"]
  end

  BUILD{{"autobiz-plugin build<br/>lint 通过才编译"}}

  subgraph COMP["编译配置（只由 build 写入，随插件发布）"]
    direction TB
    O1["runtime/config/flow.json<br/>流程契约与状态规则"]
    O2["runtime/config/session.json<br/>策略 · 会话片段 · 自定义入口"]
    O3["runtime/config/knowledge.json"]
    O4["runtime/config/runtime.json<br/>pluginId · layout"]
    O5["board_core/board_config.json<br/>固定看板接口"]
    O6["runtime/build-manifest.json<br/>输入摘要 · 文件哈希"]
  end

  I1 & I2 & I3 & I4 & I5 --> BUILD
  BUILD --> O1 & O2 & O3 & O4 & O5 & O6
  O1 & O2 & O3 & O4 --> RTR["运行框架读取"]
  O5 --> DCR["DevClaw 读取"]
  O6 --> LNT["lint 比对摘要<br/>不一致时报 BUILD_STALE"]
```

| 编译配置 | 主要来自 |
|---|---|
| `flow.json` | `workflow.json`，加上 `board.display` 中的产物显示名 |
| `session.json` | `modules/session.json`，加上知识模块注册的会话片段 |
| `knowledge.json` | `modules/knowledge.json` |
| `runtime.json` | `plugin.scaffold.json` 的 `plugin.id`、`runtime` |
| `board_config.json` | `workflow.json` + `modules/board.json` + `modules/session.json` 的节点策略 + 知识模块的命令 |

---

## 二、核心机制图

### 4. 构建流水线

前三步单独执行就是 `lint`；任何一步出现 error 都不写文件。见 [README §5](README.md)。

```mermaid
flowchart LR
  subgraph LINT["lint（build 的前三步）"]
    direction LR
    S1["load<br/>读入口及其引用的文件<br/>按 Schema 校验结构"]
    S2["normalize<br/>填默认值 · 汇总产物<br/>推断类型 · 算 checkpoint"]
    S3["validate<br/>语义规则<br/>input-config §7.2"]
    S1 --> S2 --> S3
  end

  S4["compile<br/>生成 PluginIR"]
  S5["contribute<br/>board · session<br/>knowledge · artifactSync"]
  S6["emit<br/>按归属写文件<br/>检查漂移"]
  S7["manifest<br/>写 build-manifest.json"]
  X["退出码 1<br/>不写任何文件"]

  S3 --> S4 --> S5 --> S6 --> S7
  S3 -->|"有 error"| X
  S6 -->|"managed 文件被手改"| X
```

### 5. 自动检测

核心配置会被多人和 agent 修改，所以每个可能引入错误的环节都自动检测。本地钩子可以被 `--no-verify` 跳过，CI 是最后一道。见 [input-config.md §7.1](input-config.md)。

```mermaid
flowchart TB
  EDIT["修改核心配置<br/>（人或 agent）"]
  IDE["编辑时：IDE 按 $schema 即时提示<br/>只查结构"]
  AG["agent 修改后：运行 lint"]
  BLD["build 前：同样执行 lint<br/>有 error 不写编译配置"]
  HOOK["提交时：pre-commit 运行 lint<br/>含 BUILD_STALE 检测"]
  CI["合并时：CI 运行 check --strict<br/>lint + 技能 + 漂移 + 契约测试"]
  PKG["package 发布"]
  RUN["运行时：加载 flow.json<br/>校验不变量"]
  FIX["按 Issue 修正<br/>或重新 build"]

  EDIT --> IDE & AG
  IDE & AG --> BLD
  BLD --> HOOK
  HOOK -->|"通过"| CI
  CI -->|"通过"| PKG
  PKG --> RUN
  BLD -->|"error"| FIX
  HOOK -->|"error"| FIX
  CI -->|"失败"| FIX
  FIX --> EDIT
```

### 6. 状态推进与完成判定

模型调用 `update_state.py` 推进到 `_done` 时，框架先检查必需产物是否存在（空文件也算存在），再执行节点的单行校验命令，退出码为 0 才写入状态。见 [output-spec.md §4.4](output-spec.md)、[interfaces.md §4.2–§4.4](interfaces.md)。

```mermaid
sequenceDiagram
  autonumber
  participant M as 模型
  participant U as update_state.py
  participant E as engine.py
  participant FS as 项目目录
  participant V as 校验命令（开发者）

  M->>U: --checkpoint plan_done
  U->>E: transition(project, feature, plan_done)
  E->>FS: 读取 state.json
  E->>E: 状态转移检查（plan_in_progress → plan_done）
  E->>FS: 存在性检查：必需输入与输出
  alt 有产物缺失
    E-->>U: ok:false，列出缺失的产物
  else 全部存在
    E->>V: 拆分参数 → 替换占位符 → 不经 shell 执行
    V-->>E: 退出码与输出
    alt 退出码非 0 或超时
      E->>FS: 写 node-validate 失败事件
      E-->>U: ok:false，附输出末尾 2000 字符
    else 退出码为 0
      E->>FS: 在 .state.lock 内读取、校验、原子替换 state.json
      E->>FS: 写 node-validate、update-state 事件
      E-->>U: ok:true
    end
  end
  U-->>M: JSON 结果
```

### 7. checkpoint 状态机

以最小示例为例：每个节点有 `<前缀>_in_progress`、`<前缀>_done` 两个 checkpoint，前缀取节点 id 的最后一段，按节点顺序线性推进。重开只能回到当前或之前节点的 `_in_progress`，不执行校验命令。见 [input-config.md §2.2](input-config.md)、[interfaces.md §4.2](interfaces.md)。

```mermaid
stateDiagram-v2
  direction LR
  [*] --> draft_in_progress: create_feature
  draft_in_progress --> draft_done: 输出存在且校验通过
  draft_done --> review_in_progress: 输入存在
  review_in_progress --> review_done: 输出存在且校验通过
  review_done --> [*]
  review_done --> review_in_progress: 重开
  review_in_progress --> draft_in_progress: 重开
  draft_done --> draft_in_progress: 重开
```

### 8. 会话内容组成

默认会话入口始终生成流程上下文和 `agentConfig`；知识段和自定义会话入口的输出按配置追加，自定义入口不能替换默认入口。见 [README §6.2](README.md)、[interfaces.md §3.3.7、§4.5](interfaces.md)。

```mermaid
sequenceDiagram
  autonumber
  participant D as DevClaw
  participant R as render_session_context.py
  participant Q as query.py
  participant P as 会话策略
  participant K as 知识组装器
  participant C as 自定义会话入口

  D->>R: session_context_inject（项目、Feature、发布单元、会话工作区）
  R->>Q: 查询当前节点、目标节点、输入输出及存在情况、模板
  Q-->>R: 流程上下文 flow
  R->>P: 目标节点 → 当前节点 → 默认，三级降级
  P-->>R: agentConfig
  opt 启用知识模块且 assembler = plugin
    R->>K: SessionRequest
    K-->>R: 知识段与 agentmdLoadStatus
  end
  opt 声明了 session.customEntry
    R->>C: stdin 传入请求 JSON（含 flow、agentConfig）
    C-->>R: stdout 返回 sessionContext、message
  end
  R-->>D: sessionContext（流程 + 知识 + 自定义）、flow、agentConfig
```

### 9. 知识模块

清单解析由 `inspect_deploy_units.py` 统一完成；组装方选择 `plugin` 时由插件组装知识段，选择 `devclaw` 时由 DevClaw 调用 `deploy_units` 后自行组装。知识仓库同步是可选项。见 [input-config.md §4.3](input-config.md)、[output-spec.md §7.1](output-spec.md)。

```mermaid
flowchart LR
  SRC["知识仓库<br/>（可选 source）"]
  ROOT[("知识目录 sys/<br/>agents.manifest.json")]
  IDU["inspect_deploy_units.py<br/>解析清单 → 系统与发布单元"]
  ASM["assembler.py<br/>系统 · 单元 · 会话工作区 · 词汇表"]
  SC["sessionContext 知识段"]
  DC["DevClaw 自行组装"]

  SRC -->|"pull_knowledge<br/>sync_knowledge.py"| ROOT
  ROOT --> IDU
  IDU -->|"assembler = plugin"| ASM --> SC
  IDU -->|"assembler = devclaw<br/>deploy_units 命令"| DC
```

### 10. 多插件隔离

每个插件只读写自己的元数据目录，状态、锁和产物互不干扰；legacy 布局只为迁移已有插件保留，一个项目最多一个。见 [README §6.5](README.md)。

```mermaid
flowchart TB
  subgraph PLUGINS["同一项目中安装的插件"]
    direction LR
    PA["doc-review<br/>layout: isolated"]
    PB["another-plugin<br/>layout: isolated"]
    PL["lite<br/>layout: legacy（最多一个）"]
  end

  A[".autobizdevops/doc-review/<br/>state.json · .state.lock · features/"]
  B[".autobizdevops/another-plugin/<br/>state.json · .state.lock · features/"]
  L[".autobizdevops/<br/>state.json · features/"]

  PA -->|"只读写"| A
  PB -->|"只读写"| B
  PL -->|"只读写"| L
```

### 11. 看板事件推送

DevClaw 启动本机服务并通过环境变量告诉插件；写入口在 engine 提交、释放锁之后推送看板数据，DevClaw 按 `seq` 缓存并展示。推送失败不影响命令结果，漏收由拉取兜底。见 [interfaces.md §3.5](interfaces.md)。

```mermaid
sequenceDiagram
  autonumber
  participant D as DevClaw
  participant M as 模型
  participant U as update_state.py
  participant E as engine.py
  participant B as board_events.py

  D->>D: 启动服务（127.0.0.1 随机端口）
  D->>M: 拉起会话（注入 AUTOBIZ_BOARD_ENDPOINT）
  M->>U: --checkpoint plan_done
  U->>E: transition(...)
  E->>E: 锁内提交 state.json，boardSeq + 1
  E-->>U: ok:true，boardSeq = 12
  U->>B: 释放锁后组装 projectRuns + run
  B->>D: POST board/changed（seq 12，超时 300 ms）
  alt seq 大于缓存
    D->>D: 更新总览与该 Feature 详情
  else seq 小于或等于缓存
    D->>D: 丢弃
  end
  U-->>M: JSON 结果（推送失败也不影响）
  Note over D: 冷启动、seq 跳号、插件重新 build 时<br/>调用 project_status / feature_status 拉取
```
