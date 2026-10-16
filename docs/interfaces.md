# 接口定义 v1

本文按调用双方划分，共四组接口：

| § | 调用方 → 被调用方 | 接口 |
|---|---|---|
| 1 | 插件开发者 → 脚手架 | `autobiz-plugin` CLI、初始化向导、插件开发技能 |
| 2 | 脚手架 → 模块；运行框架 → 模块 | 模块契约（构建期 `Module`、运行期会话片段） |
| 3 | DevClaw → 插件 | `inspectCommands` 命令协议 |
| 4 | 模型 → 插件；运行框架 → 开发者命令；框架入口 → 内部库 | `update_state.py`、校验命令、自定义会话入口、`query.py` / `engine.py` |

静态文件格式见 [output-spec.md](output-spec.md)，输入配置字段见 [input-config.md](input-config.md)。下文的“宿主”均指 DevClaw。

---

## 1. 脚手架 CLI

### 1.1 命令总览

| 命令 | 作用 |
|---|---|
| `autobiz-plugin new <dir> [--from blank\|lite] [--import <plugin-dir>] [--yes]` | 初始化向导：按 §1.4 的七类输入问答，生成 `plugin.scaffold.json`、`workflow.json` 和工程目录，随后执行 build |
| `autobiz-plugin add stage <id> --label <label>` | 添加阶段 |
| `autobiz-plugin add artifact <id> --path <path> [--path <path2> …] --label <label> [--type json]` | 注册产物；`--path` 写多次即为数组 |
| `autobiz-plugin add node <stage>.<name> --label <label> --skill <skill> [--after <nodeId>] [--inputs a,b] [--outputs c] [--template <path> …] [--validate "<command>"]` | 添加节点（同时生成技能桩文件） |
| `autobiz-plugin add skill <skill> [--from <dir>]` | 导入已有技能资源（正文、模板、脚本、校验器），或创建空骨架 |
| `autobiz-plugin module list` | 列出可用模块与可选能力、版本及启用状态 |
| `autobiz-plugin module enable <id> [--set key=value …]` / `disable <id>` | 启用或关闭 `knowledge`、`artifactSync`、`knowledgeSedimentation`；后两个写入 `board.capabilities` |
| `autobiz-plugin build [--dry-run] [--force]` | 输入 → 标准化输出 |
| `autobiz-plugin check [--strict]` | 校验输入、漂移、技能，并运行契约测试，只读 |
| `autobiz-plugin simulate [--feature demo] [--to <checkpoint>] [--platform <p>] [--skip-validate] [--keep]` | 在临时工作区模拟宿主调用一遍 |
| `autobiz-plugin upgrade [--to <version>]` | 升级托管的运行框架和模块 |
| `autobiz-plugin package [-o <zip>]` | 重置运行期字段、check，然后打包 |

所有命令都支持 `-C <plugin-dir>`（默认为当前目录）和 `--json`（机器可读输出）。

`add` 和 `module` 只是修改 `workflow.json`、`plugin.scaffold.json` 的便捷入口，效果与手改配置后执行 build 相同：`add stage/artifact/node` 写 `workflow.json`，`module` 写 `plugin.scaffold.json`。

