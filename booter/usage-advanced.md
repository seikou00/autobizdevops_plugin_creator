# 进阶用法：完整定制

按命令和配置文件逐项说明脚手架能定制什么。只想尽快出一个插件看 [usage-quickstart.md](usage-quickstart.md)；字段的默认值、推导和校验规则以 [docs/input-config.md](../docs/input-config.md) 为准，命令的完整契约以 [docs/interfaces.md §1](../docs/interfaces.md) 为准。

## 1. 运行方式

| 方式 | 命令前缀 |
|---|---|
| 源码直跑 | 在 `booter/` 下 `python3 -m scaffold`；任意目录下 `python3 <booter 目录>`（`booter/SKILL.md` 用这种方式） |
| 单文件 | 在 `booter/` 下 `python3 tools/make_pyz.py`，之后任意目录 `python3 <路径>/dist/autobiz-plugin.pyz` |

下文统一写作 `python3 -m scaffold`，`P` 代表插件目录。

- 全局参数：`-C <插件目录>`（默认当前目录）、`--json`（机器可读输出，适合 CI 和脚本）；
- 退出码：`0` 成功（可能带 warning），`1` 有 error 且没有写入任何文件，`2` 用法错误；
- 所有修改命令先在内存中完成并跑一次 doctor，任何一步有 error 都不写盘。

## 2. 插件目录

```
P/
├── plugin.scaffold.json      # 入口：插件元信息、运行参数、对下面各文件的引用
├── workflow.json             # 流程节点
├── modules/
│   ├── board.json            # 看板展示
│   ├── session.json          # 会话与运行策略
│   ├── knowledge.json        # 知识模块（可选）
│   └── artifactSync.json     # 产物同步模块（可选）
├── skills/autobiz|autodev|autoops/<skill>/   # 节点技能按节点阶段分组；辅助技能可以直接放 skills/<skill>/
├── agents/                   # 子代理文件，由 session.json 引用（可选）
├── hooks/                    # hooks.json（脚手架的条目 + 你的条目）、artifact_guard.py，以及你自己的钩子脚本
├── .mcp.json                 # 可选，透传进 plugin.json
├── .scaffold/                # Schema，IDE 补全用，脚手架维护
├── plugin.json、board_core/、runtime/   # 生成；其中的对话提示和展示文案可以手改，见下文
└── dist/                     # package 的输出
```

托管文件（`runtime/` 下的脚本、`hooks/artifact_guard.py` 等）被手改后 doctor 会拒绝覆盖，确认要覆盖时用 `doctor --force`；其余生成文件每次按核心配置重写，手改了 `check`、`package` 会报 `DRIFT_GENERATED`，下面列出的文字字段除外。

**可以手改的文字**：对话提示和展示文案不影响流程，生成后可以直接改：

| 文件 | 可以改的字段 |
|---|---|
| `plugin.json` | `name`、`description` |
| `board_core/board_config.json` | 各平台（`darwin`、`linux`、`win32`）的 `dialog_tips`、`system_prompt_inject`，每个平台分别改 |
| `runtime/config/board.json` | `template.label`、`template.description`，`stateLabels` 中的状态名，节点的 `description`，以及 `nextAction` 各状态下的 `userMessage`、`dialogTips` |

- 改过的文字在 `doctor`、`package` 时保留，build-manifest 的 `customized` 记下这些字段，doctor 的输出在“保留手改的文字”中列出；
- 文件的其余部分照常按核心配置重写：增删节点、改节点名、启用模块等变化照样生效，你没改过的文字也跟着更新；`plugin.json` 的 `version` 由 `package` 递增；
- 你改过的字段，如果核心配置的变化也改到了它（例如默认的对话提示含节点链，改了节点名），保留你的版本并报 `CUSTOMIZED_STALE`，确认一下文字是否还合适；
- 改了这些字段以外的内容（命令、`slashSkill`、节点 `id` 等），`check`、`package` 报 `DRIFT_GENERATED`，`doctor` 会把它们改回生成内容；
- 文件必须仍是合法的 JSON 对象（否则报 `CUSTOMIZED_INVALID`），改过的文字中的 `[TODO: …]` 要在打包前填完；
- 想全部恢复成生成内容，删掉文件再执行 `doctor`；文件按标准格式（两格缩进）重写，你的缩进和键顺序不保留，只保留值；
- 其余生成文件（`board_core/modules.json`、`runtime/config/` 下的其他文件）照旧不能改。

