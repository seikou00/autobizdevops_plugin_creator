# 接口定义 v1

本文按调用双方划分，共四组接口：

| § | 调用方 → 被调用方 | 接口 |
|---|---|---|
| 1 | 插件开发者 → 脚手架 | `autobiz-plugin` CLI、初始化向导、插件开发技能 |
| 2 | 脚手架 → 模块；运行框架 → 模块 | 模块契约（构建期 `Module`、运行期知识组装） |
| 3 | DevClaw ↔ 插件 | `inspectCommands` 命令协议（DevClaw → 插件）；看板事件推送（插件 → DevClaw） |
| 4 | 模型 → 插件；运行框架 → 开发者命令；框架入口 → 内部库 | `update_state.py`、校验命令、知识组装脚本、`query.py` / `engine.py` |

静态文件格式见 [output-spec.md](output-spec.md)，输入配置字段见 [input-config.md](input-config.md)。下文的“宿主”均指 DevClaw；`board.*`、`session.*`、`knowledge.*`、`artifactSync.*` 分别指 `modules/board.json`、`modules/session.json`、`modules/knowledge.json`、`modules/artifactSync.json` 中的字段。

---

## 1. 脚手架 CLI

### 1.1 命令总览

| 命令 | 作用 |
|---|---|
| `autobiz-plugin new <dir> [--from blank\|lite\|fullstack] [--yes]` | 初始化向导：按 §1.4 的七类输入问答，生成入口文件 `plugin.scaffold.json`、`workflow.json`、需要的 `modules/*.json` 和工程目录，随后执行 build |
| `autobiz-plugin add node <id> --name <name> --skill <skill> [--stage <name>] [--after <nodeId>] [--input <artifactId> …] [--output <artifactId>=<path>[,<path>…] …] [--template <path> …] [--validate "<command>"]` | 在 `workflow.json` 中添加节点（同时生成技能桩文件）；`--output` 中写多个路径即为数组 |
| `autobiz-plugin add skill <skill> [--from <dir>]` | 导入已有技能资源（正文、模板、脚本、校验器），或创建空骨架 |
| `autobiz-plugin module list` | 列出可用模块与可选能力、版本及启用状态 |
| `autobiz-plugin module enable <id> [--set key=value …]` / `disable <id>` | 启用或关闭 `knowledge`、`artifactSync`、`knowledgeSedimentation`。`enable knowledge` / `enable artifactSync` 在 `modules/knowledge.json` / `modules/artifactSync.json` 不存在时创建骨架，并在入口文件中引用；`disable` 只去掉引用，文件保留。`enable artifactSync` 会把当前全部文件类产物连同显示名预填进 `artifacts`，开发者删掉不需要上传的即可。`knowledgeSedimentation` 写入 `modules/board.json` 的 `capabilities`（文件不存在时创建并引用） |
| `autobiz-plugin build [--dry-run] [--force]` | 输入 → 标准化输出 |
| `autobiz-plugin lint [--strict]` | 只检查核心配置（`workflow.json`、入口文件、`modules/*.json`）的结构和语义规则，以及编译配置是否过期（input-config.md §7.2）。只读、不联网，通常在 1 秒内完成 |
| `autobiz-plugin check [--strict]` | `lint` 加上技能内容、生成文件漂移检查，并运行契约测试，只读（input-config.md §7.3） |
| `autobiz-plugin git-hook install` | 把本仓库的 `core.hooksPath` 指向 `.githooks/`，之后每次提交前自动运行 `lint` |
| `autobiz-plugin simulate [--feature demo] [--to <checkpoint>] [--platform <p>] [--skip-validate] [--keep]` | 在临时工作区模拟宿主调用一遍 |
| `autobiz-plugin upgrade [--to <version>]` | 升级托管的运行框架和模块 |
| `autobiz-plugin package [-o <zip>]` | 重置运行期字段、check，然后打包 |

所有命令都支持 `-C <plugin-dir>`（默认为当前目录）和 `--json`（机器可读输出）。

`add` 和 `module` 只是修改配置文件的便捷入口，效果与手改配置后执行 build 相同：`add node` 写 `workflow.json`，`module` 写入口文件的 `modules` 引用和对应的 `modules/*.json`。

同一套命令还以技能形式提供：`autobiz-plugin-creator`（借鉴 Codex plugin-creator，见 README §2.3；规格见 §1.6）。技能负责与开发者对话、梳理流程、编写配置文件、生成技能展示文案；生成和校验仍然只通过上面的 CLI 完成。技能必须在 `build` 之后运行 `check`，并把 Issue 原样转述给开发者，不能自己修改 generated 或 managed 文件来绕过问题。

### 1.2 通用约定

| 退出码 | 含义 |
|---|---|
| `0` | 成功（可能带 warning） |
| `1` | 存在 error 级问题（校验失败、漂移、契约测试失败），没有写入任何文件 |
| `2` | 用法错误（参数不合法、找不到 `plugin.scaffold.json` 或 `workflow.json`） |

`build` 是事务性的：先在内存中完成全部生成和校验，再统一写盘。任何 error 都不会导致只写了一半。

### 1.3 问题（Issue）格式

`--json` 输出：

```json
{
  "ok": false,
  "issues": [
    {
      "level": "error",
      "code": "INPUT_FORWARD",
      "file": "workflow.json",
      "pointer": "/nodes/1/inputs/0",
      "message": "dev.specs 的输入 plan 由后续节点 dev.plan 产出",
      "hint": "调整节点顺序，让 dev.plan 排在 dev.specs 之前，或从 dev.specs 的 inputs 中去掉 plan"
    }
  ],
  "written": []
}
```

- `file` 标明问题所在的文件（`workflow.json`、`plugin.scaffold.json`、`modules/board.json`，或 `skills/autodev-plan/SKILL.md` 这类资源文件）；`pointer` 是该文件内的 JSON Pointer，问题出在文件层面时为空；
- `code` 的取值见 input-config.md §7.2、§7.3，此外还有 `MODULE_CONFLICT`（§2.3）；
- 不加 `--json` 时输出同样内容的可读文本，按文件和位置分组。

### 1.4 初始化向导（new）

向导按 input-config.md §1.1 的七类输入依次问答，每一类都可以跳过并使用默认值：

```text
── 1 插件基础信息 ──
? 插件 ID（slug，发布后不可修改）      › doc-review
? 插件名                                › Doc-Review-Kanban
? 版本 / 一句话描述                     › 0.1.0 / 文档起草与评审
── 2 核心流程（workflow.json）──
  节点 1
? 节点 id / 显示名                      › draft / 起草
? 所属阶段（可空）                      ›
? 绑定技能                              › （新建）doc-draft     ← 同时列出 skills/ 中已有的技能（含分组目录下的）
? 产出产物（id=路径，逗号分隔）        › draft=DRAFT.md
? 读取哪些前序产物（多选）              › （无）
? 完成时的校验命令（可空）              ›
? 继续添加节点？                        › Y
  …
── 3 技能资源 ──
? doc-draft：导入已有目录 / 创建空骨架  › 创建空骨架
── 4 看板 ──
? 目标平台                              › [x] darwin  [x] linux  [x] win32
? 可选能力                              › [ ] 知识沉淀入口
── 5 会话与 Agent ──
? 默认运行策略                          › solo
? 为节点单独配置策略？                  › N
── 6 知识与产物同步 ──
? 启用知识模块？                        › N
? 启用产物同步模块？                    › N
── 7 自定义扩展 ──
  已创建 hooks/（agents/ 可选，需要外挂子代理时再创建）
```

- 产物只写路径时，id 由路径推导（`DRAFT.md` → `draft`，`specs/*/spec.md` → `specs`），冲突时追问；
- 向导写完配置后先运行 `lint`，有 error 时回到对应问题重新回答，再执行 build；
- “创建空骨架”会生成 SKILL.md 桩文件和 `scripts/`；模板由技能自己维护，向导不问、不生成（D29）；节点填写了校验命令且脚本不存在时，追问是否生成校验器骨架；
- 看板一类会生成接入脚本（`runtime/adapters/*`）和三平台命令映射；会话一类会生成默认会话入口和策略骨架；
- 第 4–6 类的回答分别写入 `modules/board.json`、`modules/session.json`、`modules/knowledge.json` 和 `modules/artifactSync.json`，并在入口文件的 `modules` 中引用。全部取默认值的类别不生成文件，所以入口文件只有基础信息和真正用到的引用；
- `--yes` 时不提问，缺少的必填项报用法错误（退出码 2）。