同一套命令还以技能形式提供：`autobiz-plugin-creator`（借鉴 Codex plugin-creator，见 README §2.3；规格见 §1.6）。技能负责与开发者对话、梳理流程、编写两份配置、生成技能展示文案；生成和校验仍然只通过上面的 CLI 完成。技能必须在 `build` 之后运行 `check`，并把 Issue 原样转述给开发者，不能自己修改 generated 或 managed 文件来绕过问题。

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
      "code": "INPUT_REF_FORWARD",
      "file": "workflow.json",
      "pointer": "/nodes/1/inputs/0",
      "message": "dev.specs 的输入 plan 由后续节点 dev.plan 产出",
      "hint": "调整节点顺序，或在输入中声明 {\"ref\":\"plan\",\"external\":true}"
    }
  ],
  "written": []
}
```

- `file` 标明问题所在的文件（`workflow.json`、`plugin.scaffold.json`，或 `skills/autodev-plan/SKILL.md` 这类资源文件）；`pointer` 是该文件内的 JSON Pointer，问题出在文件层面时为空；
- `code` 的取值见 input-config.md §6，此外还有 `DRIFT_GENERATED`、`DRIFT_MANAGED`、`MODULE_CONFLICT`、`CONTRACT_TEST`；
- 不加 `--json` 时输出同样内容的可读文本，按文件和位置分组。

### 1.4 初始化向导（new）

向导按 input-config.md §1.1 的七类输入依次问答，每一类都可以跳过并使用默认值：

```text
── 1 插件基础信息 ──
? 插件 ID（slug，发布后不可修改）      › doc-review
? 插件名                                › Doc-Review-Kanban
? 版本 / 一句话描述                     › 0.1.0 / 文档起草与评审
── 2 核心流程（workflow.json）──
? 阶段（id:显示名，逗号分隔）           › biz:Biz
  节点 1
? 所属阶段 / 节点名                     › biz / draft
? 显示名                                › 起草
? 绑定技能                              › （新建）doc-draft     ← 同时列出 skills/ 和 --import 来源中已有的技能
? 产出产物（路径，逗号分隔）            › DRAFT.md
? 读取哪些前序产物（多选）              › （无）
? 引用模板（可空）                      › skills/doc-draft/templates/DRAFT.md
? 完成时的校验命令（可空）              ›
? 继续添加节点？                        › Y
  …
── 3 技能资源 ──
? doc-draft：导入已有目录 / 创建空骨架  › 创建空骨架
── 4 看板 ──
? 目标平台                              › [x] darwin  [x] linux  [x] win32
? 可选能力                              › [ ] 知识沉淀入口  [ ] 产物同步
── 5 会话与 Agent ──
? 默认运行策略                          › solo，启用 task
? 为节点单独配置策略？                  › N
? 自定义会话入口命令（可空）            ›
── 6 知识 ──
? 启用知识模块？                        › N
── 7 自定义扩展 ──
  已创建 hooks/、agents/
