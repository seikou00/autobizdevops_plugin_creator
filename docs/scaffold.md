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
- 脚手架默认在 Windows 上执行，同时支持 macOS、Linux（D42）；插件是成品，不假设插件仓库用 git 管理（D41）；
- 下文代码只是接口签名，不是实现。签名中的 `list[...]`、`X | None` 写法是为了便于阅读，实现时用 `from __future__ import annotations`；
- “demo”指 `demo/autobiz-plugin-creator-demo/skills/autobiz-plugin-creator/` 下的演示版脚本，它们按旧版设计实现，迁入时要按本文的接口调整。

## 总览

### 目录

```text
autobizdevops_plugin_creator/
├── scaffold/
│   ├── cli.py                       # 单元 10：命令行入口
│   ├── lib/                         # 单元 1、2、12：issues  jsonschema  fsio  derive  skillmd  jsonedit
│   ├── build/                       # 单元 3–8、13：load  normalize  lint  ir  compile  contribute
│   │                                #              framework  skills  emit  manifest  pipeline  versions
│   ├── commands/                    # 单元 10–13：doctor  lint  check  simulate
│   │                                #             edit  new  package
│   ├── host.py  shapes.py           # 单元 11：扮演 DevClaw、校验命令输出结构
│   ├── wizard.py                    # 单元 12：初始化向导问答
│   └── modules/                     # 单元 6、9：模块契约与四个模块包
│       ├── __init__.py
│       └── board/  session/  knowledge/  artifact_sync/
│           └── module.json  module.py  files/
├── runtime/                         # 单元 15：运行框架模板（随插件发布）
├── skills/autobiz-plugin-creator/   # 单元 14：插件开发技能
├── schemas/  examples/  docs/
├── tools/make_pyz.py                # 单元 13：把脚手架打成 autobiz-plugin.pyz
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
| `doctor` | ✓ | ✓ | ✓ | ✓（`--dry-run` 不写） | 前置影响报告，后置复查；CLI 不单独提供 `build`（Q10.3） |
| `check` | ✓ | ✓ | ✓ | — | 资源规则、`DRIFT_GENERATED`、契约测试 |
| `simulate` | — | — | — | — | 把已生成的插件拷到临时目录执行，只写临时目录（Q11.4、Q11.6） |
| `package` | 同 `check`（不用 `--strict`，Q4.6） | | | 写 zip | |
| `add`、`module`、`new` | ✓ | ✓ | ✓ | ✓ | 在内存中修改核心配置后走 doctor 流水线，与生成结果一起写盘（Q12.4） |

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
| 10 | CLI 与核心命令 | `cli.py` `commands/{doctor,lint,check}.py` | 参数、退出码、doctor 影响报告、check | demo_lint.py `main` |
| 11 | simulate | `host.py` `shapes.py` `commands/simulate.py` | 扮演 DevClaw 执行命令、校验输出结构 | demo_simulate.py `Simulation` |
| 12 | 配置编辑与向导 | `commands/{edit,new}.py` `wizard.py` | `add`、`module`、`new` | demo_skills.py |
| 13 | 打包、升级 | `commands/package.py` `build/versions.py` `tools/make_pyz.py` | 插件 zip、版本比较（升级由 doctor 完成）、脚手架发布 | demo_package.py |
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
def read_json(path: Path) -> object                          # UTF-8，接受 BOM；重复键报错（Q3.3、Q3.4）；失败时抛 JsonError(path, line, column, message)
def dump_json(value) -> bytes                                # json.dumps(indent=2, ensure_ascii=False) + "\n"，保持键序
def digest(data: bytes) -> str                               # "sha256:<hex>"；文本先把 CRLF 换成 LF 再算（Q1.5、Q1.6）
def atomic_write(path: Path, data: bytes) -> None            # 同目录临时文件 + os.replace；按字节写入，不转换换行（Q1.6）
```

`dump_json` 的格式已与 `examples/*/output/` 下全部 28 个 JSON 文件逐字节比对一致，金样测试可以直接使用。

评审结论（2026-11-03，D42、D43）：

- **Q1.1 关键字（已定，D43）。** 脚手架自带的 Schema 校验只实现 lite、fullstack 两个示例校验时实际用到的 18 个关键字：`$ref`、`additionalProperties`、`const`、`default`、`enum`、`items`、`maxLength`、`minItems`、`minLength`、`minProperties`、`minimum`、`not`、`oneOf`、`pattern`、`properties`、`propertyNames`、`required`、`type`。加一个测试，保证 Schema 只使用这些关键字（`$schema`、`$id`、`title`、`description`、`definitions` 这些说明性的键除外）。

  Schema 中还有 4 处用到了这 18 个以外的关键字，lite、fullstack 都没有写对应的字段。校验器不实现它们，这些约束就不会生效，所以已按下表改写 Schema。改写后三个示例仍通过结构校验，默认值补全的结果不变：

  | 位置 | 关键字 | 改写 |
  |---|---|---|
  | `modules/session.schema.json` 的 `policies.default` | `allOf` | 不再用 `allOf` 引用 `runtimePolicy`，直接写出 `agentMode`、`subagentConfig`、`toolCustomConfig` 三个字段，`agentMode` 带默认值 `multi`（D44）；不再使用的 `runtimePolicy` 定义删掉 |
  | `modules/artifactSync.schema.json` 的 `maxFileSizeMiB` | `exclusiveMinimum: 0` | 改为 `"type": "integer", "minimum": 1`，上限只能写整数 MiB |
  | `modules/artifactSync.schema.json` 的 `uploadUrl` | `format: "uri"` | 改为 `"pattern": "^https?://"` |
  | `modules/board.schema.json` 的 `target.platforms` | `uniqueItems` | 删掉：重复的平台只会生成同一组命令，不影响结果 |

- **Q1.2 Schema 不带注释（已定，D43）。** 已去掉 6 个 Schema 文件中的 73 处 `//` 注释，去注释前后解析出的内容相同。脚手架只用 `json.loads` 读取，不需要 `read_jsonc`；Schema 和核心配置都必须是严格 JSON。
- **Q1.3 Issue 排序（已定，D43）。** 写入 interfaces.md §1.3：
  1. 先按文件：入口文件、`workflow.json`、`modules/` 下按 board、session、knowledge、artifactSync，其余文件按路径；
  2. 再按 pointer：逐段比较，数字段按数值比较，避免 `/nodes/dev/10` 排在 `/nodes/dev/2` 之前；
  3. 最后按 code。
- **Q1.4 用法错误的输出（已定，D43）。** `--json` 下仍输出 interfaces.md §1.3 的结构：`{"ok": false, "issues": [{"level": "error", "code": "USAGE", …}], "written": []}`，退出码 2；写入 interfaces.md §1.2。
- **Q1.5 摘要写法（已定，D43）。** 所有摘要都写成 `sha256:<hex>`，`files.<path>.sha256` 也一样；写入 output-spec.md §8。
- **Q1.6 Windows 上的换行与编码（已定，D42）。** 脚手架默认在 Windows 上执行。开发者在 Windows 编辑器里写的 `workflow.json`、`SKILL.md` 通常是 CRLF 换行，而脚手架生成的文件、examples 和 demo 的技能都是 LF。需要处理的地方：

  | 位置 | 不处理会怎样 | 做法 |
  |---|---|---|
  | 写文件 | Python 在 Windows 上以文本方式写文件时会把 `\n` 换成 `\r\n`，同一份输入在 Windows 和 macOS 上 build 出不同的文件，金样测试失败 | 一律按字节写入（`dump_json`、`atomic_write` 只处理 `bytes`），生成的文件固定为 LF |
  | SKILL.md 片段 | CRLF 的 SKILL.md 插入 LF 的片段后变成混合换行（demo 的 `upsert` 能识别 CRLF 的 frontmatter，但插入时固定用 `\n`）；编辑器保存时统一换行后，片段摘要随之变化，报 `SKILL_STATE_BLOCK` | `skillmd` 识别文件原有的换行方式，插入、更新片段时沿用；片段摘要先把 CRLF 换成 LF 再算 |
  | 摘要 | 编辑器保存时改了换行，或插件目录在 Windows 和 macOS 之间拷贝后，内容没变也报 `BUILD_STALE`；生成文件被编辑器打开再保存后报 `DRIFT_GENERATED`、`DRIFT_MANAGED` | `digest` 和“内容是否变化”的比较，对文本文件先把 CRLF 换成 LF（文本按“能以 UTF-8 解码且不含 NUL 字节”判断）。现有文件都是 LF，examples 中的摘要不变 |
  | 文件编码 | 简体中文 Windows 的默认编码是 GBK，`open()` 不指定编码时读写 UTF-8 文件会乱码或报错 | 所有读写都显式指定 UTF-8；读取时接受 BOM，写入不带 BOM（Q3.4） |
  | 命令行输出 | stdout 被管道读取时（例如插件开发技能调用 CLI 读 `--json`）按 GBK 编码，读取方按 UTF-8 解析会乱码，GBK 表示不了的字符还会抛 `UnicodeEncodeError` | CLI 启动时把 stdout、stderr 改为 UTF-8，与宿主命令加 `-X utf8` 同理（D40） |
  | 路径 | Windows 的 `Path` 用 `\`，写进 Issue 的 `file`、build-manifest 的键和 zip 条目后与其他平台不一致 | 对外输出的路径一律用 `/`（`as_posix()`） |

## 2. 推导与 SKILL.md

`derive` 是 input-config.md §2.3、§6 中推导规则的唯一实现，lint 和 compile 都调用它，避免两处各算一遍。`skillmd` 负责技能目录查找和 SKILL.md 的读写。

```python
# lib/derive.py：纯函数
GROUPS = ("biz", "dev", "ops")
def group_label(group: str) -> str                           # biz → Biz
def artifact_id(path: str) -> str                            # input-config.md §2.3 的三步规则
    # 每一段都含 glob（例如 *.md）时返回空字符串，由 lint 报 ARTIFACT_ID_INVALID
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
    # 沿用文件原有的换行方式（CRLF 或 LF，Q1.6）
    # 旧版 scaffold:begin state 片段原地替换，旧版 artifacts 片段整段删除