`--from lite` / `--from fullstack` 以 [examples/lite/](../examples/lite/) 或 [examples/fullstack/](../examples/fullstack/) 的核心配置为起点，向导中的回答覆盖样例中的对应项。脚手架不提供从已有插件的 `board_config.json` 反推核心配置的命令：迁移已有插件时，以对应样例为起点修改核心配置，再用 `add skill --from` 导入技能目录。

### 1.5 simulate

在临时目录中创建 `<tmp>/ws/<project>`，按与宿主相同的方式替换占位符并执行命令：

1. `create_project`、`create_feature`；启用知识模块时再执行 `deploy_units`；
2. 对每个节点依次执行：`session_context_inject` → 推进 `_in_progress` → 为必需输出写入桩内容 → 推进 `_done`（执行节点校验命令）→ `feature_status`；
3. 用 §3 的结构校验每次输出，打印节点状态表和失败原因。

桩内容通常过不了业务校验，所以 `--skip-validate` 可以跳过校验命令；跳过时报告中会标明。`--to` 指定停在哪个 checkpoint，`--keep` 保留临时目录便于排查。simulate 只依赖本插件，不访问网络（知识组装只读本地知识目录）。

`check` 中的契约测试走同样的流程，但始终跳过校验命令。

### 1.6 插件开发技能 autobiz-plugin-creator（v1，D9）

位于脚手架仓库的 `skills/autobiz-plugin-creator/`，安装到开发者自己的 agent 环境中使用，不随生成的插件发布。它是初始化向导的对话形式。

```text
skills/autobiz-plugin-creator/
├── SKILL.md                  # 对话流程与规则（见下）
├── agents/openai.yaml
└── references/
    ├── input-config.md       # 从 docs/ 同步，供 agent 查字段
    └── modeling-guide.md     # 如何把业务流程拆成阶段、节点、产物、校验（含正反例）
```

frontmatter 中的 `description` 要写明触发场景，例如“新建看板插件”“给插件加节点或产物”“给节点加校验”“启用知识模块或产物同步”。

流程（SKILL.md 正文）：

| 步骤 | agent 做什么 | 调用 |
|---|---|---|
| 1. 定位 | 确认是新建还是修改；新建时确认插件放在哪个目录、插件 ID（提示发布后不可修改）、插件名 | `new --yes`（参数齐全后才调用） |
| 2. 建模 | 让开发者用自然语言描述流程，整理成“节点 → 阶段 → 技能 → 输入/输出产物 → 完成校验”表格回显，开发者确认后才写入 | 编辑 `workflow.json`，或调用 `add node`；写完运行 `lint` |
| 3. 技能资源 | 对每个节点确认是导入已有技能还是创建空骨架 | `add skill` |
| 4. 模块 | 询问看板可选能力（知识沉淀入口）、节点运行策略、是否需要知识模块（组装方由谁担任）、是否需要产物同步模块（从哪个节点起允许同步、上传哪些产物） | 编辑 `modules/*.json` 和入口文件的引用，或 `module enable` |
| 5. 生成 | 执行构建；对新生成的技能桩，与开发者确认触发场景后填写 `description`，并生成 `openai.yaml` 文案 | `build` |
| 6. 校验 | 执行完整校验，把 Issue 按原文转述给开发者，修改输入后重试 | `check` |
| 7. 演示 | 在临时工作区走一遍完整流程，展示每个节点的状态和产物路径 | `simulate` |

规则：

- 只修改 `workflow.json`、`plugin.scaffold.json`、`modules/*.json` 和 seeded/developer 文件，不得修改 generated、managed、module 文件来绕过校验，也不得直接修改编译配置 `runtime/config/*`；
- 每次修改核心配置后都运行 `lint`，没有 error 才继续下一步；
- 插件已经发布后，不得修改 `plugin.id` 和 `runtime.layout`；
- 涉及节点业务逻辑的技能正文和校验器由开发者负责，agent 只能起草，不能把未经确认的流程或校验规则写进去；
- 所有判断以 CLI 的退出码和 Issue 为准，不得自行宣称“校验通过”。

---

## 2. 模块契约

模块分两类：核心模块 `board`（看板）和 `session`（会话与 Agent）始终启用；`knowledge`（知识）和 `artifactSync`（产物同步）按配置启用，各自有独立的配置文件，入口文件引用即启用。知识沉淀入口只是 `board_core/modules.json` 中的一个看板入口，由 `board` 模块直接生成。

### 2.1 模块包结构

```text
scaffold/modules/<id>/
├── module.json          # 元数据
├── module.py            # 构建期实现（Module）
├── options.schema.json  # 本模块配置的 Schema，发布为 schemas/modules/<file>.schema.json
└── files/…              # 要拷贝进插件的文件（可含 {{ }} 模板）
```

`module.json`：

```json
{
  "id": "artifactSync",
  "version": "1.0.0",
  "title": "产物同步",
  "description": "按节点输出同步 Feature 产物，可选按实际代码生成接口文档",
  "config": { "file": "artifactSync", "pointer": "" },
  "requiresCore": ">=1.0.0 <2.0.0",
  "entry": "module:ArtifactSyncModule"
}
```

`config` 说明模块配置在哪里：`file` 是入口文件 `modules` 中的键，`pointer` 是该文件内的 JSON Pointer。知识模块和产物同步模块都是整个文件：`{"file": "knowledge", "pointer": ""}` 即 `modules/knowledge.json`，`{"file": "artifactSync", "pointer": ""}` 即 `modules/artifactSync.json`（D30）。

### 2.2 构建期接口（Python）

```python
from dataclasses import dataclass, field
from typing import Optional, Protocol, Union

@dataclass(frozen=True)
class ArtifactIR:
    id: str
    label: str                     # board.display.artifacts[id]，缺省为第一个路径
    paths: tuple[str, ...]         # 核心配置中为字符串时只有一项
    type: str                      # "file" | "json"，按扩展名推断
    producer: str                  # 第一个输出该产物的节点 id

@dataclass(frozen=True)
class NodeIR:
    id: str
    name: str
    stage: str                             # 未写时为默认分组名
    skill: str
    prefix: str                            # id 的最后一段
    order: int
    inputs: tuple[ArtifactIR, ...]         # v1 中输入输出都是必需的
    outputs: tuple[ArtifactIR, ...]
    validate: Optional[str]                # 单行命令原文，占位符未替换

    @property
    def checkpoints(self) -> tuple[str, str]:
        return (f"{self.prefix}_in_progress", f"{self.prefix}_done")

@dataclass(frozen=True)
class PluginIR:
    plugin: dict
    runtime: dict
    board: dict                            # target / display / capabilities，已填默认值
    session: dict                          # policies，已填默认值
    knowledge: dict                        # 未启用时为 {"enabled": False}
    stages: tuple[str, ...]                # 阶段名，按首次出现的顺序
    nodes: tuple[NodeIR, ...]
    artifacts: dict[str, ArtifactIR]
    checkpoint_chain: tuple[str, ...]      # 按流转顺序排列的全部 checkpoint

    def node(self, node_id: str) -> NodeIR: ...
    def checkpoints_from(self, anchor: str) -> tuple[str, ...]:
        """anchor 为 "<nodeId>:<in_progress|done>" 或 checkpoint 名；返回从 anchor 到链尾的 checkpoint。"""

@dataclass
class FileSpec:
    dst: str                               # 插件内相对路径
    ownership: str                         # "module" | "generated" | "seeded"
    src: Optional[str] = None              # 模块包内 files/ 下的源文件
    content: Optional[Union[str, bytes]] = None   # 直接给出内容（generated 常用）
    render: bool = False                   # 是否用 {{ ir / options }} 渲染 src

@dataclass
class CommandSpec:
    script: Optional[str] = None           # 相对插件根；生成 {py} "${pluginPath}/<script>" <args>
    args: str = ""
    value: Optional[str] = None            # 非命令值，例如 knowledge_path
    runtime_owned: bool = False

@dataclass
class Contribution:
    files: list[FileSpec] = field(default_factory=list)
    entries: dict = field(default_factory=dict)                    # 看板入口，写入 board_core/modules.json 顶层，例如 {"artifact_sync": {...}}
    manifest: dict = field(default_factory=dict)                   # 写入 modules.json 中本模块的条目，例如 {"assembler": "plugin", "source": True}
    runtime_config: dict[str, dict] = field(default_factory=dict)  # 写入 runtime/config/<name>.json，例如 {"knowledge": {...}}
    inspect_commands: dict[str, CommandSpec] = field(default_factory=dict)
    knowledge_assembly: Optional[dict] = None                      # {"script", "timeoutSec"}，写入 session.json 的 knowledgeAssembly
    skills: list[str] = field(default_factory=list)                # 模块占用的技能名
    gitignore: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class Issue:
    level: str        # "error" | "warning"
    code: str
    message: str
    file: str = ""
    pointer: str = ""
    hint: str = ""

class Module(Protocol):
    id: str
    version: str

    def defaults(self) -> dict:
        """模块参数默认值，与 config 指向处的输入深合并；配置文件未引用时直接使用默认值。"""

    def validate(self, ir: PluginIR, options: dict) -> list[Issue]:
        """语义校验。只读，不得有副作用。"""

    def contribute(self, ir: PluginIR, options: dict) -> Contribution:
        """纯函数：相同输入必须得到相同输出（build 的漂移检测依赖这一点）。"""
```

