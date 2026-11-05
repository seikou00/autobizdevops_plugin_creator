# 接口定义 v1

本文按调用双方划分，共四组接口：

| § | 调用方 → 被调用方 | 接口 |
|---|---|---|
| 1 | 插件开发者 → 脚手架 | `autobiz-plugin` CLI、初始化向导、插件开发技能 |
| 2 | 脚手架 → 模块；运行框架 → 模块 | 模块契约（构建期 `Module`、运行期知识组装） |
| 3 | DevClaw ↔ 插件 | `inspectCommands` 命令协议（DevClaw → 插件）；看板事件推送（插件 → DevClaw） |
| 4 | 模型 → 插件；运行框架 → 开发者命令；框架入口 → 内部库 | `update_state.py`（技能的状态维护片段调用）、校验命令、知识组装脚本、`query.py` / `engine.py` |

静态文件格式见 [output-spec.md](output-spec.md)，输入配置字段见 [input-config.md](input-config.md)。下文的“宿主”均指 DevClaw；`board.*`、`session.*`、`knowledge.*`、`artifactSync.*` 分别指 `modules/board.json`、`modules/session.json`、`modules/knowledge.json`、`modules/artifactSync.json` 中的字段。

---

## 1. 脚手架 CLI

### 1.1 命令总览

| 命令 | 作用 |
|---|---|
| `autobiz-plugin new <dir> [--answers <file\|->] [--yes]` | 初始化向导：按 §1.4 的七类输入问答，生成入口文件 `plugin.scaffold.json`、`workflow.json`、需要的 `modules/*.json` 和工程目录，随后执行 doctor。`<dir>` 必须不存在或为空；`--answers` 给出回答（§1.4），`--yes` 不提问，此时 `--answers` 必须给出 `plugin` 和 `nodes`。脚手架不带样例种子，没有 `--from` |
| `autobiz-plugin new <dir> --skeleton [--module <id> …]` | 只写出带 `[TODO: …]` 占位的核心配置骨架（入口文件、`workflow.json`、`--module` 选中的模块配置）和 `.scaffold/` Schema，不执行 doctor；开发者填完后执行 `lint` 查看还缺什么，再 `doctor`、`package`（§1.4.1，D63）。不能与 `--answers`、`--yes` 一起使用 |
| `autobiz-plugin add node <id> --name <name> --skill <skill> --stage biz\|dev\|ops --seq <n> [--output <path> …] [--optional-output <path> …] [--terminal]` | 在 `workflow.json` 的 `nodes.<stage>` 中添加节点，按 `seq` 插到组内对应位置，不改其他节点的 `seq`。`--output` 是必需输出，`--optional-output` 是可选输出（写成 `{path, optional: true}`），两者按命令行上的顺序追加到 `outputs`；含 glob 的路径要加引号，避免被 shell 展开。`--terminal` 表示终态节点，不能带输出。写完后执行 doctor（技能不存在时生成空白 `SKILL.md`） |
| `autobiz-plugin add skill <skill> [--from <dir>]` | 导入已有技能资源（正文、模板、脚本、校验器）到 `skills/<skill>/`；不带 `--from` 时创建空白 `SKILL.md`（只有 frontmatter 和状态维护片段，技能已绑定节点时才有片段）。导入时 frontmatter 的 `name` 改为 `<skill>`，顶层 `version`、`author` 迁到 `metadata`；正文中的旧状态命令（`LEGACY_ENTRY_REF`）等技能内容问题报 warning，照样导入，check 和 package 时报 error（input-config.md §7.3）。目标目录已存在，或其他分组下有同名技能时拒绝导入（D56） |
| `autobiz-plugin add skills --from <skills-dir> [--agents <agents-dir>]` | 把 `<skills-dir>` 当作插件的 `skills/` 导入，保留一层分组：一级子目录含 `SKILL.md`、且它的子目录都不含 `SKILL.md` 时是技能，导入到 `skills/<skill>/`；一级子目录下有含 `SKILL.md` 的子目录时是分组，这些子目录是分组下的技能，导入到 `skills/<分组>/<skill>/`（与 build 查找技能的两层一致，input-config.md §7.3）。`<skills-dir>` 自己含 `SKILL.md`、有技能子目录且没有带 `SKILL.md` 的分组子目录时，它本身就是一个分组（例如 `skills/autodev`），按 `skills/<目录名>/<skill>/` 导入。技能以目录名作为技能名，技能目录内部更深层的 `SKILL.md` 是技能自己的资源。其余内容（集合根目录和分组目录自己的 `SKILL.md`、`references/`、`hooks/` 等）是共享资源，按原路径拷到 `skills/` 下：不存在时写入，内容相同时跳过，内容不同时拒绝导入；其中的 `SKILL.md` 同样迁移 frontmatter。上次构建登记为脚手架生成的技能（例如产物同步模块的 `autobizdevops-artifact-sync`）跳过不导入。同名技能在集合中出现两次时拒绝导入。build 生成的空白 `skills/<skill>/SKILL.md` 会被分组下的同名技能替换（删除空白文件）。每个技能沿用 `add skill --from` 的迁移、冲突检查和 warning 规则。整批先在内存中完成导入与一次 doctor，任一 error 均不写文件；成功时 JSON 输出增加 `importedSkills` 技能名数组。`agents/` 不属于技能集合，不会自动查找或创建：给了 `--agents` 时把该目录原样拷到插件的 `agents/`，与技能同批写入；已有同名文件内容相同时跳过，内容不同时拒绝导入 |
| `autobiz-plugin module list` | 列出可用模块与可选能力、版本及启用状态 |
| `autobiz-plugin hook list` / `hook enable <id> …` / `hook disable <id> …` | 插件全局钩子模块 `globalHooks` 的便捷入口：列出全部全局钩子及启用状态（JSON 输出加 `hooks`；不在插件目录中运行时也能列出，启用状态都是 `false`，供新建插件前选择，D65）；启用、关闭即在 `modules/globalHooks.json` 的 `hooks` 中加入或去掉 id，再执行 doctor——模块未启用时先启用（创建文件并在入口文件中引用），`hooks` 去光后关闭模块（只去掉引用）。id 不存在时报用法错误（D62） |
| `autobiz-plugin module enable <id> [--set key=value …]` / `disable <id>` | 启用或关闭 `knowledge`、`artifactSync`（看板能力固定开启，不能用这个命令关闭）。`enable knowledge` / `enable artifactSync` 在 `modules/knowledge.json` / `modules/artifactSync.json` 不存在时创建骨架，并在入口文件中引用；`disable` 只去掉引用，`modules/*.json` 和模块以前生成的文件都保留；这些文件不再生效：宿主命令和看板入口不再生成，build-manifest 中标为 `inactive`，`package` 不打包，lint 报 `MODULE_INACTIVE_FILES`（D52）。已存在时不重建，只加回引用。`--set` 的 key 沿模块 Schema 的属性用 `.` 逐级指定（例如 `assembly.assembler=devclaw`、`source.url=…`），value 按 Schema 的类型转换：字符串原样保留，其余按 JSON 解析；`artifacts`、`extraPaths` 这类以路径为键的映射不能用 `--set` 指定。`enable artifactSync` 必须用 `--set` 给出 `allowedFrom` 或 `allowedCheckpoints`；它会把扩展名不是 `.json` 的输出路径预填进 `artifacts`，简述写成 `[TODO: 简述]`，开发者删掉不需要上传的、补上简述即可（D56） |
| `autobiz-plugin doctor [--dry-run] [--force] [--allow-id-change] [--allow-layout-change] [--allow-major-upgrade]` | 修改核心配置（`workflow.json`、`modules/*.json`、入口文件）或更新脚手架后重新生成插件：lint → 与上次构建比较并列出影响 → build → 复查（§1.7） |
| `autobiz-plugin lint [--strict]` | 只检查核心配置（`workflow.json`、入口文件、`modules/*.json`）的结构和语义规则，以及编译配置是否过期（input-config.md §7.2）。只读、不联网，通常在 1 秒内完成 |
| `autobiz-plugin check [--strict]` | `lint` 加上技能内容、生成文件漂移检查，并运行契约测试，只读（input-config.md §7.3） |
| `autobiz-plugin simulate [--feature demo] [--to <checkpoint>] [--platform <p>] [--keep]` | 把已生成的插件拷到临时目录，按宿主的方式调用一遍（§1.5） |
| `autobiz-plugin package [-o <zip>]` | check（只把 `TODO_PLACEHOLDER` 升为 error），然后按 output-spec.md §1 的打包规则写 zip，默认为 `dist/<plugin.id>-<plugin.version>.zip` |

所有命令都支持 `-C <plugin-dir>`（默认为当前目录）和 `--json`（机器可读输出）。

脚手架以单个文件 `autobiz-plugin.pyz` 发布（标准库 zipapp），执行方式为 `python3 autobiz-plugin.pyz <命令>`，Windows 上为 `python …` 或 `py -3 …`；本文的 `autobiz-plugin` 即指它。插件开发技能在自己的 `scripts/` 下带同一个文件（D57）。

CLI 不提供单独的 `build` 命令：build 是内部流水线的名字，由 doctor 调用，`new` 写好核心配置后执行 doctor；第一次生成时没有 build-manifest，doctor 把全部节点列为新增（D54、D56）。也不提供 `upgrade`：脚手架更新后执行 doctor，由它替换 managed、module 文件并报告版本变化（§1.7，D57）。

`--allow-id-change`、`--allow-layout-change` 只用于 `doctor`：确认要修改 `plugin.id` 或 `runtime.metaRoot` 时，放行 `PLUGIN_ID_CHANGED` 或 `LAYOUT_CHANGED`，本次生成后 build-manifest 记下新值，之后 lint 不再报错。放行时仍输出一条 warning，说明已有项目中的状态需要人工处理。lint 报这两个 error 时，在 `hint` 中给出对应的命令（D47）。`--allow-major-upgrade` 同样只用于 `doctor`，放行运行框架跨主版本升级的 `CORE_MAJOR_CHANGED`（D57）。

`add node` 和 `module` 是修改配置文件的便捷入口：前者写 `workflow.json`，后者写入口文件的 `modules` 引用和对应的 `modules/*.json`。`add skill` 和 `add skills` 则导入技能资源。这些命令写完都自动执行 doctor；批量导入只执行一次。配置修改在原文上插入或替换片段，原有的键序、缩进和换行不变；修改先在内存中完成，与 doctor 的生成结果一起写盘，任何一步有 error（包括 lint 的 `SEQ_DUP` 等）都不写文件（D56）。