## 3. 核心配置

用 `module list` 查看模块简介，新建插件前也能运行。`--json` 输出的 `guide` 是填写指南相对 `booter/` 的路径：

| 模块 | 填写说明 |
|---|---|
| `board` | [scaffold/modules/board/guide.md](scaffold/modules/board/guide.md) |
| `session` | [scaffold/modules/session/guide.md](scaffold/modules/session/guide.md) |
| `knowledge` | [scaffold/modules/knowledge/guide.md](scaffold/modules/knowledge/guide.md) |
| `artifactSync` | [scaffold/modules/artifact_sync/guide.md](scaffold/modules/artifact_sync/guide.md) |

下面只补充说明文件里没有的细节。

### 3.1 `plugin.scaffold.json`

| 字段 | 说明 |
|---|---|
| `plugin.id` | 英文字母、数字、短横线和下划线，不超过 64 字符；发布后修改要 `doctor --allow-id-change` |
| `plugin.name`、`version`、`description` | 必填（连同 `id`），写进 `plugin.json` |
| `plugin.author{name,email,url}`、`homepage`、`repository`、`license`、`keywords` | 可选，写进 `plugin.json` |
| `plugin.mcpServers` | 指向 `.mcp.json`，原样透传 |
| `plugin.hooks` | 可以不写；写了只能是 `./hooks/hooks.json`（见 §3.7） |
| `runtime.metaRoot` | 元数据根目录，默认 `.autobizdevops`；同一项目装多个插件时各自不同；修改要 `doctor --allow-layout-change` |
| `workflow`、`modules.*` | 对其他核心配置的引用 |

### 3.2 `workflow.json`

```json
{
  "nodes": {
    "biz": [{ "id": "prd", "seq": 1, "name": "需求", "skill": "autobiz-prd", "outputs": ["PRD.md"] }],
    "dev": [{ "id": "code", "seq": 2, "name": "编码", "skill": "autodev-code" }],
    "ops": [
      { "id": "cicd", "seq": 3, "name": "CI/CD", "skill": "autoops-cicd",
        "outputs": ["CICD_CHECKLIST.md", { "path": "PR_BODY.md", "optional": true }] },
      { "id": "archive", "seq": 4, "name": "归档", "skill": "autoops-archive", "terminal": true }
    ]
  }
}
```

- 节点按 `seq` 串成主干，`seq` 全局不能重复；每个节点有 `<id>_in_progress`、`<id>_done` 两个 checkpoint；
- `outputs` 可以写 glob（`specs/**/*.md`），也可以写 `{path, optional: true}` 标为可选；没有输出的节点省略 `outputs`；
- `terminal: true` 是终态节点，只推进到 `archived`，不能有输出，最多一个；
- 多个节点声明同一输出时，以第一个为生产者，报 `OUTPUT_REDECLARED` warning；
- 节点的看板文案（描述、`nextAction`）由 build 推导，不在这里配置。

### 3.3 `modules/board.json`

`display` 下：`workflowLabel`、`workflowDescription`、`dialogTips`、`systemPromptInject`。文案里可以用 `${projectCode}`、`${pluginWorkspace}`、`${projectDir}`、`${feature}`、`${pluginPath}`。覆写 `systemPromptInject` 时，其中的产物目录要与 `runtime.metaRoot` 一致。

### 3.4 `modules/session.json`

按节点设置会话策略：

```json
{
  "policies": {
    "nodes": {
      "dev": [{
        "id": "plan",
        "agentMode": "multi",
        "toolCustomConfig": { "task": { "enabled": true } },
        "subagentConfig": {
          "disabledBuiltinSubagents": ["Explore", "critic"],
          "customSubagentFiles": ["agents/explore.md", "agents/critic_autodev_plan_zh.md"]
        }
      }]
    }
  }
}
```

