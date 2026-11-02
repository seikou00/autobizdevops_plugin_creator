# 脚手架模块设计 v1（草案，待评审）

本文拆分脚手架自身的代码：开发期 CLI `autobiz-plugin`、构建流水线、四个模块的构建期实现、插件开发技能，以及运行框架模板的内部结构。对外行为已经由下面三份文档确定，本文不重复，只说明由哪个模块实现，以及模块之间用什么接口：

| 已定的外部契约 | 文档 |
|---|---|
| 核心配置字段、默认值、编译规则、lint/check 规则 | [input-config.md](input-config.md) |
| 生成的目录、文件格式、文件归属 | [output-spec.md](output-spec.md) |
| CLI 命令与 Issue 格式、模块契约、宿主命令协议、运行框架入口 | [interfaces.md](interfaces.md) |

全文分 15 个评审单元，按依赖从底到顶排列，后面的单元使用前面的类型。每个单元写明职责、接口、起点（可以迁入的现有代码）和待评审点。待评审点编号为 `Q<单元>.<序号>`，结论定下后转成 [README §8](README.md) 的决策，并同步修改受影响的文档。

约定：

- 脚手架和运行框架一样只用 Python 3.9+ 标准库（README §2.3）；
- 下文代码只是接口签名，不是实现。签名中的 `list[...]`、`X | None` 写法是为了便于阅读，实现时用 `from __future__ import annotations`；
- “demo”指 `demo/autobiz-plugin-creator-demo/skills/autobiz-plugin-creator/` 下的演示版脚本，它们按旧版设计实现，迁入时要按本文的接口调整。

## 总览

### 目录

```text
autobizdevops_plugin_creator/
├── scaffold/
│   ├── cli.py                       # 单元 10：命令行入口
│   ├── lib/                         # 单元 1、2：issues  jsonschema  fsio  derive  skillmd
│   ├── build/                       # 单元 3–8：load  normalize  lint  ir  compile  contribute
│   │                                #           framework  skills  emit  manifest  pipeline
│   ├── commands/                    # 单元 10–13：build  doctor  lint  check  simulate
│   │                                #             edit  new  package  upgrade  githook
│   ├── host.py  shapes.py           # 单元 11：扮演 DevClaw、校验命令输出结构
│   ├── wizard.py                    # 单元 12：初始化向导问答
│   └── modules/                     # 单元 6、9：模块契约与四个模块包
│       ├── __init__.py
│       └── board/  session/  knowledge/  artifact_sync/
│           └── module.json  module.py  files/
├── runtime/                         # 单元 15：运行框架模板（随插件发布）
├── skills/autobiz-plugin-creator/   # 单元 14：插件开发技能
├── schemas/  examples/  docs/
└── tests/  golden/  contract/  modules/  unit/
```

README §3.1 原来把 `cli wizard normalize validate compile emit manifest simulate` 平铺在 `scaffold/` 下，这里按层分成子包；`tests/unit/` 为新增，放 `lib/` 和 `build/` 的单元测试。模块包中不再有 `options.schema.json`，见 Q6.6。

### 数据流

```text
插件目录
  │ load                          Inputs          核心配置原文、路径、摘要
  │ normalize                     Normalized      按 Schema 补默认值
  │ lint_core                     list[Issue]     核心规则；有 error 即停止
  │ compile                       PluginIR
  │ lint_modules                  list[Issue]     各模块 validate；有 error 即停止
  │ contribute                    {id: Contribution}   框架自身以 "framework" 参与
  │ merge                         Merged
  │ plan_skills                   FileSpec + SkillChanges
  │ plan_files                    WritePlan
  │ check_drift                   list[Issue]
  │ make_manifest                 build-manifest
  ▼ apply                         written
```

### 命令与阶段

| 命令 | load → lint_core | compile → lint_modules | contribute → check_drift | 写插件目录 | 另外 |
|---|---|---|---|---|---|
| `lint` | ✓ | ✓ | — | — | 报 `BUILD_STALE` |
| `build` | ✓ | ✓ | ✓ | ✓（`--dry-run` 不写） | |
| `doctor` | ✓ | ✓ | ✓ | ✓（`--dry-run` 不写） | 前置影响报告，后置复查 |
| `check` | ✓ | ✓ | ✓ | — | 资源规则、`DRIFT_GENERATED`、契约测试 |
| `simulate` | — | — | — | — | 读已生成的插件，只写临时目录（Q11.4） |
| `package` | 同 `check --strict` | | | 写 zip | |
| `add`、`module`、`new` | — | — | — | 写核心配置 | 写完调用 doctor（`new` 调用 build） |

### 单元一览

| # | 单元 | 文件 | 职责 | 起点 |
|---|---|---|---|---|
| 1 | 公共基础 | `lib/issues.py` `jsonschema.py` `fsio.py` | Issue 与报告、Schema 校验与默认值、文件读写与摘要 | demo_lint.py 的 `Report`、`schema_errors`、`fill_defaults` |
| 2 | 推导与 SKILL.md | `lib/derive.py` `skillmd.py` | 产物 id 等推导规则；技能目录查找、frontmatter、状态维护片段 | demo_lint.py `find_skill_dirs`；demo_build.py `state_block`、`upsert`、`stub_skill` |
| 3 | 读取与补全 | `build/load.py` `normalize.py` | 读入口及其引用的文件、结构校验、补默认值 | demo_lint.py `load`、`with_defaults` |
| 4 | lint | `build/lint.py` | 语义规则的注册与执行 | demo_lint.py `check_*` |
| 5 | IR 与编译 | `build/ir.py` `compile.py` | 核心配置 → `PluginIR` | demo_build.py `Compiled` |
| 6 | 模块契约与合并 | `modules/__init__.py` `build/contribute.py` | Module 协议、发现、合并规则 | interfaces.md §2 |
| 7 | 框架贡献与技能同步 | `build/framework.py` `skills.py` | 不属于模块的输出、三平台命令展开、SKILL.md 片段同步 | demo_build.py `board_config`、`plan_skills` |
| 8 | 写盘与编排 | `build/emit.py` `manifest.py` `pipeline.py` | 写盘计划、漂移检查、build-manifest、build 流水线 | demo_build.py `Plan`、`check_drift`、`manifest`、`write` |
| 9 | 四个模块 | `modules/*/module.py` | board、session、knowledge、artifactSync 的构建期实现 | lite、全栈版（README §6.3） |
| 10 | CLI 与核心命令 | `cli.py` `commands/{build,doctor,lint,check}.py` | 参数、退出码、doctor 影响报告、check | demo_lint.py `main` |
| 11 | simulate | `host.py` `shapes.py` `commands/simulate.py` | 扮演 DevClaw 执行命令、校验输出结构 | demo_simulate.py `Simulation` |
| 12 | 配置编辑与向导 | `commands/{edit,new}.py` `wizard.py` | `add`、`module`、`new` | demo_skills.py |
| 13 | 打包、升级、钩子 | `commands/{package,upgrade,githook}.py` | zip、替换托管文件、`core.hooksPath` | demo_package.py |
| 14 | 插件开发技能 | `skills/autobiz-plugin-creator/` | 对话建模并调用 CLI | demo 版 SKILL.md |
| 15 | 运行框架模板 | `runtime/` | query、engine、adapters、session、board_events 的内部拆分 | demo `assets/runtime/`、lite `board_core` |