def remove_state(text: str) -> str
def state_digest(text: str) -> str | None                    # 两个标记之间去掉首尾换行、CRLF 换成 LF 后的摘要；没有片段时为 None
def blank_skill(skill: str, block: str) -> str               # description 为 [TODO: 做什么；在什么情况下使用]
def migrate_frontmatter(text: str) -> tuple[str, list[str]]  # 顶层 version、author 移入 metadata（D8），add skill 用
```

核对结果（2026-11-03）：

- 按 input-config.md §2.3、§6 和 output-spec.md §6.1 写出 `derive` 和 `skillmd` 的候选实现，与三个示例的输出逐项比较，13 个节点、18 个产物全部一致。比较的内容包括：节点顺序、`stage`、`order`、`checkpoints`、`skillDir`、`outputs`（id 与 required）、产物表（label、type、paths、producer）、checkpoint 链、各技能 SKILL.md 中的状态维护片段、空白 SKILL.md 的全文，以及 build-manifest 中 `regions.state` 的摘要算法（两个标记之间去掉首尾换行后的内容）；
- `find_skill_dir` 用 lite、全栈版两个参考仓库核对：11 个节点技能都只找到一个目录（全栈版在 `skills/<分组>/` 下，lite 直接在 `skills/` 下），没有 `SKILL_AMBIGUOUS`。

评审结论（2026-11-03，D45）：

- **Q2.1 受限 frontmatter 解析的范围（已定）。** 两个参考仓库主干中共有 27 个 SKILL.md（不含 `.claude/worktrees/` 下的副本），其中 25 个有 frontmatter，全部是单行的 `键: 值`：没有 `>`、`|` 块标量，没有嵌套映射和列表；`description` 都没有加引号，都不超过 1024 字符，也不含 `<` `>`。用到的键是 `name`（25）、`description`（25）、`version`（19）、`author`（2）、`allowed-tools`（1，空格分隔的单行字符串）。文件全部是 LF 换行，没有 BOM。另外 2 个没有 frontmatter 的是全栈版的 `autodev-frontend`，它不绑定节点，按开发者资源原样交付，不受影响。

  只支持两种写法：
  1. 单行 `键: 值`，值可以用单引号或双引号包住；
  2. `metadata:` 下一层缩进的单行 `键: 值`。导入技能时，`migrate_frontmatter` 会把顶层的 `version`、`author` 移到这里（D8），所以必须支持。

  迁移时写成块形式（`metadata:` 换行后缩进两格），output-spec.md §6.1 的示例已相应改写。其他写法（块标量、多层嵌套、列表）报 `SKILL_FRONTMATTER`，提示改写成单行，不跳过。按上面的统计，现有技能都不受影响。
- **Q2.2 片段只有状态维护（已定）。** `render_state_block` 只需要节点 id 和是否终态。片段全文已与三个示例核对一致，文案（“技能状态维护”“技能开始执行”“技能完成执行”）写成常量，不开放配置。片段只包含状态维护，脚手架不在 SKILL.md 中生成任何产物相关的内容（输入、输出、模板）。

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
    files: dict[str, str]              # "entry"、"workflow"、模块键 → 相对插件根的路径，去掉开头的 ./
                                       # （例如 modules/board.json），用作 Issue.file 和 build-manifest 的键
    digests: dict[str, str]            # 相对路径 → 摘要；写 build-manifest 的 inputs，判断 BUILD_STALE

def load(root: Path) -> tuple[Inputs | None, list[Issue]]
    # 读取顺序与出错时的处理见 Q3.2；有 error 时返回 None

# build/normalize.py
@dataclass(frozen=True)
class Normalized:
    inputs: Inputs
    entry: dict                        # 补全后的入口文件
    workflow: dict
    modules: dict[str, dict]           # 启用的模块 → 补全后的配置；board、session 未引用时为全部默认值

def normalize(inputs: Inputs) -> Normalized
    # 只按 Schema 的 default 补全，不做推导；去掉各文件的 $schema 键（它只供 IDE 使用，编译配置中没有）
```

核对结果（2026-11-03）：只按 Schema 的 `default` 补全三个示例的核心配置，得到的值与示例编译配置中对应的部分一致：

- `runtime/config/runtime.json` 的 `pluginId`、`metaRoot`、`validateTimeoutSec`；
- `runtime/config/session.json` 的 `policies`；
- `runtime/config/board.json` 的 `stateLabels`（去掉 `skipped`，没有终态节点时再去掉 `archived`）；
- `board_core/board_config.json` 的平台列表和每个平台的解释器；
- `runtime/config/knowledge.json`（除了输入的 `$schema` 换成输出的 `schema`）；
- `artifact-sync.json` 的 `uploadUrl`、`maxFileSizeMiB`。

核对中发现 minimal 示例的 `session.json` 有 `"nodes": {}`，而 Schema 中 `policies.nodes` 没有默认值，补全后不会出现这个键。已按示例在 `modules/session.schema.json` 的 `policies.nodes` 上加 `"default": {}`，三个示例都一致了。

`board.display` 的 `workflowLabel`、`workflowDescription`、`dialogTips`、`systemPromptInject` 四个默认值由其他字段推导（input-config.md §4.1.2），不在 Schema 中，补全后仍然缺省，由 board 模块在 contribute 时计算。

评审结论（2026-11-03，D46）：

- **Q3.1 normalize 只补默认值（已定）。** README §5 和 diagrams.md 图 4 让 normalize 同时“汇总产物、推断类型、算 checkpoint”。建议 normalize 只按 Schema 补默认值、去掉 `$schema`；产物、checkpoint 等推导集中在 `derive` 和 `compile`，lint 需要推导结果时直接调用 `derive`；由其他字段推导的默认值由使用它的模块计算（例如上面 `board.display` 的四个文案由 board 模块计算）。这样 normalize 的输出就是“核心配置 + 默认值”，可以单独测试。README §5 和 diagrams.md 图 4 已改写。
- **Q3.2 读取顺序与出错时的处理（已定）。**
  1. 入口文件不存在 → `UsageError`（退出码 2）；
  2. 入口文件不是合法 JSON → `INPUT_SCHEMA`，`pointer` 为空，`message` 带行号和列号；找不到其他文件，到此为止；
  3. 入口文件结构不符：`workflow` 或 `modules` 字段本身不合法时到此为止，否则继续读其他文件；
  4. 入口引用的 `workflow.json` 不存在 → `UsageError`（退出码 2，interfaces.md §1.2）；引用的模块文件不存在 → `MODULE_FILE_MISSING`；
  5. 其余文件各自读取和校验，问题汇总后一起返回：一个文件出错，不影响检查其他文件。
- **Q3.3 JSON 中的重复键会被悄悄丢掉（已定）。** 标准库 `json.loads` 遇到重复的键时只保留最后一个，例如 `{"nodes": {"dev": [...]}, "nodes": {"biz": [...]}}` 读出来只剩 `biz` 分组，dev 的节点全部丢失，而且不报任何错误。手改 JSON 时容易出现这种情况。`read_json` 检查重复键，报 `INPUT_SCHEMA`（`message` 写明重复的键）。现有示例和 Schema 都没有重复键。
- **Q3.4 Windows 上带 BOM 的文件读不了（已定，D42）。** 有些 Windows 编辑器把 UTF-8 文件存成带 BOM 的格式，`json.loads` 遇到 BOM 直接报错（`Unexpected UTF-8 BOM`）。读取时接受 BOM（按 `utf-8-sig` 解码），SKILL.md 也一样，否则开头的 BOM 会让 frontmatter 识别失败；脚手架自己写的文件一律不带 BOM。现有示例和两个参考仓库的技能都没有 BOM。
- **Q3.5 `systemPromptInject` 的推导规则没有跟上 D28（已定）。** input-config.md §4.1.2 写的是 `{metaDir}` 在 isolated 布局为 `.autobizdevops/<plugin.id>`、legacy 布局为 `.autobizdevops`。D28 之后元数据根目录可以配置，已改为 `<runtime.metaRoot>/<plugin.id>` 和 `<runtime.metaRoot>`。D48 去掉 isolated 布局后，`{metaDir}` 就是 `runtime.metaRoot`。三个示例都用默认的 `.autobizdevops`，不受影响。

## 4. lint