同一套命令还以技能形式提供：`autobiz-plugin-creator`（借鉴 Codex plugin-creator，见 README §2.3；规格见 §1.6）。技能负责与开发者对话、梳理流程、编写配置文件、生成技能展示文案；生成和校验仍然只通过上面的 CLI 完成。技能每次修改核心配置后运行 `lint`，一组修改完成后运行 `doctor` 重新生成插件，再运行 `check`，并把 Issue 原样转述给开发者，不能自己修改 generated 或 managed 文件来绕过问题（D58）。

### 1.2 通用约定

| 退出码 | 含义 |
|---|---|
| `0` | 成功（可能带 warning） |
| `1` | 存在 error 级问题（校验失败、漂移、契约测试失败），没有写入任何文件 |
| `2` | 用法错误（参数不合法、找不到 `plugin.scaffold.json` 或 `workflow.json`） |

退出码为 `2` 时，`--json` 仍按 §1.3 输出，`issues` 中只有一条 `code` 为 `USAGE` 的 error，`written` 为空（D43）。

所有命令的 stdout、stderr 都是 UTF-8，在 Windows 上输出被管道读取时也一样；输出中的路径一律用 `/` 分隔（D42）。

`doctor`，以及会修改核心配置的 `new`、`add`、`module enable`/`disable`，先在内存中完成配置修改、全部生成和校验，再统一写盘（D56）：校验类 error 都在写盘之前报出，不会只写一半。写盘时逐个文件原子替换，`runtime/build-manifest.json` 最后写；中途出现读写错误时，重新执行即可恢复（D52）。

### 1.3 问题（Issue）格式

`--json` 输出：

```json
{
  "ok": false,
  "issues": [
    {
      "level": "error",
      "code": "ARTIFACT_ID_CONFLICT",
      "file": "workflow.json",
      "pointer": "/nodes/dev/1/outputs/0",
      "message": "节点 plan 的输出 PLAN.md 与节点 specs 的输出 plan.md 推导出同一个产物 id plan",
      "hint": "修改其中一个文件名，让两者推导出不同的产物 id"
    }
  ],
  "written": []
}
```

- `file` 标明问题所在的文件（`workflow.json`、`plugin.scaffold.json`、`modules/board.json`，或 `skills/autodev-plan/SKILL.md` 这类资源文件）；`pointer` 是该文件内的 JSON Pointer，问题出在文件层面时为空；
- `code` 的取值见 input-config.md §7.2、§7.3，此外还有 `MODULE_CONFLICT`（§2.3）、doctor 的 `CHECKPOINT_REMOVED` 和 `DOCTOR_BASELINE_MISSING`（§1.7）、simulate 的 `INTERPRETER_MISSING` 和 `KNOWLEDGE_MANIFEST_MISSING`（§1.5）、用法错误的 `USAGE`（§1.2）；
- `issues` 按文件、位置、code 稳定排序（D43）：文件依次为入口文件、`workflow.json`、`modules/` 下的 board、session、knowledge、artifactSync，其余按路径；同一文件内按 `pointer` 逐段比较，数字段按数值比较；最后按 `code`；
- 各命令在通用结构之外的附加字段（D54）：`doctor` 加 `changes`（§1.7），`check` 加 `contract`（契约测试的结果），`simulate` 加 `simulation`（§1.5），`module list` 加 `modules`（各模块的版本和启用状态），`package` 加 `package`（`{"path": 生成的 zip, "skipped": [没有打包的文件]}`，output-spec.md §1，D57）；`add skills` 成功时加 `importedSkills`（已导入的技能名数组）；`lint`、其他 `add`、`module enable`/`disable`、`new` 没有附加字段；
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
? 所属阶段（biz / dev / ops）           › biz
? 编排顺序 seq                          › 1             ← 默认取已有最大 seq + 1
? 绑定技能                              › （新建）doc-draft     ← 同时列出 skills/ 中已有的技能（含分组目录下的）
? 产出产物（文件名，逗号分隔）          › DRAFT.md
? 继续添加节点？                        › Y
  …
── 3 技能资源 ──
? doc-draft：导入已有目录 / 不提供      › 不提供        ← 不提供时生成空白 SKILL.md
── 4 看板 ──
? 目标平台                              › [x] darwin  [x] linux  [x] win32
── 5 会话与 Agent ──
? 默认运行策略                          › multi
? 为节点单独配置策略？                  › N
── 6 知识与产物同步 ──
? 启用知识模块？                        › N
? 启用产物同步模块？                    › N
── 7 自定义扩展 ──
  已创建 hooks/（agents/ 可选，需要外挂子代理时再创建）