---

## 1. 公共基础

所有命令共用的报告格式、JSON Schema 校验和文件读写。

```python
# lib/issues.py
@dataclass(frozen=True)
class Issue:
    level: str                  # "error" | "warning"
    code: str
    message: str
    file: str = ""              # 相对插件根，例如 workflow.json、modules/board.json、skills/x/SKILL.md
    pointer: str = ""           # 文件内的 JSON Pointer；问题出在文件层面时为空
    hint: str = ""

class Report:
    issues: list[Issue]
    def add(self, level, code, message, *, file="", pointer="", hint="") -> None
    def extend(self, issues: Iterable[Issue]) -> None
    def failed(self, *, strict: bool = False) -> bool       # 有 error；strict 时 warning 也算
    def to_json(self, *, written: Sequence[str] = (), **extra) -> dict
        # {"ok", "issues", "written", **extra}；doctor 的 extra 为 {"changes": …}（interfaces.md §1.3、§1.7）
    def to_text(self) -> str                                 # 按 file → pointer 分组的可读文本

class UsageError(Exception): ...                             # 参数不合法、找不到入口文件；CLI 映射为退出码 2

# lib/jsonschema.py：draft-07 子集
def validate(instance, schema: dict, *, root: dict | None = None) -> list[tuple[str, str]]
    # 返回 [(JSON Pointer, 原因)]；root 用于解析 $ref
def apply_defaults(instance, schema: dict, *, root: dict | None = None) -> object
    # 返回补全后的副本，不改入参。规则同 demo 的 fill_defaults：对象要有 default: {} 才会在缺省时创建，
    # oneOf 只进入匹配的那一种写法（D27）
def load_schema(name: str) -> dict                           # 从 schemas/ 读取并缓存，例如 "modules/board.schema.json"

# lib/fsio.py
def read_json(path: Path) -> object                          # UTF-8；失败时抛 JsonError(path, line, column, message)
def dump_json(value) -> bytes                                # indent=2、ensure_ascii=False、保持键序、末尾换行
def digest(data: bytes) -> str                               # 格式同 output-spec.md §8
def atomic_write(path: Path, data: bytes) -> None            # 同目录临时文件 + os.replace
```

待评审：

- **Q1.1** jsonschema 支持哪些关键字。以 `schemas/` 实际用到的为准：`type`、`properties`、`required`、`additionalProperties`、`items`、`enum`、`const`、`pattern`、`minLength`、`maxLength`、`minimum`、`exclusiveMinimum`、`minItems`、`uniqueItems`、`minProperties`、`propertyNames`、`not`、`oneOf`、`allOf`、`$ref`、`default`。建议加一个测试，保证 Schema 不用到子集以外的关键字。
- **Q1.2** Schema 文件现在带 `//` 注释（工作区中尚未提交的修改），标准库 `json.loads` 读不了：`tests/check_schema_defaults.py` 当前以退出码 2 失败（“无法读取 Schema”），demo_lint 也会失败。可选做法：
  1. 脚手架增加 `read_jsonc`，只用于读 Schema；
  2. 把注释改写进 `description` 或 `$comment`；
  3. 源文件保留注释，发布到插件的 `.scaffold/` 时去掉。

  无论选哪种，都要确认 IDE 能读取 `.scaffold/` 下的 Schema，因为它用于编辑时的补全。
- **Q1.3** Issue 按 file → pointer → code 稳定排序，让 `--json` 的输出可以直接比对。
- **Q1.4** `--json` 下用法错误的输出形态：interfaces.md §1.2 只定义了退出码 2，没有定义 stdout。建议仍输出 §1.3 的结构：`{"ok": false, "issues": [{"level": "error", "code": "USAGE", …}], "written": []}`。

## 2. 推导与 SKILL.md

`derive` 是 input-config.md §2.3、§6 中推导规则的唯一实现，lint 和 compile 都调用它，避免两处各算一遍。`skillmd` 负责技能目录查找和 SKILL.md 的读写。

```python
# lib/derive.py：纯函数
GROUPS = ("biz", "dev", "ops")
def group_label(group: str) -> str                           # biz → Biz
def artifact_id(path: str) -> str                            # input-config.md §2.3 的三步规则
def artifact_type(path: str) -> str                          # .json → "json"，其余 "file"
def output_item(item: str | dict) -> tuple[str, bool]        # 输出项 → (路径, required)

@dataclass(frozen=True)
class NodeRef:
    group: str
    index: int
    node: dict
    @property
    def pointer(self) -> str                                 # /nodes/<group>/<index>

def ordered_nodes(workflow: dict) -> list[NodeRef]
    # 按 seq 升序；seq 重复时按分组和下标稳定排序（重复本身由 SEQ_DUP 报出）
def checkpoints(node_id: str, terminal: bool) -> tuple[str, ...]   # 终态节点为 ("archived",)

# lib/skillmd.py
STATE_BEGIN = "<!-- plugin workflow: begin state -->"
STATE_END = "<!-- plugin workflow: end state -->"

@dataclass(frozen=True)
class Frontmatter:
    fields: dict
    body_start: int                                          # 正文起始偏移；没有 frontmatter 时为 0
    errors: list[str]                                        # 超出受限解析范围的写法

def find_skill_dir(root: Path, skill: str) -> tuple[Path | None, list[Path]]
    # 在 skills/<skill>/ 和 skills/*/<skill>/ 找含 SKILL.md 的目录（input-config.md §5）
    # 返回 (唯一命中的目录, 全部候选)；候选多于一个即 SKILL_AMBIGUOUS
def parse_frontmatter(text: str) -> Frontmatter              # 受限解析，只认五个键的简单形态（Q2.1）
def render_state_block(node_id: str, terminal: bool) -> str  # output-spec.md §6.1 的片段，解释器固定 python -X utf8
def upsert_state(text: str, block: str) -> str
    # 已有片段：只替换两个标记之间的内容；没有：插在 frontmatter 之后
    # 旧版 scaffold:begin state 片段原地替换，旧版 artifacts 片段整段删除
def remove_state(text: str) -> str
def state_digest(text: str) -> str | None                    # 两个标记之间去掉首尾换行后的摘要；没有片段时为 None
def blank_skill(skill: str, block: str) -> str               # description 为 [TODO: 做什么；在什么情况下使用]
def migrate_frontmatter(text: str) -> tuple[str, list[str]]  # 顶层 version、author 移入 metadata（D8），add skill 用
```