```

- 产物 id 由路径推导（`DRAFT.md` → `draft`，`specs/*/spec.md` → `specs`），冲突时追问；
- “创建空骨架”会生成 SKILL.md 桩文件、`templates/`、`scripts/`；节点填写了校验命令且脚本不存在时，追问是否生成校验器骨架；
- 看板一类会生成接入脚本（`runtime/adapters/*`）和三平台命令映射；会话一类会生成默认会话入口和策略骨架；
- `--yes` 时不提问，缺少的必填项报用法错误（退出码 2）。

`--import <plugin-dir>` 从现有插件反推输入：把 `board_config.json` 拆成 `workflow.json`（阶段、节点、产物）和 `plugin.scaffold.json`（展示文案覆写、运行策略、模块），可推导的部分丢弃，与默认值不同的部分写成覆写项；同时把现有技能目录作为技能资源导入。无法表达的字段（v2 能力，例如 `dynamicStages`）列为 warning，并原样保存在 `x-unsupported` 中，不会静默丢失。导入 lite 应得到与 [examples/lite/](../examples/lite/) 等价的输入。

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
| 2. 建模 | 让开发者用自然语言描述流程，整理成“阶段 → 节点 → 技能 → 输入/输出产物 → 模板 → 完成校验”表格回显，开发者确认后才写入 | 编辑 `workflow.json`，或调用 `add stage/node/artifact` |
| 3. 技能资源 | 对每个节点确认是导入已有技能还是创建空骨架 | `add skill` |
| 4. 模块 | 询问看板可选能力（知识沉淀入口、产物同步：从哪个节点起允许同步、是否生成接口文档）、节点运行策略、是否需要知识模块（组装方由谁担任） | 编辑 `plugin.scaffold.json`，或 `module enable` |
| 5. 生成 | 执行构建；对新生成的技能桩，与开发者确认触发场景后填写 `description`，并生成 `openai.yaml` 文案 | `build` |
| 6. 校验 | 执行校验，把 Issue 按原文转述给开发者，修改输入后重试 | `check` |
| 7. 演示 | 在临时工作区走一遍完整流程，展示每个节点的状态和产物路径 | `simulate` |

规则：

- 只修改 `workflow.json`、`plugin.scaffold.json` 和 seeded/developer 文件，不得修改 generated、managed、module 文件来绕过校验；
- 插件已经发布后，不得修改 `plugin.id` 和 `runtime.layout`；
- 涉及节点业务逻辑的技能正文和校验器由开发者负责，agent 只能起草，不能把未经确认的流程或校验规则写进去；
- 所有判断以 CLI 的退出码和 Issue 为准，不得自行宣称“校验通过”。

---

## 2. 模块契约

模块分两类：核心模块 `board`（看板）和 `session`（会话与 Agent）始终启用；`knowledge`（知识）和 `artifactSync`（产物同步，看板可选能力）按配置启用。知识沉淀入口只是一段 board_config 配置，由 `board` 模块直接生成。

### 2.1 模块包结构

```text
scaffold/modules/<id>/
├── module.json          # 元数据
├── module.py            # 构建期实现（Module）
├── options.schema.json  # 本模块在 plugin.scaffold.json 中对应配置的 Schema 片段
└── files/…              # 要拷贝进插件的文件（可含 {{ }} 模板）
```

`module.json`：

```json
{
  "id": "artifactSync",
  "version": "1.0.0",
  "title": "产物同步",
  "description": "按节点输出同步 Feature 产物，可选按实际代码生成接口文档",
  "optionsPointer": "/board/capabilities/artifactSync",
  "requiresCore": ">=1.0.0 <2.0.0",
  "entry": "module:ArtifactSyncModule"
}
```

`optionsPointer` 是模块配置在 `plugin.scaffold.json` 中的 JSON Pointer（知识模块为 `/knowledge`）。

### 2.2 构建期接口（Python）

```python
from dataclasses import dataclass, field
from typing import Optional, Protocol, Union

@dataclass(frozen=True)
class ArtifactIR:
    id: str
    label: str
    paths: tuple[str, ...]         # 输入为字符串时只有一项
    type: str                      # "file" | "json"
    legacy_paths: tuple[str, ...]  # 只在 paths 为单项时可能非空
    producer: Optional[str]        # 第一个输出该产物的节点 id；仅作为外部输入时为 None

@dataclass(frozen=True)
class ArtifactUse:
    artifact: ArtifactIR
    required: bool
    degrade: str = ""

@dataclass(frozen=True)
class NodeIR:
    id: str
    stage: str
    label: str
    skill: str
    prefix: str
    order: int
    inputs: tuple[ArtifactUse, ...]
    outputs: tuple[ArtifactUse, ...]
    templates: tuple[str, ...]
    validate: Optional[str]                # 单行命令原文，占位符未替换

    @property
    def checkpoints(self) -> tuple[str, str]:
        return (f"{self.prefix}_in_progress", f"{self.prefix}_done")

@dataclass(frozen=True)
class PluginIR:
    plugin: dict
    runtime: dict
    board: dict                            # target / display / capabilities，已填默认值
    session: dict                          # customEntry / policies，已填默认值
    knowledge: dict                        # 未启用时为 {"enabled": False}
    stages: tuple[dict, ...]               # [{"id","label"}]
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
    config: dict = field(default_factory=dict)                     # 新增 board_config 顶层键
    runtime_config: dict[str, dict] = field(default_factory=dict)  # 写入 runtime/config/<name>.json，例如 {"knowledge": {...}}
    runtime_fields: list[str] = field(default_factory=list)        # 例如 "supported_deploy_units"
    inspect_commands: dict[str, CommandSpec] = field(default_factory=dict)
    session_parts: list[str] = field(default_factory=list)         # "runtime.knowledge.assembler:assemble"
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
        """模块参数默认值，与 optionsPointer 处的输入深合并。"""

    def validate(self, ir: PluginIR, options: dict) -> list[Issue]:
        """语义校验。只读，不得有副作用。"""

    def contribute(self, ir: PluginIR, options: dict) -> Contribution:
        """纯函数：相同输入必须得到相同输出（build 的漂移检测依赖这一点）。"""
```

### 2.3 合并规则

| 贡献 | 规则 | 冲突时 |
|---|---|---|
| `config` | 只能新增顶层键，不能覆盖核心键（`apiVersion`、`inspectCommands`、`workflow`、`checkpointSuffixState`） | `MODULE_CONFLICT` |
| `runtime_config` | 只能新增文件名；`runtime`、`flow`、`session` 由核心生成，模块不得占用 | `MODULE_CONFLICT` |
| `inspect_commands` | 只能新增键，不能覆盖 output-spec.md §3.2 中标为“必有”的键；每个平台各生成一份。模块未启用时它贡献的键直接不出现（D1），不输出空值 | `MODULE_CONFLICT` |
| `files` | `dst` 不能与框架文件或其他模块重复 | `MODULE_CONFLICT` |
| `skills` | 不能与节点技能重名 | `MODULE_SKILL_CONFLICT` |
| `session_parts` | 按模块启用顺序写入 `runtime/config/session.json` 的 `parts` | — |
| `runtime_fields` | 汇总写入 build-manifest，供 build（保留）和 package（重置）使用 | — |

### 2.4 运行期接口：会话片段

默认会话入口 `runtime/session/render_session_context.py` 读取 `runtime/config/session.json` 中的 `parts`，依次调用模块注册的会话片段。目前只有知识模块的内置组装器注册（`assembler = plugin` 时）：

```json
{ "schema": "autobiz.session.v1", "parts": ["runtime.knowledge.assembler:assemble"], "…": "…" }
```

```python
# runtime/session 内部定义
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

@dataclass(frozen=True)
class SessionRequest:
    plugin_root: Path
    platform: str                         # "darwin" | "linux" | "win32"
    plugin_workspace: str
    project: str
    feature: str
    feature_dir: Optional[Path]           # Feature 尚未创建时为 None
    selected_deploy_units: list[dict]     # [{"deployUnitId","localRepoPath","description"}]，已解析并校验
    session_workspace_path: str
    knowledge_path: Optional[Path]
    flow: dict                            # 流程上下文，结构同 §3.3.7 的 flow
    policy_node: Optional[dict]           # 策略目标节点（规则见 §3.3.7）

@dataclass
class SessionPart:
    session_context: str = ""
    load_status: list[dict] = field(default_factory=list)   # agentmdLoadStatus 条目
    message: str = ""

def assemble(request: SessionRequest) -> SessionPart: ...
```

会话片段约束：

- 不得写 stdout（stdout 只用于协议 JSON），日志写 stderr；
- 不得访问网络、不得写文件：知识同步是 `pull_knowledge` 的职责，组装器只读本地知识目录；
- 不应抛异常。即使抛出，默认入口也会捕获，在 `message` 中追加 `"<part> 失败: <原因>"`，并继续调用后续片段；
- 结果合并方式：`sessionContext` 用空行连接各段非空内容；`agentmdLoadStatus` 依次拼接；`message` 用 ` / ` 连接。

开发者不通过这个接口扩展会话，而是使用自定义会话入口（§4.5）。

---

## 3. 宿主命令协议

DevClaw 负责展示看板、发起会话、传入运行上下文、调用插件入口。它调用的全部入口都是 `runtime/` 下的框架入口，命令写在 `board_config.json` 的 `inspectCommands` 中。

### 3.1 通用约定

- 宿主先替换占位符，再执行命令，不保证工作目录。脚本必须通过 `__file__` 定位插件根目录；
- **stdout** 输出且只输出一个 UTF-8 JSON 对象，**stderr** 用于日志；
- 退出码：`0` 表示成功；`1` 表示业务失败，此时 stdout 为 `{"ok": false, "errors": ["…"]}`。`session_context_inject` 和 `pull_knowledge` 例外：始终以 `0` 退出，用 `ok` 字段表示结果（兼容现有宿主）；
- 只读命令（`project_status`、`feature_status`、`dynamic_workflow`、`session_context_inject`、`deploy_units`）不得创建或修改任何文件；
- `create_project`、`create_feature` 是幂等的，重复执行不会丢失已有进度。

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
| `${projectCode}` | 项目编码 | `dialog_tips`、`knowledge_config.nextAction`、`artifact_sync.nextAction` |
| `${leanToken}` | 知识沉淀 token | `knowledge_config.nextAction` |
| `${workflowTemplate}` `${workflowNodes}` `${nodeId}` | kanban 专用 | v1 不使用（v2 的模板子集、skip_node） |

校验命令和自定义会话入口使用的 `${python}`、`${projectPath}`、`${featureDir}` 等占位符由运行框架替换，不是宿主占位符，见 §4.3。

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
- 接受 `--selected-deployUnit` 参数但不持久化，发布单元在每次会话时由宿主重新传入；
- Feature 目录已存在但 `state.json` 中没有对应记录时，返回 `ok:false`，避免覆盖未知产物。

#### 3.3.3 project_status（inspect_state.py）

```text
runtime/adapters/inspect_state.py --mode project --workspace <dir> --projects <name>...
```

```json
{
  "workflow": { "nodes": [ WorkflowNode ] },
  "projects": {
    "<project>": { "runs": [ { "featureId": "f1", "featureName": "f1", "currentNodeId": "dev.plan",
                               "currentNodeStatus": "in_progress", "currentNodeStatusLabel": "进行中",
                               "nodeIds": ["biz.prd", "dev.specs", "dev.plan", "dev.code"] } ] }
  }
}
```

`WorkflowNode`：

```json
{ "id": "dev.plan", "label": "任务计划", "group": "Dev", "description": "…",
  "states": [ { "nodeStatus": "not_started", "id": "not_started", "label": "未开始", "nextAction": { … } } ],
  "runtimePolicy": { … },
  "artifactDefinitions": [ { "id": "plan", "artifactType": "file", "required": true } ] }
```

`inspect_state.py` 调用 `query.py` 取得状态与流程数据，再结合 `board_config.json` 的展示字段转换成看板接口数据。`runtimePolicy` 仅在节点配置了时输出。`states[].id` 与 `nodeStatus` 相同。

`nextAction.slashSkill` 用于让宿主**带出**该技能，方便用户直接发起（D6），值为不带命名空间前缀的技能名；空字符串表示不带出任何技能。`userMessage` 和 `dialogTips` 是随技能一起带出的文案。

#### 3.3.4 feature_status（inspect_state.py）

```text
runtime/adapters/inspect_state.py --mode run --workspace <dir> --project <name> --feature <name>
```

```json
{
  "workflow": { "nodes": [ WorkflowNode ] },
  "run": {
    "featureId": "f1", "featureName": "f1",
    "workflowId": "base", "workflowProfile": "standard", "workflowTemplate": "standard", "workflowDecisions": {},
    "currentNodeId": "dev.plan", "currentNodeStatus": "in_progress", "currentNodeStatusLabel": "进行中",
    "nodes": [
      { "id": "dev.specs", "nodeStatus": "done", "nodeStatusLabel": "已完成",
        "artifacts": [
          { "id": "proposal", "artifactLabel": "变更提案", "artifactStatus": "generated", "artifactStatusLabel": "已生成",
            "path": ".autobizdevops/<pluginId>/features/f1/proposal.md" },
          { "id": "specs", "artifactLabel": "行为规格", "artifactStatus": "missing", "artifactStatusLabel": "未生成",
            "paths": [".autobizdevops/<pluginId>/features/f1/specs/*/spec.md"] } ] } ],
    "hookLogRefs": [ { "id": "default", "path": ".autobizdevops/<pluginId>/features/f1/hooks.ndjson", "format": "ndjson" } ],
    "watchRefs": [
      { "path": ".autobizdevops/<pluginId>/state.json", "purpose": "run-state" },
      { "path": ".autobizdevops/<pluginId>/features/f1", "purpose": "artifacts" },
      { "path": ".autobizdevops/<pluginId>/features/f1/hooks.ndjson", "purpose": "hook-log" } ]
  }
}
```

- `nodeStatus` 取值：当前节点之前的为 `done`；当前节点为 `in_progress` 或 `done`；之后的为 `not_started`。Feature 不存在时，`currentNodeId` 为 `"unknown"`，状态为 `unknown`；
- 示例为 isolated 布局，`<pluginId>` 为实际插件 ID；legacy 布局下没有这一层；
- 产物路径相对项目目录。单项且不含 glob 的产物用 `path`；含 glob 或 `path` 为数组的产物用 `paths`，列出实际匹配的文件，某一项没有匹配时给出该项的模式本身；
- `artifactStatus` 只表示文件是否存在（空文件也算已生成），不判断内容质量，也不代表节点已完成。

#### 3.3.5 dynamic_workflow（inspect_workflow_templates.py）

```json
{
  "ok": true, "schemaVersion": "autobizdevops.workflow.templates.v2", "mode": "templates",
  "templates": [ { "id": "standard", "templateType": "classical", "label": "需求开发", "description": "…",
                   "nodes": ["biz.prd", "dev.specs", "dev.plan", "dev.code"] } ],
  "nodes": [ { "id": "dev.plan", "label": "任务计划", "group": "Dev", "skill": "autodev-plan", "description": "…",
               "inputs": [ ArtifactDef ], "outputs": [ ArtifactDef ] } ]
}
```

通过 `query.py` 查询流程定义，返回宿主需要的模板结构。`ArtifactDef` 即 output-spec.md §3.5 中的完整产物定义。kanban 只输出 `{path, label}`，宿主应能兼容两种形态。

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
    "templates": ["/abs/plugin/skills/autodev-plan/templates/plan.md"]
  },
  "agentConfig": {
    "agentMode": "multi",
    "toolConfig": { "task": { "enabled": true } },
    "subagentConfig": { "disabledBuiltinSubagents": ["Explore", "critic"],
                        "customSubagentFiles": ["/abs/plugin/agents/explore.md"] }
  }
}
```