```python
# build/lint.py
@dataclass(frozen=True)
class LintContext:
    normalized: Normalized
    previous: dict | None                                   # 上次的 build-manifest；没有 build 过为 None
    skills: dict[str, tuple[Path | None, list[Path]]]       # 节点技能 → find_skill_dir 的结果，规则之间共用
    allow: frozenset[str]                                   # doctor 传入的放行项 {"id-change", "layout-change"}（Q4.3）

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
| `lint_core` | `NODE_DUP`、`SEQ_DUP`、`SEQ_STAGE_ORDER`、`TERMINAL_INVALID`、`SKILL_SHARED`、`ARTIFACT_ID_INVALID`、`ARTIFACT_ID_CONFLICT`、`OUTPUT_REDECLARED`、`PATH_UNSAFE`（产物路径）、`SKILL_MISSING`、`SKILL_AMBIGUOUS`、`PLUGIN_ID_CHANGED`、`LAYOUT_CHANGED`、`BUILD_STALE`、`MODULE_INACTIVE_FILES` |
| board 的 `validate` | `PLACEHOLDER_UNKNOWN`、`FEATURE_DIR_MISSING` |
| session 的 `validate` | `POLICY_NODE_UNKNOWN`、`SUBAGENT_FILE_MISSING` |
| knowledge 的 `validate` | `MODULE_OPTION` |
| artifactSync 的 `validate` | `ARTIFACT_REF_UNKNOWN`、`MODULE_OPTION`、`MODULE_SKILL_CONFLICT` |
| `merge`（只在 build 中） | `MODULE_CONFLICT` |

核对结果（2026-11-03）：按 input-config.md §7.2 写出核心规则和各模块规则的候选实现，在三个示例上运行：

| 示例 | error | warning |
|---|---|---|
| minimal | 0 | `SKILL_MISSING` 2 |
| lite | 0 | `SKILL_MISSING` 4、`SUBAGENT_FILE_MISSING` 2 |
| fullstack | 0 | `SKILL_MISSING` 7、`SUBAGENT_FILE_MISSING` 7、`OUTPUT_REDECLARED` 1 |

- `SKILL_MISSING`：示例目录里没有技能，build 会生成空白 SKILL.md，符合预期；
- `SUBAGENT_FILE_MISSING`：示例里没有放 `agents/*.md`，符合预期；
- `OUTPUT_REDECLARED`：fullstack 的 `specs` 节点再次输出 `prd` 节点的 `UI_CONTEXT.json`，是有意为之；
- 第一次运行时 lite 报了 `BUILD_STALE`：`modules/knowledge.json` 去掉注释后摘要变了，build-manifest 没跟着更新，规则如实报出。已按 examples/README.md 的约定更新了 lite 的 build-manifest 中这个文件的摘要（内容没变，编译配置不用改）。

评审结论（2026-11-03，D47）：

- **Q4.1 lint 分两段（已定）。** interfaces.md §2.2 的 `Module.validate(ir, options)` 需要 IR，而 lint 在 compile 之前运行。建议 lint 分两段：先跑核心规则，没有 error 时再 compile，然后跑各模块的 validate。compile 只在内存中进行，lint 仍然只读、不联网。代价是核心规则有 error 时，模块规则这一轮不会运行，它们的问题要等核心问题改完后的下一轮才报出，做不到 input-config.md §7.2 说的“一次性输出全部问题”。核心规则出错时（例如节点 id 重复）编不出可靠的 IR，模块规则硬跑只会报出连带的误报，所以接受这个代价，input-config.md §7.2 的说法已改成“分两段汇总输出”。
- **Q4.2 规则的位置（已定）。** 规则按上表分配：只涉及一个模块配置的规则放进该模块的 validate，`RULES` 只放核心配置和跨文件规则。`MODULE_SKILL_CONFLICT` 由 artifactSync 自己对照节点技能检查，lint 就能报出，不用等到 merge。`MODULE_CONFLICT` 是模块之间的冲突，属于脚手架自身的缺陷，只在 build 中检查。加一个测试，保证 `RULES` 与各模块规则的并集同 input-config.md §7.2 的表一一对应。
- **Q4.3 改 `plugin.id`、`metaRoot` 时怎么放行（已定）。**

  为什么要拦：插件在每个项目里把状态和产物放在 `<项目>/<metaRoot>/` 下（D48），state.json 中记着 `pluginId`（README §6.5）。插件用起来以后：改了 `runtime.metaRoot`，新版本就到新目录找状态，旧目录不再被读取；改了 `plugin.id`，state.json 中的 `pluginId` 对不上，运行框架拒绝读写。看板上已有的 Feature 都会“消失”：文件还在，但插件不再认它们，运行框架也不会自动搬迁。所以 lint 把这两个值与 build-manifest 中上次 build 记录的值比较，不一致时报 `PLUGIN_ID_CHANGED`、`LAYOUT_CHANGED`（error），build 和 doctor 不会继续。

  为什么要能放行：插件还没发布、开发中想换个 ID，或者开发者明确接受旧项目需要人工迁移时，要有一个“我知道后果，继续”的办法。两种做法的区别：

  | | 参数 `--allow-id-change`、`--allow-layout-change` | 删掉 `runtime/build-manifest.json` 再 build（demo 的做法） |
  |---|---|---|
  | 怎么用 | `autobiz-plugin doctor --allow-id-change` | 手动删文件，再执行 doctor |
  | 放行范围 | 只放行这一项检查，其他规则照常 | 所有依赖上次构建记录的检查都失效 |
  | 状态维护片段 | doctor 仍能从记录中找到上次写过片段的技能，删掉不再绑定节点的技能里的片段 | 记录没了：同一次修改中删掉或改了 id 的节点，旧技能里的片段删不掉，要手工处理 |
  | 漂移检查 | 仍能判断托管文件（`runtime/*.py` 等）是否被手改 | 没有基准，分不清托管文件是被手改过还是旧版本：要么误报漂移，要么直接覆盖 |
  | 留痕 | 命令行上写明放行了哪一项 | 看不出是有意修改还是误删 |

  用参数，只加在 `build` 和 `doctor` 上，因为只有它们会更新 build-manifest：带参数执行一次后，manifest 记下新的值，之后 lint 不再报错。lint 不需要这两个参数，报错时在 `hint` 中提示“确认要改时执行 `autobiz-plugin doctor --allow-id-change`”。放行时仍输出一条 warning，说明已有项目中的状态需要人工处理。例如发布前把 ID 从 `doc-review` 改成 `doc-review-kanban`：

  ```text
  $ autobiz-plugin lint
  error PLUGIN_ID_CHANGED  plugin.scaffold.json /plugin/id
        plugin.id 从 doc-review 改成了 doc-review-kanban，用过旧 ID 的项目会找不到状态
        hint：确认要改时执行 autobiz-plugin doctor --allow-id-change
  $ autobiz-plugin doctor --allow-id-change
  warning PLUGIN_ID_CHANGED  plugin.scaffold.json /plugin/id
        已按新 ID 重新生成；已有项目的 .autobizdevops/state.json 记录的仍是旧 ID，会被拒绝读写，需要人工处理
  ```
- **Q4.4 `PLUGIN_ID_RESERVED` 永远报不出来（已定）。** `plugin-scaffold.schema.json` 已经用 `"not": {"enum": [...]}` 排除了保留名，保留名在 load 中就报成 `INPUT_SCHEMA`，lint 的这条规则走不到。demo 的校验器对这种写法给出的提示是“features 是保留名，不能使用”，已经足够清楚；而且写在 Schema 里，IDE 在编辑时就能标红。保留 Schema 中的约束，已从 input-config.md §7.2 删掉 `PLUGIN_ID_RESERVED`。D48 去掉 isolated 布局后，`plugin.id` 不再是元数据目录名，Schema 中的保留名限制也一并去掉了。
- **Q4.5 知识目录不做重名检查（已定）。** 知识目录默认是 `sys`；由 DevClaw 自己维护知识时，路径由 DevClaw 提供，不会出现知识目录与 `runtime/` 等插件目录重名的情况，所以不做重名检查。knowledge 的 `PATH_UNSAFE` 原本要查的绝对路径、`..`、`\`、`:` 已由 Schema 覆盖，从规则中去掉：input-config.md §7.2 的 `PATH_UNSAFE` 只检查产物路径。`knowledge.root` 现在仍是用户可写的字段，是否去掉、固定为 `sys`，以及 DevClaw 怎样把路径传给插件（目前只有调试用的 `--knowledge-path`，生成的宿主命令不带它），在单元 9 的知识模块中讨论。
- **Q4.6 `--strict` 会让带有意 warning 的插件永远通不过（已定）。** 三个示例 build 之后，`SKILL_MISSING` 就不会再报，但 fullstack 仍会留下有意为之的 `OUTPUT_REDECLARED`（原来还有 `LAYOUT_LEGACY`，D48 后已去掉）。这类 warning 不需要改，加 `--strict` 后就永远是 error。D41 之后已经没有 CI 运行 `check --strict`，`--strict` 只作为手动选项，`package` 不使用它，只把 `TODO_PLACEHOLDER` 升为 error（input-config.md §7.3 原本就是这样规定的）。本文 §13 原来写成了 `check --strict`，一并改正。

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
    stage: str                      # "Biz" | "Dev" | "Ops"；需要 biz/dev/ops 分组键时用 stage.lower()
    seq: int
    order: int                      # 按 seq 排列后的位置 (i + 1) * 10
    skill: str
    description: str                # 新增：SKILL.md 的 description；缺省或仍是 [TODO] 时按 input-config.md §6 推导
    terminal: bool                  # 新增：终态节点
    outputs: tuple[OutputRef, ...]
    inputs: tuple[OutputRef, ...] = ()      # v1 恒为空（D32）
    validate: str | None = None             # v1 恒为 None（D32）

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

    def node(self, node_id: str) -> NodeIR
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
| 新增字段 | — | `description`、`terminal` | 见下表 |
| `stages` | “按首次出现的顺序” | 固定 Biz → Dev → Ops | D32 |

新增字段与方法的取舍（2026-11-03 评审时修订，原稿还多出 4 个字段和 2 个方法）：

| 字段或方法 | 谁用 | 结论 |
|---|---|---|
| `description` | board 模块生成 `board.json` 的节点描述（D33）。描述要读 SKILL.md 的 frontmatter，放进 IR 后由 compile 统一读一次，模块不用自己读技能文件 | 保留 |
| `terminal` | `flow.json` 节点的 `terminal` 字段；它还决定节点的 checkpoint 只有 `archived`、状态维护片段只有完成一行、`nextAction` 多一项 `archived`。interfaces.md §2.2 原来的 `NodeIR` 没有它，编不出 `flow.json` | 保留 |
| `group` | `board.json`、`session.json` 按 biz/dev/ops 分组 | 去掉：就是 `stage` 的小写，用 `stage.lower()` |
| `skill_dir` | `flow.json` 的 `skillDir`；状态维护片段写进哪个 SKILL.md | 去掉：框架生成 `flow.json` 时和技能同步时各自调用 `find_skill_dir`。`flow.json` 仍要写 `skillDir`：运行框架加载时按它检查 SKILL.md 是否存在（output-spec.md §5.2），而技能在分组目录下时（例如全栈版的 `skills/autodev/autodev-code/`）它不等于 `skills/<skill>` |
| `pointer` | 模块报错时定位到 workflow.json 中的节点 | 去掉：§4 的模块规则报错都指向模块自己的配置文件，没有指向 workflow.json 节点的 |
| `workflow_digest` | `flow.json` 的 `source` | 去掉：框架从 `Normalized.inputs.digests` 读取 |
| `next_node()` | board 模块推导 `nextAction.done` | 去掉：v1 是线性流程，按 `nodes` 的顺序取下一项即可 |
| `node_by_skill()` | `MODULE_SKILL_CONFLICT` | 去掉：直接与 `{n.skill for n in ir.nodes}` 比较 |

核对结果（2026-11-03）：用三个示例核对 IR 各字段与编译配置的对应关系，13 个节点全部一致：

- `flow.json` 节点的 `id`、`name`、`stage`、`skill`、`skillDir`、`seq`、`order`、`terminal`、`checkpoints`、`outputs` 除 `skillDir` 外都能直接由 `NodeIR` 给出，`skillDir` 由框架查找技能目录得到（单元 2 已逐项比对）；`stages` 为写了节点的分组，lite 是 `["Biz", "Dev"]`，minimal 是 `["Biz"]`；`checkpoints.initial` 为链的第一项；
- `checkpoints.labels` 为 `{name}进行中`、`{name}完成`，`archived` 原来取自 `board.display.stateLabels.archived`，按 Q5.3 改为终态节点的 id；
- `board.json` 中节点的 `description`：示例里的技能都是空白 SKILL.md（`description` 为 TODO 占位），全部按 `{name}；产物：{输出路径以“、”连接}` 推导，与示例一致；
- `board.json` 中节点的 `nextAction`：按 `nodes` 的顺序取下一节点，按 input-config.md §6 的规则推导，与示例一致，包括没有下一节点时的空 `slashSkill` 和 fullstack 终态节点的 `archived`；
- `checkpoints_from`：lite 的 `allowedFrom: "plan:done"` 得到 `plan_done → code_done` 三项，fullstack 的再剔除 `excludeCheckpoints` 后得到 5 项（含 `archived`），都与示例的 `artifact-sync.json` 一致。

评审结论（2026-11-03，D49）：

- **Q5.1 采用上表的修改（已定）。** 按修订后的取舍，`NodeIR` 只新增 `description`、`terminal`，`PluginIR` 不新增字段和方法；interfaces.md §2.2 已按本节改写。上面的核对说明这些字段够用：编译配置和看板文案需要的信息都能从 IR 取到，例外只有 `skillDir`（由框架查找）和 Q5.3 的 `archived` 标签。
- **Q5.2 技能描述改了，lint 发现不了（已定）。** 节点描述取自 SKILL.md 的 `description`（D33），会编译进 `runtime/config/board.json`。但 `BUILD_STALE` 只比较核心配置的摘要，开发者改了 description、没有重新生成时 lint 不报；到了 check 重放 build 才发现 board.json 不同，报的是 `DRIFT_GENERATED`（“生成文件被手改”），提示与实际原因不符。build-manifest 的 `inputs` 同时记录各节点技能 description 的摘要（例如键为 `skills/autodev-plan/SKILL.md#description`），让 `BUILD_STALE` 覆盖这种情况。已写入 output-spec.md §8 和 input-config.md §7.1、§7.2；三个示例的 build-manifest 已补上这些键（共 13 项），取值为空白 SKILL.md 中 TODO 占位的摘要。
- **Q5.3 `archived` 标签取终态节点的 id（已定，D49）。** `flow.json` 由框架生成（§7），其中 `checkpoints.labels.archived` 原来取自看板模块的 `board.display.stateLabels.archived`，框架要为此读取看板配置。用户默认不会填写这个标签，改为直接取终态节点的 id（fullstack 示例为 `archive`），不再依赖看板配置，IR 也不用为它增加字段。看板上终态节点的状态名仍取 `stateLabels.archived`（`board.json`），两者互不影响。

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
    entry: str                      # "module:BoardModule"
    core: bool                      # board、session 为 true：恒启用，不能 disable

@dataclass(frozen=True)
class ModuleContext:
    root: Path                      # 插件目录，只读（例如检查 customSubagentFiles 是否存在）
    package_dir: Path               # 模块包目录
    runtime_dir: Path               # 仓库根目录的 runtime/（Q6.5）
    core_version: str
    enabled: frozenset[str]         # 启用的模块；session 据此决定会话入口是否带知识目录参数（D53）

class Module(Protocol):
    spec: ModuleSpec
    def validate(self, ir: PluginIR, options: dict, ctx: ModuleContext) -> list[Issue]
        """语义校验，只读、无副作用。options 已按 Schema 补全。"""
    def contribute(self, ir: PluginIR, options: dict, ctx: ModuleContext) -> Contribution
        """纯函数：相同输入必须得到相同输出（漂移检测依赖这一点）。"""

def discover() -> dict[str, ModuleSpec]          # 读 scaffold/modules/*/module.json
def instantiate(spec: ModuleSpec) -> Module
def enabled_modules(normalized: Normalized) -> dict[str, Module]   # 按 MODULE_KEYS 顺序

# build/contribute.py
@dataclass(frozen=True)
class FileSpec:
    dst: str                        # 插件内相对路径
    ownership: str                  # "managed" | "module" | "generated" | "seeded"
    src: str | None = None          # "files/…" 相对模块包；"runtime/…" 相对仓库根目录的 runtime/
    content: str | bytes | None = None
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

@dataclass
class Merged:
    files: dict[str, tuple[str, FileSpec]]          # dst → (来源 id, 文件)
    entries: dict
    manifests: dict[str, dict]                      # 模块 id → 附加字段
    runtime_config: dict[str, dict]
    inspect_commands: dict[str, CommandSpec]
    knowledge_assembly: dict | None
    skills: dict[str, str]                          # 技能名 → 模块 id