待评审：

- **Q2.1** 受限 frontmatter 解析支持到什么程度：多行 `description: >`、`|`，`metadata` 下的嵌套映射，`allowed-tools` 的列表。超出范围时报 `SKILL_FRONTMATTER`，还是原样跳过、只取能解析的键？
- **Q2.2** `render_state_block` 只需要节点 id 和是否终态，片段中的文案（“技能开始执行”“技能完成执行”）是常量，不开放配置。

## 3. 读取与补全

```python
# build/load.py
ENTRY = "plugin.scaffold.json"
MODULE_KEYS = ("board", "session", "knowledge", "artifactSync")

@dataclass(frozen=True)
class Inputs:
    root: Path
    entry: dict                        # 入口文件原文
    workflow: dict                     # workflow.json 原文
    modules: dict[str, dict]           # 入口 modules 中引用了的模块 → 原文
    files: dict[str, str]              # "entry"、"workflow"、模块键 → 相对插件根的路径，用作 Issue.file
    digests: dict[str, str]            # 相对路径 → 摘要；写 build-manifest 的 inputs，判断 BUILD_STALE

def load(root: Path) -> tuple[Inputs | None, list[Issue]]
    # 入口文件或 workflow.json 不存在 → UsageError
    # JSON 语法错误、结构不符 → INPUT_SCHEMA（pointer 指到出错位置）
    # 引用的模块文件不存在 → MODULE_FILE_MISSING
    # 有 error 时返回 None

# build/normalize.py
@dataclass(frozen=True)
class Normalized:
    inputs: Inputs
    entry: dict                        # 补全后的入口文件
    workflow: dict
    modules: dict[str, dict]           # 启用的模块 → 补全后的配置；board、session 未引用时为全部默认值

def normalize(inputs: Inputs) -> Normalized       # 只按 Schema 的 default 补全，不做推导
```

待评审：

- **Q3.1** README §5 和 diagrams.md 图 4 让 normalize 同时“汇总产物、推断类型、算 checkpoint”。建议推导集中到 `derive` 和 `compile`，normalize 只补默认值；lint 需要推导结果时直接调用 `derive`。这样 normalize 的输出就是“核心配置 + 默认值”，可以单独测试。

## 4. lint

```python
# build/lint.py
@dataclass(frozen=True)
class LintContext:
    normalized: Normalized
    previous: dict | None                                   # 上次的 build-manifest；没有 build 过为 None
    skills: dict[str, tuple[Path | None, list[Path]]]       # 节点技能 → find_skill_dir 的结果，规则之间共用
    allow: frozenset[str]                                   # Q4.3

Rule = Callable[[LintContext], Iterable[Issue]]
RULES: dict[str, Rule]                                      # code → 规则；每条规则只产出自己的 code

def lint_core(ctx: LintContext, *, stale: bool = True) -> list[Issue]
    # 执行 RULES；doctor、build 调用时 stale=False（不报 BUILD_STALE）
def lint_modules(ir: PluginIR, normalized: Normalized, modules: dict[str, Module]) -> list[Issue]
    # 执行各模块的 Module.validate
```

input-config.md §7.2 各规则的位置：

| 位置 | 规则 |
|---|---|
| `load` | `INPUT_SCHEMA`、`MODULE_FILE_MISSING` |
| `lint_core` | `NODE_DUP`、`SEQ_DUP`、`SEQ_STAGE_ORDER`、`TERMINAL_INVALID`、`SKILL_SHARED`、`ARTIFACT_ID_INVALID`、`ARTIFACT_ID_CONFLICT`、`OUTPUT_REDECLARED`、`PATH_UNSAFE`（产物路径）、`SKILL_MISSING`、`SKILL_AMBIGUOUS`、`PLUGIN_ID_RESERVED`、`LAYOUT_LEGACY`、`PLUGIN_ID_CHANGED`、`LAYOUT_CHANGED`、`BUILD_STALE` |
| board 的 `validate` | `PLACEHOLDER_UNKNOWN`、`FEATURE_DIR_MISSING` |
| session 的 `validate` | `POLICY_NODE_UNKNOWN`、`SUBAGENT_FILE_MISSING` |
| knowledge 的 `validate` | `PATH_UNSAFE`（`knowledge.root`）、`MODULE_OPTION` |
| artifactSync 的 `validate` | `ARTIFACT_REF_UNKNOWN`、`MODULE_OPTION`、`MODULE_SKILL_CONFLICT` |
| `merge`（只在 build 中） | `MODULE_CONFLICT` |

待评审：

- **Q4.1 lint 分两段。** interfaces.md §2.2 的 `Module.validate(ir, options)` 需要 IR，而 lint 在 compile 之前运行。建议 lint 分两段：先跑核心规则，没有 error 时再 compile，然后跑各模块的 validate。compile 只在内存中进行，lint 仍然只读、不联网。
- **Q4.2** 规则按上表分配：只涉及一个模块配置的规则放进该模块的 validate，`RULES` 只放核心配置和跨文件规则。`MODULE_SKILL_CONFLICT` 由 artifactSync 自己对照节点技能检查，lint 就能报出，不用等到 merge。`MODULE_CONFLICT` 是模块之间的冲突，属于脚手架自身的缺陷，只在 build 中检查。加一个测试，保证 `RULES` 与各模块规则的并集同 input-config.md §7.2 的表一一对应。
- **Q4.3** `--allow-id-change`、`--allow-layout-change` 出现在 input-config.md §7.2，但 interfaces.md §1.1 的命令总览中没有，demo 的提示则是“删除 build-manifest 后重新 build”。两种做法需要选一种；选参数的话，要写进 `build`、`doctor` 的命令行。
- **Q4.4 `PLUGIN_ID_RESERVED` 永远报不出来。** `plugin-scaffold.schema.json` 已经用 `"not": {"enum": [...]}` 排除了保留名，保留名会先在 load 中报成 `INPUT_SCHEMA`，提示信息不如专门的规则清楚。建议去掉 Schema 中的 `not`，改由 lint 报 `PLUGIN_ID_RESERVED`；或者删掉这条规则。