会话内容按以下顺序组成，`sessionContext` 用空行连接各段非空内容：

1. **流程上下文**（始终生成）：由 `query.py` 给出当前 Feature 的产物目录、当前节点与状态、策略目标节点及其技能、输入输出及存在情况、模板路径、下一节点。结构化结果同时放在 `flow` 中；
2. **知识组装结果**（知识模块启用且 `assembler = plugin`）：依次调用 `session.json` 中注册的会话片段（§2.4）；
3. **自定义会话入口的输出**（声明了 `session.customEntry`）：见 §4.5。

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
| `toolConfig.task.enabled` | `toolCustomConfig.task.enabled` | `true` |
| `subagentConfig.disabledBuiltinSubagents` | 原样输出 | `[]` |
| `subagentConfig.customSubagentFiles` | 外挂资源路径拼接插件根目录，转为绝对路径，并按 `--platform` 规范分隔符 | `[]` |

只有 `--selected-deployUnit` 不是合法 JSON 数组时才返回 `ok:false`，此时其余字段照常输出。未启用知识模块或 `assembler = devclaw` 时，`sessionContext` 中没有知识段，`agentmdLoadStatus` 为 `[]`。

#### 3.3.8 deploy_units（inspect_deploy_units.py，知识模块）

调用方是知识模块接入方：`assembler = devclaw` 时由 DevClaw 调用；`assembler = plugin` 时内置组装器复用同一套解析逻辑。inspectCommands 中的键名 `deploy_units` 待与 DevClaw 确认（README §9）。

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
  "supported_deploy_units_source": "agents.manifest.json",
  "boardConfigWritten": true
}
```

失败时返回 `{"ok": false, "schemaVersion": "…", "message": "…", "errors": ["…"]}`，已有的知识目录保持不变。

### 3.4 技能执行期的环境变量

由宿主在会话中注入，供技能和脚本使用：

| 变量 | 含义 |
|---|---|
| `PLUGIN_WORKSPACE` | 项目集合工作区 |
| `PROJECT_DIR` | 项目目录名（旧名 `PROJECT_CODE` 仍可读取） |
| `FEATURE_ID` | 当前 Feature |
| `SESSION_ID` | 会话 ID，写入 hooks.ndjson |

显式参数与环境变量冲突时（例如 `--feature` 与 `FEATURE_ID` 不同），脚本必须报错，不能任选其一。

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
| `runtime/session/render_session_context.py` | DevClaw 的会话机制 | 获取流程上下文，结合会话策略及知识组装结果生成会话内容 |
| `runtime/knowledge/inspect_deploy_units.py` | 知识模块接入方 | 解析知识清单，提供支持的系统和发布单元信息 |
| `runtime/knowledge/sync_knowledge.py` | DevClaw 的 `pull_knowledge` | 拉取知识仓库并回写运行期字段（仅声明 `knowledge.source` 时） |

### 4.2 update_state.py（模型推进状态的唯一入口）

```text
python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --checkpoint <cp>
       [--feature <name>] [--workspace <dir> [--project <name>]]
       [--reopen --reason <text>] [--owner <s>] [--iteration <s>] [--dry-run]
