# v1 功能分期：P0 / P1（草案，待确认）

按 [README §8](README.md) 中截至 D59 的评审结论划分（2026-11-04）。P0、P1 都在 v1 范围内，只是交付先后不同；v2 预留和尚未评审的草案见 §4。

已确认（2026-11-04）：知识模块和产物同步模块都在 P0。

mods.md 中的 P0/P1/P2 是 mod 能力自己的分档，与本文无关。

## 1. 划分标准

| 档 | 标准 |
|---|---|
| P0 | 第一个交付版本必须有：开发者以手写的核心配置为起点，用 CLI 生成、检查、打包插件，DevClaw 导入后能展示看板、发起会话、推进状态；lite 能迁入并通过金样测试。缺了会有正确性风险的检查也放在这一档 |
| P1 | 在 P0 之后交付：降低上手门槛（向导、插件开发技能、编辑命令），补齐全栈版迁入（产物同步等），以及脚手架发布第二个版本之前才需要的升级处理。不做时有替代做法，例如手写配置、手工操作 |

## 2. P0

### 2.1 构建流水线（scaffold.md 单元 1–8）

| 功能点 | 依据 |
|---|---|
| 公共基础：Issue 格式与稳定排序、只支持 18 个关键字的 Schema 校验、UTF-8 读写、生成文件固定为 LF、摘要前把 CRLF 换成 LF、`sha256:` 摘要 | D42、D43 |
| 读取与补全：入口文件及其引用的文件、按 Schema 补默认值、重复键报错、接受 BOM | D27、D46 |
| lint：input-config.md §7.2 的核心规则和模块规则，分两段输出（版本类规则见 P1） | D47 |
| 编译：按 `seq` 排序、产物 id 推导、checkpoint 链、终态节点、可选输出、节点描述取技能 `description` | D33、D38、D49 |
| 模块契约与合并：`module.json`、`Contribution`、按固定顺序合并、`MODULE_CONFLICT` | D50 |
| 技能同步：状态维护片段的插入、更新、删除，空白 `SKILL.md`，旧 `scaffold` 片段原地替换 | D38、D45、output-spec.md §6.1 |
| 写盘：归属规则、`DRIFT_MANAGED` 与 `--force`、逐个文件原子替换、build-manifest 最后写（记录脚手架、运行框架和模块版本） | D52、output-spec.md §8 |
| 改 `plugin.id`、`runtime.metaRoot` 的保护：`PLUGIN_ID_CHANGED`、`LAYOUT_CHANGED` 与 `--allow-id-change`、`--allow-layout-change` | D47、D48 |

### 2.2 CLI

| 功能点 | 依据 |
|---|---|
| `doctor`：lint → build → 复查，同步技能的状态维护片段（影响报告见 P1） | D38、D54 |
| `lint`、`check`：技能内容规则（`SKILL_FRONTMATTER`、`SKILL_STATE_BLOCK`、`LEGACY_ENTRY_REF`、`TODO_PLACEHOLDER` 等）、`DRIFT_GENERATED`、契约测试 | D51、D54、D55 |
| `package`：打包规则、zip 只有一个顶层目录 `<plugin.id>/`、可重复 | D57 |
| `add skill --from`：导入已有技能，`version`、`author` 迁入 `metadata`，内容问题报 warning | D51、D56 |
| `autobiz-plugin.pyz`：用 zipapp 发布成一个文件 | D57 |

### 2.3 运行框架（scaffold.md 单元 15）

| 功能点 | 依据 |
|---|---|
| `query.py`、`engine.py`：线性推进、终态节点、重开、必需产物存在且非空、加锁提交、变更日志 `hooks.ndjson` | D17、D37、D59 |
| 多插件隔离：`metaRoot`、state.json 中 `pluginId` 校验、Feature 名路径安全 | D48、README §6.5 |
| 入口：`update_state.py`、`init_workspace.py`、`init_feature.py`、`inspect_state.py`、`inspect_workflow_templates.py`（只返回 `standard`） | interfaces.md §4.1 |
| 入口共用的 `cli.py`，看板数据拼装 `board_view.py` | D59 |
| 看板事件推送的插件侧：`board_events.py`、`boardSeq`；未设置端点时静默跳过，读取命令照常兜底 | D21 |

### 2.4 模块（scaffold.md 单元 9）

| 功能点 | 依据 |
|---|---|
| board：三平台 `inspectCommands`（一律 `-X utf8`）、`modules.json`（含 `boardEvents` 和固定开启的知识沉淀入口 `knowledge_config`）、`runtime/config/board.json` | D31、D33、D40 |
| session：默认会话入口 `render_session_context.py`（流程上下文、`agentConfig`、知识段），`session.policies`，宿主命令键 `session_context_inject` | D35、D40、D44 |
| knowledge：`inspect_deploy_units.py`（`deploy_units`）、内置组装脚本和 `collect-knowledge.js`、声明 `source` 时的 `sync_knowledge.py`（`pull_knowledge`）、`${knowledgePath}`；没有 Node 时退回清单映射和 `AGENTS.md` | D26、D53 |
| artifactSync：按节点生成 `stages`、同步配置 `artifact-sync.json`（`schemaVersion: 3`，兼容读取 v1、v2）、同步技能、看板入口 `artifact_sync`、工号确认；通过 `runtime.common.query` 定位 Feature 目录，不再写死 `.autobizdevops` | D30、D35、README §6.3 |