## 5. IR 与编译

IR 是模块看到的流程，只包含核心流程和入口文件的信息；模块配置作为 `options` 单独传给模块（§6）。

```python
# build/ir.py
@dataclass(frozen=True)
class ArtifactIR:
    id: str
    label: str                      # 输出路径原文（D39）
    paths: tuple[str, ...]          # v1 只有一项
    type: str                       # "file" | "json"
    producer: str                   # 第一个输出它的节点 id

@dataclass(frozen=True)
class OutputRef:
    artifact: str                   # 产物 id
    required: bool                  # 核心配置中 optional 的反面

@dataclass(frozen=True)
class NodeIR:
    id: str                         # 同时是 checkpoint 前缀（D36）
    name: str
    group: str                      # "biz" | "dev" | "ops"
    stage: str                      # "Biz" | "Dev" | "Ops"
    seq: int
    order: int                      # 按 seq 排列后的位置 (i + 1) * 10
    skill: str
    skill_dir: str                  # 相对插件根，例如 skills/autodev/autodev-plan；技能不存在时为 skills/<skill>
    description: str                # SKILL.md 的 description；缺省或仍是 [TODO] 时按 input-config.md §6 推导
    terminal: bool
    outputs: tuple[OutputRef, ...]
    inputs: tuple[OutputRef, ...] = ()      # v1 恒为空（D32）
    validate: str | None = None             # v1 恒为 None（D32）
    pointer: str = ""                       # /nodes/<group>/<index>，模块报错时定位

    @property
    def checkpoints(self) -> tuple[str, ...]   # ("<id>_in_progress", "<id>_done")；终态节点为 ("archived",)

@dataclass(frozen=True)
class PluginIR:
    plugin: dict                    # 入口文件的 plugin 段，已补全
    runtime: dict                   # 入口文件的 runtime 段，已补全
    stages: tuple[str, ...]         # 写了节点的分组，按 Biz → Dev → Ops
    nodes: tuple[NodeIR, ...]       # 按 seq 升序
    artifacts: dict[str, ArtifactIR]       # 按首次出现的顺序
    checkpoint_chain: tuple[str, ...]
    workflow_digest: str            # 写入 flow.json（input-config.md §7.1）

    def node(self, node_id: str) -> NodeIR
    def next_node(self, node_id: str) -> NodeIR | None       # board.json 的 nextAction.done
    def node_by_skill(self, skill: str) -> NodeIR | None     # MODULE_SKILL_CONFLICT
    def checkpoints_from(self, anchor: str) -> tuple[str, ...]
        # anchor 为 "<nodeId>:<in_progress|done>" 或 checkpoint 名；artifactSync 的 allowedFrom 用

# build/compile.py
def compile(normalized: Normalized, skills: dict[str, tuple[Path | None, list[Path]]]) -> PluginIR
    # 前提：lint_core 没有 error；skills 取自 LintContext，不再重复扫描目录
```

与 [interfaces.md §2.2](interfaces.md) 的差异：

| 项 | interfaces.md §2.2 | 本文 | 原因 |
|---|---|---|---|
| 模块配置 | `PluginIR` 带 `board`、`session`、`knowledge` 三个字典 | 移出 IR，作为 `options` 传给模块 | 原字段里没有 artifactSync；每个模块只需要看到自己的配置 |
| 输出 | `outputs: tuple[ArtifactIR]`，注释为“v1 中输入输出都是必需的” | `OutputRef(artifact, required)` | 可选输出是节点的属性：同一产物被两个节点输出时，必需性可以不同 |
| 新增字段 | — | `group`、`skill_dir`、`description`、`terminal`、`pointer`、`workflow_digest` | board.json 按组输出、片段同步、`${skillPath}`、终态片段、报错定位、`BUILD_STALE` |
| `stages` | “按首次出现的顺序” | 固定 Biz → Dev → Ops | D32 |
| 方法 | `node`、`checkpoints_from` | 增加 `next_node`、`node_by_skill` | board 的 `nextAction`、模块技能冲突检查 |

待评审：

- **Q5.1** 是否采用上表的修改。采用后按本节改写 interfaces.md §2.2。
- **Q5.2 技能描述改了，lint 发现不了。** 节点描述取自 SKILL.md 的 `description`（D33），会编译进 `runtime/config/board.json`。但 `BUILD_STALE` 只比较核心配置的摘要，开发者改了 description、没有重新生成时 lint 不报，到了 check 重放 build 才发现 board.json 不同，报的是 `DRIFT_GENERATED`（“生成文件被手改”），提示与实际原因不符。建议 build-manifest 的 `inputs` 同时记录各节点技能 description 的摘要（例如键为 `skills/autodev-plan/SKILL.md#description`），让 `BUILD_STALE` 覆盖这种情况。

## 6. 模块契约与合并