### 2.3 合并规则

| 贡献 | 规则 | 冲突时 |
|---|---|---|
| `entries` | 只能新增 `modules.json` 的顶层键，不能占用 `apiVersion`、`modules`、`boardEvents` | `MODULE_CONFLICT` |
| `manifest` | 只写本模块在 `modules.<id>` 下的条目，`enabled`、`version` 由核心填写 | `MODULE_CONFLICT` |
| `runtime_config` | 只能新增文件名；`runtime`、`flow`、`board`、`session` 由核心生成，模块不得占用 | `MODULE_CONFLICT` |
| `inspect_commands` | 写入 `board_config.json`。只能新增键，不能覆盖 output-spec.md §3.2 中标为“必有”的键；每个平台各生成一份。模块未启用时它贡献的键直接不出现（D1），不输出空值 | `MODULE_CONFLICT` |
| `files` | `dst` 不能与框架文件或其他模块重复 | `MODULE_CONFLICT` |
| `skills` | 不能与节点技能重名 | `MODULE_SKILL_CONFLICT` |
| `knowledge_assembly` | 写入 `runtime/config/session.json` 的 `knowledgeAssembly`（§2.4）；只有知识模块提供 | — |

### 2.4 运行期接口：知识组装

默认会话入口 `runtime/session/render_session_context.py` 读取 `runtime/config/session.json` 中的 `knowledgeAssembly`，执行其中的组装脚本，把输出并入会话内容。`knowledgeAssembly` 由知识模块在 `assembler = plugin` 时写入，其他情况为 `null`：

```json
{ "schema": "autobiz.session.v1",
  "knowledgeAssembly": { "script": "runtime/knowledge/render_collected_session_context.py", "timeoutSec": 30 },
  "…": "…" }
```

`script` 固定为内置组装脚本（output-spec.md §7.1），默认入口用运行框架当前的解释器执行它。插件替换了这个文件时，执行的就是插件的版本，协议不变（§4.5）。

---

## 3. 宿主命令协议

DevClaw 负责展示看板、发起会话、传入运行上下文、调用插件入口。它调用的全部入口都是 `runtime/` 下的框架入口，命令写在 `board_core/board_config.json` 的 `inspectCommands` 中；插件开启了哪些模块、看板上放哪些入口写在 `board_core/modules.json`（output-spec.md §3）。看板要展示的流程、节点、状态和产物全部由下面的命令输出，DevClaw 不读插件的其他文件。反方向上，插件在状态提交后把看板数据推送给 DevClaw 的本机服务（§3.5）。

### 3.1 通用约定

- 宿主先替换占位符，再执行命令，不保证工作目录。脚本必须通过 `__file__` 定位插件根目录；
- **stdout** 输出且只输出一个 UTF-8 JSON 对象，**stderr** 用于日志；
- 退出码：`0` 表示成功；`1` 表示业务失败，此时 stdout 为 `{"ok": false, "errors": ["…"]}`。`session_context_inject` 和 `pull_knowledge` 例外：始终以 `0` 退出，用 `ok` 字段表示结果（兼容现有宿主）；
- 只读命令（`project_status`、`feature_status`、`dynamic_workflow`、`session_context_inject`、`deploy_units`）不得创建或修改任何文件；
- `create_project`、`create_feature` 是幂等的，重复执行不会丢失已有进度；
- 写命令（`create_project`、`create_feature`、`skip_node`）和模型调用的 `update_state.py` 提交成功后推送看板事件（§3.5）。推送结果不影响 stdout 和退出码。

### 3.2 占位符

运行上下文全部由 DevClaw 通过下列占位符和 §3.4 的环境变量传入，插件配置中不得写死（D15）：

| 占位符 | 含义 | 允许出现在 |
|---|---|---|
| `${pluginPath}` | 插件安装目录 | 所有命令、`knowledge_path`、`system_prompt_inject`、技能正文 |
| `${pluginWorkspace}` | 项目集合工作区 | 所有命令、`plugin_dir_hook`、`system_prompt_inject`、`dialog_tips` |
| `${projectDir}` | 项目目录名 | 同上 |
| `${projectDirs...}` | 多个项目目录名，宿主逐个转义后展开 | `project_status` |
| `${feature}` | 当前 Feature | `feature_status`、`create_feature`、`session_context_inject`、`system_prompt_inject`、技能正文 |
| `${selectedDeployUnits}` | 所选发布单元，JSON 数组，宿主作为一个参数整体转义 | `create_feature`、`session_context_inject` |
| `${sessionWorkspacePath}` | 会话工作区目录 | `session_context_inject` |
| `${projectCode}` | 项目编码 | `dialog_tips`、`modules.json` 的 `knowledge_config.nextAction`、`artifact_sync.nextAction` |
| `${leanToken}` | 知识沉淀 token | `modules.json` 的 `knowledge_config.nextAction` |
| `${nodeId}` | 用户在看板上选中的节点 | `skip_node` |
| `${workflowTemplate}` `${workflowNodes}` | 全栈版旧模板（精简路线、自定义节点子集）使用 | 不使用（模板子集预留到 v2） |

校验命令使用的 `${python}`、`${projectPath}`、`${featureDir}` 等占位符由运行框架替换，不是宿主占位符，见 §4.3。

### 3.3 命令

#### 3.3.1 create_project（init_workspace.py）

```text
runtime/adapters/init_workspace.py --workspace <dir> --project <name>
```

```json
{ "ok": true, "initialized": true, "created": true,
  "statePath": "/…/<project>/.autobizdevops/<pluginId>/state.json", "warnings": [] }
```

处理宿主参数后调用 `engine.init_project`。路径按布局推导（output-spec.md §4.1），示例为 isolated 布局；legacy 布局下没有 `<pluginId>/` 这一层。

#### 3.3.2 create_feature（init_feature.py）

```text
runtime/adapters/init_feature.py --workspace <dir> --project <name> --feature <name>
                                 [--selected-deployUnit <json>] [--workflow-template standard] [--owner <s>] [--iteration <s>]
```

```json
{ "ok": true, "created": true, "checkpoint": "draft_in_progress",
  "statePath": "/…/<project>/.autobizdevops/<pluginId>/state.json",
  "featureDir": "/…/<project>/.autobizdevops/<pluginId>/features/<feature>",
  "warnings": [] }
```

- 处理宿主参数后调用 `engine.init_feature`；项目尚未初始化时先初始化项目；
- 新 Feature 的 checkpoint 为 `flow.json` 的 `checkpoints.initial`；
- `--selected-deployUnit` 中每个单元的 `deployUnitId`、`localRepoPath` 记入 Feature 记录的 `deployUnits`，git 产物（input-config.md §2.9）按它找仓库。重复执行时用新传入的列表更新 `deployUnits`，已记录的基线不变。会话中宿主仍会重新传入发布单元，`session_context_inject` 发现与记录不一致时只在 `message` 中提示，不改记录；
- Feature 目录已存在但 `state.json` 中没有对应记录时，返回 `ok:false`，避免覆盖未知产物。

#### 3.3.3 project_status（inspect_state.py）

```text
runtime/adapters/inspect_state.py --mode project --workspace <dir> --projects <name>...
```

```json
{
  "workflow": { "nodes": [ WorkflowNode ], "dynamicStages": [ DynamicStage ] },
  "projects": {
    "<project>": { "runs": [ { "featureId": "f1", "featureName": "f1", "currentNodeId": "dev.plan",
                               "currentNodeStatus": "in_progress", "currentNodeStatusLabel": "进行中",
                               "nodeIds": ["biz.prd", "dev.specs", "dev.plan", "dev.code"] } ] }
  }
}
```

`inspect_state.py` 调用 `query.py` 取得状态与流程数据（`runtime/config/flow.json`），再结合 `runtime/config/board.json` 的展示文案和 `session.json` 的运行策略，转换成看板接口数据。`workflow` 是静态的，同一次 build 下每次输出都相同；`runs[].nodeIds` 是该 Feature 实际经过的节点，包含已决定执行的动态阶段节点，不含被跳过的节点。