### 2.5 测试

| 功能点 | 依据 |
|---|---|
| `tests/unit/`、`tests/contract/`（含看板事件推送规则）、`tests/golden/` 的 lite 基线、`tests/check_schema_defaults.py` | README §3.1、D27、D55 |

## 3. P1

### 3.1 降低上手门槛

| 功能点 | 依据 | 不做时 |
|---|---|---|
| 初始化向导的交互问答、`new --answers` | interfaces.md §1.4、D56 | 用 `new --skeleton` 写出骨架后手填 |
| `add node`、`module list`、`module enable`/`disable`、`--set`，以及保留键序和缩进的配置编辑 | D56 | 手改核心配置后执行 doctor |
| 插件开发技能 `autobiz-plugin-creator` 和它的 DevClaw 插件包；依赖 `new --answers`、doctor 的 `changes`、`simulate` | D9、D58 | 开发者直接用 CLI |
| `simulate` 命令：复用 check 的契约测试流程 | D55 | `check` 中的契约测试 |
| doctor 的影响报告：`--dry-run`、`changes`、`CHECKPOINT_REMOVED`、`DOCTOR_BASELINE_MISSING` | D54 | 生成后对比文件 |
| `.scaffold/` 下的 Schema 拷贝（IDE 补全；插件开发技能也靠它查字段） | D51、D55、D58 | 直接看仓库中的 Schema |
| 模块关闭后的遗留文件处理：标 `inactive`、`MODULE_INACTIVE_FILES` | D52 | 关闭模块后手动删除它生成的文件 |

### 3.2 全栈版迁入

| 功能点 | 依据 | 不做时 |
|---|---|---|
| `plugin.mcpServers`、`plugin.hooks` 透传与 `PLUGIN_REF_MISSING` | D38、D57 | — |
| 全栈版金样测试 | README §3.1 | — |
| 全栈版已有项目的状态接续（`autobizdevops.state.v3`） | README §9 第 3 条（待定） | — |

### 3.3 运行框架的保留能力

| 功能点 | 依据 | 不做时 |
|---|---|---|
| `inputs` 检查与 `validate` 校验命令的执行：v1 的 build 固定写 `[]`、`null`，由契约测试手写 `flow.json` 覆盖 | D59、interfaces.md §4.3、§4.4 | 节点只做存在且非空检查，与 v1 的 build 结果一致 |

### 3.4 版本与升级（脚手架发布第二个版本之前完成）

| 功能点 | 依据 | 不做时 |
|---|---|---|
| 版本比较：`SCAFFOLD_OUTDATED`、`CORE_MAJOR_CHANGED`、`SCAFFOLD_VERSION_CHANGED`、`doctor --allow-major-upgrade`、`changes.versions`；同一主版本内 doctor 替换 managed、module 文件 | D57 | 第一个版本没有可比较的旧版本；P0 的 build-manifest 已经记下版本号 |

## 4. 不在 v1

| 内容 | 依据 |
|---|---|
| v2 预留：回流修复、模板子集、动态阶段与跳过节点（含 `skip_node.py`）、外部输入、旧文件名回退、checkpoint 前缀覆写、模块自带宿主钩子 | README §7、D52、D59 |
| 看板事件的后续项：鉴权、产物实时刷新、静态结果预生成、会话入口提速 | interfaces.md §3.5.6 |
| `migrate` 命令 | D57 |
| 尚未评审的草案：mods.md（有自己的 P0/P1/P2 分档和分期）、rpc.md | — |

## 5. 依赖 DevClaw 确认的事项

| 事项 | README §9 | 影响 |
|---|---|---|
| `deploy_units` 的键名 | 第 6 条 | P0（知识模块） |
| DevClaw 不读根目录的 `board.json` | 第 8 条 | P0 |
| 看板数据中的产物路径数组 `paths` | 第 9 条 | P0 |
| 看板事件服务、`AUTOBIZ_BOARD_ENDPOINT` 注入、读取 `boardEvents` | 第 10 条 | P0；插件侧不依赖它也能工作 |
| zip 的顶层目录作为安装目录名 | 第 11 条 | P0 |
| 内置组装脚本的 Node 依赖 | 第 7 条 | 已定（2026-11-05）：doctor 安装、随包带上 |
| 产物同步的服务端路径是否加 `pluginId` | 第 1 条 | P0（产物同步模块） |
| 全栈版已有项目的状态接续 | 第 3 条 | P1 |

## 6. 实现状态（2026-11-04）