```python
# modules/__init__.py
@dataclass(frozen=True)
class ModuleSpec:                   # module.json
    id: str                         # "board" | "session" | "knowledge" | "artifactSync"
    version: str
    title: str
    description: str
    schema: str                     # 配置的 Schema，相对 schemas/，例如 "modules/board.schema.json"
    requires_core: str              # semver 范围，例如 ">=1.0.0 <2.0.0"
    entry: str                      # "module:BoardModule"
    core: bool                      # board、session 为 true：恒启用，不能 disable

@dataclass(frozen=True)
class ModuleContext:
    root: Path                      # 插件目录，只读（例如检查 customSubagentFiles 是否存在）
    package_dir: Path               # 模块包目录
    runtime_dir: Path               # 仓库根目录的 runtime/（Q6.5）
    core_version: str

class Module(Protocol):
    spec: ModuleSpec
    def validate(self, ir: PluginIR, options: dict, ctx: ModuleContext) -> list[Issue]
        """语义校验，只读、无副作用。options 已按 Schema 补全。"""
    def contribute(self, ir: PluginIR, options: dict, ctx: ModuleContext) -> Contribution
        """纯函数：相同输入必须得到相同输出（漂移检测依赖这一点）。"""

def discover() -> dict[str, ModuleSpec]          # 读 scaffold/modules/*/module.json
def instantiate(spec: ModuleSpec) -> Module      # requires_core 不满足时抛错
def enabled_modules(normalized: Normalized) -> dict[str, Module]   # 按 MODULE_KEYS 顺序

# build/contribute.py
@dataclass(frozen=True)
class FileSpec:
    dst: str                        # 插件内相对路径
    ownership: str                  # "managed" | "module" | "generated" | "seeded"
    src: str | None = None          # "files/…" 相对模块包；"runtime/…" 相对仓库根目录的 runtime/
    content: str | bytes | None = None
    render: bool = False            # 用 {{ }} 渲染 src（§8）
    replaceable: bool = False       # 插件可以整个替换：与记录不符时保留插件的版本，不报漂移

@dataclass(frozen=True)
class CommandSpec:
    script: str | None = None       # 相对插件根；展开为 {py} "${pluginPath}/<script>" <args>
    args: str = ""                  # 可含 {platform}，展开时替换为平台名
    value: str | None = None        # 非命令值：plugin_dir_hook、dialog_tips、system_prompt_inject、knowledge_path

@dataclass
class Contribution:
    files: list[FileSpec] = field(default_factory=list)
    entries: dict = field(default_factory=dict)                    # board_core/modules.json 顶层的看板入口
    manifest: dict = field(default_factory=dict)                   # modules.json 中 modules.<id> 的附加字段
    runtime_config: dict[str, dict] = field(default_factory=dict)  # runtime/config/<name>.json
    inspect_commands: dict[str, CommandSpec] = field(default_factory=dict)
    knowledge_assembly: dict | None = None                         # 写入 session.json 的 knowledgeAssembly
    skills: list[str] = field(default_factory=list)                # 模块占用的技能名
    gitignore: list[str] = field(default_factory=list)

@dataclass
class Merged:
    files: dict[str, tuple[str, FileSpec]]          # dst → (来源 id, 文件)
    entries: dict
    manifests: dict[str, dict]                      # 模块 id → 附加字段
    runtime_config: dict[str, dict]
    inspect_commands: dict[str, CommandSpec]
    knowledge_assembly: dict | None
    skills: dict[str, str]                          # 技能名 → 模块 id
    gitignore: list[str]

def contribute_all(ir, normalized, modules, ctx_for) -> dict[str, Contribution]
    # 键为 "framework"（§7）与各模块 id
def merge(contribs: dict[str, Contribution]) -> tuple[Merged, list[Issue]]
    # 合并规则见 interfaces.md §2.3；冲突报 MODULE_CONFLICT
```

待评审：

- **Q6.1** 删除 `Module.defaults()`：它与 D27（常量默认值只写在 Schema 的 `default` 中）冲突。模块配置统一由 normalize 按 Schema 补全后传入。
- **Q6.2** `module.json` 去掉 `config.pointer`（目前都是 `""`，配置总是整个文件）；`config.file` 与 `id` 相同，也去掉；新增 `schema`、`core` 两个字段。
- **Q6.3** `CommandSpec` 删除 `runtime_owned`：D31 去掉运行期回写之后，这个字段已经没有用处。新增 `args` 中的 `{platform}`，供 `session_collector_context_inject` 的 `--platform <platform>` 使用。
- **Q6.4 board、session 算不算模块，现在两处说法矛盾。** README §3.1 把它们放在 `scaffold/modules/board|session/`，interfaces.md §2.3 又规定 `runtime_config` 中的 `board`、`session`“由核心生成，模块不得占用”。建议两者实现同一个 Module 协议并标 `core: true`；§2.3 中的保留名只约束非核心模块。各自的贡献见 §9。
- **Q6.5 运行期代码只放一处。** README §3.1 同时把 adapters 模板写在 `scaffold/modules/board/` 和根目录的 `runtime/` 下。建议运行期代码统一放在根目录 `runtime/`：adapters、session 都要 import `runtime/common/`，放在一起才能整体测试；board、session 的 `FileSpec.src` 写成 `runtime/…`。knowledge 是可选模块，版本独立，仍放在自己的 `files/` 下。
- **Q6.6 模块配置的 Schema 只保留一份。** interfaces.md §2.1 让模块包带 `options.schema.json`，再“发布为” `schemas/modules/<file>.schema.json`，这样就有两份。建议只保留 `schemas/modules/*.schema.json`，`module.json` 的 `schema` 字段指向它，模块包中不再有 `options.schema.json`。
- **Q6.7** 新增 `FileSpec.replaceable`，用来表达“内置知识组装脚本可以被插件替换”（README §4）。这样 emit 不用写死这个文件的路径。

## 7. 框架贡献与技能同步

不属于任何模块的输出由 `framework` 产出，在 merge 中与模块贡献同等对待，这样框架文件和模块文件重名时也能统一报 `MODULE_CONFLICT`。

| 输出 | 归属 | 规格 |
|---|---|---|
| `plugin.json` | generated | output-spec.md §2.1 |
| `runtime/config/runtime.json` | generated | output-spec.md §5.1 |
| `runtime/config/flow.json` | generated | output-spec.md §5.2 |
| `runtime/workflow/update_state.py` | managed | interfaces.md §4.2 |
| `runtime/common/query.py`、`engine.py` | managed | interfaces.md §4.6 |
| `runtime/adapters/board_events.py` | managed | interfaces.md §3.5；写入口共用，所以归框架（Q7.3） |
| `runtime/` 各级 `__init__.py` | managed | |
| `.scaffold/**/*.schema.json` | managed | 供 IDE 补全 |
| `.githooks/pre-commit` | seeded | 内容取决于 Q13.3 |
| `.gitignore` | seeded | 合并各贡献的 `gitignore` 条目（Q7.2） |

`board_core/` 的两个文件需要所有贡献合并后才能生成，所以单独渲染：

