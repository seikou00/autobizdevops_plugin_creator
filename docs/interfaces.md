# 接口定义 v1

本文按调用双方划分，共四组接口：

| § | 调用方 → 被调用方 | 接口 |
|---|---|---|
| 1 | 插件开发者 → 脚手架 | `autobiz-plugin` CLI |
| 2 | 脚手架 → 模块；内核 → 模块 | 模块契约（构建期 `Module`、运行期 Provider） |
| 3 | 宿主 → 插件 | `inspectCommands` 命令协议 |
| 4 | 技能 / 模块脚本 → 内核 | `update_state.py` CLI 与 `board_core.api` |

静态文件格式见 [output-spec.md](output-spec.md)，输入配置字段见 [input-config.md](input-config.md)。

---

## 1. 脚手架 CLI

### 1.1 命令总览

| 命令 | 作用 |
|---|---|
| `autobiz-plugin new <dir> [--from blank\|lite] [--import <plugin-dir>] [--yes]` | 创建插件：交互式问答生成 `plugin.scaffold.json`，随后执行 build |
| `autobiz-plugin add stage <id> --label <label>` | 添加阶段 |
| `autobiz-plugin add artifact <id> --path <path> --label <label> [--type json] [--no-sync]` | 注册产物 |
| `autobiz-plugin add node <stage>.<name> --label <label> --skill <skill> [--after <nodeId>] [--inputs a,b] [--outputs c]` | 添加节点（同时生成技能桩文件） |
| `autobiz-plugin module list` | 列出可用模块、版本及启用状态 |
| `autobiz-plugin module enable <id> [--set key=value …]` / `disable <id>` | 勾选或取消模块 |
| `autobiz-plugin build [--dry-run] [--force]` | 输入 → 标准化输出 |
| `autobiz-plugin check [--strict]` | 校验输入、漂移、技能，并运行契约测试，只读 |
| `autobiz-plugin simulate [--feature demo] [--to <checkpoint>] [--platform <p>] [--keep]` | 在临时工作区模拟宿主调用一遍 |
| `autobiz-plugin upgrade [--to <version>]` | 升级托管内核和模块 |
| `autobiz-plugin package [-o <zip>]` | 重置运行期字段、check，然后打包 |

所有命令都支持 `-C <plugin-dir>`（默认为当前目录）和 `--json`（机器可读输出）。

`add` 和 `module` 只是修改 `plugin.scaffold.json` 的便捷入口，效果与手改配置后执行 build 相同。

同一套命令还以技能形式提供：`autobiz-plugin-creator`（借鉴 Codex plugin-creator，见 README §2.3；规格见 §1.6）。技能负责与开发者对话、梳理阶段/节点/产物、编写 `plugin.scaffold.json`、生成技能展示文案；生成和校验仍然只通过上面的 CLI 完成。技能必须在 `build` 之后运行 `check`，并把 Issue 原样转述给开发者，不能自己修改 generated 或 managed 文件来绕过问题。

### 1.2 通用约定

| 退出码 | 含义 |
|---|---|
| `0` | 成功（可能带 warning） |
| `1` | 存在 error 级问题（校验失败、漂移、契约测试失败），没有写入任何文件 |
| `2` | 用法错误（参数不合法、找不到 `plugin.scaffold.json`） |

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
      "pointer": "/nodes/1/inputs/0",
      "message": "dev.specs 的输入 plan 由后续节点 dev.plan 产出",
      "hint": "调整节点顺序，或在输入中声明 {\"ref\":\"plan\",\"external\":true}"
    }
  ],
  "written": []
}
```

- `pointer` 是 JSON Pointer，指向 `plugin.scaffold.json` 中的位置；问题出在文件层面时用 `file` 字段代替（例如 `skills/autodev-plan/SKILL.md`）；
- `code` 的取值见 input-config.md §5，此外还有 `DRIFT_GENERATED`、`DRIFT_MANAGED`、`CONTRACT_TEST`；
- 不加 `--json` 时输出同样内容的可读文本，按文件和位置分组。

### 1.4 new 的交互流程

```text
? 插件 ID（slug，发布后不可修改）      › doc-review
? 插件名                                › Doc-Review-Kanban
? 一句话描述                            › 文档起草与评审
? 阶段（id:显示名，逗号分隔）           › biz:Biz
── 节点 1 ──
? 所属阶段                              › biz
? 节点名 / 技能名                       › draft / doc-draft
? 显示名                                › 起草
? 产出产物（路径，逗号分隔）            › DRAFT.md
? 读取哪些前序产物（多选）              › （无）
? 继续添加节点？                        › Y
…
? 勾选模块                              › [x] 知识沉淀与解析  [ ] 产物同步
  知识仓库 HTTPS 地址                   › https://…
  SSH 回退地址（可空）                  › …
  分支                                  › master