`WorkflowNode`（字段沿用全栈版 board_config 中的节点，DevClaw 原来从静态文件读取，现在从命令输出读取）：

```jsonc
{
  "id": "dev.plan", "label": "任务计划", "group": "Dev", "order": 40, "skill": "autodev-plan",
  "description": "…",
  "runtimePolicy": { "agentMode": "multi", "subagentConfig": { … } },   // 仅在节点配置了时输出
  "checkpoints": ["plan_in_progress", "plan_done"],
  "states": [
    { "nodeStatus": "not_started", "id": "not_started", "label": "未开始", "nextAction": { "slashSkill": "…", "userMessage": "…", "dialogTips": "…" } },
    { "nodeStatus": "in_progress", "id": "in_progress", "label": "进行中", "nextAction": { … } },
    { "nodeStatus": "done",        "id": "done",        "label": "已完成", "nextAction": { … } }
  ],
  "artifacts": { "inputs": [ ArtifactDef ], "outputs": [ ArtifactDef ] }
}
```

- `states` 按 not_started、in_progress、done 的顺序给出；终态节点只有 not_started、archived 两项，`checkpoints` 为 `["archived"]`。`skipped` 是运行期状态，由 `feature_status` 给出，不在 `states` 中列出。`states[].id` 与 `nodeStatus` 相同；
- `nextAction.slashSkill` 为空字符串表示流程结束，没有下一步；
- `workflow.nodes` 只列主干节点，动态阶段的节点在 `workflow.dynamicStages[].nodes` 中；
- 不再输出 `validators`：节点的校验命令由运行框架执行，不交给 DevClaw。

`ArtifactDef`（产物定义）：

```json
{ "id": "plan", "label": "实施计划", "artifactType": "file", "path": "plan.md", "required": true }
{ "id": "spec_bundle", "label": "proposal.md", "artifactType": "file", "path": "proposal.md",
  "paths": ["proposal.md", "specs/*/spec.md"], "required": true }
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

`DynamicStage`（有动态阶段时）：

```json
{
  "id": "detail_design_before_code", "phase": "Dev", "label": "详细设计", "description": "…", "order": 45,
  "choiceCheckpoint": "plan_done", "defaultDecision": "pending", "insertAfter": "dev.plan",
  "enableTargetCheckpoint": "detail_design_in_progress", "skipTargetCheckpoint": "code_in_progress",
  "enableLabel": "…", "skipLabel": "…", "enableDescription": "…", "skipDescription": "…",
  "nodes": [ { "id": "dev.detail_design", "phase": "Dev", "checkpointPrefix": "detail_design", "…": "其余字段同 WorkflowNode" } ]
}
```

执行时 `choiceCheckpoint → 阶段节点依次推进 → skipTargetCheckpoint`，跳过时 `choiceCheckpoint → skipTargetCheckpoint`。主干的 checkpoint 链与阶段标签见 `dynamic_workflow`（§3.3.5）。

`nextAction.slashSkill` 用于让宿主**带出**该技能，方便用户直接发起（D6），值为不带命名空间前缀的技能名；空字符串表示不带出任何技能。`userMessage` 和 `dialogTips` 是随技能一起带出的文案。

#### 3.3.4 feature_status（inspect_state.py）

```text
runtime/adapters/inspect_state.py --mode run --workspace <dir> --project <name> --feature <name>
```

```json
{
  "workflow": { "nodes": [ WorkflowNode ], "dynamicStages": [ DynamicStage ] },
  "run": {
    "featureId": "f1", "featureName": "f1",
    "workflowId": "base", "workflowProfile": "standard", "workflowTemplate": "standard",
    "workflowDecisions": {}, "workflowSkippedNodes": [],
    "pendingChoice": null,
    "currentNodeId": "dev.plan", "currentNodeStatus": "in_progress", "currentNodeStatusLabel": "进行中",
    "nodes": [
      { "id": "dev.specs", "nodeStatus": "done", "nodeStatusLabel": "已完成",
        "artifacts": [
          { "id": "proposal", "artifactLabel": "变更提案", "artifactStatus": "generated", "artifactStatusLabel": "已生成",
            "path": ".autobizdevops/<pluginId>/features/f1/proposal.md" },
          { "id": "specs", "artifactLabel": "行为规格", "artifactStatus": "missing", "artifactStatusLabel": "未生成",
            "paths": [".autobizdevops/<pluginId>/features/f1/specs/*/spec.md"] } ] },
      { "id": "dev.code", "nodeStatus": "in_progress", "nodeStatusLabel": "进行中",
        "artifacts": [
          { "id": "code", "artifactLabel": "代码提交", "artifactType": "git", "artifactStatus": "missing", "artifactStatusLabel": "未生成",
            "git": { "repos": [ { "key": "LF39.18_wg_flow", "path": "/Users/u/code/wg_flow", "branch": "feature/f1",
                                  "currentBranch": "feature/f1", "base": "a1b2c3d", "head": "9f8e7d6", "commits": 5,
                                  "uncommitted": ["src/Foo.java"], "unmergedWorktrees": [] } ],
                     "reasons": ["wg_flow 有 1 个文件未提交"] } } ] } ],
    "hookLogRefs": [ { "id": "default", "path": ".autobizdevops/<pluginId>/features/f1/hooks.ndjson", "format": "ndjson" } ],
    "watchRefs": [
      { "path": ".autobizdevops/<pluginId>/state.json", "purpose": "run-state" },
      { "path": ".autobizdevops/<pluginId>/features/f1", "purpose": "artifacts" },
      { "path": ".autobizdevops/<pluginId>/features/f1/hooks.ndjson", "purpose": "hook-log" } ]
  }
}
```

- `nodeStatus` 取值：当前节点之前的为 `done`；当前节点为 `in_progress` 或 `done`；之后的为 `not_started`；被跳过的为 `skipped`；终态节点到达后为 `archived`。Feature 不存在时，`currentNodeId` 为 `"unknown"`，状态为 `unknown`；
- `run.nodes` 按流程顺序列出：动态阶段已决定执行时，它的节点出现在插入位置；尚未选择（`pending`）时也列出，`nodeStatus` 为 `not_started`；已决定跳过时不列出；
- `pendingChoice` 在 Feature 停在某个动态阶段的选择点且尚未选择时给出，否则为 `null`：`{"stageId", "stageLabel", "choiceCheckpoint", "defaultDecision", "options": [{"decision": "enabled", "label", "description", "targetCheckpoint", "slashSkill"}, {"decision": "skipped", …}]}`；
- 示例为 isolated 布局，`<pluginId>` 为实际插件 ID；legacy 布局下没有这一层；
- 产物路径相对项目目录。单项且不含 glob 的产物用 `path`；含 glob 或 `path` 为数组的产物用 `paths`，列出实际匹配的文件，某一项没有匹配时给出该项的模式本身；
- `artifactStatus` 只表示文件是否存在（空文件也算已生成），不判断内容质量，也不代表节点已完成；
- git 产物（`artifactType: "git"`）没有 `path`，改为 `git`：每个仓库的基线与当前状态，以及不满足齐全条件的原因 `reasons`。节点已经开始时按记录的基线实时查仓库，满足全部齐全条件才算 `generated`；节点还没开始时没有基线，只列出仓库，状态为 `missing`。

#### 3.3.5 dynamic_workflow（inspect_workflow_templates.py）

```json
{
  "ok": true, "schemaVersion": "autobizdevops.workflow.templates.v2", "mode": "templates",
  "templates": [ { "id": "standard", "templateType": "classical", "label": "需求开发", "description": "…",
                   "nodes": ["biz.prd", "dev.specs", "dev.plan", "dev.code"] } ],
  "nodes": [ { "id": "dev.plan", "label": "任务计划", "group": "Dev", "skill": "autodev-plan", "description": "…",
               "inputs": [ ArtifactDef ], "outputs": [ ArtifactDef ] } ],
  "checkpoints": {
    "initial": ["prd_in_progress"],
    "transitions": { "prd_in_progress": ["prd_done"], "prd_done": ["specs_in_progress"], "…": [], "cicd_done": ["archived"], "archived": [] },
    "stageLabels": { "prd_in_progress": "需求澄清与 PRD进行中", "…": "…", "archived": "已归档" }
  },
  "transitions": [ { "id": "prd-to-specs", "from": { "nodeId": "biz.prd", "state": "done" }, "to": { "nodeId": "dev.specs", "state": "in_progress" } } ],
  "skipPolicy": { "lockedNodes": [] }
}
```

通过 `query.py` 查询流程定义，返回宿主需要的模板结构。`ArtifactDef` 见 §3.3.3；全栈版现有入口只输出 `{path, label}`，宿主应能兼容两种形态。全栈版 board_config 中 `workflow` 下的 `checkpoints`、`transitions`、`skipPolicy` 改由这里输出：`checkpoints.transitions` 只描述主干，最后一个主干节点是终态节点时前一节点的 `_done → archived`；`transitions` 是主干相邻节点的流转；`skipPolicy` 仅在开启 `rules.skip` 时输出。`templates` 只有 `standard` 一项（精简路线、自定义节点子集预留到 v2）；`nodes` 只列主干节点。

#### 3.3.6 system_prompt_inject / dialog_tips / plugin_dir_hook / knowledge_path

这些是模板字符串，宿主替换占位符后直接使用，不执行。

#### 3.3.7 session_context_inject（render_session_context.py）

```text
runtime/session/render_session_context.py --platform <p> --plugin-workspace <dir> --project <name> --feature <name>
                                          --selected-deployUnit <json> --session-workspace-path <dir>
                                          [--knowledge-path <dir>] [--node-id <id>]