- `agentMode`：`multi`、`agent_team`、`workflow` 等；
- `customSubagentFiles` 引用的文件不存在时报 `SUBAGENT_FILE_MISSING` warning，运行时跳过。

### 3.5 `modules/knowledge.json`（可选）

启用前要定两件事：知识目录从哪来（Git 仓库、随插件打包放在 `sys/`、由 DevClaw 提供），以及由插件还是 DevClaw 把知识拼进上下文。每个选项怎么写见 [guide.md](scaffold/modules/knowledge/guide.md)。

- 由插件组装时，组装脚本是 `runtime/knowledge/render_collected_session_context.py`，可以整个替换成自己的实现，doctor 不会覆盖；
- 项目在 DevClaw 中绑定了知识库时，总是优先用绑定的知识库，插件的 `sys/` 只在没有绑定时使用。

### 3.6 `modules/artifactSync.json`（可选）

字段见 [guide.md](scaffold/modules/artifact_sync/guide.md)。启用后会生成同步技能 `skills/autobizdevops-artifact-sync/`（技能名可用 `skillName` 修改），看板上带出“发起产物同步”入口。技能每次执行时：

1. 先向用户确认工号、Feature 和上传目录 `{PROJECT_CODE}/DEV/Features/{feature}/{工号}/`，确认后才继续；
2. 常规同步前，按实际代码生成或更新 Feature 目录下的接口交付文档 `FEATURE_API_DETAIL.md`。代码仓库取创建 Feature 时选定的发布单元（`localRepoPath`），没有时取会话工作区中的 Git 仓库；实现范围取这些仓库中带“cmbdevclaw提交”的提交。没有源码或没有接口变更时，在文档中说明，不阻断其他产物的同步；
3. 按同步配置上传有变化的产物，再上传产物清单 `ARTIFACT_CATALOG.json`；失败的上传保留记录，修复后可以重试。

产物清单中的 `category` 按文件名对照（如 `PRD.md` 为 `requirement`，`plan.md`、`PLAN.md` 为 `implementation_plan`），对照表中没有的文件为 `artifact`。

### 3.7 钩子与产物检查

生成的插件默认注册一个宿主钩子：脚本是 `hooks/artifact_guard.py`，注册在 `hooks/hooks.json` 的 `PreToolUse`（`execute`）第一条，`plugin.json` 的 `hooks` 固定指向 `./hooks/hooks.json`。

| 检查点 | 时机 | 必需产物缺失或为空时 |
|---|---|---|
| 钩子 `artifact_guard.py` | 模型执行 `update_state.py --checkpoint <节点>_done` 之前 | 拦截这条命令，告诉模型缺哪些、哪些为空，补齐后重试 |
| `update_state.py` | 推进状态时 | 冗余检查，只在 `warnings` 中报告并写 `artifact-check` 变更日志，照常推进 |

- **你自己的钩子直接写在 `hooks/hooks.json` 里**，照着脚手架生成的条目打样，脚本也放在 `hooks/` 下。写法 `{"PreToolUse": [{"matcher": …, "hooks": […]}]}` 或包在 `{"hooks": {…}}` 下都可以；
- 命令指向 `hooks/artifact_guard.py` 或 `hooks/<全局钩子 id>/` 的条目归脚手架：每次重新生成都排在最前面并按当前配置重写，手改会被覆盖；其他条目都是你的，原样保留；
- 改自己的条目直接生效，不需要 doctor；结构不对报 `PLUGIN_HOOKS_INVALID`；
- 钩子命令写的是 `python -X utf8 hooks/artifact_guard.py`，路径相对插件根目录。

## 4. 新建插件：`new`

```bash
python3 -m scaffold new <目录> [--yes --answers <file>|-]
```