```

- 产物 id 由路径推导（`DRAFT.md` → `draft`，`specs/*/spec.md` → `spec`），冲突时追问改文件名；`seq` 重复或与阶段先后不一致时当场追问；
- 最后一个节点没有产物时，追问它是否为终态节点（只推进到 `archived`，D56）；
- 向导在内存中生成配置后先运行 `lint`，有 error 时回到对应问题重新回答；通过后写入配置并执行 doctor，第一次生成时全部节点列为新增；
- 选择“不提供”时，build 生成空白 `SKILL.md`：只有 frontmatter 和状态维护片段，正文由开发者自行填写（output-spec.md §6.1）；导入已有目录时，build 只在 `SKILL.md` 开头插入状态维护片段。模板由技能自己维护，向导不问、不生成（D29）；
- 看板一类会生成接入脚本（`runtime/adapters/*`）和三平台命令映射；会话一类会生成默认会话入口和策略骨架；
- 第 4–6 类的回答分别写入 `modules/board.json`、`modules/session.json`、`modules/knowledge.json` 和 `modules/artifactSync.json`，并在入口文件的 `modules` 中引用。全部取默认值的类别不生成文件，所以入口文件只有基础信息和真正用到的引用。启用产物同步时追问从哪个节点起允许同步，`artifacts` 的预填与 `module enable artifactSync` 相同（§1.1）；
- `--yes` 时不提问，回答全部取自 `--answers`，必须给出 `plugin` 和 `nodes`，缺少必填项报用法错误（退出码 2）；lint 有 error 时报出 Issue，不写任何文件。

`--answers <file|->` 从文件或 stdin 读入回答（D56），供插件开发技能等非交互的调用方使用：

```json
{
  "plugin": { "id": "doc-review", "name": "Doc-Review-Kanban", "version": "0.1.0", "description": "文档起草与评审" },
  "nodes": [
    { "id": "draft", "name": "起草", "stage": "biz", "seq": 1, "skill": "doc-draft", "outputs": ["DRAFT.md"] },
    { "id": "review", "name": "评审", "stage": "biz", "seq": 2, "skill": "doc-review", "outputs": ["REVIEW.md"] } ],
  "skills": { "doc-draft": null, "doc-review": "/path/to/doc-review" },
  "agents": "/path/to/agents",
  "globalHooks": { "hooks": ["secrets-check"] }
}
```

- `nodes` 每项的字段同 `workflow.json` 的节点，另加 `stage`；终态节点写 `"terminal": true`；
- `skills` 为技能名 → 导入目录，`null` 表示不提供；导入规则同 `add skill --from`；
- `agents` 可选，为 agents 目录的路径，规则同 `add skills --agents`；不写时不创建 `agents/`；
- `globalHooks` 可选，内容与 `modules/globalHooks.json` 相同，写了即启用插件全局钩子模块（input-config.md §4.6）；向导中对每个钩子逐个询问，默认不启用，选了任何一个才启用模块；
- `board`、`session`、`knowledge`、`artifactSync`、`globalHooks` 可选，内容与对应的模块配置文件相同；写了 `knowledge`、`artifactSync`、`globalHooks` 即表示启用，不写的模块取默认值。

脚手架不带样例种子：`new` 只从问答或 `--answers` 生成核心配置，想自己手写时用 `new --skeleton`（§1.4.1）。lite、fullstack 两份样例放在仓库根目录的 [fixtures/](../fixtures/)，只供脚手架自身的测试，不随 booter 和 `autobiz-plugin.pyz` 发布（D67）。脚手架也不提供从已有插件的 `board_config.json` 反推核心配置的命令：迁移已有插件时，用向导、`--answers` 或 `--skeleton` 写出核心配置，再用 `add skills --from` 导入技能集合目录；只有单个技能时可用 `add skill --from`。

#### 1.4.1 只写骨架（new --skeleton，D63）

不问答、不生成插件，只写出核心配置的结构，由开发者（或 agent）照着 `[TODO: …]` 的说明填写：

```bash
autobiz-plugin new my-plugin --skeleton --module board --module artifactSync --module globalHooks
```

| 文件 | 骨架内容 |
|---|---|
| `plugin.scaffold.json` | `plugin` 的 `id`、`name`、`description` 是占位，`version` 为 `0.1.0`；`modules` 引用 `--module` 选中的模块 |
| `workflow.json` | `biz`、`dev` 各一个节点，`id`、`name`、`skill`、`outputs` 是占位，`seq` 为 1、2；需要 `ops` 组或更多节点时自己加 |
| `modules/board.json` | `display.workflowLabel` 占位 |
| `modules/session.json` | `policies.default.agentMode` 为 `multi`，没有占位 |
| `modules/knowledge.json` | `assembly.assembler` 为 `plugin`，`source.url` 占位 |
| `modules/artifactSync.json` | `allowedFrom`、`artifacts` 的产物路径和简述都是占位 |
| `modules/globalHooks.json` | `hooks` 列出全部可用的全局钩子（不是占位），用户删掉不需要的（D65） |
| `.scaffold/` | 6 个输入 Schema（拷贝，IDE 补全用），首次 doctor 时登记为 managed |

- 不加 `--module` 时只写入口文件和 `workflow.json`；`board`、`session` 不写就全部取默认值，`knowledge`、`artifactSync`、`globalHooks` 不写就不启用，之后可以用 `module enable` 加上；
- 填写前后都可以运行 `lint`：每个还没填的占位报一条 `TODO_FIELD`，`pointer` 指出位置，`message` 带占位中的说明（input-config.md §7.1）。占位报 error，`doctor` 不生成、不写任何文件；只有 `artifactSync` 的 `artifacts`、`extraPaths` 中的简述报 warning，可以先生成，`package` 时由 `TODO_PLACEHOLDER` 拦下（与 `module enable artifactSync` 预填的简述一致，D56）；
- 占位所在位置的 Schema 问题由 `TODO_FIELD` 代替，不再另报 `INPUT_SCHEMA`；
- 填完后 `doctor` 照常生成插件（技能不存在时生成空白 `SKILL.md`），之后 `check`、`package`。

### 1.5 simulate

simulate 在临时目录中扮演 DevClaw，调用一遍已经生成的插件，只写临时目录（D55）：

1. 准备：按 output-spec.md §1 的打包清单把插件拷到 `<tmp>/plugin`（`sys/` 存在时一并拷贝），创建工作区 `<tmp>/ws/<project>`。`--platform` 缺省为当前平台，`board_config.json` 中没有该平台的命令时报用法错误；`--to` 不是 `flow.json` 中的 checkpoint 时同样报用法错误。核心配置或节点技能 `description` 的摘要与 build-manifest 中的记录不一致时报 warning `BUILD_STALE`，照常执行；
2. 建项目和 Feature：`create_project`、`create_feature`（`--selected-deployUnit` 传 `[]`）各执行两次，第二次应返回 `created: false`，checkpoint 不变。`create_feature` 返回的 checkpoint 应为 `checkpoints.initial`，桩内容写到它返回的 `featureDir` 下；
3. 读流程：`dynamic_workflow`、`project_status`。节点列表取 `project_status` 输出的 `workflow.nodes`，与 `dynamic_workflow` 的 checkpoint 链对照。启用知识模块时执行 `deploy_units`；知识目录中没有清单时（例如声明了 `knowledge.source` 但还没有执行 `pull_knowledge`）报 warning `KNOWLEDGE_MANIFEST_MISSING`，不算失败；
4. 逐个节点：`session_collector_context_inject`（策略目标节点应为本节点）→ 执行该技能 SKILL.md 状态维护片段中的开始命令 → 为必需输出写入桩内容（glob 中的 `*`、`**` 换成 `demo`，`?` 换成 `x`；可选输出不写）→ 执行片段中的完成命令 → `feature_status`（本节点及之前的节点为 `done`，之后的为 `not_started`）。终态节点只有完成命令，推进到 `archived` 后它的状态为 `archived`；
5. 只读命令（§3.1）执行前后比较临时工作区，有文件被创建或修改即失败；
6. 每次输出都按 §3.3 的结构校验（Schema 在脚手架的 `schemas/host/outputs.schema.json`），最后打印节点状态表和失败原因。

执行方式：

- 宿主命令取 `board_config.json` 中所选平台的命令，先按 POSIX 规则拆成参数，再逐个参数替换占位符：`${projectDirs...}` 展开为多个参数，`${selectedDeployUnits}` 替换为一个参数，`${knowledge-path}` 替换为空字符串。宿主命令只带参数，不注入 §3.4 的会话变量，也不设 `AUTOBIZ_BOARD_ENDPOINT`，所以不推送看板事件；
- 状态维护片段中的命令开头固定写 `python`（output-spec.md §6.1），执行时换成所选平台在 `board.target.python` 中配置的解释器（darwin、linux 取 `posix`，win32 取 `win32`，即该平台宿主命令开头的解释器），再替换 `${pluginPath}`、`${feature}`，并注入 `PLUGIN_WORKSPACE`、`PROJECT_DIR`、`FEATURE_ID`、`SESSION_ID`（值为 `simulate`）；
- 解释器在 PATH 上找不到时改用脚手架自己的解释器，报 warning `INTERPRETER_MISSING`：DevClaw 在这台机器上执行同样会失败。

`--to` 指定停在哪个 checkpoint，`--keep` 保留临时目录便于排查。v1 的节点没有校验命令（input-config.md §2.5），simulate 也就不执行校验命令。simulate 只依赖本插件，不访问网络；内置知识组装脚本调用的 collector（`collect-knowledge.js`）除外。

失败的步骤各报一条 `CONTRACT_TEST` error：宿主命令的 `file` 为 `board_core/board_config.json`，`pointer` 为 `/inspectCommands/<platform>/<key>`；片段命令的 `file` 为该技能的 `SKILL.md`，`pointer` 为空。`--json` 输出的附加字段 `simulation`：

```json
{
  "ran": true, "platform": "darwin", "feature": "demo", "workspace": null, "stale": false, "stoppedAt": null,
  "steps": [
    { "node": null, "key": "create_feature", "ok": true, "exitCode": 0, "detail": "draft_in_progress" },
    { "node": "draft", "key": "model:update_state", "ok": true, "exitCode": 0, "detail": "draft_done" } ],
  "nodes": [ { "id": "draft", "status": "done" }, { "id": "review", "status": "not_started" } ]
}
```

- `workspace` 只在 `--keep` 时给出临时目录，否则为 `null`；`stale` 为是否报了 `BUILD_STALE`；
- `stoppedAt` 是因 `--to` 或失败停下时 Feature 的 checkpoint，走完全部节点时为 `null`；
- `steps[].node` 为步骤所属的节点，建项目、建 Feature、读流程这些步骤为 `null`；`key` 为 inspectCommands 的键，片段命令为 `model:update_state`；
- `nodes` 取最后一次 `feature_status` 中的节点状态。

`check` 中的契约测试走同样的流程，结果放在附加字段 `contract` 中，结构与 `simulation` 相同。lint 或漂移检查有 error 时不跑契约测试，`contract` 为 `{"ran": false, "reason": "…"}`：磁盘上的插件已经不对应当前配置。

### 1.6 插件开发技能 autobiz-plugin-creator（v1，D9）

源码位于脚手架仓库的 `skills/autobiz-plugin-creator/`，不随生成的插件发布。它是初始化向导的对话形式，以只含这个技能的 DevClaw 插件发布（与 demo 的 `autobiz-plugin-creator-demo` 相同，D58）：

```text
autobiz-plugin-creator/               # 插件包的顶层目录（D57 ④）
├── plugin.json                       # 发布时生成：name、version（取脚手架版本）、description、"skills": "./skills/"
└── skills/autobiz-plugin-creator/
    ├── SKILL.md                      # 对话流程与规则（见下）
    ├── references/
    │   └── modeling-guide.md         # 如何把业务流程拆成阶段、节点和产物，更严格的完成条件怎么写进技能正文（含正反例）
    └── scripts/autobiz-plugin.pyz    # 发布时放入，与脚手架是同一个文件（D57），不提交进仓库
```

插件包由 `tools/make_pyz.py` 在打出 `.pyz` 之后组装。技能不带 `input-config.md` 副本：SKILL.md 只写建模和配置的要点（节点的 6 个字段与 `seq` 规则、产物 id 的推导、四个模块配置各管什么、`new --answers` 的格式），细节以 CLI 的 Issue（`code`、`pointer`、`hint`）和插件目录 `.scaffold/` 下的 Schema 为准（D58）。

SKILL.md 中的命令写作 `python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/autobiz-plugin.pyz" <命令>`，Windows 上把 `python3` 换成 `python`。装在 DevClaw 中时 `${pluginPath}` 由 DevClaw 替换（§3.2）；装在其他 agent 中、`${pluginPath}` 没有被替换时，按 SKILL.md 所在目录定位 `scripts/autobiz-plugin.pyz`。

frontmatter 中的 `description` 要写明触发场景，例如“新建看板插件”“给插件加节点或产物”“导入已有技能”“启用知识模块或产物同步”。v1 不能配置节点校验命令（input-config.md §2.5），所以不写“给节点加校验”。

流程（SKILL.md 正文）：

| 步骤 | agent 做什么 | 调用 |
|---|---|---|
| 1. 定位 | 确认是新建还是修改；新建时确认插件放在哪个目录、插件 ID（提示发布后不可修改）、插件名 | —（新建时到第 2 步确认后再调用 `new`） |
| 2. 建模 | 让开发者用自然语言描述流程，整理成“seq → 阶段（biz/dev/ops）→ 节点 → 技能 → 输出产物”表格回显，开发者确认后才写入；每个节点一个技能 | 新建：`new --yes --answers`（§1.4，D56）；修改：编辑 `workflow.json` 或调用 `add node`，写完运行 `lint` |
| 3. 技能资源 | 对每个节点确认是导入已有技能，还是先不提供（由 build 生成空白 `SKILL.md`）；同一来源有多个技能时批量导入 | `add skills --from` 或 `add skill` |
| 4. 模块 | 询问目标平台、节点运行策略、是否需要知识模块（组装方由谁担任）、是否需要产物同步模块（从哪个节点起允许同步、上传哪些产物）；知识沉淀入口固定开启，不用问（D33） | 编辑 `modules/*.json` 和入口文件的引用，或 `module enable` |
| 5. 生成 | 生成插件；对新生成的空白 `SKILL.md`，与开发者确认触发场景后填写 `description`，再执行一次 doctor：节点描述取自 `description`，改了不重新生成会报 `BUILD_STALE`（D49） | `doctor`（填写 `description` 后再执行一次） |
| 6. 校验 | 执行完整校验，把 Issue 按原文转述给开发者，修改输入后重试 | `check` |
| 7. 演示 | 在临时工作区走一遍完整流程，展示每个节点的状态和产物路径 | `simulate` |

规则：

- 只修改 `workflow.json`、`plugin.scaffold.json`、`modules/*.json` 和 seeded/developer 文件，不得修改 generated、managed、module 文件来绕过校验，也不得直接修改编译配置 `runtime/config/*`；
- 每次修改核心配置后都运行 `lint`，没有 error 才继续下一步；一组修改完成后运行 `doctor` 重新生成插件，再运行 `check`，不能只改配置不重新生成；
- 不修改 `SKILL.md` 中 `<!-- plugin workflow: begin state -->` 到 `<!-- plugin workflow: end state -->` 之间的内容，节点或 checkpoint 变了就运行 `doctor`；
- 插件已经发布后，不得修改 `plugin.id` 和 `runtime.metaRoot`；
- `--force`、`--allow-id-change`、`--allow-layout-change`、`--allow-major-upgrade` 只在开发者看过对应的 Issue 并明确同意后才加，执行后把放行时的 warning 原样转述（D58）；
- 涉及节点业务逻辑的技能正文和校验器由开发者负责，agent 只能起草，不能把未经确认的流程或校验规则写进去；
- 所有判断以 CLI 的退出码和 Issue 为准，不得自行宣称“校验通过”。

### 1.7 doctor（修改核心配置后重新生成插件）

开发者或 agent 改了 `workflow.json`、`modules/*.json` 或入口文件之后，用 doctor 重新生成插件。build 只管“输入 → 输出”；doctor 在它前后加上诊断：先说明这次改动影响了什么，再生成，最后复查，保证核心配置、编译配置和各技能 `SKILL.md` 中的状态维护片段三者一致。

```text
autobiz-plugin doctor [-C <plugin-dir>] [--dry-run] [--force] [--allow-id-change] [--allow-layout-change] [--allow-major-upgrade] [--json]
```

| 步骤 | 做什么 | 失败时 |
|---|---|---|
| 1. 检查 | 执行 lint（input-config.md §7.2；`BUILD_STALE`、`SCAFFOLD_VERSION_CHANGED` 不报，过期和可升级正是要重新生成的原因） | 有 error 时退出码 1，不写任何文件 |
| 2. 比较 | 按 build-manifest 的 `inputs` 找出改过的核心配置；在内存中编译新流程，与当前的 `runtime/config/flow.json` 和 build-manifest 记录的技能片段比较，列出影响（下表） | 从未生成过（没有 build-manifest）时，全部节点列为新增，不报 warning（D56）。有 build-manifest 但 `runtime/config/flow.json` 不存在或无法解析时不做比较：报 warning `DOCTOR_BASELINE_MISSING`，说明本次没有影响报告，直接进入第 3 步重新生成，重新生成即修复了 flow.json（D54） |
| 3. 生成 | 执行 build：重写编译配置和 `board_core/`；同步技能：缺失的技能生成空白 `SKILL.md`，已有技能插入或更新状态维护片段，不再绑定节点的技能删掉片段（output-spec.md §6.1） | managed 文件被手改时报 `DRIFT_MANAGED`，确认要覆盖时加 `--force` |
| 4. 复查 | 重新 lint（不应再有 `BUILD_STALE`），并检查每个节点技能的片段与推导结果一致（`SKILL_STATE_BLOCK`） | 报出问题，退出码 1 |

`--dry-run` 只执行前两步，打印将要发生的变化，不写文件。核心配置与记录一致、技能片段也都正确时，doctor 不写任何文件，报告插件已是最新。核心配置没改、只是有人手改或删掉了技能中的片段时，doctor 同样会把片段修好。

影响报告：

| 变化 | 举例 | doctor 怎么做 |
|---|---|---|
| 改了哪些核心配置 | `workflow.json`、`modules/board.json` | 列出文件 |
| 新增节点 | 加了 `design` | 技能已存在：在它的 `SKILL.md` 开头插入片段；不存在：生成空白 `SKILL.md` |
| 删除节点，或节点换了技能 | 删了 `detail_design` | 删掉原技能 `SKILL.md` 中的片段，技能目录保留，按开发者资源交付 |
| 节点改了 id | `specs` → `spec` | 按删除加新增处理，片段中的 checkpoint 换成新 id |
| 调整顺序 | 改了 `seq` | 重算 `order`、checkpoint 链和各节点的 `nextAction`；只改号、先后不变时编译配置中只有 `seq` 变化 |
| 改了输出或模块配置 | `outputs`、`board.display`、`session.policies` | 只重新生成编译配置，技能不变 |
| 脚手架更新（D57） | 当前脚手架的 `coreVersion` 为 `1.1.0`，build-manifest 中记录的是 `1.0.0` | 替换 managed、module 文件（被插件替换的内置组装脚本保留，手改过的报 `DRIFT_MANAGED`），`changes.versions` 列出脚手架、运行框架和各模块的版本变化。`coreVersion` 主版本变化时报 `CORE_MAJOR_CHANGED`，确认后加 `--allow-major-upgrade`；脚手架、运行框架或任一模块的版本低于记录时报 `SCAFFOLD_OUTDATED`，不写任何文件，应先更新脚手架 |
| checkpoint 消失 | 上次构建的 checkpoint 在新流程中不存在（删除或改名了节点） | 报 `CHECKPOINT_REMOVED`（warning）：已有 Feature 停在这些 checkpoint 上时无法继续推进。doctor 只读插件目录，不知道哪些项目在用这个插件，不检查也不迁移已有 Feature 的状态 |

`--json` 输出在 §1.3 的基础上增加 `changes`：

```json
{
  "ok": true,
  "issues": [
    { "level": "warning", "code": "CHECKPOINT_REMOVED", "file": "workflow.json", "pointer": "",
      "message": "上次构建的 detail_design_in_progress、detail_design_done 在新流程中不存在",
      "hint": "停在这些 checkpoint 上的已有 Feature 需要人工处理" }
  ],
  "changes": {
    "inputs": ["workflow.json"],
    "nodes": { "added": ["design"], "removed": ["detail_design"], "reordered": false },
    "skills": { "created": ["skills/autodev/autodev-design/SKILL.md"], "stateInserted": [], "stateUpdated": [],
                "stateRemoved": ["skills/autodev/autodev-detail-design/SKILL.md"],
                "moved": [ { "from": "skills/autodev-plan", "to": "skills/autodev/autodev-plan" } ] },
    "versions": { "scaffold": null, "core": null, "modules": {} }
  },
  "written": ["runtime/config/flow.json", "runtime/config/board.json", "skills/autodev/autodev-design/SKILL.md", "…"]
}
```

触发方式：开发者手动执行；插件开发技能完成一组修改后执行（§1.6）；`add`、`module` 写完配置后自动执行。`lint`、`check` 只检查不生成，发现 `BUILD_STALE`、`SCAFFOLD_VERSION_CHANGED` 或 `SKILL_STATE_BLOCK` 时提示执行 doctor。

`changes.skills.moved` 列出 doctor 挪进分组目录的节点技能（input-config.md §5，D64）：挪动在 lint 之后、生成之前进行，与生成结果一起写盘。

`changes.versions` 中有变化的项写成 `{"from": 记录的版本, "to": 当前版本}`，例如 `"core": {"from": "1.0.0", "to": "1.1.0"}`；`modules` 只列版本有变化的模块。

---

## 2. 模块契约

模块分两类：核心模块 `board`（看板）和 `session`（会话与 Agent）始终启用；`knowledge`（知识）和 `artifactSync`（产物同步）按配置启用，各自有独立的配置文件，入口文件引用即启用。知识沉淀入口只是 `board_core/modules.json` 中的一个看板入口，由 `board` 模块直接生成。

### 2.1 模块包结构

```text
scaffold/modules/<id>/
├── module.json          # 元数据
├── module.py            # 构建期实现（Module）
└── files/…              # 要拷贝进插件的文件，原样拷贝；需要替换内容时由 module.py 生成 content（D52）；board、session 的运行期代码在仓库根目录的 runtime/ 下（D50）
```

`module.json`：

```json
{
  "id": "artifactSync",
  "version": "1.0.0",
  "title": "产物同步",
  "description": "按节点输出同步 Feature 产物，可选按实际代码生成接口文档",
  "schema": "modules/artifactSync.schema.json",
  "core": false,
  "entry": "module:ArtifactSyncModule"
}
```

`id` 同时是入口文件 `modules` 中的键，模块配置就是该键引用的整个文件，例如 `modules/artifactSync.json`（D30）。`schema` 是模块配置的 Schema，相对仓库的 `schemas/`，只有这一份（D50）。`core` 为 `true` 的模块（board、session）始终启用，不能 `module disable`；它们的运行期代码和框架一起发布，版本号直接取 `coreVersion`，`module.json` 中不写 `version`（D53）。模块都随脚手架一起发布，v1 不支持第三方模块，所以不声明对运行框架版本的要求（D50）。

### 2.2 构建期接口（Python）

IR 只包含核心流程和入口文件的信息；模块配置按 Schema 补全后作为 `options` 单独传给模块的 `validate` 和 `contribute`（D49）。`flow.json` 的 `skillDir` 不在 IR 中，由框架生成 `flow.json` 时查找技能目录得到。

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, Union

@dataclass(frozen=True)
class ArtifactIR:
    id: str
    label: str                     # 路径本身（用户不配置产物名称）
    paths: tuple[str, ...]         # 核心配置中为字符串时只有一项
    type: str                      # "file" | "json"，按扩展名推断
    producer: str                  # 第一个输出该产物的节点 id

@dataclass(frozen=True)
class OutputRef:
    artifact: str                  # 产物 id
    required: bool                 # 核心配置中 optional 的反面

@dataclass(frozen=True)
class NodeIR:
    id: str                                # 同时是 checkpoint 前缀（D36）
    name: str
    stage: str                             # 节点所在分组：Biz、Dev、Ops；需要 biz/dev/ops 分组键时取小写
    skill: str
    seq: int                               # workflow.json 中手动填写的编排顺序
    order: int                             # 按 seq 排列后的位置 (i + 1) * 10
    description: str                       # SKILL.md 的 description；缺省或仍是 [TODO] 占位时按 input-config.md §6 推导
    terminal: bool                         # 终态节点
    outputs: tuple[OutputRef, ...]
    inputs: tuple[OutputRef, ...] = ()     # v1 恒为空（D32）
    validate: Optional[str] = None         # v1 恒为 None（D32）

    @property
    def checkpoints(self) -> tuple[str, ...]:
        return ("archived",) if self.terminal else (f"{self.id}_in_progress", f"{self.id}_done")

@dataclass(frozen=True)
class PluginIR:
    plugin: dict                           # 入口文件的 plugin 段，已填默认值
    runtime: dict                          # 入口文件的 runtime 段，已填默认值
    stages: tuple[str, ...]                # 写了节点的分组，按 Biz → Dev → Ops
    nodes: tuple[NodeIR, ...]              # 按 seq 从小到大排列
    artifacts: dict[str, ArtifactIR]       # 按首次出现的顺序
    checkpoint_chain: tuple[str, ...]      # 按流转顺序排列的全部 checkpoint

    def node(self, node_id: str) -> NodeIR: ...
    def checkpoints_from(self, anchor: str) -> tuple[str, ...]:
        """anchor 为 "<nodeId>:<in_progress|done>" 或 checkpoint 名；返回从 anchor 到链尾的 checkpoint。"""

@dataclass(frozen=True)
class FileSpec:
    dst: str                               # 插件内相对路径
    ownership: str                         # "managed" | "module" | "generated" | "seeded"
    src: Optional[str] = None              # "files/…" 相对模块包；"runtime/…" 相对仓库根目录的 runtime/
    content: Optional[Union[str, bytes]] = None   # 直接给出内容（generated 常用）
    replaceable: bool = False              # 插件可以整个替换：与记录不符时保留插件的版本，不报漂移（内置知识组装脚本）

@dataclass(frozen=True)
class CommandSpec:
    script: Optional[str] = None           # 相对插件根；生成 {py} "${pluginPath}/<script>" <args>
    args: str = ""                         # 可含 {platform}，展开时替换为平台名
    value: Optional[str] = None            # 非命令值，例如 knowledge_path

@dataclass
class Contribution:
    files: list[FileSpec] = field(default_factory=list)
    entries: dict = field(default_factory=dict)                    # 看板入口，写入 board_core/modules.json 顶层，例如 {"artifact_sync": {...}}
    manifest: dict = field(default_factory=dict)                   # 写入 modules.json 中本模块的条目，例如 {"assembler": "plugin", "source": True}
    runtime_config: dict[str, dict] = field(default_factory=dict)  # 写入 runtime/config/<name>.json，例如 {"knowledge": {...}}
    inspect_commands: dict[str, CommandSpec] = field(default_factory=dict)
    knowledge_assembly: Optional[dict] = None                      # {"script", "timeoutSec"}，写入 session.json 的 knowledgeAssembly
    skills: list[str] = field(default_factory=list)                # 模块占用的技能名

@dataclass(frozen=True)
class Issue:
    level: str        # "error" | "warning"
    code: str
    message: str
    file: str = ""
    pointer: str = ""
    hint: str = ""

@dataclass(frozen=True)
class ModuleContext:
    root: Path                             # 插件目录，只读（例如检查 customSubagentFiles 是否存在）
    package_dir: Path                      # 模块包目录
    runtime_dir: Path                      # 仓库根目录的 runtime/
    core_version: str
    enabled: frozenset[str]                # 启用的模块；session 据此决定会话入口是否带知识目录参数（D53）

class Module(Protocol):
    id: str
    version: str

    def validate(self, ir: PluginIR, options: dict, ctx: ModuleContext) -> list[Issue]:
        """语义校验。只读，不得有副作用。options 已按 Schema 补全（D46）。"""

    def contribute(self, ir: PluginIR, options: dict, ctx: ModuleContext) -> Contribution:
        """纯函数：相同输入必须得到相同输出（build 的漂移检测依赖这一点）。"""
```

### 2.3 合并规则

| 贡献 | 规则 | 冲突时 |
|---|---|---|
| 总则 | 按 framework、board、session、knowledge、artifactSync 的顺序合并，各部分保留贡献顺序；同一个键或文件路径有两个来源即为冲突（D50） | `MODULE_CONFLICT` |
| `entries` | 写入 `modules.json` 的顶层键，不能占用由核心写入的 `apiVersion`、`modules`、`boardEvents` | `MODULE_CONFLICT` |
| `manifest` | 只写本模块在 `modules.<id>` 下的条目，`enabled`、`version` 由核心填写 | `MODULE_CONFLICT` |
| `runtime_config` | 写入 `runtime/config/<name>.json`：`runtime`、`flow` 由框架生成，`board`、`session` 由同名的核心模块生成，`knowledge` 由知识模块生成 | `MODULE_CONFLICT` |
| `inspect_commands` | 写入 `board_config.json`，每个平台各生成一份，键按贡献顺序排列；output-spec.md §3.2 中标为“必有”的键都由 board、session 贡献。模块未启用时它贡献的键直接不出现（D1），不输出空值 | `MODULE_CONFLICT` |
| `files` | `dst` 不能与框架文件或其他模块重复 | `MODULE_CONFLICT` |
| `skills` | 不能与节点技能重名，由 artifactSync 在 validate 中检查（D47） | `MODULE_SKILL_CONFLICT` |
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
- 退出码：`0` 表示成功；`1` 表示业务失败，此时 stdout 为 `{"ok": false, "errors": ["…"]}`。`session_collector_context_inject` 和 `pull_knowledge` 例外：始终以 `0` 退出，用 `ok` 字段表示结果（兼容现有宿主）；
- 只读命令（`project_status`、`feature_status`、`dynamic_workflow`、`session_collector_context_inject`、`deploy_units`）不得创建或修改任何文件；
- `create_project`、`create_feature` 是幂等的，重复执行不会丢失已有进度；
- 写命令（`create_project`、`create_feature`）和模型调用的 `update_state.py` 提交成功后推送看板事件（§3.5），v2 的 `skip_node` 同样推送。推送结果不影响 stdout 和退出码。

### 3.2 占位符

运行上下文全部由 DevClaw 通过下列占位符和 §3.4 的环境变量传入，插件配置中不得写死（D15）：

| 占位符 | 含义 | 允许出现在 |
|---|---|---|
| `${pluginPath}` | 插件安装目录 | 所有命令、`knowledge_path`、`system_prompt_inject`、技能正文 |
| `${pluginWorkspace}` | 项目集合工作区 | 所有命令、`plugin_dir_hook`、`system_prompt_inject`、`dialog_tips` |
| `${projectDir}` | 项目目录名 | 同上 |
| `${projectDirs...}` | 多个项目目录名，宿主逐个转义后展开 | `project_status` |
| `${feature}` | 当前 Feature | `feature_status`、`create_feature`、`session_collector_context_inject`、`system_prompt_inject`、技能正文 |
| `${selectedDeployUnits}` | 所选发布单元，JSON 数组，宿主作为一个参数整体转义 | `create_feature`、`session_collector_context_inject` |
| `${sessionWorkspacePath}` | 会话工作区目录 | `session_collector_context_inject` |
| `${knowledge-path}` | DevClaw 自己维护的知识目录；DevClaw 不维护时替换为空字符串（D53） | `session_collector_context_inject`（启用知识模块时）、`deploy_units` |
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
  "statePath": "/…/<project>/.autobizdevops/state.json", "warnings": [] }
```

处理宿主参数后调用 `engine.init_project`。路径按 `runtime.metaRoot` 推导（output-spec.md §4.1），示例中为默认的 `.autobizdevops`。

#### 3.3.2 create_feature（init_feature.py）

```text
runtime/adapters/init_feature.py --workspace <dir> --project <name> --feature <name>
                                 [--selected-deployUnit <json>] [--workflow-template standard] [--owner <s>] [--iteration <s>]
```

```json
{ "ok": true, "created": true, "checkpoint": "draft_in_progress",
  "statePath": "/…/<project>/.autobizdevops/state.json",
  "featureDir": "/…/<project>/.autobizdevops/features/<feature>",
  "warnings": [] }
```

- 处理宿主参数后调用 `engine.init_feature`；项目尚未初始化时先初始化项目；
- 新 Feature 的 checkpoint 为 `flow.json` 的 `checkpoints.initial`；
- `--selected-deployUnit` 中每个单元的 `deployUnitId`、`localRepoPath` 记入 Feature 记录的 `deployUnits`。重复执行时用新传入的列表更新 `deployUnits`。会话中宿主仍会重新传入发布单元，`session_collector_context_inject` 发现与记录不一致时只在 `message` 中提示，不改记录；
- Feature 目录已存在但 `state.json` 中没有对应记录时，返回 `ok:false`，避免覆盖未知产物。

#### 3.3.3 project_status（inspect_state.py）

```text
runtime/adapters/inspect_state.py --mode project --workspace <dir> --projects <name>...
```

```json
{
  "workflow": { "nodes": [ WorkflowNode ], "dynamicStages": [ DynamicStage ] },
  "projects": {
    "<project>": { "runs": [ { "featureId": "f1", "featureName": "f1", "currentNodeId": "plan",
                               "currentNodeStatus": "in_progress", "currentNodeStatusLabel": "进行中",
                               "nodeIds": ["prd", "specs", "plan", "code"] } ] }
  }
}
```

`inspect_state.py` 调用 `query.py` 取得状态与流程数据（`runtime/config/flow.json`），再结合 `runtime/config/board.json` 的展示文案和 `session.json` 的运行策略，转换成看板接口数据。`workflow` 是静态的，同一次 build 下每次输出都相同；`runs[].nodeIds` 是该 Feature 实际经过的节点，包含已决定执行的动态阶段节点，不含被跳过的节点。

`WorkflowNode`（字段沿用全栈版 board_config 中的节点，DevClaw 原来从静态文件读取，现在从命令输出读取）：

```jsonc
{
  "id": "plan", "label": "任务计划", "group": "Dev", "order": 40, "skill": "autodev-plan",
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
{ "id": "plan", "label": "plan.md", "artifactType": "file", "path": "plan.md", "required": true }
{ "id": "spec_bundle", "label": "proposal.md", "artifactType": "file", "path": "proposal.md",
  "paths": ["proposal.md", "specs/*/spec.md"], "required": true }