```

```json
{
  "ok": true,
  "message": "remote 1 / local 0 / 缺 0",
  "sessionContext": "## 当前流程\n…\n\n## 知识\n…",
  "agentmdLoadStatus": [ { "deployUnitId": "LF39.18_wg_flow", "path": "…", "loaded": true, "source": "remote", "message": "…" } ],
  "flow": {
    "featureDir": "/…/<project>/.autobizdevops/<pluginId>/features/f1",
    "currentNodeId": "dev.plan", "currentNodeStatus": "in_progress",
    "targetNodeId": "dev.plan", "nextNodeId": "dev.code", "skill": "autodev-plan",
    "inputs":  [ { "id": "requirements", "required": true, "exists": true } ],
    "outputs": [ { "id": "plan", "required": true, "exists": false } ],
    "pendingChoice": null
  },
  "agentConfig": {
    "agentMode": "multi",
    "subagentConfig": { "disabledBuiltinSubagents": ["Explore", "critic"],
                        "customSubagentFiles": ["/abs/plugin/agents/explore.md"] }
  }
}
```

会话内容按以下顺序组成，`sessionContext` 用空行连接各段非空内容：

1. **流程上下文**（始终生成）：由 `query.py` 给出当前 Feature 的产物目录、当前节点与状态、策略目标节点及其技能、输入输出及存在情况、下一节点；停在动态阶段选择点时给出待选项（与 `feature_status` 的 `pendingChoice` 相同），提示模型先询问用户。结构化结果同时放在 `flow` 中；
2. **知识组装结果**（知识模块启用且 `assembler = plugin`）：执行知识模块的组装脚本 `render_collected_session_context.py`，插件可以替换它（§2.4、§4.5）。

`flow` 是新增字段，现有宿主忽略即可。`--knowledge-path` 覆盖 `knowledge.root`，生成的命令不带它，用于本地调试。

**策略目标节点**（与宿主拉起技能时依据的 nextAction 保持一致）：

1. 读取当前节点、当前状态下的 `nextAction.slashSkill`，找到拥有该技能的节点；
2. 找不到时，退回当前节点本身；
3. 仍然找不到时（Feature 未创建、参数缺失），只用 `session.policies.default`。

因此 not_started 和 in_progress 状态下取的是当前节点的策略，done 状态下取的是下一个节点的策略。`--node-id` 只用于本地调试，会直接指定节点。

**运行策略 → agentConfig 的映射**（目标节点的 `session.policies.nodes` 与 `policies.default` 深合并后映射）：

| agentConfig | 来源 | 内置默认值 |
|---|---|---|
| `agentMode` | `agentMode` | `solo` |
| `subagentConfig.disabledBuiltinSubagents` | 原样输出 | `[]` |
| `subagentConfig.customSubagentFiles` | 外挂资源路径拼接插件根目录，转为绝对路径，并按 `--platform` 规范分隔符；文件不存在时跳过，并在 `message` 中追加 `"外挂资源不存在，已跳过: <路径>"` | `[]` |
| `toolCustomConfig` | 原样输出；未配置时不输出 | — |

只有 `--selected-deployUnit` 不是合法 JSON 数组时才返回 `ok:false`，此时其余字段照常输出。未启用知识模块或 `assembler = devclaw` 时，`sessionContext` 中没有知识段，`agentmdLoadStatus` 为 `[]`。

#### 3.3.8 deploy_units（inspect_deploy_units.py，知识模块）

调用方是知识模块接入方：`assembler = devclaw` 时由 DevClaw 调用；`assembler = plugin` 时内置组装脚本在 collector 未命中时复用同一套解析逻辑。inspectCommands 中的键名 `deploy_units` 待与 DevClaw 确认（README §9）。

```text
runtime/knowledge/inspect_deploy_units.py [--knowledge-path <dir>] [--system <systemId>]
```

```json
{
  "ok": true, "schemaVersion": "autobizdevops.deploy-units.v1",
  "knowledgePath": "/abs/plugin/sys", "manifest": "agents.manifest.json", "manifestFormat": "agents-manifest-v1",
  "systems": [ { "systemId": "LF39", "systemName": "…", "agentsReady": true, "agentsPath": "sys/LF39/AGENTS.md",
                 "deployUnits": [ { "deployUnitId": "LF39.18_wg_flow", "name": "…", "description": "…" } ] } ],
  "supportedDeployUnits": ["LF39.18_wg_flow"]
}
```

只读，不访问网络。清单不存在或格式不符时返回 `{"ok": false, "errors": ["…"]}`，退出码 1。

#### 3.3.9 pull_knowledge（sync_knowledge.py，声明 knowledge.source 时）

```json
{
  "ok": true, "schemaVersion": "autobizdevops.agents.sync.v1",
  "message": "agents 仓库已同步：2 个系统、5 个发布单元，AGENTS.md 就绪 2/2",
  "repo": { "url": "…", "sshUrl": "…", "ref": "master", "commit": "…", "transport": "https" },
  "knowledge_path": "/abs/plugin/sys",
  "supported_deploy_units": ["…"],
  "systems": [ { "systemId": "LF39", "systemName": "…", "agentsReady": true, "agentsPath": "sys/LF39/AGENTS.md",
                 "deployUnits": [ { "deployUnitId": "…", "name": "…" } ] } ],
  "supported_deploy_units_source": "agents.manifest.json"
}
```

只更新知识目录，不回写任何配置文件。DevClaw 需要最新的发布单元时，读本输出的 `supported_deploy_units` 或再执行 `deploy_units`。失败时返回 `{"ok": false, "schemaVersion": "…", "message": "…", "errors": ["…"]}`，已有的知识目录保持不变。

#### 3.3.10 skip_node（skip_node.py，开启 rules.skip 时）

看板上用户选中节点并选择跳过时调用。此时不在会话中，没有 `PLUGIN_WORKSPACE`、`FEATURE_ID` 等环境变量，所以全部通过参数定位：

```text
runtime/adapters/skip_node.py --workspace <dir> --project <name> --feature <name> --node <nodeId> [--node <nodeId> …]
                              [--reason <text>] [--dry-run]
```

```json
{ "ok": true, "changed": true, "feature": "f1", "skipped": ["dev.design"],
  "oldCheckpoint": "design_in_progress", "checkpoint": "plan_in_progress", "statePath": "…", "warnings": [] }