| 写法 | 效果 |
|---|---|
| `new P` | 交互向导；回答先在内存中校验，有错时让你重答，放弃则什么都不写 |
| `new P --yes --answers a.json` | 不提问，完全由回答生成，必须给出 `plugin` 和 `nodes` |
| `new P --skeleton [--module <id> …]` | 只写出带 `[TODO: …]` 占位的核心配置骨架，不生成插件；填完后 `lint` 查看还缺什么，再 `doctor`、`package`（见下文） |

回答文件（`-` 表示从 stdin 读取）：

```json
{
  "plugin": { "id": "my-plugin", "name": "My Plugin", "version": "0.1.0", "description": "示例插件" },
  "nodes": [
    { "stage": "biz", "id": "prd", "seq": 1, "name": "需求", "skill": "my-prd", "outputs": ["PRD.md"] },
    { "stage": "dev", "id": "code", "seq": 2, "name": "编码", "skill": "my-code" }
  ],
  "board": { "display": { "workflowLabel": "需求开发" } },
  "artifactSync": { "allowedFrom": "prd:done", "artifacts": { "PRD.md": "需求" } },
  "skills": { "my-prd": "/path/to/my-prd", "my-code": null },
  "agents": "/path/to/agents"
}
```

- `plugin`、`nodes` 必填；`board`、`session` 不写就用默认值；可选模块 `knowledge`、`artifactSync` 写了即启用。脚手架给插件 ID 和名称加上 `AutoBizDevOps_` 前缀，已带前缀时直接沿用；
- `skills` 是技能名 → 技能目录，`null` 表示先不提供（生成空白 `SKILL.md`）；要逐个写，导入到 `skills/<skill>/`，不保留分组。整个技能集合（尤其是分组的集合）建议 `new` 之后用 `add skills --from` 导入；
- `agents` 是 agents 目录，原样拷到 `P/agents/`；不写就不创建 `agents/`；

由回答生成插件，再带上分组的技能和 agents（技能会引用 `skills/references/`、`skills/autobiz/hooks/` 等共享路径，所以用 `add skills` 整体导入，而不是在 `--answers` 里逐个列出）：

```bash
cd ~/Documents/GitHub/autobizdevops_plugin_creator/booter
G=~/Documents/GitHub; OUT=$G/my-plugin

python3 -m scaffold new $OUT --yes --answers answers.json
python3 -m scaffold -C $OUT add skills --from $G/my-skills --agents $G/my-agents
```

**只写骨架**：想自己手写配置时，先让脚手架按 Schema 写出结构，再照着占位填：

```bash
python3 -m scaffold new P --skeleton --module board --module artifactSync
```

- 写出 `plugin.scaffold.json`、`workflow.json`（biz、dev 各一个节点）、`--module` 选中的模块配置，以及 IDE 补全用的 `.scaffold/` Schema；可选模块：`board`、`session`、`knowledge`、`artifactSync`；
- 要填的地方都写成 `[TODO: 说明]`，插件 ID 和名称保留预填的 `AutoBizDevOps_` 前缀；`lint` 每个占位报一条 `TODO_FIELD`，带文件和 JSON Pointer。还有占位时 `doctor` 不生成（`artifactSync` 的简述除外：可以先生成，打包前填完）；
- 填完后：

```bash
python3 -m scaffold -C P lint       # 确认没有 TODO_FIELD
python3 -m scaffold -C P doctor     # 生成插件，技能不存在时生成空白 SKILL.md
python3 -m scaffold -C P package    # 技能和简述也要填完
```

## 5. 增量修改

### 5.1 节点

```bash
python3 -m scaffold -C P add node review --name 评审 --skill doc-review --stage dev --seq 5 \
  --output REVIEW.md --optional-output "notes/*.md"
python3 -m scaffold -C P add node archive --name 归档 --skill my-archive --stage ops --seq 9 --terminal
```

按 `seq` 插到组内对应位置，不改其他节点的 `seq`；含 glob 的路径要加引号；技能不存在时生成空白 `SKILL.md`。删除、改名节点直接编辑 `workflow.json`，再执行 doctor。

### 5.2 技能和 agents