```python
# build/framework.py
def framework_contribution(ir: PluginIR, normalized: Normalized, ctx: ModuleContext) -> Contribution
def render_board_core(ir: PluginIR, board_options: dict, merged: Merged,
                      modules: dict[str, Module]) -> dict[str, bytes]
    # board_core/board_config.json：按 board.target.platforms 逐个平台展开 merged.inspect_commands
    #   命令为 {py} "${pluginPath}/<script>" <args>；{py} 为 target.python.posix（win32 用 .win32）加 " -X utf8"（D40）
    #   单值占位符加双引号（D2）；键按 output-spec.md §3.2 表格的顺序输出，模块新增的键排在后面
    # board_core/modules.json：四个模块逐个列出（未启用的为 {"enabled": false}）、boardEvents、merged.entries

# build/skills.py
@dataclass
class SkillChanges:
    created: list[str]              # 生成的空白 SKILL.md
    stateInserted: list[str]
    stateUpdated: list[str]
    stateRemoved: list[str]

def plan_skills(ir: PluginIR, root: Path, previous: dict | None) -> tuple[list[FileSpec], SkillChanges]
    # 节点技能不存在 → blank_skill（seeded）；已存在 → upsert_state，内容不变时不写
    # previous 中记录过片段、这次不再绑定节点的技能 → remove_state（output-spec.md §6.1）
```

待评审：

- **Q7.1 `agents/openai.yaml` 的规格已经不存在。** output-spec.md 现在没有 §6.2，但 README §2.3、output-spec.md §1 的目录、check 规则 `OPENAI_YAML` 和插件开发技能第 5 步仍然引用它。按 README §4，seeded 文件“缺失时创建”，那么 build 会生成一个带 TODO 的骨架，然后被 check 报 `OPENAI_YAML`。建议：build 不生成 `openai.yaml`；`OPENAI_YAML` 只在文件存在时检查；约束补回 output-spec.md §6.2。如果不再需要这个文件，就把引用和规则一起删掉。
- **Q7.2 `.gitignore` 的托管部分怎么标记。** README §4 说 seeded 文件“已存在时只更新托管片段”，output-spec.md §7.1 也要求声明 `knowledge.source` 时追加 `<root>/` 等条目，但 `.gitignore` 没有定义片段标记。建议仿照 SKILL.md，用 `# plugin: begin managed` … `# plugin: end managed` 包住脚手架写入的条目，片段外由开发者维护。
- **Q7.3** `board_events.py` 被 `update_state.py`（框架）和 `init_workspace.py`、`init_feature.py`（board）共同使用，建议归框架，与 board 模块的 adapters 分开。

## 8. 写盘与编排

```python
# build/emit.py
@dataclass(frozen=True)
class PlannedFile:
    path: str
    ownership: str
    data: bytes | None              # None 表示删除
    source: str                     # 来源：framework、模块 id、skills
    replaceable: bool = False
    regions: dict[str, str] | None = None     # SKILL.md 的片段摘要，写进 build-manifest

class WritePlan:
    files: dict[str, PlannedFile]
    def add(self, planned: PlannedFile) -> None

def plan_files(merged: Merged, skill_files: list[FileSpec], board_core: dict[str, bytes],
               options: dict[str, dict], ir: PluginIR, root: Path, previous: dict | None) -> WritePlan
    # 读取 src、渲染模板、序列化 runtime_config；已存在的 seeded 文件不进计划（SKILL.md 由 plan_skills 处理）
    # previous 中记录、这次没有任何贡献的 module/generated 文件 → 删除（Q8.1）
def render_template(text: str, scope: dict) -> str     # 只支持 {{ a.b.c }} 取值（Q8.3）
def check_drift(plan: WritePlan, root: Path, previous: dict | None, *, force: bool) -> list[Issue]
    # managed、module 文件：当前内容既不等于记录也不等于新内容 → DRIFT_MANAGED
    # replaceable 的文件与记录不符时视为插件的替换：保留，不报
def apply(plan: WritePlan, root: Path) -> list[str]    # 只写内容有变化的文件，逐个 atomic_write

# build/manifest.py
MANIFEST = "runtime/build-manifest.json"
def read_manifest(root: Path) -> dict | None
def make_manifest(ir: PluginIR, normalized: Normalized, plan: WritePlan,
                  modules: dict[str, Module]) -> dict  # output-spec.md §8；不记录构建时间
def stale_inputs(inputs: Inputs, previous: dict | None) -> list[str]   # 摘要变化的核心配置 → BUILD_STALE

# build/pipeline.py
@dataclass
class BuildResult:
    report: Report
    ir: PluginIR | None
    plan: WritePlan | None
    skills: SkillChanges | None
    written: list[str]

def build(root: Path, *, dry_run: bool = False, force: bool = False,
          allow: frozenset[str] = frozenset()) -> BuildResult
    # 按“数据流”一节的顺序执行；任何一步有 error 都返回，不写文件
```

待评审：

- **Q8.1 模块关闭后，它以前生成的文件怎么处理。** interfaces.md §1.1 只说 `module disable` 保留 `modules/*.json`，没有说 `runtime/knowledge/*`、同步技能目录这些生成物。建议 build 按 build-manifest 删除不再有任何贡献的 module 文件；被插件替换过的组装脚本不删，报 warning。
- **Q8.2 “事务性”的范围。** interfaces.md §1.2 要求“任何 error 都不会导致只写了一半”。按本节的顺序，校验类 error 都在写盘之前报出；写到一半发生 IO 错误则无法回滚。建议接受这一点：文件逐个原子替换，重跑 build 即可恢复，不另做临时目录整体替换。
- **Q8.3** `{{ }}` 模板只支持取值，不支持循环和条件。复杂内容由模块用 `FileSpec.content` 直接给出。

## 9. 四个模块

每个模块的配置字段和默认值见 input-config.md §4，生成内容见 output-spec.md §3、§5、§7。下表是各模块 `validate` 和 `contribute` 的分工：