```

- 处理宿主参数后调用 `engine.skip_nodes`，规则见 input-config.md §2.8；不满足时返回 `ok:false`，`state.json` 不变；
- 跳过的是当前节点时，`checkpoint` 为落地后的 checkpoint；跳过的是尚未开始的节点时，`checkpoint` 不变；
- 宿主未传 `--reason` 时记为 `看板操作跳过`；
- 成功后写一条 `skip-node` 变更日志（output-spec.md §4.3），并推送 `reason = skip_node` 的看板事件（§3.5）。

### 3.4 技能执行期的环境变量

由宿主在会话中注入，供技能和脚本使用：

| 变量 | 含义 |
|---|---|
| `PLUGIN_WORKSPACE` | 项目集合工作区 |
| `PROJECT_DIR` | 项目目录名（旧名 `PROJECT_CODE` 仍可读取） |
| `FEATURE_ID` | 当前 Feature |
| `SESSION_ID` | 会话 ID，写入 hooks.ndjson |
| `AUTOBIZ_BOARD_ENDPOINT` | DevClaw 看板事件服务的地址（§3.5）。除会话外，DevClaw 执行 inspectCommands 时也要注入 |

显式参数与环境变量冲突时（例如 `--feature` 与 `FEATURE_ID` 不同），脚本必须报错，不能任选其一。

### 3.5 看板事件推送（P0）

`project_status`、`feature_status` 是 DevClaw 调用最频繁的命令，每次调用都要启动一个 Python 进程（macOS、Python 3.9 上实测空解释器启动约 34 ms，再加上导入和读配置）。P0 改为插件主动推送：DevClaw 启动一个本机服务，插件的写入口提交成功后把最新的看板数据发给它，DevClaw 缓存后直接展示。§3.3 的读取命令保留，只用于冷启动和兜底。

由 DevClaw 起服务、插件作为客户端，原因是：

- 整台机器只有一个服务，插件再多也不增加常驻进程；
- 状态只在写入口中变化，在提交时推送即可，不需要监听文件；
- 状态仍由插件维护和解释。推送的内容就是读取命令输出的 JSON，DevClaw 不需要了解 `state.json`。

#### 3.5.1 通道与发现

| 项 | 约定 |
|---|---|
| 协议 | JSON-RPC 2.0 通知（不带 `id`，不需要回复），通过 HTTP/1.1 `POST` 发送，`Content-Type: application/json`，UTF-8 编码 |
| 服务端 | DevClaw 启动时在 `127.0.0.1` 的随机端口上监听，路径由 DevClaw 决定。收到后返回任意 2xx（建议 204），响应体会被忽略 |
| 发现 | DevClaw 把服务地址写入环境变量 `AUTOBIZ_BOARD_ENDPOINT`，例如 `http://127.0.0.1:53817/rpc`（§3.4）。它要注入到 DevClaw 执行的全部 inspectCommands 和发起的会话中；模型在会话中执行 `update_state.py` 时会自动继承 |
| 声明 | 插件在 `board_core/modules.json` 中写 `boardEvents`（output-spec.md §3.3），DevClaw 据此知道该插件会推送。没有这个键的插件按原方式处理 |

#### 3.5.2 消息

```json
{ "jsonrpc": "2.0", "method": "board/changed", "params": {
    "schema": "autobiz.board-events.v1",
    "pluginId": "doc-review", "pluginPath": "/abs/plugins/doc-review",
    "pluginWorkspace": "/abs/workspace", "projectDir": "p1",
    "seq": 12, "reason": "update_state", "sessionId": "…",
    "feature": "f1",
    "projectRuns": [ { "featureId": "f1", "currentNodeId": "dev.plan", "currentNodeStatus": "in_progress", "…": "…" } ],
    "run": { "featureId": "f1", "currentNodeId": "dev.plan", "nodes": [ "…" ], "…": "…" } } }
```

| 字段 | 说明 |
|---|---|
| `pluginPath`、`pluginWorkspace`、`projectDir` | 用于定位缓存。路径都已解析为绝对路径，DevClaw 应先对自己持有的路径取 realpath 再比较 |
| `seq` | 该项目内的事件序号，即 `state.json` 中的 `boardSeq`（output-spec.md §4.2），每次提交加 1 |
| `reason` | `create_project`、`create_feature`、`update_state`（重开、模型跳过节点也属于 `update_state`）、`skip_node`（看板上跳过节点） |
| `sessionId` | 环境变量 `SESSION_ID` 的值，没有时为空字符串 |
| `feature`、`run` | 本次涉及的 Feature 及其 `feature_status.run`（§3.3.4）；`create_project` 时两者都为 `null` |
| `projectRuns` | 该项目**全部** Feature 的摘要，即 `project_status` 中的 `projects.<project>.runs`（§3.3.3） |

节点定义 `workflow` 是静态的，不随事件发送。DevClaw 第一次调用读取命令时取得它并缓存。

#### 3.5.3 插件侧的发送规则

| 项 | 规则 |
|---|---|
| 谁发送 | `init_workspace.py`、`init_feature.py`、`skip_node.py`、`update_state.py` 在 engine 提交成功后调用 `runtime/adapters/board_events.py`。engine 只负责递增 `boardSeq` 并在返回值中给出，看板数据由适配层组装（D17） |
| 何时发送 | `create_project`、`create_feature` 每次调用都会提交并推送；`update_state` 只在状态实际改变时推送。`--dry-run`、检查失败、校验不通过、状态没有变化时都不推送 |
| 锁 | 必须在释放 `.state.lock` 之后发送，不能持锁发网络请求 |
| 超时与失败 | 只尝试一次，超时 300 ms，不重试。失败只在 stderr 写一行警告，命令的 stdout、退出码和 `warnings` 都不受影响 |
| 端点校验 | 只接受 `http`、回环地址（`127.0.0.1`、`localhost`、`::1`）和显式端口；不合法时在 stderr 警告并跳过。未设置端点时静默跳过 |
| 实现 | 只用标准库 `socket` 手写 HTTP 请求，并且只在设置了端点时才导入。不使用 `http.client`：它会连带导入 `email` 和 `ssl`，比 `socket` 方式多花约 30 ms。实测（macOS、Python 3.9）：导入 `socket` 方式约 10 ms，进程内推送一次不到 1 ms |

契约测试（`tests/contract/`）用一个模拟的 DevClaw 服务验证：事件内容与同一时刻读取命令的输出一致；`seq` 依次递增；DevClaw 未运行、响应超时或返回错误时，命令结果不变；未设置端点时不发送任何请求。

#### 3.5.4 顺序与一致性

- 看板数据在释放锁之后按当时的状态组装，所以事件内容可能比它的 `seq` 更新，但不会更旧。DevClaw 只保留 `seq` 最大的数据，结果总是正确的；
- `projectRuns` 每次都是全量。看板总览只需要最近一条事件，即使漏收了中间的事件也不会出错；
- 推送是尽力而为的：DevClaw 未运行、超时或重启都会漏收事件，由 §3.5.5 的拉取规则兜底。

#### 3.5.5 DevClaw 侧的处理规则

| 场景 | 处理 |
|---|---|
| 收到事件 | 按 (`pluginPath`, 项目目录的 realpath) 缓存。`seq` 小于或等于已缓存的值时丢弃；否则用 `projectRuns` 替换总览，用 `run` 替换该 Feature 的详情 |
| `seq` 跳号 | 说明漏收了事件。总览以本条事件为准；该项目其他 Feature 的详情缓存作废，下次显示时调用 `feature_status` |
| 冷启动 | DevClaw 启动后第一次显示某个项目时，按插件合并调用一次 `project_status`；第一次打开某个 Feature 时调用 `feature_status` |
| 插件升级或重新 build | 重新加载 `board_core/` 时，清空该插件的缓存（包括静态的 `workflow`） |
| 未声明 `boardEvents` 的插件 | 保持现有方式：执行读取命令、使用 `watchRefs` |
| 产物状态 | P0 中产物状态在两种时候更新：收到事件时（也就是节点推进时），以及打开 Feature 时拉取。对声明了 `boardEvents` 的插件，DevClaw 不再需要轮询读取命令或监听 `state.json` |

#### 3.5.6 后续（不在 P0）

| 项 | 内容 |
|---|---|
| 鉴权 | DevClaw 每次运行生成一个随机 token，通过 `AUTOBIZ_BOARD_TOKEN` 注入，插件请求时带上 `Authorization: Bearer <token>`。服务端校验 token 和 `Host` 头，防止浏览器页面发起跨站请求。服务只接受 `board/*` 通知，不提供任何执行操作的方法 |
| 产物实时刷新 | 不监听文件，改用 DevClaw 掌握的会话事件：模型写文件的工具调用落在 `run.watchRefs` 中 `purpose: artifacts` 的目录下时，防抖 1～2 秒后拉取一次 `feature_status` |
| 静态结果预生成 | `dynamic_workflow`、`deploy_units` 在 build 和 `pull_knowledge` 时预先写成文件，DevClaw 读一次后缓存 |
| 会话入口提速 | 根据 `session_context_inject` 的实测耗时，决定是否需要单独优化 |

P0 不做鉴权，本机任何进程都可以向 DevClaw 发送伪造的看板事件。因此推送只用于刷新显示，有疑问时以读取命令的结果为准；在鉴权实现之前，服务不得监听回环地址以外的地址。

---

## 4. 运行框架入口与内部库

### 4.1 入口总览