```

| 字段 | 必有 | 语义 |
|---|---|---|
| `id` / `artifactType` / `required` | 是 | `artifactType` 按扩展名推断为 `file` 或 `json`；`required` 为核心配置中 `optional` 的反面 |
| `path` | 是 | 核心配置中路径为数组时取首项，保证只认 `path` 的旧版宿主仍能工作 |
| `label` | 是 | 产物卡片标题，为核心配置中写的路径本身（用户不配置产物名称，D39） |
| `paths` | 否 | 仅在核心配置中路径为数组时输出，给出全部项 |

`DynamicStage`（有动态阶段时；v1 的 `flow.json` 中 `dynamicStages` 固定为 `[]`，不会输出）：

```json
{
  "id": "detail_design_before_code", "phase": "Dev", "label": "详细设计", "description": "…", "order": 45,
  "choiceCheckpoint": "plan_done", "defaultDecision": "pending", "insertAfter": "plan",
  "enableTargetCheckpoint": "detail_design_in_progress", "skipTargetCheckpoint": "code_in_progress",
  "enableLabel": "…", "skipLabel": "…", "enableDescription": "…", "skipDescription": "…",
  "nodes": [ { "id": "detail_design", "phase": "Dev", "checkpointPrefix": "detail_design", "…": "其余字段同 WorkflowNode" } ]
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
    "currentNodeId": "plan", "currentNodeStatus": "in_progress", "currentNodeStatusLabel": "进行中",
    "nodes": [
      { "id": "specs", "nodeStatus": "done", "nodeStatusLabel": "已完成",
        "artifacts": [
          { "id": "proposal", "artifactLabel": "proposal.md", "artifactStatus": "generated", "artifactStatusLabel": "已生成",
            "path": ".autobizdevops/features/f1/proposal.md" },
          { "id": "specs", "artifactLabel": "specs/*/spec.md", "artifactStatus": "missing", "artifactStatusLabel": "未生成",
            "paths": [".autobizdevops/features/f1/specs/*/spec.md"] } ] },
      { "id": "code", "nodeStatus": "in_progress", "nodeStatusLabel": "进行中", "artifacts": [] } ],
    "hookLogRefs": [ { "id": "default", "path": ".autobizdevops/hooks.ndjson", "format": "ndjson" } ],
    "watchRefs": [
      { "path": ".autobizdevops/state.json", "purpose": "run-state" },
      { "path": ".autobizdevops/features/f1", "purpose": "artifacts" },
      { "path": ".autobizdevops/hooks.ndjson", "purpose": "hook-log" } ]
  }
}
```

- `nodeStatus` 取值：当前节点之前的为 `done`；当前节点为 `in_progress` 或 `done`；之后的为 `not_started`；被跳过的为 `skipped`；终态节点到达后为 `archived`。Feature 不存在时，`currentNodeId` 为 `"unknown"`，状态为 `unknown`；Feature 停在当前流程没有的 checkpoint 上时同样为 `unknown`，并带 `readOnly: true` 和说明原因的 `readOnlyReason`（D60，`project_status` 的 `runs` 中也一样）；
- `run.nodes` 按流程顺序列出：动态阶段已决定执行时，它的节点出现在插入位置；尚未选择（`pending`）时也列出，`nodeStatus` 为 `not_started`；已决定跳过时不列出；
- `pendingChoice` 在 Feature 停在某个动态阶段的选择点且尚未选择时给出，否则为 `null`：`{"stageId", "stageLabel", "choiceCheckpoint", "defaultDecision", "options": [{"decision": "enabled", "label", "description", "targetCheckpoint", "slashSkill"}, {"decision": "skipped", …}]}`；
- 示例中的 `.autobizdevops` 是默认的 `runtime.metaRoot`；
- 产物路径相对项目目录。单项且不含 glob 的产物用 `path`；含 glob 或 `path` 为数组的产物用 `paths`，列出实际匹配的文件，某一项没有匹配时给出该项的模式本身；
- `artifactStatus` 只表示文件是否存在（与完成判定一致，空文件不算已生成），不判断内容质量，也不代表节点已完成。

#### 3.3.5 dynamic_workflow（inspect_workflow_templates.py）

```json
{
  "ok": true, "schemaVersion": "autobizdevops.workflow.templates.v2", "mode": "templates",
  "templates": [ { "id": "standard", "templateType": "classical", "label": "需求开发", "description": "…",
                   "nodes": ["prd", "specs", "plan", "code"] } ],
  "nodes": [ { "id": "plan", "label": "任务计划", "group": "Dev", "skill": "autodev-plan", "description": "…",
               "inputs": [ ArtifactDef ], "outputs": [ ArtifactDef ] } ],
  "checkpoints": {
    "initial": ["prd_in_progress"],
    "transitions": { "prd_in_progress": ["prd_done"], "prd_done": ["specs_in_progress"], "…": [], "cicd_done": ["archived"], "archived": [] },
    "stageLabels": { "prd_in_progress": "需求澄清与 PRD进行中", "…": "…", "archived": "archive" }
  },
  "transitions": [ { "id": "prd-to-specs", "from": { "nodeId": "prd", "state": "done" }, "to": { "nodeId": "specs", "state": "in_progress" } } ],
  "skipPolicy": { "lockedNodes": [] }
}
```

通过 `query.py` 查询流程定义，返回宿主需要的模板结构。`ArtifactDef` 见 §3.3.3；全栈版现有入口只输出 `{path, label}`，宿主应能兼容两种形态。全栈版 board_config 中 `workflow` 下的 `checkpoints`、`transitions`、`skipPolicy` 改由这里输出：`checkpoints.transitions` 只描述主干，最后一个主干节点是终态节点时前一节点的 `_done → archived`；`transitions` 是主干相邻节点的流转；`skipPolicy` 仅在`flow.json` 的 `skip` 不为 `null`（v1 不会出现） 时输出。`templates` 只有 `standard` 一项（精简路线、自定义节点子集预留到 v2）；`nodes` 只列主干节点。

#### 3.3.6 system_prompt_inject / dialog_tips / plugin_dir_hook / knowledge_path

这些是模板字符串，宿主替换占位符后直接使用，不执行。

#### 3.3.7 session_collector_context_inject（render_session_context.py）

会话入口在 `board_config.json` 中的键默认为 `session_collector_context_inject`，取代旧插件使用的 `session_context_inject`（D40）；脚本和下面的输入输出协议不变。

```text
runtime/session/render_session_context.py --platform <p> --plugin-workspace <dir> --project <name> --feature <name>
                                          --selected-deployUnit <json> --session-workspace-path <dir>
                                          [--knowledge-path <dir> --knowledge-path-platform <dir>] [--node-id <id>]