| 模块 | validate | runtime_config | files | inspect_commands | entries / manifest |
|---|---|---|---|---|---|
| board（core） | `PLACEHOLDER_UNKNOWN`、`FEATURE_DIR_MISSING` | `board.json` | `runtime/adapters/` 下的 `init_workspace.py`、`init_feature.py`、`inspect_state.py`、`inspect_workflow_templates.py`、`skip_node.py` | `project_status`、`feature_status`、`create_project`、`create_feature`、`dynamic_workflow`、`plugin_dir_hook`、`dialog_tips`、`system_prompt_inject`（`skip_node` v1 不生成） | `knowledge_config` |
| session（core） | `POLICY_NODE_UNKNOWN`、`SUBAGENT_FILE_MISSING` | `session.json` | `runtime/session/render_session_context.py` | `session_collector_context_inject` | — |
| knowledge | `PATH_UNSAFE`（`root`）、`MODULE_OPTION` | `knowledge.json` | `runtime/knowledge/` 下的 `inspect_deploy_units.py`、`render_collected_session_context.py`（replaceable）、`collect-knowledge.js`；`sync_knowledge.py` 只在声明 `source` 时生成 | `knowledge_path`、`deploy_units`；`pull_knowledge` 只在声明 `source` 时生成 | `manifest`：`{assembler, source}`；`knowledge_assembly`；声明 `source` 时追加 `gitignore` |
| artifactSync | `ARTIFACT_REF_UNKNOWN`、`MODULE_OPTION`、`MODULE_SKILL_CONFLICT` | — | `skills/autobizdevops-artifact-sync/**`，其中 `config/artifact-sync.json` 由输入生成 | — | `entries.artifact_sync`（`entry.enabled` 时）；`manifest`：`{skill}`；`skills` |

起点：board、session 以 lite 的 `board_core` 和 demo 的 `assets/runtime/` 为起点；knowledge 以 lite 的 `hooks/` 和全栈版的 `render_collected_session_context.py`、`collect-knowledge.js` 为起点；artifactSync 以全栈版 `9411fc3` 的 `skills/autobizdevops-artifact-sync` 为起点。改造内容见 README §6.3。

待评审：

- **Q9.1** knowledge 的 Node 依赖（README §9 第 7 条）决定 `files` 里是否要带 `node_modules`。这一点需要先定下来，knowledge 模块才能实现。
- **Q9.2** 四个模块的版本号：board、session 标 `core: true`，是否直接使用 `coreVersion`，不单独编号？output-spec.md §8 的 build-manifest 示例中四个模块都有独立版本。

## 10. CLI 与核心命令

```python
# cli.py
def main(argv: list[str] | None = None) -> int
    # 全局参数 -C <plugin-dir>、--json；子命令见 interfaces.md §1.1
    # 退出码：report.failed(strict) → 1；UsageError → 2；其余 → 0（interfaces.md §1.2）

@dataclass
class CommandResult:
    report: Report
    extra: dict = field(default_factory=dict)      # 例如 doctor 的 {"changes": …}
    written: list[str] = field(default_factory=list)

# commands/lint.py
def lint(root: Path, *, strict: bool = False, allow=frozenset()) -> CommandResult
    # load → normalize → lint_core → compile → lint_modules

# commands/build.py
def build(root: Path, *, dry_run: bool = False, force: bool = False, allow=frozenset()) -> CommandResult

# commands/doctor.py
@dataclass
class Changes:
    inputs: list[str]                              # 改过的核心配置
    nodes: dict                                    # {"added": [...], "removed": [...], "reordered": bool}
    skills: SkillChanges

def diff(previous_flow: dict | None, previous: dict | None, ir: PluginIR,
         inputs: Inputs) -> tuple[Changes, list[Issue]]          # CHECKPOINT_REMOVED（interfaces.md §1.7）
def doctor(root: Path, *, dry_run: bool = False, force: bool = False) -> CommandResult
    # lint（不报 BUILD_STALE）→ diff → build → 复查（lint + SKILL_STATE_BLOCK）

# commands/check.py
RESOURCE_RULES: dict[str, Rule]                    # input-config.md §7.3
def check(root: Path, *, strict: bool = False) -> CommandResult
    # lint → RESOURCE_RULES → build(dry_run=True) 重放，与磁盘比较 → DRIFT_GENERATED、DRIFT_MANAGED
    # → 契约测试：simulate(skip_validate=True) 的失败报 CONTRACT_TEST
```

待评审：

- **Q10.1** README §5 提到 check 的“`--check` 模式重放 build”，interfaces.md §1.1 的 `check` 没有这个参数。建议 check 总是重放，不单设参数，并改掉 README §5 的说法。
- **Q10.2** doctor 以 `runtime/config/flow.json` 为比较基线。flow.json 被删掉或无法解析时，退回只用 build-manifest 比较（只能列出改过的输入和技能片段，列不出节点的增删）。

## 11. simulate

simulate 和 check 的契约测试都要在脚手架中扮演 DevClaw：按宿主规则替换占位符、执行命令、检查输出。

```python
# host.py
@dataclass
class HostCall:
    key: str                        # inspectCommands 的键，或 "model:update_state"
    argv: list[str]
    code: int
    payload: dict | None            # stdout 解析出的 JSON；不是合法 JSON 时为 None
    stderr: str

class Host:
    def __init__(self, plugin_root: Path, workspace: Path, platform: str, *, env: dict | None = None): ...
    def render(self, key: str, **ctx) -> list[str]
        # 取 board_config.json 中当前平台的命令，按 interfaces.md §3.2 替换占位符并拆成参数
    def run(self, key: str, **ctx) -> HostCall
        # 注入 interfaces.md §3.4 的环境变量后执行
    def run_model(self, command: str, **ctx) -> HostCall
        # 执行技能状态维护片段中的命令（替换 ${pluginPath}、${feature}）

# shapes.py
def check_shape(key: str, payload: dict) -> list[str]   # interfaces.md §3.3 各命令的输出结构

# commands/simulate.py
def simulate(root: Path, *, feature: str = "demo", to: str | None = None, platform: str | None = None,
             skip_validate: bool = False, keep: bool = False) -> CommandResult
    # 步骤见 interfaces.md §1.5
```

待评审：

- **Q11.1** 占位符的替换和转义规则（`${projectDirs...}` 展开、`${selectedDeployUnits}` 整体转义、去掉 `"${x}"` 的引号）必须与 DevClaw 一致。需要 DevClaw 确认它是交给 shell 解析，还是自己拆分参数。
- **Q11.2** check 的契约测试是否起一个模拟的看板事件服务，验证 interfaces.md §3.5.3 的推送规则？`tests/contract/` 要做这件事；放进 check，开发者改了插件之后也能发现问题，但每次 check 会多花一些时间。
- **Q11.3** 输出结构用手写的 `shapes.py` 校验，还是给命令输出也写 JSON Schema、复用 `lib/jsonschema`？建议后者，Schema 同时可以作为给 DevClaw 的协议文档。
- **Q11.4** simulate 读的是已经生成的插件。核心配置改了但没有重新生成（`BUILD_STALE`）时，simulate 是拒绝执行，还是只给出 warning？

## 12. 配置编辑与向导