```

| 场景 | 规则 |
|---|---|
| 正常推进 | `<cp>` 必须等于当前 checkpoint，或是状态规则允许的下一个 |
| 推进到 `_in_progress` | 检查本节点的必需输入是否存在 |
| 推进到 `_done` | 检查本节点的必需输入和必需输出是否存在，再执行节点校验命令（§4.4），全部通过才写入 |
| 重开 | 必须加 `--reopen` 和非空的 `--reason`；只能回到当前或之前节点的 `_in_progress`。下游节点在看板上显示为未开始，旧产物保留。重开不执行校验命令 |
| `--dry-run` | 执行全部检查（包括校验命令），但不写 `state.json`、不写变更日志 |
| 定位 | 省略 `--workspace` 时，使用 `PLUGIN_WORKSPACE` + `PROJECT_DIR`；省略 `--feature` 时，使用 `FEATURE_ID` |

```json
{ "ok": true, "changed": true, "feature": "f1", "oldCheckpoint": "plan_in_progress", "checkpoint": "plan_done",
  "statePath": "…", "dryRun": false, "warnings": [],
  "validation": { "ran": true, "passed": true, "exitCode": 0, "durationMs": 812, "timedOut": false, "output": "…" } }
```

`validation` 只在执行了校验命令时输出。校验不通过时返回 `ok:false`，`errors` 中包含退出码（或超时）以及命令输出的末尾部分，`state.json` 保持不变。

不再提供 `update_checkpoint.py` 别名：迁移进来的技能由托管片段统一指向新入口，正文中残留的旧路径由 `check` 报 `LEGACY_ENTRY_REF`。

### 4.3 单行命令约定

节点校验命令（`validate`）和自定义会话入口（`session.customEntry.command`）都是开发者提供的完整单行命令，由运行框架按同一套规则执行：

1. 用 POSIX shell 规则（`shlex.split`）把命令拆成参数列表；
2. 逐个参数替换占位符：

   | 占位符 | 值 |
   |---|---|
   | `${python}` | 运行框架当前使用的解释器（`sys.executable`） |
   | `${pluginPath}` | 插件安装目录 |
   | `${projectPath}` | `<pluginWorkspace>/<projectDir>` |
   | `${featureDir}` | 当前 Feature 的产物目录；尚无 Feature 时为空字符串 |
   | `${feature}` | 当前 Feature；尚无 Feature 时为空字符串 |
   | `${nodeId}` | 校验命令为被完成的节点；自定义会话入口为策略目标节点 |

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

### 4.5 自定义会话入口（customEntry）

默认会话入口生成流程上下文和知识组装结果之后，执行开发者声明的命令：

- **stdin**：一个 JSON 对象，字段与 `SessionRequest`（§2.4）一致（camelCase），另含已经算好的 `agentConfig`：

  ```json
  { "schema": "autobiz.session.request.v1", "platform": "darwin", "pluginRoot": "…",
    "pluginWorkspace": "…", "project": "…", "feature": "f1", "featureDir": "…",
    "selectedDeployUnits": [ … ], "sessionWorkspacePath": "…", "knowledgePath": "…",
    "flow": { … }, "agentConfig": { … } }
  ```

- **stdout**：`{"sessionContext": "…", "message": "…"}`，两个字段都可以省略；
- 工作目录为插件根目录，超时为 `session.customEntry.timeoutSec`（默认 30 秒）；
- 退出码非 0、超时或输出不是合法 JSON 时，忽略它的输出，在 `message` 中追加 `"自定义会话入口失败: <原因>"`，`session_context_inject` 仍然返回 `ok:true`；
- 不能修改 `agentConfig`、`flow`、`agentmdLoadStatus`，也不能替换默认入口：运行策略和流程上下文始终由框架给出（README §9）；
- 与会话片段一样，应当只读、不访问网络。

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
query.next_node(node_id: str) -> dict | None
query.node_skill(node_id: str) -> str
query.node_artifacts(node_id: str, direction: str = "outputs") -> list[dict]
query.node_templates(node_id: str) -> list[Path]
query.checkpoint_chain() -> list[str]

# —— query：产物存在情况 ——
query.artifact_presence(project_path: Path, feature: str, artifact_id: str) -> dict
    # {"exists": bool, "files": [Path], "missing": [pattern], "source": "path"|"legacy"|None}；拒绝越界符号链接

# —— engine：初始化与状态变更 ——
engine.init_project(project_path: Path) -> dict
engine.init_feature(project_path: Path, feature: str, *, owner: str | None = None,
                    iteration: str | None = None, template: str = "standard") -> dict
engine.transition(project_path: Path, feature: str, checkpoint: str, *, reopen: bool = False,
                  reason: str = "", dry_run: bool = False) -> dict
    # 状态转移检查 → 产物存在性检查 → （_done 时）校验命令 → 加锁提交 state.json → 写变更日志

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
| `scaffoldVersion` | `plugin.scaffold.json` | 工程配置格式出现不兼容变化时升主版本，脚手架提供 `migrate` |
| `workflowVersion` | `workflow.json` | 流程配置格式出现不兼容变化时升主版本 |
| `apiVersion` | `board_config.json` | 宿主协议出现不兼容变化时（与 DevClaw 共同决定） |
| 运行框架版本 | build-manifest 的 `coreVersion` | 遵循 semver；同一主版本内 `upgrade` 可以直接替换 |
| 模块版本 | `module.json`、build-manifest | 遵循 semver；`requiresCore` 不满足时拒绝启用 |
| `state.json.schemaVersion` | 运行期 | 状态格式变化时；新版运行框架必须能读取旧版本 |
| `schemaVersion` 字符串 | 各命令输出 | 例如 `autobizdevops.workflow.templates.v2`、`autobizdevops.agents.sync.v1`；沿用现有值 |

兼容承诺：

- 由 lite 迁移过来的插件只要保持 `plugin.id` 和 `layout: legacy` 不变，已有项目的 `state.json` 可以直接继续使用；
- 现有 kanban 插件的产物同步 v1 配置，在新模块中仍可读取。

由 lite 迁移时的行为差异：

- 入口从 `hooks/`、根目录迁到 `runtime/`，board_config 中的命令随之重新生成；技能托管片段中的状态命令也会更新；
- 框架不再检查产物是否为空。lite 现在“去除空白后非空”的判定，如需保留，要写成节点的校验命令；
- 会话内容新增流程上下文段。