| 入口 | 调用方 | 主要职责 |
|---|---|---|
| `runtime/workflow/update_state.py` | 模型 | 接收状态更新请求，通过 `engine.py` 检查并修改 `state.json` |
| `runtime/adapters/init_workspace.py` | DevClaw 的 `create_project` | 处理宿主参数，通过引擎初始化项目 |
| `runtime/adapters/init_feature.py` | DevClaw 的 `create_feature` | 处理宿主参数，通过引擎初始化 Feature |
| `runtime/adapters/inspect_state.py` | DevClaw 的项目和 Feature 查询 | 调用查询库，将结果转换为看板接口数据 |
| `runtime/adapters/inspect_workflow_templates.py` | DevClaw 的动态工作流能力 | 查询流程定义，返回宿主需要的模板结构 |
| `runtime/adapters/skip_node.py` | DevClaw 的 `skip_node`（开启 `rules.skip` 时） | 处理宿主参数，通过引擎跳过节点 |
| `runtime/session/render_session_context.py` | DevClaw 的会话机制 | 获取流程上下文，结合会话策略及知识组装结果生成会话内容 |
| `runtime/knowledge/inspect_deploy_units.py` | 知识模块接入方 | 解析知识清单，提供支持的系统和发布单元信息 |
| `runtime/knowledge/sync_knowledge.py` | DevClaw 的 `pull_knowledge` | 拉取知识仓库并回写运行期字段（仅声明 `knowledge.source` 时） |

`update_state.py`、`init_workspace.py`、`init_feature.py`、`skip_node.py` 四个写入口在提交成功后，通过 `runtime/adapters/board_events.py` 推送看板事件（§3.5）。

### 4.2 update_state.py（模型推进状态的唯一入口）

```text
python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --checkpoint <cp> | --skip-node <nodeId> [--skip-node …]
       [--feature <name>] [--workspace <dir> [--project <name>]]
       [--reopen] [--reason <text>] [--owner <s>] [--iteration <s>] [--dry-run]
```

| 场景 | 规则 |
|---|---|
| 正常推进 | `<cp>` 必须等于当前 checkpoint，或是状态规则允许的下一个 |
| 推进到 `_in_progress` | 检查本节点的必需输入是否存在（optional、生产者被跳过或未执行的输入除外）；本节点有 git 产物时记录各仓库的基线，找不到仓库时拒绝推进。重开时沿用原基线 |
| 推进到 `_done` | 检查本节点的必需输入和必需输出是否存在，git 产物按齐全条件检查，再执行节点校验命令（§4.4），全部通过才写入，并记下各仓库完成时的 HEAD。git 条件不满足时 `errors` 中逐条列出原因（例如“wg_flow 有 3 个文件未提交”“工作树 ../wg_flow-sub 的分支 agent/t2 还有 2 个提交未合并”），不执行校验命令 |
| 推进到 `archived` | 只能从终态节点前一个节点的 `_done` 推进；检查终态节点的必需输入，不执行校验命令。之后不能再推进或重开 |
| 动态阶段选择 | 当前 checkpoint 是选择点时，推进到阶段第一个节点的 `_in_progress` 记为执行，推进到下一个主干节点的 `_in_progress` 记为跳过，写入 `workflowDecisions`。阶段执行时，最后一个节点 `_done` 的下一个是下一个主干节点的 `_in_progress` |
| 重开 | 必须加 `--reopen` 和非空的 `--reason`；只能回到当前或之前节点的 `_in_progress`（含已执行的动态阶段节点）。下游节点在看板上显示为未开始，旧产物保留；回到选择点之前时清除该阶段的决定，回到被跳过节点之前时恢复这些节点。重开不执行校验命令 |
| 跳过节点 | 开启 `rules.skip` 时，`--skip-node` 加非空的 `--reason`，不能与 `--checkpoint` 同时使用；规则见 input-config.md §2.8，与 `skip_node.py` 共用 `engine.skip_nodes` |
| `--dry-run` | 执行全部检查（包括校验命令），但不写 `state.json`、不写变更日志 |
| 定位 | 省略 `--workspace` 时，使用 `PLUGIN_WORKSPACE` + `PROJECT_DIR`；省略 `--feature` 时，使用 `FEATURE_ID` |

```json
{ "ok": true, "changed": true, "feature": "f1", "oldCheckpoint": "plan_in_progress", "checkpoint": "plan_done",
  "statePath": "…", "dryRun": false, "warnings": [],
  "validation": { "ran": true, "passed": true, "exitCode": 0, "durationMs": 812, "timedOut": false, "output": "…" } }
```

`validation` 只在执行了校验命令时输出。校验不通过时返回 `ok:false`，`errors` 中包含退出码（或超时）以及命令输出的末尾部分，`state.json` 保持不变。

状态实际改变时（`changed: true` 且不是 `--dry-run`），提交后推送一条 `reason = update_state` 的看板事件（§3.5）。输出格式不变。

不再提供 `update_checkpoint.py` 别名：迁移进来的技能由托管片段统一指向新入口，正文中残留的旧路径由 `check` 报 `LEGACY_ENTRY_REF`。

### 4.3 单行命令约定

节点校验命令（`validate`）是开发者提供的完整单行命令，由运行框架按以下规则执行：

1. 用 POSIX shell 规则（`shlex.split`）把命令拆成参数列表；
2. 逐个参数替换占位符：

   | 占位符 | 值 |
   |---|---|
   | `${python}` | 运行框架当前使用的解释器（`sys.executable`） |
   | `${pluginPath}` | 插件安装目录 |
   | `${skillPath}` | 本节点的技能目录 |
   | `${projectPath}` | `<pluginWorkspace>/<projectDir>` |
   | `${featureDir}` | 当前 Feature 的产物目录；尚无 Feature 时为空字符串 |
   | `${feature}` | 当前 Feature；尚无 Feature 时为空字符串 |
   | `${nodeId}` | 被完成的节点 |
   | `${repos}` | 本节点 git 产物涉及的仓库（或子目录）绝对路径，JSON 数组；没有 git 产物时为 `[]` |
   | `${gitRanges}` | 本节点每个仓库的提交范围 `<base>..<当前 HEAD>`，JSON 对象；没有 git 产物时为 `{}` |

3. 不经过 shell 直接执行（`shell=False`），所以不支持管道、重定向和 `&&`。Windows 上 `.cmd`/`.bat` 需要写成 `cmd /c …`；
4. 追加环境变量 `PLUGIN_ROOT`、`PROJECT_PATH`、`FEATURE_DIR`、`FEATURE_ID`、`NODE_ID`、`PYTHONIOENCODING=utf-8`，其余环境变量（包括 `SESSION_ID`）原样继承；
5. stdout 和 stderr 按 UTF-8 解码（无法解码的字节替换）。

占位符先拆分后替换，所以替换出来的路径含空格也不会被拆开，命令中的路径不需要加引号。

### 4.4 校验命令（validate）

| 项 | 约定 |
|---|---|
| 执行时机 | 仅在推进到 `<prefix>_done` 时、存在性检查通过之后执行；`_in_progress`、重开、查询都不执行 |
| 工作目录 | 当前 Feature 的产物目录 |
| 超时 | `runtime.validateTimeoutSec`，默认 120 秒 |
| 通过 | 退出码 `0` |
| 不通过 | 退出码非 `0`、超时，或命令无法启动。拒绝推进，`state.json` 不变 |
| 输出 | stdout 与 stderr 合并后截取末尾 2000 个字符，作为错误信息返回给模型；写给人看的原因应打印在输出末尾 |
| 变更日志 | 无论是否通过，都写一条 `node-validate` 事件（output-spec.md §4.3）；`--dry-run` 时不写 |

校验器负责判断空文件、格式、内容是否合格（D13）。它应当只读：不得修改产物、`state.json` 或插件目录。

### 4.5 知识组装脚本（render_collected_session_context.py）

知识模块启用且 `assembler = plugin` 时，默认会话入口在生成流程上下文和 `agentConfig` 之后，用运行框架当前的解释器执行 `runtime/knowledge/render_collected_session_context.py`。这个文件默认是脚手架内置的版本，插件可以整个替换它（input-config.md §4.4）。不论哪个版本，都按以下协议交互：

- **stdin**：一个 JSON 对象，含会话请求和已经算好的流程上下文与 `agentConfig`：

  ```json
  { "schema": "autobiz.session.request.v1", "platform": "darwin", "pluginRoot": "…",
    "pluginWorkspace": "…", "project": "…", "feature": "f1", "featureDir": "…",
    "selectedDeployUnits": [ { "deployUnitId": "…", "localRepoPath": "…", "description": "…" } ],
    "sessionWorkspacePath": "…", "knowledgePath": "/abs/plugin/sys",
    "flow": { … }, "agentConfig": { … } }
  ```

  `selectedDeployUnits` 已解析并校验；`knowledgePath` 为 `knowledge.root` 的绝对路径，调用方传了 `--knowledge-path` 时以它为准；`featureDir` 在 Feature 尚未创建时为空字符串；