def contribute_all(ir, normalized, modules, ctx_for) -> dict[str, Contribution]
    # 键为 "framework"（§7）与各模块 id
def merge(contribs: dict[str, Contribution]) -> tuple[Merged, list[Issue]]
    # 合并规则见 interfaces.md §2.3：同一个键或文件路径有两个来源即报 MODULE_CONFLICT，保留贡献顺序
```

核对结果（2026-11-03）：

- 按 output-spec.md §3.2 为 board、session、knowledge 写出各自的 `CommandSpec`（脚本加参数，或固定值），按 board → session → knowledge 的贡献顺序逐个平台展开：三个示例共 99 条宿主命令（3 个示例 × 3 个平台）与示例逐字一致（D53 之后，lite、fullstack 的会话入口和 `deploy_units` 命令末尾多了两个知识目录参数，见 §9 Q9.3、Q9.4），包括解释器（darwin、linux 为 `python3`，win32 为 `python`）、`-X utf8`、引号规则，以及会话入口参数中的 `--platform {platform}`；
- `board_core/modules.json`：`modules.<id>` 为 `{enabled, version}` 加上模块的 `manifest`（knowledge 为 `{assembler, source}`，artifactSync 为 `{skill}`），未启用的模块为 `{"enabled": false}`；顶层的 `knowledge_config` 来自 board，`artifact_sync` 来自 artifactSync，键的顺序就是贡献顺序。三个示例都对得上。

评审结论（2026-11-03，D50）：

- **Q6.1（已定）** 删除 `Module.defaults()`：它与 D27（常量默认值只写在 Schema 的 `default` 中）冲突。模块配置统一由 normalize 按 Schema 补全后传入。
- **Q6.2（已定）** `module.json` 去掉 `config.pointer`（目前都是 `""`，配置总是整个文件）；`config.file` 与 `id` 相同，也去掉；新增 `schema`、`core` 两个字段。
- **Q6.3（已定）** `CommandSpec` 删除 `runtime_owned`：D31 去掉运行期回写之后，这个字段已经没有用处。新增 `args` 中的 `{platform}`，供 `session_collector_context_inject` 的 `--platform <platform>` 使用。
- **Q6.4 board、session 算不算模块，现在两处说法矛盾（已定）。** README §3.1 把它们放在 `scaffold/modules/board|session/`，interfaces.md §2.3 又规定 `runtime_config` 中的 `board`、`session`“由核心生成，模块不得占用”。两者实现同一个 Module 协议并标 `core: true`；§2.3 中的保留名只约束非核心模块。各自的贡献见 §9。
- **Q6.5 运行期代码只放一处（已定）。** README §3.1 同时把 adapters 模板写在 `scaffold/modules/board/` 和根目录的 `runtime/` 下。运行期代码统一放在根目录 `runtime/`：adapters、session 都要 import `runtime/common/`，放在一起才能整体测试；board、session 的 `FileSpec.src` 写成 `runtime/…`。knowledge 是可选模块，版本独立，仍放在自己的 `files/` 下。
- **Q6.6 模块配置的 Schema 只保留一份（已定）。** interfaces.md §2.1 让模块包带 `options.schema.json`，再“发布为” `schemas/modules/<file>.schema.json`，这样就有两份。只保留 `schemas/modules/*.schema.json`，`module.json` 的 `schema` 字段指向它，模块包中不再有 `options.schema.json`。
- **Q6.7（已定）** 新增 `FileSpec.replaceable`，用来表达“内置知识组装脚本可以被插件替换”（README §4）。这样 emit 不用写死这个文件的路径。
- **Q6.8 宿主命令按贡献顺序排列（已定）。** §7 原来写的是“键按 output-spec.md §3.2 表格的顺序输出，模块新增的键排在后面”，要维护一份键的列表。核对发现示例中的顺序就是 board → session → knowledge 的贡献顺序（模块内按声明顺序），所以合并时直接保留贡献顺序，不维护列表。
- **Q6.9 宿主命令冲突的判断简化（已定）。** interfaces.md §2.3 规定模块“不能覆盖 output-spec.md §3.2 中标为必有的键”。按 Q6.4，必有的键都由 board、session 贡献，所以规则可以简化为：同一个键有两个来源就报 `MODULE_CONFLICT`，不用另外维护“必有”列表。`files` 的 `dst`、`entries` 的键、`runtime_config` 的文件名同样按“有两个来源即冲突”判断，`apiVersion`、`modules`、`boardEvents` 这三个由核心写入的顶层键仍不允许模块占用。
- **Q6.10 v1 去掉 `requiresCore`（已定）。** 四个模块都随脚手架一起发布，版本不会与运行框架对不上，v1 也不支持第三方模块。保留 `requires_core` 就要在 `instantiate` 中实现 semver 范围比较（标准库没有），却没有任何情况会用到。v1 从 `module.json` 中去掉 `requiresCore`，同时删掉 interfaces.md §5 中“`requiresCore` 不满足时拒绝启用”。

## 7. 框架贡献与技能同步

不属于任何模块的输出由 `framework` 产出，在 merge 中与模块贡献同等对待，这样框架文件和模块文件重名时也能统一报 `MODULE_CONFLICT`。

| 输出 | 归属 | 规格 |
|---|---|---|
| `plugin.json` | generated | output-spec.md §2.1 |
| `runtime/config/runtime.json` | generated | output-spec.md §5.1 |
| `runtime/config/flow.json` | generated | output-spec.md §5.2。`skillDir` 由 `find_skill_dir` 查找；`source` 取 `Normalized.inputs.digests`；`checkpoints.labels.archived` 取终态节点的 id（D49），不读看板配置 |
| `runtime/workflow/update_state.py` | managed | interfaces.md §4.2 |
| `runtime/common/query.py`、`engine.py` | managed | interfaces.md §4.6 |
| `runtime/adapters/board_events.py` | managed | interfaces.md §3.5；写入口共用，所以归框架（Q7.2） |
| `runtime/` 各级 `__init__.py` | managed | |
| `.scaffold/**/*.schema.json` | managed | 供 IDE 补全；拷贝仓库 `schemas/` 下 6 个输入配置的 Schema，显式列出，不含 `schemas/host/`（Q7.4、Q11.3） |

`board_core/` 的两个文件需要所有贡献合并后才能生成，所以单独渲染：

```python
# build/framework.py
def framework_contribution(ir: PluginIR, normalized: Normalized, ctx: ModuleContext) -> Contribution
def render_board_core(ir: PluginIR, board_options: dict, merged: Merged,
                      modules: dict[str, Module]) -> dict[str, bytes]
    # board_core/board_config.json：按 board.target.platforms 逐个平台展开 merged.inspect_commands
    #   命令为 {py} "${pluginPath}/<script>" <args>；{py} 为 target.python.posix（win32 用 .win32）加 " -X utf8"（D40）
    #   单值占位符加双引号（D2）；键按贡献顺序排列（Q6.8）
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

核对结果（2026-11-03）：

- `plugin.json`：取入口文件 `plugin` 段中声明了的字段，按 `name`、`version`、`description`、`author`、`homepage`、`repository`、`license`、`keywords`、`skills`、`mcpServers`、`hooks` 的顺序输出，`skills` 固定为 `./skills/`，不输出 `id`。三个示例逐字一致；
- `runtime.json`、`flow.json` 已在单元 3、2、5 中核对，`board_core/` 的两个文件已在单元 6 中核对；
- 技能同步：三个示例的技能都是新生成的空白 SKILL.md，已在单元 2 中核对。另外用 lite、全栈版两个参考仓库中的 11 个节点技能检查了已有技能的情况，见 Q7.3。

评审结论（2026-11-03，D51）：

- **Q7.1 不再处理 `agents/openai.yaml`（已定）。** 这是 Codex 技能的展示信息。D40 已经不再生成 Codex 清单，output-spec.md 中它的规格（原 §6.2）也已删除，但 README §2.3、§4，output-spec.md §1 的目录，check 规则 `OPENAI_YAML`，以及插件开发技能第 5 步仍在引用它。两个参考仓库中，只有全栈版的回滚技能 `autobizdevops-rollback`（不绑定节点）有这个文件，11 个节点技能都没有。脚手架不再生成、也不检查 `openai.yaml`：已删掉 `OPENAI_YAML` 规则和上述引用，已有的 `openai.yaml` 按开发者资源原样交付。
- **Q7.2 `board_events.py` 归框架（已定）。** 它被 `update_state.py`（框架）和 `init_workspace.py`、`init_feature.py`（board）共同使用，归框架，与 board 模块的 adapters 分开。
- **Q7.3 已有技能正文中的旧状态命令（已定）。** 两个参考仓库的 11 个节点技能，正文中都写着自己的状态命令，build 插入状态维护片段后会出现两套：
  - lite 的技能在正文中有一节“技能状态维护”或“更新状态”，命令指向 `hooks/update_state.py`。新目录结构中这个文件已不存在，模型照着执行就会失败；
  - 全栈版的技能把 `hooks/update_checkpoint.py` 写在操作步骤中，并且放在 `stage_gate.py validate` 等前置步骤之后。只删掉这一行而不说明，就丢了“先校验、再完成”的顺序。

  正文归开发者所有，build 不自动删除，由 `LEGACY_ENTRY_REF` 逐行报出，开发者（或插件开发技能）按提示修改。检查只做一件事：跳过 frontmatter 和托管片段，逐行查找下面的字符串，命中一行报一条。

  | 检查哪些技能 | 查找的字符串 | 原因 |
  |---|---|---|
  | 节点技能 | `update_state.py`、`update_checkpoint.py`、`route_checkpoint.py` | 节点状态只由开头的状态维护片段维护，正文不应再写状态命令 |
  | 所有技能 | `hooks/update_state.py`、`hooks/update_checkpoint.py`、`hooks/route_checkpoint.py`、`hooks/skip_node.py`、`hooks/init_workspace.py`、`${pluginPath}/inspect_state.py` | 旧入口路径，新目录结构中已不存在 |

  不绑定节点的技能（例如回滚技能）可能确实需要调用 `runtime/workflow/update_state.py --reopen`，所以它们只查旧路径。不区分“整节”还是“写在步骤中”，也不尝试理解上下文，只报行号和所在小节，提示统一写成：“状态由开头的状态维护片段维护，删掉这一行；整节只剩状态命令时连同小节标题一起删；这一行前面有校验等步骤时，改写成‘执行完成命令之前先……’”。级别为 error：`check` 报出、`package` 拒绝打包，`add skill --from` 导入时也报。例如：

  ```text
  error LEGACY_ENTRY_REF  skills/autodev/autodev-plan/SKILL.md
        第 46 行（小节“生成、回检与发布”）：python -X utf8 "${pluginPath}/hooks/update_checkpoint.py" --checkpoint plan_done
        hint：状态由开头的状态维护片段维护，删掉这一行；……
  ```

  用原型在两个参考仓库上试过：11 个节点技能共报出 20 行（lite 8 行，全栈版 12 行），全部是旧状态命令；不绑定节点的技能报出 4 行，在全栈版分组目录自己的 `SKILL.md` 和已经不绑定节点的 `autodev-detail-design` 中，也都是旧路径；三个示例生成的空白 SKILL.md 没有误报。行号写在 `message` 中，`pointer` 留空（它只用于 JSON 文件）。原设计中“旧版 `scaffold:begin state` 片段原地替换”的迁移规则，在两个参考仓库中都用不到，只对 demo 生成过的插件有用，保留即可。