P0、P1 已全部实现。代码都在 `booter/` 下：`scaffold/`（CLI、构建流水线、初始化向导）、`runtime/`（运行框架模板）、`scaffold/modules/`（四个模块）、`skills/autobiz-plugin-creator/`（插件开发技能）、`schemas/host/outputs.schema.json`（命令输出结构）和 `tools/make_pyz.py`（发布 `.pyz` 与插件开发技能的插件包）中。`tests/` 下 51 个测试在 Python 3.9 和 3.14 上通过：

| 测试 | 内容 |
|---|---|
| `tests/golden/test_examples.py` | `booter/examples/minimal` 和仓库根目录 `fixtures/` 下的 lite、fullstack（不在时跳过）build 后与各自的 `output/` 逐字节一致，重复 build 不写文件 |
| `tests/golden/test_reference.py` | 命令输出的看板数据与 lite、全栈版现有 `board_config.json` 比较；lite 全部一致，全栈版只有文件开头列出的有意差异（参考仓库不在时跳过） |
| `tests/contract/` | 状态推进、存在且非空检查、重开、终态节点、`pluginId` 隔离、只读命令、保留字段拒绝加载、校验命令；看板事件用模拟的 DevClaw 服务验证 |
| `tests/test_cli.py` | `new` → `check`（含契约测试）→ `package`，lint 核心规则，改 `plugin.id` 的放行，doctor 删节点，`add skill --from` 导入 lite 技能 |
| `tests/test_p1.py` | 初始化向导、`add node`、`module list/enable/disable --set`、`simulate`、版本升级、全栈版 v3 状态接续、插件开发技能的插件包 |
| `tests/unit/` | 推导规则、SKILL.md 片段（含 CRLF）、Schema 子集与关键字限制、JSON 重复键与 BOM |

P1 中定下的新决策：全栈版已有项目的状态接续（D60，README §9 第 3 条）。

2026-11-05 调整（D67）：`new` 去掉 `--from blank|lite|fullstack`，`autobiz-plugin.pyz` 不再带样例种子。`new` 只从问答或 `--answers` 生成核心配置（`--yes` 时必须给出 `plugin` 和 `nodes`），自己手写时用 `new --skeleton`；骨架引导技能只提供空白骨架。lite、fullstack 样例从 `booter/examples/` 移到仓库根目录的 `fixtures/`，只供测试，不随 booter 分发；用到它们的测试在 `fixtures/` 不在时跳过。

与设计文档不同、需要确认的地方：

| 位置 | 做法 | 原因 |
|---|---|---|
| `BUILD_STALE`、`SCAFFOLD_VERSION_CHANGED` | 在模块规则之后报，不挡住模块规则 | 改完配置后最常见的就是过期；按 D47 的两段式，lint 此时只报“过期”，模块配置的问题要等 doctor 才看得到。过期不影响 IR 是否可靠 |
| `add skill --from` | 目标目录里只有 doctor 生成的空白 `SKILL.md` 时允许覆盖导入 | `new` 会为每个节点生成空白 `SKILL.md`，否则 interfaces.md §1.4 的迁移路径（先 `new`、再 `add skill --from`）走不通 |
| 编辑命令写入的新内容 | 跟随同级元素的写法；新写的对象逐个键换行，只含标量的数组写在一行 | 与示例的手排格式一致；原有内容的字节不变 |
| 内置知识组装脚本 | 缺 `gray-matter` 时不执行 `npm install`，直接按清单映射加载 | 会话入口不得写文件（interfaces.md §3.1）；依赖由 doctor 安装、随包带上，失败报 `KNOWLEDGE_NODE_DEPS`（README §9 第 7 条） |
| 内置知识组装脚本 | 按全栈版的结构（`<SCOPE>`、`<SYSTEM>`、`<UNIT>`、`<DOMAIN_CONTEXT>`）重写，没有逐行移植 | 全栈版的脚本依赖 1100 多行的旧会话入口；已用清单映射和本地 `AGENTS.md` 验证，collector 分支还没有在装了 `gray-matter` 的环境中跑过 |
| 产物同步技能 | 带上全栈版共享的 `references/ask-user-question.md` | 技能正文引用了它，原来在 `skills/references/` 下，单独拷出技能后链接会断 |
| 运行框架目录 | 各级 `__init__.py`、`runtime/knowledge/__init__.py` 记入 build-manifest | 避免其他同名的 `runtime` 包遮住插件的包；三个示例的 build-manifest 已补上（摘要写作 `…`） |
| `fixtures/fullstack/` | 新增 `.mcp.json`、`hooks/hooks.json` 两个占位文件 | 入口文件引用了它们，D57 之后缺失会报 `PLUGIN_REF_MISSING` |
| 全栈版 v3 状态 | 旧别名 `discuss_in_progress`、`discuss_done` 不做映射，停在它们上面的 Feature 只读 | 别名是全栈版自己的历史，运行框架不写死某个插件的名字 |