`add`、`module`、`new` 只修改核心配置，写完后调用 doctor（`new` 调用 build），不直接生成插件文件（interfaces.md §1.1）。

```python
# commands/edit.py：修改核心配置时保持原有键序和缩进
def add_node(root: Path, *, id: str, name: str, skill: str, stage: str, seq: int,
             outputs: list[str]) -> CommandResult            # seq 冲突时当场报 SEQ_DUP，不写文件
def add_skill(root: Path, skill: str, *, source: Path | None = None) -> CommandResult
    # 拷贝技能目录，migrate_frontmatter；不带 source 时生成空白 SKILL.md
def module_list(root: Path) -> CommandResult
def module_enable(root: Path, module_id: str, sets: dict[str, str]) -> CommandResult
    # 创建 modules/<id>.json 骨架并在入口中引用；artifactSync 预填全部文件类产物的路径
def module_disable(root: Path, module_id: str) -> CommandResult   # 只去掉引用；board、session 不能关闭

# wizard.py：问答与写配置分开，便于测试
@dataclass
class Answers:
    plugin: dict
    nodes: list[dict]
    skills: dict[str, Path | None]          # 技能名 → 导入目录；None 为不提供
    board: dict
    session: dict
    knowledge: dict | None
    artifact_sync: dict | None

class Prompter(Protocol):                   # 终端实现与测试用的脚本化实现
    def ask(self, question: str, *, default=None, choices=None) -> str: ...

def ask(prompter: Prompter, seed: Answers | None = None) -> Answers   # interfaces.md §1.4 的七类问题
def to_configs(answers: Answers) -> dict[str, dict]                   # 只写与默认值不同的部分

# commands/new.py
def new(target: Path, *, template: str = "blank", yes: bool = False) -> CommandResult
    # template 为 lite、fullstack 时以 examples/<template>/ 为种子；lint 有 error 时回到对应问题
```

待评审：

- **Q12.1** `--from lite|fullstack` 要读 `examples/`，所以脚手架的安装包要带上 `examples/` 的核心配置（不带 `output/`）。
- **Q12.2** `add node --output` 只能写字符串；可选输出 `{path, optional: true}` 需要手改，或者增加 `--optional-output <path>`。

## 13. 打包、升级、钩子

```python
# commands/package.py
def package(root: Path, *, output: Path | None = None) -> CommandResult
    # check --strict（TODO_PLACEHOLDER 升为 error）→ 按 output-spec.md §1 的打包清单写 zip
    # 默认输出 dist/<plugin.id>-<plugin.version>.zip

# commands/upgrade.py
def upgrade(root: Path, *, force: bool = False) -> CommandResult      # Q13.2

# commands/githook.py
def git_hook_install(root: Path) -> CommandResult
    # 写 .githooks/pre-commit（seeded，已存在时不覆盖），执行 git config core.hooksPath .githooks
```

待评审：

- **Q13.1** interfaces.md §1.1 说 package 会“重置运行期字段”。D31 之后已经没有运行期字段，README §6.1 也写明“build 和 package 不需要保留或重置任何字段”，这句应该删掉。
- **Q13.2 upgrade 和 build 的边界不清楚。** coreVersion 变化时 build 本来就会替换 managed 文件（README §4）。一个脚手架安装包只带一个版本的运行框架，`upgrade --to <version>` 没法实现。建议 v1 去掉 `--to`：upgrade 等于“用当前脚手架重新 build，并报告运行框架和各模块的版本变化”；跨主版本时先报告、要求确认。
- **Q13.3 脚手架怎么安装，文档没有写。** 用 pip/pipx 安装命令行入口 `autobiz-plugin`，还是 `python -m autobiz_plugin`，还是像 demo 那样把脚本放在技能里？这决定了 `.githooks/pre-commit` 的内容、CI 的写法，以及插件开发技能怎么调用 CLI（Q14.2）。

## 14. 插件开发技能

结构和对话流程见 interfaces.md §1.6。技能本身没有代码接口，评审的是它与 CLI 的关系：

| 项 | 做法 |
|---|---|
| 调用 CLI | 所有生成和校验只通过 CLI 完成，判断以退出码和 `--json` 的 Issue 为准 |
| 写哪些文件 | 只写核心配置和 seeded、developer 文件（interfaces.md §1.6 的规则） |
| `references/input-config.md` | 从 `docs/input-config.md` 同步 |

待评审：

- **Q14.1** `references/input-config.md` 靠同步脚本生成，还是靠测试保证两者一致？`tests/check_schema_defaults.py` 已经同时检查这两份文件的默认值表，说明两份内容会分别修改，容易不一致。
- **Q14.2** 技能依赖开发者已经安装 `autobiz-plugin`，还是像 demo 那样在自己的 `scripts/` 下带一份脚手架？取决于 Q13.3。

## 15. 运行框架模板

对外协议已经在 interfaces.md §3、§4 中确定，本单元只评审内部拆分：

| 文件 | 职责 | 使用者 |
|---|---|---|
| `runtime/common/query.py` | 只读：读编译配置和状态，查询节点、产物存在情况（interfaces.md §4.6） | 全部入口、模块脚本 |
| `runtime/common/engine.py` | 初始化、状态转移、存在性检查、校验命令、加锁提交、变更日志 | 写入口 |
| `runtime/common/cli.py` | 入口共用的参数解析、单个 JSON 输出、`BoardError` → `{"ok": false}` 与退出码 | 全部入口 |
| `runtime/adapters/board_view.py` | 看板数据拼装：`WorkflowNode`、`run`、`projectRuns` | `inspect_state.py`、`inspect_workflow_templates.py`、`board_events.py` |
| `runtime/adapters/board_events.py` | 提交后推送 `board/changed`（interfaces.md §3.5.3） | 四个写入口 |

待评审：

- **Q15.1** demo 中的 `runtime/common/cli.py` 和 `runtime/adapters/board_view.py` 不在 output-spec.md §1 的文件清单中。看板事件的内容要与读取命令的输出一致（interfaces.md §3.5.3），所以 `inspect_state.py` 和 `board_events.py` 必须共用同一套拼装代码。建议两个文件都加入 output-spec.md §1，归属 managed。
- **Q15.2** interfaces.md §4.1 说 `sync_knowledge.py`“拉取知识仓库并回写运行期字段”，与 §3.3.9 的“只更新知识目录，不回写任何配置文件”以及 D31 矛盾，应改为只更新知识目录。