```

```json
{
  "ok": true,
  "message": "remote 1 / local 0 / 缺 0",
  "sessionContext": "## 当前流程\n…\n\n## 知识\n…",
  "agentmdLoadStatus": [ { "deployUnitId": "LF39.18_wg_flow", "path": "…", "loaded": true, "source": "remote", "message": "…" } ],
  "flow": {
    "featureDir": "/…/<project>/.autobizdevops/features/f1",
    "currentNodeId": "plan", "currentNodeStatus": "in_progress",
    "targetNodeId": "plan", "nextNodeId": "code", "skill": "autodev-plan",
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

`flow` 是新增字段，现有宿主忽略即可。

启用知识模块时，生成的命令末尾带 `--knowledge-path "${pluginPath}/sys" --knowledge-path-platform "${knowledge-path}"`（D53），用来兼容两种知识目录：`--knowledge-path-platform` 不为空时，知识目录取它（DevClaw 自己维护的目录）；为空时走旧模式，取 `--knowledge-path`，即插件自己的 `${pluginPath}/sys`。未启用知识模块时命令不带这两个参数。

**策略目标节点**（与宿主拉起技能时依据的 nextAction 保持一致）：

1. 读取当前节点、当前状态下的 `nextAction.slashSkill`，找到拥有该技能的节点；
2. 找不到时，退回当前节点本身；
3. 仍然找不到时（Feature 未创建、参数缺失），只用 `session.policies.default`。

因此 not_started 和 in_progress 状态下取的是当前节点的策略，done 状态下取的是下一个节点的策略。`--node-id` 只用于本地调试，会直接指定节点。

**运行策略 → agentConfig 的映射**（按 `id` 在 `session.policies.nodes` 的分组中找到目标节点的策略，与 `policies.default` 深合并后映射）：

| agentConfig | 来源 | 内置默认值 |
|---|---|---|
| `agentMode` | `agentMode` | `multi` |
| `subagentConfig.disabledBuiltinSubagents` | 原样输出 | `[]` |
| `subagentConfig.customSubagentFiles` | 外挂资源路径拼接插件根目录，转为绝对路径，并按 `--platform` 规范分隔符；文件不存在时跳过，并在 `message` 中追加 `"外挂资源不存在，已跳过: <路径>"` | `[]` |
| `toolCustomConfig` | 原样输出；未配置时不输出 | — |

只有 `--selected-deployUnit` 不是合法 JSON 数组时才返回 `ok:false`，此时其余字段照常输出。未启用知识模块或 `assembler = devclaw` 时，`sessionContext` 中没有知识段，`agentmdLoadStatus` 为 `[]`。

#### 3.3.8 deploy_units（inspect_deploy_units.py，知识模块）

调用方是知识模块接入方：`assembler = devclaw` 时由 DevClaw 调用；`assembler = plugin` 时内置组装脚本在 collector 未命中时复用同一套解析逻辑。inspectCommands 中的键名 `deploy_units` 待与 DevClaw 确认（README §9）。

```text
runtime/knowledge/inspect_deploy_units.py --knowledge-path <dir> --knowledge-path-platform <dir> [--system <systemId>]
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

知识目录的选择与会话入口相同（§3.3.7）：`--knowledge-path-platform` 不为空时取它，为空时取 `--knowledge-path`（D53）。只读，不访问网络。清单不存在或格式不符时返回 `{"ok": false, "errors": ["…"]}`，退出码 1。

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

#### 3.3.10 skip_node（skip_node.py，skip 不为 null 时，v1 不生成）

看板上用户选中节点并选择跳过时调用。此时不在会话中，没有 `PLUGIN_WORKSPACE`、`FEATURE_ID` 等环境变量，所以全部通过参数定位：

```text
runtime/adapters/skip_node.py --workspace <dir> --project <name> --feature <name> --node <nodeId> [--node <nodeId> …]
                              [--reason <text>] [--dry-run]
```

```json
{ "ok": true, "changed": true, "feature": "f1", "skipped": ["design"],
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
    "projectRuns": [ { "featureId": "f1", "currentNodeId": "plan", "currentNodeStatus": "in_progress", "…": "…" } ],
    "run": { "featureId": "f1", "currentNodeId": "plan", "nodes": [ "…" ], "…": "…" } } }
```

| 字段 | 说明 |
|---|---|
| `pluginPath`、`pluginWorkspace`、`projectDir` | 用于定位缓存。路径都已解析为绝对路径，DevClaw 应先对自己持有的路径取 realpath 再比较 |
| `seq` | 该项目内的事件序号，即 `state.json` 中的 `boardSeq`（output-spec.md §4.2），每次提交加 1 |
| `reason` | `create_project`、`create_feature`、`update_state`（重开也属于 `update_state`）、`skip_node`（v2：看板上跳过节点；v1 运行框架不实现跳过，D59） |
| `sessionId` | 环境变量 `SESSION_ID` 的值，没有时为空字符串 |
| `feature`、`run` | 本次涉及的 Feature 及其 `feature_status.run`（§3.3.4）；`create_project` 时两者都为 `null` |
| `projectRuns` | 该项目**全部** Feature 的摘要，即 `project_status` 中的 `projects.<project>.runs`（§3.3.3） |

节点定义 `workflow` 是静态的，不随事件发送。DevClaw 第一次调用读取命令时取得它并缓存。

#### 3.5.3 插件侧的发送规则

| 项 | 规则 |
|---|---|
| 谁发送 | `init_workspace.py`、`init_feature.py`、`update_state.py`（v2 再加上 `skip_node.py`）在 engine 提交成功后调用 `runtime/adapters/board_events.py`，看板数据由它调用 `board_view.py` 组装，与读取命令共用同一套代码。engine 只负责递增 `boardSeq` 并在返回值中给出（D17、D59） |
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
| 会话入口提速 | 根据 `session_collector_context_inject` 的实测耗时，决定是否需要单独优化 |

P0 不做鉴权，本机任何进程都可以向 DevClaw 发送伪造的看板事件。因此推送只用于刷新显示，有疑问时以读取命令的结果为准；在鉴权实现之前，服务不得监听回环地址以外的地址。

---

## 4. 运行框架入口与内部库

### 4.1 入口总览

| 入口 | 调用方 | 主要职责 |
|---|---|---|
| `runtime/workflow/update_state.py` | 模型（按技能 `SKILL.md` 开头的状态维护片段）、人工操作 | 接收状态更新请求，通过 `engine.py` 检查并修改 `state.json` |
| `runtime/adapters/init_workspace.py` | DevClaw 的 `create_project` | 处理宿主参数，通过引擎初始化项目 |
| `runtime/adapters/init_feature.py` | DevClaw 的 `create_feature` | 处理宿主参数，通过引擎初始化 Feature |
| `runtime/adapters/inspect_state.py` | DevClaw 的项目和 Feature 查询 | 调用查询库，将结果转换为看板接口数据 |
| `runtime/adapters/inspect_workflow_templates.py` | DevClaw 的动态工作流能力 | 查询流程定义，返回宿主需要的模板结构 |
| `runtime/adapters/skip_node.py` | DevClaw 的 `skip_node`（`flow.json` 的 `skip` 不为 `null`（v1 不会出现） 时） | 处理宿主参数，通过引擎跳过节点。v1 不生成这个文件（D52） |
| `hooks/artifact_guard.py` | DevClaw 的 PreToolUse 钩子（`hooks/hooks.json` 注册，matcher 为 `execute`） | 执行完成命令前检查必需产物存在且非空，不满足时拦截（§4.7，D61） |
| `runtime/session/render_session_context.py` | DevClaw 的会话机制 | 获取流程上下文，结合会话策略及知识组装结果生成会话内容 |
| `runtime/knowledge/inspect_deploy_units.py` | 知识模块接入方 | 解析知识清单，提供支持的系统和发布单元信息 |
| `runtime/knowledge/sync_knowledge.py` | DevClaw 的 `pull_knowledge` | 拉取知识仓库，只更新知识目录，不回写任何配置文件（仅声明 `knowledge.source` 时，§3.3.9，D59） |

`update_state.py`、`init_workspace.py`、`init_feature.py` 这三个写入口在提交成功后，通过 `runtime/adapters/board_events.py` 推送看板事件（§3.5）；v2 的 `skip_node.py` 同样推送。入口共用 `runtime/common/cli.py`（参数解析、单个 JSON 输出、`BoardError` 转成 `{"ok": false}` 与退出码），看板数据由 `runtime/adapters/board_view.py` 拼装（D59）。

### 4.2 update_state.py（状态变更入口）

模型按技能 `SKILL.md` 开头的状态维护片段调用它：技能开始时 `--checkpoint <id>_in_progress`，技能完成时 `--checkpoint <id>_done`，终态节点完成时 `--checkpoint archived`（output-spec.md §6.1）。片段由 build 写入，技能正文不另写状态命令。重开等例外操作由人执行。

```text
python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --checkpoint <cp>
       [--feature <name>] [--workspace <dir> [--project <name>]]
       [--reopen] [--reason <text>] [--owner <s>] [--iteration <s>] [--dry-run]
```

| 场景 | 规则 |
|---|---|
| 正常推进 | `<cp>` 必须等于当前 checkpoint，或是状态规则允许的下一个 |
| 推进到 `_in_progress` | 检查本节点的必需输入是否存在（optional、生产者被跳过或未执行的输入除外；v1 的 `inputs` 固定为 `[]`）；缺少时同样只报 warning |
| 推进到 `_done` | 检查本节点的必需输入和必需输出都存在且非空（output-spec.md §4.4）；缺少或为空时只在 `warnings` 中逐条列出（`推进到 <cp> 时必需产物缺失: …`），照常推进，并写一条 `eventId = artifact-check`、`eventStatus = warning` 的变更日志。拦截由钩子 `artifact_guard.py` 在执行这条命令之前完成（§4.7，D61）。`validate` 不为 `null` 时再执行节点校验命令（§4.4），通过才写入 |
| 推进到 `archived` | 只能从终态节点前一个节点的 `_done` 推进；检查终态节点的必需输入，不执行校验命令。之后不能再推进或重开 |
| 动态阶段选择（v2） | v1 运行框架不实现，`flow.json` 的 `dynamicStages` 不为 `[]` 时拒绝加载（D59）。v2 的规则：当前 checkpoint 是选择点时，推进到阶段第一个节点的 `_in_progress` 记为执行，推进到下一个主干节点的 `_in_progress` 记为跳过，写入 `workflowDecisions`。阶段执行时，最后一个节点 `_done` 的下一个是下一个主干节点的 `_in_progress` |
| 重开 | 必须加 `--reopen` 和非空的 `--reason`；只能回到当前或之前节点的 `_in_progress`。下游节点在看板上显示为未开始，旧产物保留。重开不执行校验命令。v2 有动态阶段和跳过节点后，还可以回到已执行的动态阶段节点，回到选择点之前时清除该阶段的决定，回到被跳过节点之前时恢复这些节点 |
| 跳过节点（v2） | v1 不提供 `--skip-node`，`flow.json` 的 `skip` 不为 `null` 时拒绝加载（D59）。v2 的规则：`skip` 不为 `null` 时，`--skip-node` 加非空的 `--reason`，不能与 `--checkpoint` 同时使用；规则见 input-config.md §2.8，与 `skip_node.py` 共用 `engine.skip_nodes` |
| `--dry-run` | 执行全部检查（包括校验命令），但不写 `state.json`、不写变更日志 |
| 定位 | 省略 `--workspace` 时，使用 `PLUGIN_WORKSPACE` + `PROJECT_DIR`；省略 `--feature` 时，使用 `FEATURE_ID` |

```json
{ "ok": true, "changed": true, "feature": "f1", "oldCheckpoint": "plan_in_progress", "checkpoint": "plan_done",
  "statePath": "…", "dryRun": false, "warnings": [],
  "validation": { "ran": true, "passed": true, "exitCode": 0, "durationMs": 812, "timedOut": false, "output": "…" } }
```

`validation` 只在执行了校验命令时输出。校验不通过时返回 `ok:false`，`errors` 中包含退出码（或超时）以及命令输出的末尾部分，`state.json` 保持不变。

状态实际改变时（`changed: true` 且不是 `--dry-run`），提交后推送一条 `reason = update_state` 的看板事件（§3.5）。输出格式不变。

不再提供 `update_checkpoint.py` 别名：迁移进来的技能由状态维护片段统一指向新入口（旧版 `scaffold` 状态片段由 build 原地替换），正文中残留的状态命令和旧路径由 `check` 报 `LEGACY_ENTRY_REF`。

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

校验器负责判断格式、内容是否合格（D13），非空由框架检查。它应当只读：不得修改产物、`state.json` 或插件目录。

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

  `selectedDeployUnits` 已解析并校验；`knowledgePath` 为按 §3.3.7 选出的知识目录的绝对路径（`--knowledge-path-platform` 不为空时取它，否则取 `--knowledge-path`）；`featureDir` 在 Feature 尚未创建时为空字符串；
- **stdout**：`{"sessionContext": "…", "agentmdLoadStatus": [ … ], "message": "…"}`，三个字段都可以省略。`sessionContext` 是知识段，追加在流程上下文之后；`agentmdLoadStatus` 的条目格式见 §3.3.7；
- 工作目录为插件根目录，超时为 `knowledge.assembly.timeoutSec`（默认 30 秒）；
- 退出码非 0、超时或输出不是合法 JSON 时，本次会话不含知识段，`agentmdLoadStatus` 为 `[]`，在 `message` 中追加 `"知识组装失败: <原因>"`，`session_collector_context_inject` 仍然返回 `ok:true`；
- 只负责知识段：不能修改 `agentConfig` 和 `flow`，流程上下文和运行策略始终由默认入口给出；
- stdout 只用于协议 JSON，日志写 stderr；不得修改项目文件和知识目录，知识仓库同步是 `pull_knowledge` 的职责。

内置组装脚本的做法（来自全栈版）：调用同目录的 `collect-knowledge.js`（需要 Node）列出 collector 支持的发布单元，再逐个取所选单元的知识；collector 不可用（没有 Node、接口失败、超时）或单元不在它的列表中时，按清单映射加载，最后回退 `<localRepoPath>/AGENTS.md`。另外始终读取 `<sessionWorkspacePath>/AGENTS.md` 作为会话工作区指令。collector 依赖的 `gray-matter` 缺失时，首次运行会在 `runtime/knowledge/` 下执行 `npm install`（README §9）。

插件替换这个文件时，只需在同一路径实现上面的协议。主体逻辑可以用任何语言写，由这个 Python 文件调用（内置版本就是这样调用 Node 的）。doctor 重新生成或替换运行框架时都不覆盖被替换的文件（README §4）。

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
query.load_flow() -> dict                                        # runtime/config/flow.json，已校验不变量；dynamicStages 不为 [] 或 skip 不为 null 时抛 BoardError（D59）
query.resolve_project(workspace: str | None = None, project: str | None = None) -> Path
    # 显式参数优先；否则读 PLUGIN_WORKSPACE + PROJECT_DIR；拒绝插件安装目录
query.resolve_feature(feature: str | None = None, *, required: bool = True) -> str
    # 与 FEATURE_ID 冲突时报错；校验路径安全
query.metadata_dir(project_path: Path) -> Path
    # <project>/<metaRoot>，metaRoot 默认 .autobizdevops
query.feature_dir(project_path: Path, feature: str) -> Path      # metadata_dir(...) / "features" / feature

# —— query：流程与状态 ——
query.list_features(project_path: Path) -> list[dict]
query.feature_record(project_path: Path, feature: str) -> dict | None
query.current_node(project_path: Path, feature: str) -> tuple[dict, str]   # (节点, "in_progress"|"done")
query.next_node(node_id: str, record: dict | None = None) -> dict | None
    # v1 按 seq 线性求下一节点；v2 再按 Feature 记录中的 workflowDecisions、workflowSkippedNodes 求
query.active_nodes(record: dict) -> list[dict]                   # 该 Feature 实际经过的节点；v1 即全部节点，v2 含已执行的动态阶段节点、不含被跳过的
query.node_skill(node_id: str) -> str
query.node_artifacts(node_id: str, direction: str = "outputs") -> list[dict]
query.checkpoint_chain() -> list[str]

# —— query：产物存在情况 ——
query.artifact_presence(project_path: Path, feature: str, artifact_id: str) -> dict
    # {"exists": bool, "files": [Path], "missing": [pattern], "empty": [Path]}；空文件不算存在；拒绝越界符号链接

# —— engine：初始化与状态变更 ——
engine.init_project(project_path: Path) -> dict
engine.init_feature(project_path: Path, feature: str, *, owner: str | None = None,
                    iteration: str | None = None, template: str = "standard") -> dict
engine.transition(project_path: Path, feature: str, checkpoint: str, *, reopen: bool = False,
                  reason: str = "", dry_run: bool = False) -> dict
    # 状态转移检查（含 archived）→ 产物存在且非空检查（只提醒，写入 warnings）→ （_done 且 validate 不为 null 时）校验命令
    # → 加锁提交 state.json → 写变更日志
# v2 再加 query.pending_choice（停在选择点时的待选项）和 engine.skip_nodes（跳过节点），v1 不提供（D59）
# 以上函数提交时都在锁内把 state.json 的 boardSeq 加 1，返回值中带 "boardSeq"，供入口推送看板事件（§3.5）

class query.BoardError(ValueError): ...                           # 所有业务错误都抛这个类型；engine、cli 从 query 导入（D59）
```

使用范围：

- 框架入口（`runtime/` 下的脚本）和框架模块（知识模块、产物同步脚本）与运行框架同版本发布，可以导入这两个模块；
- 开发者的技能脚本、校验器和自定义扩展不需要、也不应该导入它们：所需的路径和状态从会话上下文、校验命令占位符和环境变量获得；
- 两个模块不承诺对开发者代码的接口稳定性，随运行框架版本一起变化。

---


### 4.7 默认钩子 artifact_guard.py（D61）

build 把产物检查脚本拷到插件根目录的 `hooks/artifact_guard.py`（managed，模板在脚手架的 `runtime/hooks/`），并在 `hooks/hooks.json` 中注册；`plugin.json` 的 `hooks` 固定指向 `./hooks/hooks.json`。`hooks/hooks.json` 由脚手架和开发者共用：脚手架只维护自己的条目——命令指向 `hooks/artifact_guard.py` 或 `hooks/<全局钩子 id>/` 下脚本的条目，每次重新生成都排在各事件的最前面并按当前配置重写；其他条目是开发者的，按原顺序原样保留。生成的条目也是给开发者打样的写法：

```json
{
  "PreToolUse": [
    { "matcher": "execute",
      "hooks": [ { "type": "command", "command": "python -X utf8 hooks/artifact_guard.py", "timeout": 30,
                   "onBlock": { "reason": "产物检查不通过", "systemMessage": "必需产物缺失或为空",
                                "additionalContext": "补全必需产物后再执行技能完成命令" },
                   "persistAfterInterrupt": true } ] },
    "…开发者 PreToolUse 条目按原顺序接在后面"
  ],
  "…开发者的其他事件原样保留": []
}
```

- 合并规则：默认钩子放在 `PreToolUse` 最前面；其次是插件全局钩子模块 `globalHooks` 启用的钩子，按 `modules/globalHooks.json` 中列出的顺序（§4.8）；框架和模块通过 `Contribution.hooks` 贡献条目，按合并顺序 framework → … → globalHooks 追加；开发者的条目按原顺序接在最后。文件包在 `{"hooks": {…}}` 下时保持这种写法，否则写成顶层事件（与全栈版 `autobiz_kanban` 的写法一致）；没有这个文件时 build 创建它。开发者改了自己的条目不需要重新生成，lint 也不报 `BUILD_STALE`；改了脚手架的条目会在下次生成时被重写。build-manifest 把它记为 `seeded`，`regions.hooks` 是脚手架条目的摘要。结构不是“事件名 → 条目对象数组”时报 `PLUGIN_HOOKS_INVALID`；入口文件的 `plugin.hooks` 可以不写，写了只能是 `./hooks/hooks.json`，否则报 `PLUGIN_HOOKS_PATH`（input-config.md §7.1）；
- 输入：宿主从 stdin 传入的 JSON，命令取自 `tool_input.command`（或 `cmd`、`script`、顶层 `command`）。命令按 POSIX 规则拆分，展开 `sh -c`、`bash -lc`、`cmd /c` 包装，按 `&&`、`||`、`;`、`|` 拆成多条；
- 只处理 `update_state.py --checkpoint <节点>_done`（也接受 `--checkpoint=<cp>`）：按命令中的 `--workspace`、`--project`、`--feature`，缺省时按 `PLUGIN_WORKSPACE`、`PROJECT_DIR`、`FEATURE_ID` 定位，用 `engine.check_artifacts` 检查该节点的必需输出；
- 有缺失或为空的产物时：stdout 输出 `{"decision": "block", "reason": "不能推进到 <cp>：必需产物缺失: …", "systemMessage": …}`，原因同时写 stderr，以退出码 2 退出；
- 其余情况都以 0 退出、不输出：其他命令、`_in_progress`、`archived`、`--reopen`、`--dry-run`、Feature 已在该 checkpoint、无法定位项目或 Feature、Feature 不存在。这些情况交给 `update_state.py` 自己报告，钩子出错不影响流程；
- 命令中的解释器写 `python`，脚本路径相对插件根目录，与全栈版 `hooks.json` 的写法一致。


### 4.8 插件全局钩子模块 globalHooks（D62）

`globalHooks` 是一个非核心模块（`modules/globalHooks.json`，input-config.md §4.6），启用脚手架自带的公共宿主钩子。模块包在 `booter/scaffold/modules/global_hooks/`，每个钩子是 `hooks/` 下的一个目录：

```text
scaffold/modules/global_hooks/
├── module.json  module.py          # 模块契约：validate 检查 id，contribute 贡献脚本和钩子条目
├── catalog.py                      # catalog()：扫描 hooks/*/hook.json
└── hooks/
    ├── secrets_check/
    │   ├── hook.json               # id、title、description、files、entries
    │   └── files/check_secrets.py
    └── performance_check/
        ├── hook.json
        └── files/performance_checker.py
```

```json
{
  "id": "secrets-check",
  "title": "明文密码检查",
  "description": "写入 .yaml/.yml/.properties 时发现明文的密码、密钥、token 就拦截，提示先加密再写入",
  "files": ["check_secrets.py"],
  "entries": { "PreToolUse": [ { "matcher": "write_file|edit_file|apply_patch",
    "hooks": [ { "type": "command", "command": "python -X utf8 ${hookDir}/check_secrets.py", "timeout": 1000,
                 "persistAfterInterrupt": true } ] } ] }
}
```

- `catalog()` 扫描 `hooks/*/hook.json` 得到全部钩子，源码运行和 `.pyz` 中都通过 `importlib.resources` 读取。**新增钩子只需在 `hooks/` 下加一个目录**：写 `hook.json`，把脚本放进 `files/`，不用改代码；`hook list`、向导和 `--answers` 自动包含它。`tests/test_global_hooks.py` 检查每个钩子的文件齐全、`entries` 只引用自己的文件；
- `id` 为 kebab-case，全局唯一；`entries` 的写法与 `hooks.json` 相同，`command` 中的 `${hookDir}` 在 build 时替换为 `hooks/<id>`；
- `contribute` 把 `files` 拷到插件根目录的 `hooks/<id>/`（module），条目放进 `Contribution.hooks`，由 build 写进 `hooks/hooks.json` 中脚手架维护的部分（§4.7）；
- 脚本自带的协议由脚本决定：拦截时以退出码 2 退出或输出 `{"decision": "block", …}`，放行时以 0 退出。

| id | 来源 | 事件 / matcher | 做什么 |
|---|---|---|---|
| `secrets-check` | 全栈版 `hooks/check-secrets-new.py`，原样 | PreToolUse / `write_file\|edit_file\|apply_patch` | 写入 `.yaml`、`.yml`、`.properties` 时，键以 password、secret、pwd、key、token 结尾（以及 Redis、Kafka、Zookeeper 的密码项）且值不是加密、掩码或变量引用时，以退出码 2 拦截 |
| `performance-check` | 全栈版 `hooks/performance_checker.py`，适配新入口 | PreToolUse / `execute` | 命令是 `update_state.py`（或旧的 `update_checkpoint.py`）推进到 `code_done` 时，对工作区 `git diff` 中变动的前端文件执行 7 条性能规则，发现问题输出 block。工作区取 `WORKSPACE_PATH`，缺省时取 `PLUGIN_WORKSPACE/PROJECT_DIR`；触发的 checkpoint 写在命令参数中，固定为 `code_done` |

## 5. 版本与兼容

| 版本号 | 位置 | 何时升级 |
|---|---|---|
| `scaffoldVersion`（入口文件格式） | `plugin.scaffold.json` | 入口文件格式出现不兼容变化时升主版本。v1 不提供迁移命令，格式升主版本时再定；入口文件的版本比脚手架支持的高时报 `SCAFFOLD_OUTDATED`（D57） |
| 脚手架版本 | build-manifest 的 `scaffoldVersion`、`autobiz-plugin.pyz` | 遵循 semver；当前脚手架比记录旧时报 `SCAFFOLD_OUTDATED`，doctor 拒绝执行（D57） |
| 模块配置格式 | `modules/*.json` | 不单独标版本，随模块主版本变化；出现不兼容变化时由模块提供迁移 |
| 核心流程格式 | `workflow.json` | 不单独标版本，随 `scaffoldVersion` 变化 |
| `apiVersion` | `board_core/board_config.json`、`board_core/modules.json` | 宿主协议出现不兼容变化时（与 DevClaw 共同决定） |
| 运行框架版本 | build-manifest 的 `coreVersion` | 遵循 semver；同一主版本内 doctor 直接替换，跨主版本要 `doctor --allow-major-upgrade`，比记录旧时拒绝（D57） |
| 模块版本 | 模块包的 `module.json`、插件的 `board_core/modules.json`、build-manifest | 遵循 semver；board、session 取 `coreVersion`，knowledge、artifactSync 各自维护；模块随脚手架一起发布，v1 不检查模块与运行框架的版本是否匹配（D50） |
| `state.json.schemaVersion` | 运行期 | 状态格式变化时；新版运行框架必须能读取旧版本 |
| `schemaVersion` 字符串 | 各命令输出 | 例如 `autobizdevops.workflow.templates.v2`、`autobizdevops.agents.sync.v1`；沿用现有值 |
| `boardEvents.protocol` | `board_core/modules.json`、看板事件的 `params.schema` | 看板事件消息出现不兼容变化时，例如 `autobiz.board-events.v1` → `v2`（§3.5） |

兼容承诺：

- 由 lite 迁移过来的插件只要保持 `plugin.id` 和默认的 `metaRoot` 不变，已有项目的 `state.json` 可以直接继续使用；
- 现有全栈版插件的产物同步 v1 配置，在新模块中仍可读取；
- 全栈版迁入后保持默认的 `metaRoot`；它已有项目的 `state.json`（`autobizdevops.state.v3`，不带 `pluginId`）可以直接读取，第一次写入时备份并升级，停在当前流程没有的 checkpoint 上的 Feature 只读（D60，output-spec.md §4.2）。

由 lite 迁移时的行为差异：

- 入口从 `hooks/`、根目录迁到 `runtime/`，board_config 中的命令随之重新生成；board_config 只剩 `inspectCommands`，流程定义改由命令输出，看板入口移到 `modules.json`；技能中旧的 `scaffold` 状态片段原地替换成 `plugin workflow` 状态维护片段，`artifacts` 托管片段删除；
- 完成判定的标准不变：必需产物存在且去掉首尾空白后非空（D37）；不满足时由钩子 `artifact_guard.py` 拦截完成命令，`update_state.py` 本身只报 warning（D61）；v1 也不能配置校验命令；
- 会话内容新增流程上下文段；会话入口的键由 `session_context_inject` 改为 `session_collector_context_inject`；宿主命令统一加 `-X utf8`（lite 原来没有）；
- 产物显示名不再配置，取路径本身（lite 的“结构化需求”“实施计划”等名称不再保留）；节点描述改为取技能的 `description`、`nextAction` 改用默认文案，lite 的节点文案覆写不再保留；产物 id 改由路径推导（`requirements` → `prd`、`specs` → `spec`）；
- `plan.md` 对旧文件名 `PLAN.md` 的回退不再支持。macOS、Windows 默认文件系统不区分大小写，不受影响；Linux 上的旧 Feature 需要把文件改名。