```bash
python3 -m scaffold -C P add skill doc-review --from ../skills/doc-review   # 导入一个
python3 -m scaffold -C P add skill doc-review                               # 创建空白 SKILL.md
python3 -m scaffold -C P add skills --from ../skills --agents ../agents     # 导入整个技能集合（含分组），可同时拷 agents
```

- `add skills` 把来源目录当作插件的 `skills/` 导入，以目录名为技能名，最多一层分组（与 build 查找技能的 `skills/<skill>/`、`skills/<分组>/<skill>/` 一致）：

  | 来源中的位置 | 识别为 | 导入到 |
  |---|---|---|
  | `<集合>/<x>/SKILL.md`，`<x>` 的子目录都不含 `SKILL.md` | 技能 | `skills/<x>/` |
  | `<集合>/<g>/<x>/SKILL.md` | 分组 `<g>` 下的技能 | `skills/<g>/<x>/` |
  | 集合根目录、分组目录下的其他内容（自己的 `SKILL.md`、`references/`、`hooks/` 等） | 共享资源 | 原路径，例如 `skills/references/`、`skills/<g>/hooks/` |
  | 技能目录内更深层的 `SKILL.md` | 技能自己的资源 | 随技能拷贝 |

  - 来源本身是一个分组（自己含 `SKILL.md`、下面是技能，例如 `my-skills/autodev`）时按 `skills/autodev/<skill>/` 导入，所以分组逐个导入和整体导入的结果一致；
  - 共享资源已存在时，内容相同就跳过，不同就拒绝导入；其中的 `SKILL.md` 同样迁移 frontmatter；
  - 脚手架生成的技能（如产物同步模块的 `autobizdevops-artifact-sync`）跳过不导入；同名技能在集合中出现两次时拒绝导入；
  - 生成的空白 `SKILL.md` 会被导入的同名技能替换；
  - 导入后 doctor 把节点技能挪进节点阶段对应的分组目录（biz → `skills/autobiz/`，dev → `skills/autodev/`，ops → `skills/autoops/`），平铺的集合也一样，见下文「技能目录」；
  - 未被节点绑定的技能也会导入，原样交付；
- 导入时 frontmatter 的 `name` 改为目标技能名，顶层 `version`、`author` 迁到 `metadata`；
- 技能已存在或其他分组下有同名技能时拒绝导入（同一集合重复导入也会被拒绝）；只有 build 生成的空白 `SKILL.md` 可以被导入覆盖；
- `--agents`：已有同名文件且内容相同时跳过，内容不同时拒绝导入；
- 正文中的旧状态命令（`LEGACY_ENTRY_REF`）导入时只报 warning，`check`、`package` 时是 error，必须手工删掉。状态维护片段由脚手架写在 `SKILL.md` 开头，不要手改。
- 正文引用的文件在插件里不存在时报 `SKILL_REF_DANGLING`（warning，`doctor`、`check`、`package` 都报）：检查 `${pluginPath}/…` 路径和以 `templates/`、`references/`、`scripts/`、`hooks/`、`agents/`、`assets/` 开头的相对路径。`add skills` 只搬技能集合目录，原插件根目录 `hooks/` 下由技能调用的脚本要自己拷进插件的 `hooks/`；
- 正文里写死的绝对路径（含 `skills` 或上述资源目录的 `/…`、`~/…`、`C:\…`）报 `SKILL_REF_ABSOLUTE`（warning），改成 `${pluginPath}/…` 或相对技能目录的路径；

**技能目录**：节点技能按节点所属阶段放进分组目录，与技能名无关：

| 节点阶段 | 技能目录 |
|---|---|
| biz | `skills/autobiz/<skill>/` |
| dev | `skills/autodev/<skill>/` |
| ops | `skills/autoops/<skill>/` |

- 空白 `SKILL.md` 直接生成在这里；
- 技能放在别处（平铺在 `skills/<skill>/`、在别的分组，或节点换了阶段）时，`lint` 报 `SKILL_LAYOUT`，`doctor` 会把整个技能目录挪过去，并把 `skills/` 下文件中对旧路径的引用（如 `${pluginPath}/skills/<skill>/references/…`）改成新路径；挪了哪些列在 `changes.skills.moved`。目标目录已存在时报 `SKILL_LAYOUT_CONFLICT`，什么都不写；
- 不绑定节点的辅助技能（如回滚、评审）和模块生成的技能（如产物同步）不分组，放在哪里就在哪里。