```

产物 id 由路径推导（`DRAFT.md` → `draft`，`specs/*/spec.md` → `specs`），冲突时追问。

`--import <plugin-dir>` 从现有插件的 `board_config.json` 反推输入：可推导的部分丢弃，与默认值不同的部分写成覆写项。无法表达的字段（v2 能力，例如 `dynamicStages`）列为 warning，并原样保存在 `x-unsupported` 中，不会静默丢失。导入 lite 应得到与 [examples/lite.plugin.scaffold.json](../examples/lite.plugin.scaffold.json) 等价的输入。

### 1.5 simulate

在临时目录中创建 `<tmp>/ws/<project>`，按与宿主相同的方式替换占位符并执行命令：

1. `create_project`、`create_feature`；
2. 对每个节点依次执行：`session_context_inject` → 推进 `_in_progress` → 为必需输出写入桩内容 → 推进 `_done` → `feature_status`；
3. 用 §3 的结构校验每次输出，打印节点状态表和失败原因。

`--to` 指定停在哪个 checkpoint，`--keep` 保留临时目录便于排查。simulate 只依赖本插件，不访问网络（知识模块的 Provider 只读本地 `sys/`）。

### 1.6 插件开发技能 autobiz-plugin-creator（v1，D9）

位于脚手架仓库的 `skills/autobiz-plugin-creator/`，安装到开发者自己的 agent 环境中使用，不随生成的插件发布。

```text
skills/autobiz-plugin-creator/
├── SKILL.md                  # 对话流程与规则（见下）
├── agents/openai.yaml
└── references/
    ├── input-config.md       # 从 docs/ 同步，供 agent 查字段
    └── modeling-guide.md     # 如何把业务流程拆成阶段、节点、产物（含正反例）
```

frontmatter 中的 `description` 要写明触发场景，例如“新建看板插件”“给插件加节点或产物”“启用知识或产物同步模块”。

流程（SKILL.md 正文）：

| 步骤 | agent 做什么 | 调用 |
|---|---|---|
| 1. 定位 | 确认是新建还是修改；新建时确认插件放在哪个目录、插件 ID（提示发布后不可修改）、插件名 | `new --yes`（参数齐全后才调用） |
| 2. 建模 | 让开发者用自然语言描述流程，整理成“阶段 → 节点 → 输入/输出产物”表格回显，开发者确认后才写入 | 编辑 `plugin.scaffold.json`，或调用 `add stage/node/artifact` |
| 3. 模块 | 询问是否需要知识沉淀与解析（需要仓库地址）、产物同步（需要确定从哪个节点起允许同步，以及是否生成接口文档） | `module enable` |
| 4. 生成 | 执行构建；对新生成的技能桩，与开发者确认触发场景后填写 `description`，并生成 `openai.yaml` 文案 | `build` |
| 5. 校验 | 执行校验，把 Issue 按原文转述给开发者，修改输入后重试 | `check` |
| 6. 演示 | 在临时工作区走一遍完整流程，展示每个节点的状态和产物路径 | `simulate` |

规则：

- 只修改 `plugin.scaffold.json` 和 seeded/developer 文件，不得修改 generated、managed、module 文件来绕过校验；
- 插件已经发布后，不得修改 `plugin.id` 和 `runtime.layout`；
- 涉及节点业务逻辑的技能正文由开发者负责，agent 只能起草，不能把未经确认的流程写进去；
- 所有判断以 CLI 的退出码和 Issue 为准，不得自行宣称“校验通过”。

---

## 2. 模块契约

### 2.1 模块包结构

```text
scaffold/modules/<id>/
├── module.json          # 元数据
├── module.py            # 构建期实现（Module）
├── options.schema.json  # 本模块在 plugin.scaffold.json 中 modules.<optionsKey> 的 Schema 片段
└── files/…              # 要拷贝进插件的文件（可含 {{ }} 模板）
```

`module.json`：

```json
{
  "id": "artifactSync",
  "version": "1.0.0",
  "title": "产物同步",
  "description": "按节点输出同步 Feature 产物，可选按实际代码生成接口文档",
  "optionsKey": "artifactSync",
  "requiresCore": ">=1.0.0 <2.0.0",
  "entry": "module:ArtifactSyncModule"
}
```

### 2.2 构建期接口（Python）

```python
from dataclasses import dataclass, field
from typing import Optional, Protocol, Union

@dataclass(frozen=True)
class ArtifactIR:
    id: str
    label: str
    path: str
    type: str                      # "file" | "json"
    legacy_paths: tuple[str, ...]
    sync: bool
    sync_description: str
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
    runtime_policy: Optional[dict]

    @property
    def checkpoints(self) -> tuple[str, str]:
        return (f"{self.prefix}_in_progress", f"{self.prefix}_done")

@dataclass(frozen=True)
class PluginIR:
    plugin: dict
    runtime: dict
    board: dict
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
    runtime_fields: list[str] = field(default_factory=list)        # 例如 "supported_deploy_units"
    inspect_commands: dict[str, CommandSpec] = field(default_factory=dict)
    session_providers: list[str] = field(default_factory=list)     # "hooks.knowledge_context:provide"
    skills: list[str] = field(default_factory=list)                # 模块占用的技能名
    gitignore: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class Issue:
    level: str        # "error" | "warning"
    code: str
    message: str
    pointer: str = ""
    file: str = ""
    hint: str = ""

class Module(Protocol):
    id: str
    version: str

    def defaults(self) -> dict:
        """模块参数默认值，与输入中的 modules.<optionsKey> 深合并。"""

    def validate(self, ir: PluginIR, options: dict) -> list[Issue]:
        """语义校验。只读，不得有副作用。"""

    def contribute(self, ir: PluginIR, options: dict) -> Contribution:
        """纯函数：相同输入必须得到相同输出（build 的漂移检测依赖这一点）。"""
```

### 2.3 合并规则

| 贡献 | 规则 | 冲突时 |
|---|---|---|
| `config` | 只能新增顶层键，不能覆盖内核键（`apiVersion`、`inspectCommands`、`workflow`、`checkpointSuffixState`） | `MODULE_CONFLICT` |
| `inspect_commands` | 只能新增键，不能覆盖 output-spec.md §3.2 中标为“必有”的键；每个平台各生成一份。模块未启用时它贡献的键直接不出现（D1），不输出空值 | `MODULE_CONFLICT` |
| `files` | `dst` 不能与内核文件或其他模块重复 | `MODULE_CONFLICT` |
| `skills` | 不能与节点技能重名 | `MODULE_SKILL_CONFLICT` |
| `session_providers` | 按 `modules` 中的声明顺序写入 `board_core/runtime.json` 的 `sessionContextProviders` | — |
| `runtime_fields` | 汇总写入 lock，供 build（保留）和 package（重置）使用 | — |

### 2.4 运行期接口：会话上下文 Provider

内核的 `hooks/render_session_context.py` 读取 `board_core/runtime.json` 中的 `sessionContextProviders`，依次调用其中注册的 Provider：

```json
{ "schema": "autobiz.runtime.v1", "pluginId": "…", "layout": "isolated",
  "sessionContextProviders": ["hooks.knowledge_context:provide"] }
```

```python
# board_core/extensions.py
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
    selected_deploy_units: list[dict]     # [{"deployUnitId","localRepoPath","description"}]，内核已解析并校验
    session_workspace_path: str
    policy_node: Optional[dict]           # 策略目标节点（规则见 §3.3.6）
    config: dict                          # board_config

@dataclass
class SessionContextPart:
    session_context: str = ""
    load_status: list[dict] = field(default_factory=list)   # agentmdLoadStatus 条目
    message: str = ""

def provide(request: SessionRequest) -> SessionContextPart: ...
```

Provider 约束：

- 不得写 stdout（stdout 只用于协议 JSON），日志写 stderr；
- 不得访问网络、不得写文件：同步是 `pull_knowledge` 的职责，Provider 只读本地缓存；
- 不应抛异常。即使抛出，内核也会捕获，在 `message` 中追加 `"<provider> 失败: <原因>"`，并继续调用后续 Provider；
- 结果合并方式：`sessionContext` 用空行连接各段非空内容；`agentmdLoadStatus` 依次拼接；`message` 用 ` / ` 连接。

---

## 3. 宿主命令协议

### 3.1 通用约定

- 宿主先替换占位符，再执行命令，不保证工作目录。脚本必须通过 `__file__` 定位插件根目录；
- **stdout** 输出且只输出一个 UTF-8 JSON 对象，**stderr** 用于日志；
- 退出码：`0` 表示成功；`1` 表示业务失败，此时 stdout 为 `{"ok": false, "errors": ["…"]}`。`session_context_inject` 和 `pull_knowledge` 例外：始终以 `0` 退出，用 `ok` 字段表示结果（兼容现有宿主）；
- 只读命令（`project_status`、`feature_status`、`dynamic_workflow`、`session_context_inject`）不得创建或修改任何文件；
- `create_project`、`create_feature` 是幂等的，重复执行不会丢失已有进度。

### 3.2 占位符

| 占位符 | 含义 | 允许出现在 |
|---|---|---|
| `${pluginPath}` | 插件安装目录 | 所有命令、`knowledge_path`、`system_prompt_inject`、技能正文 |
| `${pluginWorkspace}` | 项目集合工作区 | 所有命令、`plugin_dir_hook`、`system_prompt_inject`、`dialog_tips` |
| `${projectDir}` | 项目目录名 | 同上 |
| `${projectDirs...}` | 多个项目目录名，宿主逐个转义后展开 | `project_status` |
| `${feature}` | 当前 Feature | `feature_status`、`create_feature`、`session_context_inject`、`system_prompt_inject`、技能正文 |
| `${selectedDeployUnits}` | JSON 数组，宿主作为一个参数整体转义 | `create_feature`、`session_context_inject` |
| `${sessionWorkspacePath}` | 会话工作区目录 | `session_context_inject` |
| `${projectCode}` | 项目编码 | `dialog_tips`、`knowledge_config.nextAction` |
| `${leanToken}` | 知识沉淀 token | `knowledge_config.nextAction` |
| `${workflowTemplate}` `${workflowNodes}` `${nodeId}` | kanban 专用 | v1 不使用（v2 的模板子集、skip_node） |

### 3.3 命令

#### 3.3.1 create_project / create_feature

```text
init_workspace.py --mode createProject --workspace <dir> --project <name>
init_workspace.py --mode createFeature --workspace <dir> --project <name> --feature <name>
                  [--selected-deployUnit <json>] [--workflow-template standard] [--owner <s>] [--iteration <s>]
```

```json
{ "ok": true, "initialized": true, "created": true,
  "statePath": "/…/<project>/.autobizdevops/<pluginId>/state.json",
  "featureDir": "/…/<project>/.autobizdevops/<pluginId>/features/<feature>",
  "warnings": [] }
```

- 路径按布局推导（output-spec.md §4.1），示例为 isolated 布局；legacy 布局下没有 `<pluginId>/` 这一层；
- `createProject` 返回的 `featureDir` 为 `null`；
- 新 Feature 的 checkpoint 为 `workflow.checkpoints.initial[0]`；
- 内核接受 `--selected-deployUnit` 参数但不持久化，部署单元在每次会话时由宿主重新传入；
- Feature 目录已存在但 `state.json` 中没有对应记录时，返回 `ok:false`，避免覆盖未知产物。

#### 3.3.2 project_status

```text
inspect_state.py --mode project --workspace <dir> --projects <name>...
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

`runtimePolicy` 仅在节点配置了时输出。`states[].id` 与 `nodeStatus` 相同。

`nextAction.slashSkill` 用于让宿主**带出**该技能，方便用户直接发起（D6），值为不带命名空间前缀的技能名；空字符串表示不带出任何技能。`userMessage` 和 `dialogTips` 是随技能一起带出的文案。

#### 3.3.3 feature_status

```text
inspect_state.py --mode run --workspace <dir> --project <name> --feature <name>
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
- 产物路径相对项目目录。glob 产物用 `paths`（列出实际匹配的文件，无匹配时给出模式本身），非 glob 产物用 `path`；
- `artifactStatus` 只看文件是否存在且非空，不判断内容质量。

#### 3.3.4 dynamic_workflow

```json
{
  "ok": true, "schemaVersion": "autobizdevops.workflow.templates.v2", "mode": "templates",
  "templates": [ { "id": "standard", "templateType": "classical", "label": "需求开发", "description": "…",
                   "nodes": ["biz.prd", "dev.specs", "dev.plan", "dev.code"] } ],
  "nodes": [ { "id": "dev.plan", "label": "任务计划", "group": "Dev", "skill": "autodev-plan", "description": "…",
               "inputs": [ ArtifactDef ], "outputs": [ ArtifactDef ] } ]
}
```

`ArtifactDef` 即 output-spec.md §3.5 中的完整产物定义。kanban 只输出 `{path, label}`，宿主应能兼容两种形态。

#### 3.3.5 system_prompt_inject / dialog_tips / plugin_dir_hook / knowledge_path

这些是模板字符串，宿主替换占位符后直接使用，不执行。

#### 3.3.6 session_context_inject

```text
render_session_context.py --platform <p> --plugin-workspace <dir> --project <name> --feature <name>
                          --selected-deployUnit <json> --session-workspace-path <dir> [--node-id <id>]
```

```json
{
  "ok": true,
  "message": "remote 1 / local 0 / 缺 0",
  "sessionContext": "…",
  "agentmdLoadStatus": [ { "deployUnitId": "LF39.18_wg_flow", "path": "…", "loaded": true, "source": "remote", "message": "…" } ],
  "agentConfig": {
    "agentMode": "multi",
    "toolConfig": { "task": { "enabled": true } },
    "subagentConfig": { "disabledBuiltinSubagents": ["Explore", "critic"],
                        "customSubagentFiles": ["/abs/plugin/agents/explore.md"] }
  }
}
```

**策略目标节点**（与宿主拉起技能时依据的 nextAction 保持一致）：

1. 读取当前节点、当前状态下的 `nextAction.slashSkill`，找到拥有该技能的节点；
2. 找不到时，退回当前节点本身；
3. 仍然找不到时（Feature 未创建、参数缺失），使用全局默认值。

因此 not_started 和 in_progress 状态下取的是当前节点的策略，done 状态下取的是下一个节点的策略。`--node-id` 只用于本地调试，会直接指定节点。

**runtimePolicy → agentConfig 的映射**：

| agentConfig | 来源 | 默认值 |
|---|---|---|
| `agentMode` | `runtimePolicy.agentMode` | `solo` |
| `toolConfig.task.enabled` | `runtimePolicy.toolCustomConfig.task.enabled` | `true` |
| `subagentConfig.disabledBuiltinSubagents` | 原样输出 | `[]` |
| `subagentConfig.customSubagentFiles` | 拼接插件根目录，转为绝对路径，并按 `--platform` 规范分隔符 | `[]` |

只有 `--selected-deployUnit` 不是合法 JSON 数组时才返回 `ok:false`，此时其余字段照常输出。未启用知识模块时，`sessionContext` 为 `""`，`agentmdLoadStatus` 为 `[]`。

#### 3.3.7 pull_knowledge（知识模块）

```json
{
  "ok": true, "schemaVersion": "autobizdevops.agents.sync.v1",
  "message": "agents 仓库已同步：2 个系统、5 个部署单元，AGENTS.md 就绪 2/2",
  "repo": { "url": "…", "sshUrl": "…", "ref": "master", "commit": "…", "transport": "https" },
  "knowledge_path": "/abs/plugin/sys",
  "supported_deploy_units": ["…"],
  "systems": [ { "systemId": "LF39", "systemName": "…", "agentsReady": true, "agentsPath": "sys/LF39/AGENTS.md",
                 "deployUnits": [ { "deployUnitId": "…", "name": "…" } ] } ],
  "supported_deploy_units_source": "agents.manifest.json",
  "boardConfigWritten": true
}
```

失败时返回 `{"ok": false, "schemaVersion": "…", "message": "…", "errors": ["…"]}`，已有的 `sys/` 保持不变。

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

## 4. 运行时 API

### 4.1 update_state.py（技能推进状态的唯一入口）

```text
python -X utf8 "${pluginPath}/hooks/update_state.py" --checkpoint <cp>
       [--feature <name>] [--workspace <dir> [--project <name>]]
       [--reopen --reason <text>] [--owner <s>] [--iteration <s>] [--dry-run]
```

| 场景 | 规则 |
|---|---|
| 正常推进 | `<cp>` 必须等于当前 checkpoint，或是 transitions 允许的下一个 |
| 推进到 `_done` | 先校验本节点的必需输入和必需输出，再写入 |
| 推进到 `_in_progress` | 校验本节点的必需输入 |
| 重开 | 必须加 `--reopen` 和非空的 `--reason`；只能回到当前或之前节点的 `_in_progress`。下游节点在看板上显示为未开始，旧产物保留 |
| 定位 | 省略 `--workspace` 时，使用 `PLUGIN_WORKSPACE` + `PROJECT_DIR`；省略 `--feature` 时，使用 `FEATURE_ID` |

```json
{ "ok": true, "changed": true, "feature": "f1", "oldCheckpoint": "plan_in_progress", "checkpoint": "plan_done",
  "statePath": "…", "dryRun": false, "warnings": [] }
```

`hooks/update_checkpoint.py` 是它的别名，参数和输出完全相同。

### 4.2 board_core.api（给技能脚本和模块使用）

模块和技能脚本只能通过这一层访问状态与路径，不得直接读写 `state.json`，也不得自己拼接 `.autobizdevops` 路径。只有这样，同一份模块代码才能同时用于 isolated 和 legacy 布局（D3）。

```python
from board_core import api

# —— 定位 ——
api.plugin_root() -> Path
api.load_config() -> dict                                      # 已通过 output-spec.md §3.3 的不变量校验
api.resolve_workspace(workspace: str | None = None, project: str | None = None) -> Path
    # 显式参数优先；否则读 PLUGIN_WORKSPACE + PROJECT_DIR；拒绝插件安装目录
api.resolve_feature(feature: str | None = None, *, required: bool = True) -> str
    # 与 FEATURE_ID 冲突时报错；校验路径安全
api.plugin_id() -> str                                         # 来自 board_core/runtime.json
api.metadata_dir(workspace: Path) -> Path
    # isolated：<workspace>/.autobizdevops/<pluginId>；legacy：<workspace>/.autobizdevops

# —— 状态（只读）——
api.feature_record(workspace: Path, feature: str) -> dict      # state.json 中该 Feature 的记录
api.current_checkpoint(workspace: Path, feature: str) -> str
api.locate(checkpoint: str) -> tuple[dict, str]                # (节点, "in_progress"|"done")
api.checkpoint_chain() -> list[str]
api.checkpoint_reached(current: str, target: str) -> bool      # current 是否已到达或越过 target

# —— 产物 ——
api.feature_dir(workspace: Path, feature: str) -> Path         # metadata_dir(workspace) / "features" / feature
api.artifact_files(feature_dir: Path, artifact: dict) -> list[Path]   # glob、legacyPaths，拒绝越界符号链接
api.node_artifacts(node_id: str, direction: str = "outputs") -> list[dict]

# —— 日志 ——
api.append_event(workspace: Path, feature: str, event_id: str, status: str, message: str,
                 *, source: str, **extra) -> None             # 自动填充 ts、pluginId、sessionId、featureId

# —— 异常 ——
class api.BoardError(ValueError): ...                          # 所有业务错误都抛这个类型
```

稳定性：`board_core.api` 遵循语义化版本，同一主版本内只增不改。`runtime.py`、`inspect.py`、`cli.py` 属于内部实现，模块不得导入。

---

## 5. 版本与兼容

| 版本号 | 位置 | 何时升级 |
|---|---|---|
| `scaffoldVersion` | `plugin.scaffold.json` | 输入格式出现不兼容变化时升主版本，脚手架提供 `migrate` |
| `apiVersion` | `board_config.json` | 宿主协议出现不兼容变化时（与宿主共同决定） |
| 内核版本 | `board_core/VERSION`、lock | 遵循 semver；同一主版本内 `upgrade` 可以直接替换 |
| 模块版本 | `module.json`、lock | 遵循 semver；`requiresCore` 不满足时拒绝启用 |
| `state.json.schemaVersion` | 运行期 | 状态格式变化时；新内核必须能读取旧版本 |
| `schemaVersion` 字符串 | 各命令输出 | 例如 `autobizdevops.workflow.templates.v2`、`autobizdevops.agents.sync.v1`；沿用现有值 |

兼容承诺：

- 由 lite 迁移过来的插件只要保持 `plugin.id` 不变，已有项目的 `state.json` 可以直接继续使用；
- 现有 kanban 插件的产物同步 v1 配置，在新模块中仍可读取。