- **stdout**：`{"sessionContext": "…", "agentmdLoadStatus": [ … ], "message": "…"}`，三个字段都可以省略。`sessionContext` 是知识段，追加在流程上下文之后；`agentmdLoadStatus` 的条目格式见 §3.3.7；
- 工作目录为插件根目录，超时为 `knowledge.assembly.timeoutSec`（默认 30 秒）；
- 退出码非 0、超时或输出不是合法 JSON 时，本次会话不含知识段，`agentmdLoadStatus` 为 `[]`，在 `message` 中追加 `"知识组装失败: <原因>"`，`session_context_inject` 仍然返回 `ok:true`；
- 只负责知识段：不能修改 `agentConfig` 和 `flow`，流程上下文和运行策略始终由默认入口给出；
- stdout 只用于协议 JSON，日志写 stderr；不得修改项目文件和知识目录，知识仓库同步是 `pull_knowledge` 的职责。

内置组装脚本的做法（来自全栈版）：调用同目录的 `collect-knowledge.js`（需要 Node）列出 collector 支持的发布单元，再逐个取所选单元的知识；collector 不可用（没有 Node、接口失败、超时）或单元不在它的列表中时，按清单映射加载，最后回退 `<localRepoPath>/AGENTS.md`。另外始终读取 `<sessionWorkspacePath>/AGENTS.md` 作为会话工作区指令。collector 依赖的 `gray-matter` 缺失时，首次运行会在 `runtime/knowledge/` 下执行 `npm install`（README §9）。

插件替换这个文件时，只需在同一路径实现上面的协议。主体逻辑可以用任何语言写，由这个 Python 文件调用（内置版本就是这样调用 Node 的）。build 和 upgrade 不覆盖被替换的文件（README §4）。

### 4.6 内部库 query.py / engine.py

| 模块 | 负责什么 | 边界 |
|---|---|---|
| `query.py` | 读取编译配置和现有状态；查询 Feature、当前节点、下一节点、技能、输入输出及产物存在情况 | 只读，不执行校验命令、不修改状态、不运行技能；文件存在不代表节点完成 |
| `engine.py` | 初始化项目及 Feature；检查状态转移；检查产物；完成时运行配置的校验；提交状态及变更日志 | 不执行技能正文、不生成业务产物、不处理看板格式或会话提示词 |

两个模块由框架入口通过 Python import 使用，不注册为宿主命令，也不要求用户技能调用（D17）。

```python
from runtime.common import query, engine

# —— query：定位 ——
query.plugin_root() -> Path
query.plugin_id() -> str                                         # runtime/config/runtime.json
query.load_flow() -> dict                                        # runtime/config/flow.json，已校验不变量
query.resolve_project(workspace: str | None = None, project: str | None = None) -> Path
    # 显式参数优先；否则读 PLUGIN_WORKSPACE + PROJECT_DIR；拒绝插件安装目录
query.resolve_feature(feature: str | None = None, *, required: bool = True) -> str
    # 与 FEATURE_ID 冲突时报错；校验路径安全
query.metadata_dir(project_path: Path) -> Path
    # isolated：<project>/.autobizdevops/<pluginId>；legacy：<project>/.autobizdevops
query.feature_dir(project_path: Path, feature: str) -> Path      # metadata_dir(...) / "features" / feature

# —— query：流程与状态 ——
query.list_features(project_path: Path) -> list[dict]
query.feature_record(project_path: Path, feature: str) -> dict | None
query.current_node(project_path: Path, feature: str) -> tuple[dict, str]   # (节点, "in_progress"|"done")
query.next_node(node_id: str, record: dict | None = None) -> dict | None
    # 按 Feature 记录中的 workflowDecisions、workflowSkippedNodes 求下一节点；不传 record 时按 defaultDecision
query.active_nodes(record: dict) -> list[dict]                   # 该 Feature 实际经过的节点（含已执行的动态阶段节点，不含被跳过的）
query.pending_choice(record: dict) -> dict | None                 # 停在选择点且尚未选择时返回待选项
query.node_skill(node_id: str) -> str
query.node_artifacts(node_id: str, direction: str = "outputs") -> list[dict]
query.checkpoint_chain() -> list[str]

# —— query：产物存在情况 ——
query.artifact_presence(project_path: Path, feature: str, artifact_id: str) -> dict
    # 文件产物：{"exists": bool, "files": [Path], "missing": [pattern]}；拒绝越界符号链接
    # git 产物：{"exists": bool, "repos": [ … ], "reasons": [str]}，按 Feature 记录中的基线实时查仓库，只读

# —— engine：初始化与状态变更 ——
engine.init_project(project_path: Path) -> dict
engine.init_feature(project_path: Path, feature: str, *, owner: str | None = None,
                    iteration: str | None = None, template: str = "standard") -> dict
engine.transition(project_path: Path, feature: str, checkpoint: str, *, reopen: bool = False,
                  reason: str = "", dry_run: bool = False) -> dict
    # 状态转移检查（含动态阶段选择、archived）→ 产物存在性检查 → （_done 时）校验命令
    # → 加锁提交 state.json → 写变更日志
engine.skip_nodes(project_path: Path, feature: str, node_ids: list[str], *, reason: str,
                  dry_run: bool = False) -> dict
    # 跳过规则检查 → 记录 workflowSkippedNodes → 必要时落到下一个节点 → 加锁提交 → 写 skip-node 日志
# 以上函数提交时都在锁内把 state.json 的 boardSeq 加 1，返回值中带 "boardSeq"，供入口推送看板事件（§3.5）

class engine.BoardError(ValueError): ...                          # 所有业务错误都抛这个类型
```

使用范围：

- 框架入口（`runtime/` 下的脚本）和框架模块（知识模块、产物同步脚本）与运行框架同版本发布，可以导入这两个模块；
- 开发者的技能脚本、校验器和自定义扩展不需要、也不应该导入它们：所需的路径和状态从会话上下文、校验命令占位符和环境变量获得；
- 两个模块不承诺对开发者代码的接口稳定性，随运行框架版本一起变化。

---

## 5. 版本与兼容

| 版本号 | 位置 | 何时升级 |
|---|---|---|
| `scaffoldVersion` | `plugin.scaffold.json` | 入口文件格式出现不兼容变化时升主版本，脚手架提供 `migrate` |
| 模块配置格式 | `modules/*.json` | 不单独标版本，随模块主版本变化；出现不兼容变化时由模块提供迁移 |
| 核心流程格式 | `workflow.json` | 不单独标版本，随 `scaffoldVersion` 变化 |
| `apiVersion` | `board_core/board_config.json`、`board_core/modules.json` | 宿主协议出现不兼容变化时（与 DevClaw 共同决定） |
| 运行框架版本 | build-manifest 的 `coreVersion` | 遵循 semver；同一主版本内 `upgrade` 可以直接替换 |
| 模块版本 | 模块包的 `module.json`、插件的 `board_core/modules.json`、build-manifest | 遵循 semver；`requiresCore` 不满足时拒绝启用 |
| `state.json.schemaVersion` | 运行期 | 状态格式变化时；新版运行框架必须能读取旧版本 |
| `schemaVersion` 字符串 | 各命令输出 | 例如 `autobizdevops.workflow.templates.v2`、`autobizdevops.agents.sync.v1`；沿用现有值 |
| `boardEvents.protocol` | `board_core/modules.json`、看板事件的 `params.schema` | 看板事件消息出现不兼容变化时，例如 `autobiz.board-events.v1` → `v2`（§3.5） |

兼容承诺：

- 由 lite 迁移过来的插件只要保持 `plugin.id` 和 `layout: legacy` 不变，已有项目的 `state.json` 可以直接继续使用；
- 现有全栈版插件的产物同步 v1 配置，在新模块中仍可读取；
- 全栈版迁入后保持 `layout: legacy`；它已有项目的 `state.json`（`autobizdevops.state.v3`，不带 `pluginId`）怎么接续，见 README §9。

由 lite 迁移时的行为差异：

- 入口从 `hooks/`、根目录迁到 `runtime/`，board_config 中的命令随之重新生成；board_config 只剩 `inspectCommands`，流程定义改由命令输出，看板入口移到 `modules.json`；技能托管片段中的状态命令也会更新；
- 框架不再检查产物是否为空。lite 现在“去除空白后非空”的判定，如需保留，要写成节点的校验命令；
- 会话内容新增流程上下文段；
- 节点描述、产物显示名移到 `modules/board.json`，编译结果不变；
- `plan.md` 对旧文件名 `PLAN.md` 的回退不再支持。macOS、Windows 默认文件系统不区分大小写，不受影响；Linux 上的旧 Feature 需要把文件改名。