### 5.3 模块

```bash
python3 -m scaffold -C P module list
python3 -m scaffold -C P module enable knowledge --set assembly.assembler=devclaw --set source.url=https://…
python3 -m scaffold -C P module enable artifactSync --set allowedFrom=plan:done
python3 -m scaffold -C P module disable knowledge
```

- `board`、`session` 始终启用；可以开关的是可选模块 `knowledge`、`artifactSync`；
- 不确定要不要某个模块，先 `module list` 看说明；
- `enable` 在模块配置不存在时创建骨架；`enable artifactSync` 会把非 `.json` 的输出预填进 `artifacts`，简述写成 `[TODO: 简述]`，删掉不需要的、补上简述；
- `--set` 的 key 沿 Schema 用 `.` 逐级指定，字符串原样保留，其余按 JSON 解析；`artifacts`、`extraPaths` 这类以路径为键的映射不能用 `--set`，直接编辑文件；
- `disable` 只去掉入口文件中的引用，`modules/*.json` 保留，之后 `enable` 会加回引用。

## 6. 重新生成：`doctor`

手改核心配置、改了节点技能 `SKILL.md` 的 `description`（会写进编译配置，不重新生成时报 `BUILD_STALE`），或更新了脚手架之后执行。流程是 lint → 与上次构建比较并列出影响 → build → 复查。

| 参数 | 作用 |
|---|---|
| `--dry-run` | 只列出将要发生的变化，不写文件 |
| `--force` | 覆盖被手改过的托管文件 |
| `--allow-id-change` | 确认修改 `plugin.id` |
| `--allow-layout-change` | 确认修改 `runtime.metaRoot` |
| `--allow-major-upgrade` | 确认运行框架跨主版本升级 |

## 7. 检查、模拟、打包

```bash
python3 -m scaffold -C P lint                    # 只检查核心配置
python3 -m scaffold -C P check [--strict]        # 再加技能内容、漂移检查和契约测试；--strict 把 warning 也当 error
python3 -m scaffold -C P simulate [--feature demo] [--to plan_done] [--platform darwin|linux|win32] [--keep]
python3 -m scaffold -C P package [-o out/my.zip] [--bump patch|minor|major|none]
```

- `simulate` 在临时目录中按宿主的方式走一遍流程：`--to` 停在某个 checkpoint，`--platform` 模拟其他平台的宿主命令，`--keep` 保留临时目录便于排查。知识目录中没有清单时会报 `KNOWLEDGE_MANIFEST_MISSING` warning，不影响流程。声明了 `knowledge.source` 时，`doctor` 会在 `sys/` 还没有清单时自动拉取知识仓库，拉取失败报 `KNOWLEDGE_PULL` warning；
- `package` 先做 check，技能里还有 `[TODO: …]` 占位时拒绝打包；通过后把 `plugin.scaffold.json` 的 `plugin.version` 递增一位并重新生成 `plugin.json`（默认 `--bump patch`：0.1.0 → 0.1.1；`minor`、`major` 递增对应位、低位归零；`none` 不改版本），默认输出 `P/dist/<plugin.id>-<新版本>.zip`。

CI 示例：

```bash
python3 -m scaffold -C P check --strict --json > check.json && python3 -m scaffold -C P package --json
```

## 8. 脚手架自身

```bash
cd booter     # 仓库根目录下；已在 booter/ 中可省略
python3 -m unittest discover -s tests -t .   # 金样、参考插件基线、契约、CLI 端到端和单元测试
python3 tests/check_schema_defaults.py       # input-config.md 的默认值与 Schema 是否一致
python3 tools/make_pyz.py                    # 发布 dist/autobiz-plugin.pyz
```

改了 `booter/examples/` 的输入后，要重新生成对应的 `output/` 金样（见 [examples/README.md](examples/README.md)）。