- **Q7.4 `.scaffold/` 少了一个 Schema（已定）。** `.scaffold/` 是 build 在插件目录里放的一份输入配置 Schema，作用只有一个：让开发者写核心配置时，IDE 能补全和标红。插件目录中的核心配置用相对路径引用它，例如 `workflow.json` 写 `"$schema": "./.scaffold/workflow.schema.json"`，`modules/board.json` 写 `"$schema": "../.scaffold/modules/board.schema.json"`（input-config.md §2.1、§4）。插件目录里通常没有脚手架仓库的 `schemas/`，所以要拷贝一份进来；它不随包发布（output-spec.md §1）。examples 下没有这个目录，是因为示例就在脚手架仓库里，核心配置直接写 `"$schema": "../../schemas/…"` 引用仓库的 `schemas/`；而且 examples/README.md 约定 `output/` 不收录内容固定、与输入无关的文件，`.scaffold/` 就是这类文件。

  问题在于 output-spec.md §1 的目录中，`.scaffold/modules/` 只列了 board、session、knowledge 三个 Schema，缺少 `artifactSync.schema.json`，而 input-config.md §4.5 的示例写的正是 `"$schema": "../.scaffold/modules/artifactSync.schema.json"`。`.scaffold/` 拷贝仓库 `schemas/` 下的全部 Schema，output-spec.md §1 已补上。单元 11 起改为显式列出这 6 个输入配置的 Schema（Q11.3）。

## 8. 写盘与编排

```python
# build/emit.py
@dataclass(frozen=True)
class PlannedFile:
    path: str
    ownership: str
    data: bytes
    source: str                     # 来源：framework、模块 id、skills
    replaceable: bool = False
    regions: dict[str, str] | None = None     # SKILL.md 的片段摘要，写进 build-manifest

class WritePlan:
    files: dict[str, PlannedFile]
    def add(self, planned: PlannedFile) -> None

def plan_files(merged: Merged, skill_files: list[FileSpec], board_core: dict[str, bytes],
               options: dict[str, dict], ir: PluginIR, root: Path, previous: dict | None) -> WritePlan
    # 读取 src、渲染模板、序列化 runtime_config；已存在的 seeded 文件不进计划（SKILL.md 由 plan_skills 处理）
    # previous 中记录、这次没有任何贡献的 module/generated 文件不删除，在 manifest 中标为 inactive（Q8.1）
def check_drift(plan: WritePlan, root: Path, previous: dict | None, *, force: bool) -> list[Issue]
    # managed、module 文件：当前内容既不等于记录也不等于新内容 → DRIFT_MANAGED
    # replaceable 的文件与记录不符时视为插件的替换：保留，不报
def apply(plan: WritePlan, root: Path) -> list[str]    # 只写内容有变化的文件，逐个 atomic_write

# build/manifest.py
MANIFEST = "runtime/build-manifest.json"
def read_manifest(root: Path) -> dict | None
def make_manifest(ir: PluginIR, normalized: Normalized, plan: WritePlan,
                  modules: dict[str, Module]) -> dict  # output-spec.md §8；files 按路径排序，不记录构建时间
def stale_inputs(inputs: Inputs, descriptions: dict[str, str], previous: dict | None) -> list[str]
    # 摘要变化的核心配置和节点技能 description（键为 <SKILL.md 路径>#description，Q5.2）→ BUILD_STALE

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

核对结果（2026-11-03）：三个示例的 build-manifest 与 output-spec.md §8 的结构一致：

- 顶层依次为 `schema`、`scaffoldVersion`、`coreVersion`、`pluginId`、`metaRoot`、`modules`、`inputs`、`files`；`modules` 只列启用的模块（minimal 只有 board、session），而 `board_core/modules.json` 四个模块都列出；
- `files` 不记录 build-manifest 自己；节点技能的 SKILL.md（seeded）只记 `regions.state`，其余文件记 `sha256`；minimal 记了 24 个文件，lite 37 个，fullstack 40 个；
- 与本文不一致的有两处，见 Q8.4、Q8.5。

评审结论（2026-11-03，D52）：

- **Q8.1 模块关闭后，文件保留、机制失效（已定）。** build 不删除关闭的模块以前生成的文件（`runtime/knowledge/*`、`skills/autobizdevops-artifact-sync/**`），但要保证它们不再起作用。逐个入口检查：

  | 入口 | 模块关闭后 | 是否已失效 |
  |---|---|---|
  | 宿主命令 `knowledge_path`、`deploy_units`、`pull_knowledge` | 不生成（D1） | 是 |
  | `board_core/modules.json` 的 `modules.<id>` | `{"enabled": false}` | 是 |
  | 看板入口 `artifact_sync` | 不生成 | 是 |
  | 知识组装脚本 | `session.json` 的 `knowledgeAssembly` 为 `null`，默认会话入口不再执行它 | 是 |
  | 产物同步技能 `skills/autobizdevops-artifact-sync/` | 仍在 `skills/` 下。`plugin.json` 的 `skills` 指向整个 `skills/` 目录，宿主照样加载这个技能，用户可以手动发起 `/autobizdevops-artifact-sync`；`package` 也会把它和 `runtime/knowledge/*` 打进包里 | 否 |

  所以只靠“不生成入口”还不够，还要处理留下的文件：
  1. build-manifest 继续记录这些文件，标上 `"inactive": true`（归属和摘要不变），不再更新它们；重新启用模块时去掉标记，照常更新；
  2. `package` 不打包标了 `inactive` 的文件，发布出去的插件里就没有这个技能和这些脚本；
  3. lint 对这些文件报 warning（新增 `MODULE_INACTIVE_FILES`），列出文件并说明“模块已关闭，这些文件不再生效、不会打包，可以删除”；
  4. 被插件替换过的内置组装脚本也按这个办法处理。
- **Q8.2 “事务性”的范围（已定）。** interfaces.md §1.2 要求“任何 error 都不会导致只写了一半”。按本节的顺序，校验类 error 都在写盘之前报出；写到一半发生 IO 错误则无法回滚。建议接受这一点：文件逐个原子替换，重跑 build 即可恢复，不另做临时目录整体替换。 写盘顺序上，build-manifest 最后写：中途失败时，已写的文件与新内容相同，旧 manifest 中的记录仍然有效，重跑 build 时漂移检查会认出“当前内容等于新内容”，不会误报；反过来先写 manifest，中途失败后没写到的文件既不等于新记录、也不等于新内容，会被误报为手改。
- **Q8.3 不做通用的模板渲染（已定）。** 原稿让 `FileSpec` 带 `render`，用 `{{ ir / options }}` 渲染模块包中的文件。目前唯一需要替换内容的地方，是产物同步技能的名字可以配置（`artifactSync.skillName`），它的 SKILL.md 中 `name` 要随之改变。去掉 `render` 和 `{{ }}` 语法：需要替换内容的模块在 `contribute` 中自己读源文件、替换后通过 `FileSpec.content` 给出，emit 只负责写字节。
- **Q8.4 `files` 的排列顺序（已定）。** 顺序不影响功能：读取 build-manifest 时都按路径查找。它只关系到“同样的输入构建出同样的文件”（output-spec.md §8）：顺序不固定，每次 build 后 manifest 的字节就可能不同，金样比对和“内容没变就不写”都会受影响。所以示例的顺序本身没有问题，要做的只是把它写成一条明确的规则。示例中的顺序是：先按 output-spec.md §1 目录树的顺序列出拷贝的文件（`runtime/workflow/`、`runtime/adapters/`、`runtime/session/`、`runtime/common/`、`runtime/knowledge/`、同步技能、`.scaffold/`），再按路径列出生成的文件和 SKILL.md。保留这个顺序，实现时要内置一份目录顺序表，新增文件时还要决定插在哪里；改为全部按路径排序，只需要排一次序。定为全部按路径排序，三个示例的 build-manifest 已调整键的顺序，内容不变。
- **Q8.5 `runtime/adapters/skip_node.py` 是否生成（已定，D52）。** output-spec.md §1 的目录把它列为托管文件，README §6.8 也写“运行框架保留 `skip_node.py` 入口”；但三个示例的 build-manifest 都没有它。v1 的 `flow.json` 中 `skip` 固定为 `null`，不生成 `skip_node` 宿主命令（D32），这个入口不会被调用。按示例，v1 不生成这个文件：已从 output-spec.md §1 的目录和本文 §9 的 board 文件清单中去掉，interfaces.md §3.3.10、§4.1 中的说明保留为 v2 的预留。

## 9. 四个模块

每个模块的配置字段和默认值见 input-config.md §4，生成内容见 output-spec.md §3、§5、§7。下表是各模块 `validate` 和 `contribute` 的分工：

| 模块 | validate | runtime_config | files | inspect_commands | entries / manifest |
|---|---|---|---|---|---|
| board（core） | `PLACEHOLDER_UNKNOWN`、`FEATURE_DIR_MISSING` | `board.json` | `runtime/adapters/` 下的 `init_workspace.py`、`init_feature.py`、`inspect_state.py`、`inspect_workflow_templates.py`（v1 不生成 `skip_node.py`，D52） | `project_status`、`feature_status`、`create_project`、`create_feature`、`dynamic_workflow`、`plugin_dir_hook`、`dialog_tips`、`system_prompt_inject`（`skip_node` v1 不生成） | `knowledge_config` |
| session（core） | `POLICY_NODE_UNKNOWN`、`SUBAGENT_FILE_MISSING` | `session.json` | `runtime/session/render_session_context.py` | `session_collector_context_inject`；启用知识模块时末尾加 `--knowledge-path`、`--knowledge-path-platform`（Q9.3） | — |
| knowledge | `MODULE_OPTION` | `knowledge.json` | `runtime/knowledge/` 下的 `inspect_deploy_units.py`、`render_collected_session_context.py`（replaceable）、`collect-knowledge.js`；`sync_knowledge.py` 只在声明 `source` 时生成 | `knowledge_path`、`deploy_units`（带两个知识目录参数，Q9.4）；`pull_knowledge` 只在声明 `source` 时生成 | `manifest`：`{assembler, source}`；`knowledge_assembly` |
| artifactSync | `ARTIFACT_REF_UNKNOWN`、`MODULE_OPTION`、`MODULE_SKILL_CONFLICT` | — | `skills/autobizdevops-artifact-sync/**`，其中 `config/artifact-sync.json` 由输入生成 | — | `entries.artifact_sync`（`entry.enabled` 时）；`manifest`：`{skill}`；`skills` |

起点：board、session 以 lite 的 `board_core` 和 demo 的 `assets/runtime/` 为起点；knowledge 以 lite 的 `hooks/` 和全栈版的 `render_collected_session_context.py`、`collect-knowledge.js` 为起点；artifactSync 以全栈版 `9411fc3` 的 `skills/autobizdevops-artifact-sync` 为起点。改造内容见 README §6.3。

核对结果（2026-11-03）：按 input-config.md §4、§6 和 output-spec.md §7 写出四个模块的生成规则，与三个示例逐项比较，全部一致：

- board：`board.json` 的 `template`（`label`、`description` 未配置时取 `plugin.name` 和节点名以“ → ”连接）、`stateLabels`、各节点的 `description` 与 `nextAction`（单元 5 已核对），以及宿主命令中的 `dialog_tips`、`system_prompt_inject`。minimal 没有 `modules/board.json`，这四项文案都按 input-config.md §4.1.2 的推导规则得出，`system_prompt_inject` 中的产物目录为 `.autobizdevops/features`；`knowledge_config` 入口内容固定；
- session：`session.json` 的 `policies`（单元 3 已核对）；`knowledgeAssembly` 在启用知识模块且组装方为 `plugin` 时为 `{"script": "runtime/knowledge/render_collected_session_context.py", "timeoutSec": 30}`，minimal 中为 `null`；
- knowledge：`knowledge.json` 为补全后的模块配置，去掉 `$schema`、加上 `"schema": "autobiz.knowledge.v1"`；lite、fullstack 都声明了 `source`，所以有 `sync_knowledge.py` 和 `pull_knowledge`；
- artifactSync：`config/artifact-sync.json` 的 `stages` 按节点顺序、只登记 `artifacts` 中列出的路径、每个路径只登记到第一个产出它的节点下；`allowedCheckpoints`、`uploadUrl`、`maxFileSizeMiB`、`extraPaths` 与示例一致；`artifact_sync` 看板入口取自 `entry` 和 `skillName`。

评审结论（2026-11-03，D53）：

- **Q9.1 知识组装继续调用 JS 脚本（已定）。** 内置组装脚本保持现状，调用 `collect-knowledge.js`。这个脚本由知识库开发同事提供，脚手架原样拷贝、不改写，也不用 Python 重写。它对 `gray-matter` 的依赖怎么安装（随包带 `node_modules`，还是 build 或 package 时安装）仍是 README §9 第 7 条的遗留问题。
- **Q9.2 模块的版本号（已定）。** `board_core/modules.json` 和 build-manifest 中每个启用的模块都带 `version`（三个示例都是 `1.0.0`）。board、session 的运行期代码在仓库根目录的 `runtime/` 中，和框架一起发布（D50），不可能单独升级。board、session 的版本号直接取 `coreVersion`，`module.json` 中不再单独维护；knowledge、artifactSync 的文件在各自的模块包中，保留自己的版本号，供 doctor 判断哪些模块文件变了（单元 13 去掉了 upgrade，Q13.2）。
- **Q9.3 知识目录固定为 `sys`，DevClaw 维护的目录通过参数传入（已定）。** Schema 中去掉 `knowledge.root`，插件自己的知识目录固定为 `sys/`；编译后的 `knowledge.json` 仍写 `"root": "sys"`，宿主命令 `knowledge_path` 固定为 `${pluginPath}/sys`。为兼容两种知识目录，启用知识模块时，会话入口 `session_collector_context_inject` 的命令末尾带两个参数：

  ```text
  --knowledge-path "${pluginPath}/sys" --knowledge-path-platform "${knowledge-path}"
  ```

  `${knowledge-path}` 是新增的宿主占位符，由 DevClaw 替换为它自己维护的知识目录，不维护时替换为空字符串。`--knowledge-path-platform` 不为空时，知识目录取它；为空时走旧模式，取 `--knowledge-path`，即 `${pluginPath}/sys`。会话入口把选出的目录作为 `knowledgePath` 传给组装脚本。未启用知识模块时命令不带这两个参数，所以 minimal 示例不变；lite、fullstack 示例的会话入口命令已补上。session 模块要知道知识模块是否启用，所以 `ModuleContext` 增加 `enabled`。路径分隔符和其他宿主命令一样统一写 `/`，Windows 上同样可用。
- **Q9.4 `deploy_units` 也带这两个参数（已定）。** `deploy_units`（`inspect_deploy_units.py`）解析知识目录中的清单、列出支持的发布单元，现在只接受 `--knowledge-path`，生成的命令不带参数，始终读 `${pluginPath}/sys`。DevClaw 自己维护知识时，清单在 DevClaw 的目录里，这条命令读到的就不是同一份。`deploy_units` 与会话入口一样带上这两个参数，按同样的规则选目录；output-spec.md §3.2、interfaces.md §3.3.8 和 lite、fullstack 示例的命令已补上。



## 10. CLI 与核心命令

```python
# cli.py
def main(argv: list[str] | None = None) -> int
    # 全局参数 -C <plugin-dir>、--json；子命令见 interfaces.md §1.1
    # 启动时把 stdout、stderr 改为 UTF-8（Q1.6）
    # 退出码：report.failed(strict) → 1；UsageError → 2；其余 → 0（interfaces.md §1.2）

@dataclass
class CommandResult:
    report: Report
    extra: dict = field(default_factory=dict)      # 例如 doctor 的 {"changes": …}
    written: list[str] = field(default_factory=list)

# commands/lint.py
def lint(root: Path, *, strict: bool = False) -> CommandResult
    # load → normalize → lint_core → compile → lint_modules

# commands/doctor.py
@dataclass
class Changes:
    inputs: list[str]                              # 改过的核心配置
    nodes: dict                                    # {"added": [...], "removed": [...], "reordered": bool}
    skills: SkillChanges
    versions: VersionChanges                       # 脚手架、运行框架、模块的版本变化（Q13.2）

def diff(previous_flow: dict | None, previous: dict | None, ir: PluginIR,
         inputs: Inputs) -> tuple[Changes, list[Issue]]          # CHECKPOINT_REMOVED（interfaces.md §1.7）
def doctor(root: Path, *, dry_run: bool = False, force: bool = False, allow=frozenset()) -> CommandResult
    # lint（不报 BUILD_STALE、SCAFFOLD_VERSION_CHANGED）→ diff → build 流水线 → 复查（lint + SKILL_STATE_BLOCK）
    # allow 可含 CORE_MAJOR_CHANGED（--allow-major-upgrade，Q13.2）
    # 没有 build-manifest（从未生成过）时全部节点列为新增；有 build-manifest 但 flow.json 不存在或无法解析时
    # 跳过 diff，报 DOCTOR_BASELINE_MISSING（Q10.2、Q12.9）

# commands/check.py
RESOURCE_RULES: dict[str, Rule]                    # input-config.md §7.3
def check(root: Path, *, strict: bool = False) -> CommandResult
    # lint → RESOURCE_RULES → build(dry_run=True) 重放，与磁盘比较 → DRIFT_GENERATED、DRIFT_MANAGED
    # → 契约测试：lint 和漂移检查都没有 error 时执行 simulate，失败报 CONTRACT_TEST（Q11.4）
```

核对结果（2026-11-03）：

- 命令清单：D41 去掉了 `git-hook install`，D47 把 `--allow-id-change`、`--allow-layout-change` 只放在 `build`、`doctor` 上，interfaces.md §1.1 已同步；`upgrade --to`、`package` 的“重置运行期字段”留到单元 13；
- 用仓库 HEAD 中 fullstack 的 `flow.json` 和 build-manifest 作为“上次构建”，模拟一次 doctor 的比较：只报出 `plugin.scaffold.json` 改过（D48 去掉了 `runtime.layout`），节点、checkpoint 和技能绑定都没有变化，与实际改动一致。interfaces.md §1.7 中“删 `detail_design`、加 `design`”的 `changes` 示例在仓库历史中找不到对应的版本，只能作为格式示例。

评审结论（2026-11-03，D54）：

- **Q10.1 check 总是重放 build（已定）。** README §5 提到 check 的“`--check` 模式重放 build”，interfaces.md §1.1 的 `check` 没有这个参数。check 总是重放，不单设参数，README §5 的说法已改掉。
- **Q10.2 doctor 的比较基线（已定）。** doctor 以 `runtime/config/flow.json` 为比较基线。flow.json 不存在或无法解析时不做比较：报 warning `DOCTOR_BASELINE_MISSING`，说明本次没有影响报告，直接重新生成，重新生成即修复了 flow.json。单元 12 补充：从未生成过（没有 build-manifest）时不报这个 warning，全部节点列为新增（Q12.9）。
- **Q10.3 CLI 不再提供 `build` 命令（已定）。** 现在开发者能用来重新生成插件的命令有 `build` 和 `doctor` 两个，区别只是 doctor 在前后多了影响报告和复查；input-config.md §7.1 也写着“`build` 仍是底层流水线，供 `new` 和 doctor 调用”。两个命令做同一件事，开发者和插件开发技能都要判断该用哪个（interfaces.md §1.6 第 5 步就写成“新建时 `build`，修改时 `doctor`”）。CLI 只保留 `doctor`：第一次生成时没有上次构建的记录，doctor 把全部节点列为新增，效果与 build 相同；`build` 只作为内部流水线的名字，供 `new` 和 doctor 调用。interfaces.md §1.1 已删掉 `build` 一行，§1.4、§1.6 中“执行 build”已改为“执行 doctor”，放行参数只用于 doctor。
- **Q10.4 各命令 `--json` 输出的附加字段（已定）。** interfaces.md §1.3 只定义了通用结构 `{"ok", "issues", "written"}`，§1.7 给 doctor 加了 `changes`。其余命令的附加字段已写入 interfaces.md §1.3：`check` 加 `contract`（契约测试的结果，单元 11）、`simulate` 加 `simulation`（单元 11）、`module list` 加 `modules`（各模块的版本和启用状态）、`package` 加 `package`（生成的 zip 路径）；`lint`、`add`、`module enable`/`disable`、`new` 没有附加字段。

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
    def __init__(self, plugin_root: Path, workspace: Path, platform: str): ...
        # plugin_root 是临时目录中的插件拷贝（Q11.6）
    def interpreter(self) -> str
        # 所选平台在 board.target.python 中配置的解释器，从 board_config.json 中该平台的命令取得（Q11.9）
    def render(self, key: str, values: dict[str, str | list[str]]) -> list[str]
        # 取 board_config.json 中所选平台的命令，先按 POSIX 规则拆分，再逐个参数替换占位符（Q11.1）
        # values 的键是占位符名，例如 "knowledge-path"、"projectDirs..."（值为列表）
    def run(self, key: str, values: dict) -> HostCall
        # 只带参数，不注入会话变量（Q11.7）
    def run_model(self, command: str, values: dict) -> HostCall
        # 执行技能状态维护片段中的命令：开头的 python 换成 interpreter()，替换 ${pluginPath}、${feature}，
        # 注入 PLUGIN_WORKSPACE、PROJECT_DIR、FEATURE_ID、SESSION_ID=simulate（Q11.7、Q11.9）

# shapes.py
def check_shape(key: str, payload: dict) -> list[tuple[str, str]]
    # 用 schemas/host/outputs.schema.json 的 definitions/<key> 校验，复用 lib/jsonschema（Q11.3）

# commands/simulate.py
def simulate(root: Path, *, feature: str = "demo", to: str | None = None, platform: str | None = None,
             keep: bool = False) -> CommandResult
    # 步骤见 interfaces.md §1.5；extra 为 {"simulation": …}（Q11.10）
```

核对结果（2026-11-03）：

- 占位符：三个示例、三个平台的可执行命令中共 234 处占位符，全部符合 D2。按“先拆分、再逐个参数替换”和“先文本替换、再交给 shell 拆分”两种做法比较得到的参数：路径含空格、中文时两者相同；值以 `\` 结尾（例如 `C:\ws\`）时有 3 条命令不同，值中含 `"` 时有 4 条不同。`${knowledge-path}` 为空时两种做法都得到一个空参数（D53）；
- demo_simulate.py 有 5 处按旧设计实现：从 `board_config.json` 的 `workflow.nodes` 取节点（D31 之后没有这一项）；用 `runtime.layout` 推导产物目录（D48 之后没有这个字段）；会话入口键名为 `session_context_inject`（D40 已改）；终态节点只有 `archived` 一个 checkpoint，`start, finish = node["checkpoints"]` 会抛异常；`--skip-validate` 调用 engine 的私有参数 `_skip_validate`，interfaces.md §4.6 的 `engine.transition` 没有这个参数。`demo/rehearse.py` 现在在第 4 步因读取 `runtime.layout` 中止；
- v1 中 `flow.json` 的 `validate` 固定为 `null`，`workflow.json` 也不能写（input-config.md §2.5），simulate 不会执行任何校验命令；
- lite、fullstack 启用了知识模块（`assembler = plugin`，声明了 `source`），示例中都没有 `sys/`，执行 `deploy_units` 会因清单不存在返回 `ok:false`；
- macOS 默认的 PATH 上只有 `python3`，没有 `python`，而状态维护片段固定写 `python -X utf8`（D40）。

评审结论（2026-11-03，D55）：

- **Q11.1 占位符格式不改（已定）。** `${…}` 是 DevClaw 替换用的模板格式，引号规则沿用 D2，interfaces.md §3.2 不变。`Host.render` 按 demo 的办法模拟：先按 POSIX 规则把命令拆成参数，再逐个参数替换；`${projectDirs...}` 展开成多个参数，`${selectedDeployUnits}` 替换为一个参数。上面的核对说明，路径只含空格、中文时，这样得到的参数与交给 shell 拆分的结果相同；simulate 只验证到这一层，不代表 DevClaw 对特殊字符的处理。占位符名含 `-`、`...`，不能作关键字参数，所以 `render` 改为接受 `dict`。
- **Q11.2 check 不起模拟的看板事件服务（已定）。** 推送代码 `board_events.py`、`board_view.py` 都是 managed 文件，被改时 check 报 `DRIFT_MANAGED`；开发者改配置、改技能都影响不到推送规则。推送规则只在脚手架仓库的 `tests/contract/` 中验证（interfaces.md §3.5.3）。simulate 不设 `AUTOBIZ_BOARD_ENDPOINT`，不发送事件。
- **Q11.3 命令输出用 JSON Schema 校验（已定）。**
  - Schema 放在一个文件 `schemas/host/outputs.schema.json` 中，每个命令（包括 `update_state`）一个 `definitions` 项，`WorkflowNode`、`ArtifactDef`、`run` 共用定义：`lib/jsonschema` 的 `$ref` 只支持本文件内的 `#/definitions/<name>`。这份 Schema 同时作为给 DevClaw 的协议文档；
  - 只用 D43 的 18 个关键字，可以为 `null` 的字段用 `type` 数组；不写 `additionalProperties: false`，宿主应忽略不认识的字段；
  - `check_shape` 只校验结构；初始 checkpoint、策略目标节点、节点状态序列这类语义期望由 simulate 的步骤检查；
  - `.scaffold/` 原来拷贝 `schemas/` 下的全部文件（Q7.4），改为显式列出 6 个输入配置的 Schema，`schemas/host/` 不拷进插件。output-spec.md §1、本文 §7 已同步。
- **Q11.4 生成结果过期时只报 warning（已定）。** simulate 不执行 load、lint：按 build-manifest 中 `inputs` 记录的键（包括 `<SKILL.md 路径>#description`）重算摘要，与记录不一致时报 warning `BUILD_STALE`，照常执行，`simulation.stale` 为 `true`。check 中 `BUILD_STALE` 仍是 error；lint 或漂移检查有 error 时，check 不跑契约测试，`contract.ran` 为 `false`：磁盘上的插件已经不对应当前配置，跑出来的失败多半是噪声。input-config.md §7.2 已注明 simulate 中的级别。
- **Q11.5 v1 去掉 `--skip-validate`（已定）。** v1 不执行校验命令，这个参数没有作用；demo 为了实现它绕过命令行入口调用 engine 的私有参数，也不符合“按宿主的方式调用”。等 `validate` 开放（v2）时再加。check 的契约测试与 simulate 走完全相同的流程。interfaces.md §1.1、§1.5，README §5，本文 §10 已同步。
- **Q11.6 在插件的拷贝上执行（已定）。** simulate 先按打包清单（output-spec.md §1）把插件拷到 `<tmp>/plugin`，`${pluginPath}` 指向这份拷贝；`sys/` 存在时一并拷贝（声明了 `source` 时相当于已经执行过 `pull_knowledge`）。DevClaw 运行的是打包后的插件，其中没有核心配置和 `inactive` 文件，在拷贝上执行才能发现脚本误读了这些文件；运行中生成的 `__pycache__/`、collector 首次运行时的 `npm install` 也都落在临时目录，插件目录不被修改。interfaces.md §1.5 的“不访问网络”不包括内置知识组装脚本调用的 collector（`collect-knowledge.js`），已注明。
- **Q11.7 按调用方注入环境变量（已定）。** 脚手架作为独立脚本运行，不在项目会话中，环境里没有 `FEATURE_ID`、`AUTOBIZ_BOARD_ENDPOINT` 这些变量，不需要清理。注入按 interfaces.md §3.4 区分调用方：宿主命令只带参数，不注入会话变量；状态维护片段的命令注入 `PLUGIN_WORKSPACE`、`PROJECT_DIR`、`FEATURE_ID`、`SESSION_ID=simulate`。demo 给所有调用都注入，会掩盖宿主命令依赖环境变量而不是参数的错误。
- **Q11.8 补全执行步骤（已定）。** interfaces.md §1.5 已改写：`create_project`、`create_feature` 各执行两次检查幂等；节点列表取 `project_status` 输出的 `workflow.nodes`，产物目录取 `create_feature` 输出的 `featureDir`；知识目录中没有清单时 `deploy_units` 只报 warning；节点的推进执行技能 SKILL.md 中状态维护片段的命令，只为必需输出写桩内容，终态节点只推进到 `archived`；只读命令执行前后比较临时工作区；`--to` 在执行前对照 `flow.json` 的 checkpoint 链检查。
- **Q11.9 解释器按平台配置（已定）。** 宿主命令照 `board_config.json` 中所选平台的命令执行。状态维护片段固定写 `python`（D40），simulate 执行时把它换成所选平台在 `board.target.python` 中配置的解释器：darwin、linux 取 `posix`（默认 `python3`），win32 取 `win32`（默认 `python`）。这个值从 `board_config.json` 中该平台的命令取得，不读核心配置。解释器在 PATH 上找不到时改用脚手架自己的解释器，报 warning `INTERPRETER_MISSING`：DevClaw 在这台机器上执行同样会失败。
- **Q11.10 输出格式（已定）。** `--json` 的附加字段 `simulation` 与 check 的 `contract` 结构相同，见 interfaces.md §1.5。每个失败的步骤报一条 `CONTRACT_TEST` error：宿主命令的 `file` 为 `board_core/board_config.json`、`pointer` 为 `/inspectCommands/<platform>/<key>`；片段命令的 `file` 为该技能的 `SKILL.md`。

## 12. 配置编辑与向导

`add`、`module`、`new` 修改核心配置（`add skill` 和 `new` 还会导入技能目录），然后执行 doctor，不直接生成插件文件（interfaces.md §1.1）。修改先在内存中完成，与 doctor 的生成结果一起写盘（Q12.4）。

```python
# lib/jsonedit.py：在原文上修改，保留原有键序、缩进和换行（Q12.3）
def insert_item(text: str, pointer: str, index: int, value) -> str   # 往数组中插入一项
def set_member(text: str, pointer: str, key: str, value) -> str      # 对象中增加或替换一个键
def remove_member(text: str, pointer: str, key: str) -> str          # 删除对象中的一个键
    # 只改动涉及的片段，其余字节不变；新内容的写法跟随同级元素（多行还是单行、缩进单位）

# commands/edit.py
@dataclass
class Edit:
    files: dict[str, bytes]                 # 相对插件根的路径 → 修改后的内容，包括导入的技能文件
    issues: list[Issue]                     # 导入技能时发现的内容问题，级别为 warning（Q12.5）

def apply(root: Path, edit: Edit) -> CommandResult
    # 用 edit.files 覆盖读入的内容执行 doctor 流水线；没有 error 时 edit 与生成结果一起写盘，否则什么都不写（Q12.4）

def add_node(root: Path, *, id: str, name: str, skill: str, stage: str, seq: int,
             outputs: list[tuple[str, bool]], terminal: bool = False) -> CommandResult
    # outputs 按命令行上的顺序记录 (路径, 是否可选)（Q12.2）；terminal 见 Q12.6
def add_skill(root: Path, skill: str, *, source: Path | None = None) -> CommandResult
    # 拷贝技能目录，migrate_frontmatter 并把 name 改为 skill；不带 source 时生成空白 SKILL.md（Q12.5）
def module_list(root: Path) -> CommandResult
def module_enable(root: Path, module_id: str, sets: dict[str, str]) -> CommandResult
    # 骨架和 --set 的规则见 Q12.7
def module_disable(root: Path, module_id: str) -> CommandResult   # 只去掉引用；board、session 不能关闭

# wizard.py：问答与写配置分开，便于测试
@dataclass
class Answers:
    plugin: dict
    nodes: list[dict]                       # {id, name, stage, seq, skill, outputs, terminal}
    skills: dict[str, Path | None]          # 技能名 → 导入目录；None 为不提供
    board: dict
    session: dict
    knowledge: dict | None
    artifact_sync: dict | None

class Prompter(Protocol):                   # 终端实现与测试用的脚本化实现
    def ask(self, question: str, *, default=None, choices=None) -> str: ...

def ask(prompter: Prompter, seed: Answers | None = None) -> Answers   # interfaces.md §1.4 的七类问题
def load_answers(data: dict) -> Answers                               # --answers 的 JSON（Q12.8）
def to_configs(answers: Answers) -> dict[str, dict]                   # 只写与默认值不同的部分

# commands/new.py
def new(target: Path, *, template: str = "blank", answers: Answers | None = None,
        yes: bool = False) -> CommandResult
    # template 为 lite、fullstack 时以种子的核心配置为起点（Q12.1），answers 覆盖对应项；
    # 写盘前在内存中 lint，有 error 时交互模式回到对应问题，yes 时报出、不写文件；通过后执行 doctor（Q12.9）
```

核对结果（2026-11-03）：

- 格式：三个示例的 14 份核心配置中，9 份与 `json.dumps(indent=2)` 的输出不同（短数组写在一行）；换成“缩进 2、只含标量的数组写一行”仍有 5 份不同（`{ "path": "PR_BODY.md", "optional": true }`、`{ "assembler": "plugin" }`、`toolCustomConfig` 这类小对象也写在一行）。整份重新输出会改掉开发者手排的格式；
- 两个参考插件的 11 个节点技能正文中都有旧的状态命令（Q7.3），`add skill --from` 导入其中任何一个都会命中 `LEGACY_ENTRY_REF`；
- `workflow.json` 的 Schema 要求至少一个阶段、每个阶段至少一个节点，没有节点的 `workflow.json` 通不过 lint；
- 示例核心配置的 `$schema` 指向脚手架仓库的 `schemas/`（`../../schemas/…`），原样拷进新插件会指错；
- `artifactSync.schema.json` 要求 `artifacts`，`allowedFrom`、`allowedCheckpoints` 必须二选一；fullstack 的 `artifacts` 没有收 `.json` 输出；
- `new` 怎样生成插件，说法不一致：interfaces.md §1.1、§1.4 是执行 doctor，本节原来写的是调用 build。D54 中“第一次生成时 doctor 把全部节点列为新增”与“`flow.json` 不存在时报 `DOCTOR_BASELINE_MISSING`”在第一次生成时互相矛盾。

评审结论（2026-11-03，D56）：

- **Q12.1 新建插件的种子（已定）。** 脚手架安装包带上 `examples/lite/`、`examples/fullstack/` 的核心配置，不带 `output/`。种子文件显式列出：入口文件、`workflow.json`，以及入口文件引用的 `modules/*.json`。拷贝时把 `$schema` 改写为 `./.scaffold/…`（入口文件、`workflow.json`）和 `../.scaffold/modules/…`（模块配置），其余内容和格式不变。安装包怎么组织取决于 Q13.3。
- **Q12.2 增加 `--optional-output`（已定）。** `add node` 增加可以重复的 `--optional-output <path>`，写成 `{path, optional: true}`。它与 `--output` 记到同一个列表中，`outputs` 的顺序就是命令行上的顺序。含 glob 的路径要加引号，避免被 shell 展开，写进参数说明。
- **Q12.3 保留原文格式（已定）。** 不整份重新输出，由 `lib/jsonedit.py` 在原文上插入或替换片段，只需要三种操作：往数组中插入一项、对象中增加或替换一个键、删除一个键。只改动涉及的片段，其余字节不变；新内容的写法跟随同级元素（多行还是单行、缩进单位），换行符沿用原文件（D42）。标准库的 `json` 不给出位置，所以实现一个记录位置的小型 JSON 解析器。
- **Q12.4 编辑命令先在内存中完成（已定）。** 原来先写配置再执行 doctor：doctor 失败时（例如 `DRIFT_MANAGED`）退出码为 1，配置却已经写入，与 interfaces.md §1.2 “退出码 1 表示没有写入任何文件”矛盾。改为在内存中算出修改后的文件，用它们覆盖读入的内容执行 doctor 流水线（`load` 接受覆盖内容），没有 error 时与生成结果一起写盘，有 error 时什么都不写。原来“`seq` 冲突时当场报 `SEQ_DUP`”的特殊处理由完整的 lint 覆盖。managed 文件被手改时，hint 提示先执行 `doctor --force`。
- **Q12.5 导入技能时的内容问题只报 warning（已定）。** `add skill --from`（以及 `new` 按 `skills` 导入）发现的技能内容问题（input-config.md §7.3 的 `LEGACY_ENTRY_REF`、`SKILL_FRONTMATTER` 等）照样导入，报 warning，hint 说明 check 和 package 会报 error；否则两个参考插件的技能都导不进来。frontmatter 的 `name` 与命令给出的技能名不同时改为技能名，并在报告中说明；顶层的 `version`、`author` 迁到 `metadata`（D8）。目标目录已存在，或其他分组下有同名技能（导入后会报 `SKILL_AMBIGUOUS`）时拒绝导入。拷贝时跳过 `__pycache__/`、`*.pyc`、`.DS_Store`。
- **Q12.6 终态节点的入口（已定）。** `add node` 增加 `--terminal`，不能与 `--output`、`--optional-output` 同时使用；`seq` 最大、最多一个等规则由 lint 检查。向导在最后一个节点没有产物时，问它是否为终态节点。
- **Q12.7 `module enable` 的骨架与 `--set`（已定）。**
  - `--set key=value` 的 key 沿 Schema 的 `properties` 用 `.` 逐级指定，value 按 Schema 的类型转换：`string` 原样保留，其余按 JSON 解析。以产物路径或节点 id 为键的映射（`artifacts`、`extraPaths`、`policies.nodes`）不能用 `--set` 指定，要改文件；Schema 中没有的路径报 `USAGE`；
  - `enable knowledge`：骨架只有 `$schema`；
  - `enable artifactSync`：必须用 `--set` 给出 `allowedFrom` 或 `allowedCheckpoints`，否则报 `USAGE`（Schema 要求二选一）。`artifacts` 预填扩展名不是 `.json` 的输出路径（按节点顺序、去重），值为 `[TODO: 简述]`，没有填写的由 `TODO_PLACEHOLDER` 报出（input-config.md §7.3 已写明）；
  - 模块配置文件已存在（以前关闭过）时不重建，只加回引用并应用 `--set`；
  - 向导第 6 类回答“启用”时调用同一套逻辑。
- **Q12.8 `new` 的非交互输入（已定）。** 原来的 `--yes` 没有参数能传入回答，而 interfaces.md §1.6 让技能在建模之前调用 `new --yes`，此时还没有节点，lint 一定失败。`new` 增加 `--answers <file|->`，内容为 `Answers` 的 JSON（interfaces.md §1.4）；`--yes` 只表示不提问，回答取自种子和 `--answers`，缺少必填项报 `USAGE`。插件开发技能第 1 步只确认目录、插件 ID 和插件名，不调用 CLI；第 2 步建模经开发者确认后再调用 `new --yes --answers`。目标目录必须不存在或为空，否则报 `USAGE`。lint 在写盘前完成，有 error 时交互模式回到对应问题，`--yes` 时报出 Issue、不写任何文件。interfaces.md §1.6 和 mods.md §3.2 的流程已同步。
- **Q12.9 第一次生成（已定）。** `new` 写好核心配置后执行 doctor，本节原来写的“调用 build”已改。D54 中的矛盾按有没有 build-manifest 区分：没有 build-manifest 说明从未生成过，doctor 把全部节点列为新增，不报 warning（与 `BUILD_STALE` 的“从未 build 过时不报”一致）；有 build-manifest 但 `flow.json` 不存在或无法解析时，才报 `DOCTOR_BASELINE_MISSING`。interfaces.md §1.7、本文 §10 已同步。

## 13. 打包、升级

```python
# build/versions.py：当前脚手架与 build-manifest 记录的版本比较（Q13.2）
@dataclass
class VersionChanges:
    scaffold: tuple[str, str] | None        # (记录的版本, 当前版本)；没有变化时为 None
    core: tuple[str, str] | None
    modules: dict[str, tuple[str, str]]     # 只列版本有变化的模块；新启用、关闭的模块不在这里

def compare_versions(previous: dict | None, current: dict) -> tuple[VersionChanges, list[Issue]]
    # previous 为 build-manifest，没有时（从未生成过）不比较
    # 任一版本低于记录 → SCAFFOLD_OUTDATED；coreVersion 主版本变化 → CORE_MAJOR_CHANGED；
    # 其余变化 → SCAFFOLD_VERSION_CHANGED（warning）。lint、check、doctor、package 共用

# commands/package.py
def package(root: Path, *, output: Path | None = None) -> CommandResult
    # check（只把 TODO_PLACEHOLDER 升为 error，不用 --strict，Q4.6）→ 按 output-spec.md §1 的打包规则写 zip（Q13.5）
    # 默认输出 dist/<plugin.id>-<plugin.version>.zip，zip 内只有一个顶层目录 <plugin.id>/（Q13.4）
    # extra 为 {"package": {"path": …, "skipped": […]}}

# tools/make_pyz.py：脚手架仓库的发布脚本，自己不进 .pyz（Q13.3）
def make_pyz(output: Path) -> None
    # 用标准库 zipapp 把 scaffold/、runtime/、schemas/ 和 Q12.1 的种子打成 autobiz-plugin.pyz，文件显式列出
```

CLI 不提供 `upgrade`：脚手架更新后，由 doctor 替换 managed、module 文件（Q13.2）。

核对结果（2026-11-03）：

- “重置运行期字段”只出现在 interfaces.md §1.1 的 `package` 一行；
- 提到 upgrade 的有 interfaces.md §1.1、§4.5、§5，README §4，input-config.md §4.4，output-spec.md §7.1 和本文 Q9.2。interfaces.md §5 说“脚手架提供 `migrate`”，§1.1 中没有这个命令；
- `plugin-scaffold.schema.json` 中入口文件的 `scaffoldVersion` 是 `const: 1`，写成 2 时只报一条 `INPUT_SCHEMA`“只能是 1”，看不出是脚手架太旧；
- `plugin.json` 中没有 `id`。lite 的 `plugin.id`（`autodev-planning-kanban`）与 `name`（`AutoBizDevOps-Plugin-Lite`）不同，而 input-config.md §3.3 规定 `id` 是安装目录名，DevClaw 只能从 zip 得知 `id`。README §2.3 中“`plugin.id` 同时作为……元数据目录名”在 D48 之后已经不成立；
- 在 Python 3.9.6 上用标准库 `zipapp` 打出 `.pyz`，`importlib.resources.files()` 能遍历并读取包内的文件；
- output-spec.md §1 的打包清单写的是 `.mcp.json`，但 `plugin.mcpServers`、`plugin.hooks` 可以指向 `./` 下的任意路径。

评审结论（2026-11-03，D57）：

- **Q13.1 删掉“重置运行期字段”（已定）。** D31 之后没有运行期字段（README §6.1）。interfaces.md §1.1 的 `package` 改为“check（只把 `TODO_PLACEHOLDER` 升为 error），然后打包”。
- **Q13.2 不提供 `upgrade`，版本变化由 doctor 处理（已定）。** 与 D54 去掉 `build` 的理由相同：两个命令做同一件事；开发者每次改配置都执行 doctor，单独的 upgrade 也拦不住 doctor 顺手升级。doctor（以及 lint、check、package）把当前脚手架的版本、`coreVersion` 和各模块版本与 build-manifest 中的记录比较：

  | 情况 | 处理 |
  |---|---|
  | 版本相同 | 同现在 |
  | 脚手架更新，`coreVersion` 主版本不变 | doctor 替换 managed、module 文件，漂移检查和“被替换的内置组装脚本保留”照旧；`changes.versions` 列出变化。lint、check 报 warning `SCAFFOLD_VERSION_CHANGED`，提示执行 doctor |
  | `coreVersion` 主版本变化 | 报 error `CORE_MAJOR_CHANGED`，`doctor --allow-major-upgrade` 放行（同 D47 的放行方式） |
  | 脚手架、运行框架或任一模块的版本低于记录 | 报 error `SCAFFOLD_OUTDATED`：doctor 会把运行框架降级，拒绝执行，没有放行参数，提示更新脚手架。入口文件的 `scaffoldVersion`（格式主版本）比脚手架支持的高时，也报这个 code，不再报 `INPUT_SCHEMA` |

  漂移只按“磁盘内容与 build-manifest 的记录不同”判断：磁盘与记录一致、只是与当前脚手架重放的结果不同时，check 报 `SCAFFOLD_VERSION_CHANGED`，不报 `DRIFT_GENERATED`。v1 不提供 `migrate`，interfaces.md §5 改为等入口文件格式升主版本时再定。各处“build 和 upgrade”的说法统一改为 doctor。
- **Q13.3 脚手架发布成一个 zipapp 文件（已定）。** 脚手架只用标准库，用 `tools/make_pyz.py` 打成一个文件 `autobiz-plugin.pyz`，执行方式为 `python3 autobiz-plugin.pyz <命令>`（Windows 上为 `python …` 或 `py -3 …`），文档中的 `autobiz-plugin` 指的就是它。插件开发技能在 `scripts/` 下带同一个 `.pyz`（Q14.2 随之确定）。理由：Windows 上 pip 安装的入口在 `Scripts\` 下，常常不在 PATH 中；内网环境拷贝一个文件即可使用；技能和 CLI 始终是同一个版本。包内的 `runtime/`、模块文件、Schema 和种子用 `importlib.resources` 读取，已在 3.9.6 上验证。缺点是没有直接可用的 `autobiz-plugin` 命令，以后需要时再加包装脚本。
- **Q13.4 zip 的顶层目录（已定，待 DevClaw 确认）。** zip 中只有一个顶层目录 `<plugin.id>/`，插件文件都在它下面，DevClaw 由它得到安装目录名。已记入 README §9，README §2.3 中过时的“元数据目录名”已改掉。
- **Q13.5 打包规则（已定）。** 写入 output-spec.md §1：
  - `plugin.json`、`board_core/`、`runtime/` 只收 build-manifest 记录的文件（标了 `inactive` 的除外）和 build-manifest 本身。这些区域本来就由记录显式列出，`node_modules/`、`__pycache__/` 等其他文件不会进包，没收进的文件列在 `package.skipped` 中；
  - `skills/`、`hooks/`、`agents/` 整个打包，跳过 `__pycache__/`、`*.pyc`、`.DS_Store`、`Thumbs.db`；
  - `plugin.mcpServers`、`plugin.hooks` 引用的文件按实际路径打包，文件不存在时报 error `PLUGIN_REF_MISSING`（lint 规则，check、package 同样报出）；
  - `sys/` 只在启用知识模块、并且没有声明 `source` 时打包；
  - zip 条目按路径排序、时间戳固定、路径用 `/`，同一个插件每次打出的 zip 相同；
  - `--json` 的 `package` 字段为 `{"path", "skipped"}`。
- **Q13.6 Node 依赖仍待定（已定）。** README §9 第 7 条不在本单元决定。在它定下之前，按 Q13.5，package 不执行 `npm install`，也不会带上 `node_modules/`；以后决定随包带上时，由知识模块把它登记进 build-manifest。

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
- **Q14.3 插件开发技能自己的 `agents/openai.yaml`。** D51 之后，生成的插件中的技能不再处理 `openai.yaml`。插件开发技能本身装在开发者的 agent 环境里（可能是 Codex），README §3.1 和 interfaces.md §1.6 的目录中仍列着它自己的 `agents/openai.yaml`，是否保留在本单元决定。

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
