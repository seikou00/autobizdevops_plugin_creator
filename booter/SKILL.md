---
name: autobiz-plugin-skeleton
description: 引导用户亲手搭建 AutoBiz 看板插件（DevClaw 插件）：生成带 [TODO] 占位的配置骨架，逐项讲解 workflow.json 和各模块配置怎么填，检查配置、导入或编写节点技能，最后打包成可以导入 DevClaw 的 zip。用户想新做或改造一个看板插件、问节点和模块配置怎么写、想把已有技能组装成插件，或者说“给我一个骨架我自己填”时，都应该使用这个技能，即使没有提到“骨架”两个字
metadata:
  version: 1.2.0
---

# 看板插件骨架引导

这个技能陪用户亲手做出一个 AutoBiz 看板插件：先生成只有结构和 `[TODO]` 占位的配置骨架，讲清每个字段的含义，由用户自己填；再检查配置、补齐节点技能，最后打成能导入 DevClaw 的 zip。

用户走这条路，通常是想看懂并掌握自己的配置，而不是拿到一份黑盒。所以你是向导：给选项、讲字段、跑命令、转述检查结果，配置和技能的内容由用户决定。你代写得越少，用户以后自己改插件就越顺手。

整体顺序是：选目录和模块 → 生成骨架 → 用户填配置 → 检查 → 处理节点技能 → 打包。用户已经走到某一步（比如骨架早就有了，只差打包），就从那一步接着做，不必从头来。

## 怎么问

需要用户拿主意时，用 `request_user_input` 出选择题。点选比打字省事，答案也更明确，后面拼命令时不容易出错。

- 每轮放 1–3 个相关的问题。每题有简短的 `header`、稳定的 `snake_case` `id`、完整的 `question`，以及 2–3 个互斥选项（`label` 加一句 `description`）；
- 你推荐的选项放第一个，`label` 末尾加 ` (Recommended)`，在 `description` 里用一句话说明为什么推荐；
- 客户端会自动提供 Other 自由输入，不用自己加。要路径、名称这类具体值时，选项给最常见的取值，并在问题里提示可以在 Other 中直接填写；
- 候选超过 3 个时，先在消息里列出完整清单，选择题里只放最可能的 2–3 个；
- 用户已经说清楚的就别再问；没说清楚的，等用户真的回答再往下走。目录或模块选错了，后面要返工。

## 调用 CLI

```bash
python "<booter>" <命令> --json
```

- `<booter>` 是本文件所在目录的绝对路径。CLI 直接从这个目录的源码运行（入口是目录下的 `__main__.py`），不用切换目录，也不用另外安装；
- 针对已有插件目录的命令加 `-C "<插件目录>"`；
- 退出码：`0` 成功（可能带 warning），`1` 有 error、没有写入任何文件，`2` 用法错误；
- `--json` 输出 `{"ok", "issues": [{level, code, file, pointer, message, hint}], "written": [...]}`。

检查结论以退出码和 `issues` 为准。CLI 会按 Schema、推导规则和契约测试逐项核对，光读配置文件看不全这些，所以不要在 CLI 之外自己下“没问题”的结论。转述 issue 时带上文件和位置，`message`、`hint` 尽量原样给出，用户照着就能找到要改的地方。

## 流程

### 1. 选目录和模块

先单独问 `plugin_dir`（插件放在哪个目录）。目录需要为空或尚未创建。推荐当前工作区下的 `my-plugin`，也可以给上一级目录下的 `my-plugin`，或让用户在 Other 中填写路径。

运行模块列表。它在新建插件前就可以用：

```bash
python "<booter>" module list --json
```

逐个介绍 `core` 为 `false` 的模块，原样展示 `title` 和 `description`，再为每个模块问一道“要／不要”的题。按用户的场景推荐，缺少线索时推荐“不要”。

- 选了知识，按列表中的 `guide` 路径读取知识指南。用「要定的两件事」提问 `knowledge_source`（知识从哪来）和 `knowledge_assembler`（谁把知识放进会话上下文）。选项说明取自表里的「怎么写」，在来源问题下附上表后的知识目录优先顺序。来源根据已有的知识目录、Git 仓库或 DevClaw 绑定情况推荐，组装方默认选插件。用户选 Git 时可以当场提供 HTTPS 地址，也可以留到第 2 步填写。

单独问 `custom_policy`（要不要自定义运行策略）。推荐“沿用默认”，各节点使用 `multi`。选“自定义”就生成 `modules/session.json`，可以设置全局默认策略，也可以覆盖单个节点。

生成骨架，在命令里为每个选中的可选模块追加一次 `--module <id>`：

```bash
python "<booter>" new "<插件目录>" --skeleton --json
```

自定义运行策略时加 `--module session`。用户想自定义看板名称、文案或目标平台时加 `--module board`。看板的流程名称默认取插件名。

生成后按选择写入配置，并告诉用户改了哪些字段：

- `knowledge_source` 选了 Git 仓库并给了地址：填进 `modules/knowledge.json` 的 `source.url`；没给地址就留着占位，等用户填；
- `knowledge_source` 选了随插件打包或由 DevClaw 提供：删掉 `modules/knowledge.json` 中的整个 `source`；
- `knowledge_assembler` 选了插件或 DevClaw：`assembly.assembler` 分别写 `plugin` 或 `devclaw`；

### 2. 讲清怎么填，交给用户

先按下文「填写指南」讲 `plugin.scaffold.json` 和 `workflow.json`。根据入口文件 `modules` 中的引用，用 `module list` 返回的 `guide` 路径（相对 `<booter>`）读取对应指南。

每个选中的可选模块展示一张卡片，标题用 `title` 加上配置文件名。四栏依次为「启用后多出什么」「什么时候需要」「要先准备什么」「最少要填哪些字段」。首栏直接用 `description`，其余三栏取自指南开头。已生成配置的看板和运行策略按各自指南讲解。需要填写的字段逐项讲清，告警等实际出现时再解释。

讲完问一道选择题：

| id | 要决定什么 | 推荐 | 其他选项 |
|---|---|---|---|
| `fill_mode` | 配置由谁来填 | 用户自己填，填好告诉你 | 用户描述流程，你起草，确认后再写入 |

- **用户自己填**：这时就等用户填完。用户正在编辑这些文件，你同时去改很容易覆盖对方的内容。用户问到哪个字段，就按填写指南或模块说明文件解释，必要时举个例子，最后怎么写由用户定；
- **你来起草**：先读同目录下的 `modeling-guide.md`，里面有节点拆分原则、产物写法和常见错误。请用户用一两句话描述流程，整理成“seq → 阶段 → 节点 id → 显示名 → 技能 → 产出文件”的表格给用户看，确认后再写进文件。

### 3. 检查配置

用户说填好了，运行：

```bash
python "<booter>" -C "<插件目录>" lint --json
```

- `TODO_FIELD` 是还没填的占位：按 `file`、`pointer` 列出来，用户一眼就能看到还差哪几处；
- 其他 error（例如 `SEQ_DUP`、`SEQ_STAGE_ORDER`、`SKILL_SHARED`、`ARTIFACT_REF_UNKNOWN`）：转述 `message` 和 `hint`，指出文件和位置，需要时结合填写指南说明正确写法；
- 只剩 warning 时可以往下走：`SKILL_MISSING` 下一步处理；artifactSync 简述的 `TODO_FIELD` 打包前填完就行。

有 error 就请用户改，改完再 lint，直到没有 error。lint 只读而且很快，多跑几次没关系。

### 4. 节点技能

| id | 要决定什么 | 推荐 | 其他选项 |
|---|---|---|---|
| `skill_source` | 节点技能从哪里来 | 已有技能集合目录（下一级是各技能，或者多一层 `autobiz/`、`autodev/`、`autoops/` 分组），Other 中填路径 | 没有，生成空白 `SKILL.md` 自己写；只有其中几个，其余生成空白 |

**导入已有技能**：如果 `modules/session.json` 引用了子代理文件，再问一下 agents 目录在哪（常见的是与技能集合同级的 `agents/`）。然后运行：

```bash
python "<booter>" -C "<插件目录>" add skills --from "<技能集合目录>" [--agents "<agents 目录>"] --json
```

- 这条命令导入技能的同时会生成插件：节点技能按阶段挪进 `skills/autobiz/`、`skills/autodev/`、`skills/autoops/`，正文里对旧路径的引用一并改掉（列在 `changes.skills.moved`），还没有技能的节点生成空白 `SKILL.md`；
- 技能目录名就是技能名，要与 `workflow.json` 中节点的 `skill` 一致。导入后仍然报 `SKILL_MISSING`，多半是名字没对上，告诉用户是哪个节点；
- `SKILL_REF_DANGLING` 表示技能正文引用的文件在插件里找不到：技能自己的 `templates/`、`references/`、`scripts/`，或者 `${pluginPath}/hooks/…` 这类放在原插件根目录、由技能直接调用的脚本。`add skills` 只搬技能集合目录，原插件根目录 `hooks/` 下的脚本要用户自己拷到插件的 `hooks/`。把缺的文件按技能列给用户，问清楚来源目录，拷完再跑 `doctor` 确认不再报；指的是用户工程里的路径时可以忽略；
- `SKILL_REF_ABSOLUTE` 表示技能正文里写死了绝对路径（例如 `/root/.openclaw/workspace/skills/…`），换一台机器就找不到。`hint` 里列出了插件中同名的文件时，建议用户改成那个 `${pluginPath}/…` 路径，用户同意后再改；
- `LEGACY_ENTRY_REF` 表示技能正文里残留了旧的状态命令（`update_state.py`、`hooks/update_checkpoint.py` 等）。现在节点状态由技能开头的片段统一维护，这些行留着会让状态被重复推进或推进错。把行号和所在小节告诉用户，用户同意后再删。

**生成空白技能**：运行 `doctor --json`，把 `changes.skills.created` 中的文件列给用户，讲清每个文件要写什么，然后等用户写完：

- frontmatter 的 `description`：写“做什么；在什么情况下使用”。看板上的节点描述也取自这里，写清楚了，看板使用者也能看懂这一步在干什么；
- 正文：这个节点的工作步骤、要产出哪些文件（与 `outputs` 一致）、做到什么程度才算完成（例如测试通过、评审结论明确）；
- 开头 `<!-- plugin workflow: begin state -->` 到 `<!-- plugin workflow: end state -->` 之间是状态维护片段，由脚手架按 `workflow.json` 写入，节点靠它推进状态。这一段不要动，正文里也不用再写调用 `update_state.py` 的命令；
- 参考资料放进技能目录的 `references/`，脚本放进 `scripts/`，并在正文里写明什么时候用哪个文件。

### 5. 打包

用户说技能都写好后，运行：

```bash
python "<booter>" -C "<插件目录>" doctor --json
python "<booter>" -C "<插件目录>" package --json
```

- 先跑 `doctor`，是因为技能的 `description` 会编译进看板配置，改过之后不重新生成，`package` 会报 `BUILD_STALE`；
- `package` 会先做完整检查。`TODO_PLACEHOLDER` 说明还有没填的 `[TODO: …]`（空白技能的 `description`、artifactSync 的简述等），`LEGACY_ENTRY_REF` 说明正文里还有旧状态命令。转述位置，请用户改完，再从 `doctor` 重来；
- 成功后告诉用户 zip 在哪：`package.path` 是相对插件目录的路径（默认 `dist/<plugin.id>-<version>.zip`），可以直接导入 DevClaw。每打一次包，版本号自动加一。

### 之后微调文案

用户看过生成结果，想改改对话提示或看板上的文字时，不用为此往核心配置里加字段，直接改生成文件中的这些文字即可，之后的 `doctor`、`package` 都会保留：

| 文件 | 可以改的字段 |
|---|---|
| `plugin.json` | `name`、`description` |
| `board_core/board_config.json` | 各平台（`darwin`、`linux`、`win32`）的 `dialog_tips`、`system_prompt_inject`，每个平台要分别改 |
| `runtime/config/board.json` | `template.label`、`template.description`，`stateLabels` 中的状态名，节点的 `description`，`nextAction` 各状态下的 `userMessage`、`dialogTips` |

这些文字不影响流程，所以放开给用户改，文件的其余部分仍按核心配置生成。以后改了节点名、增删了节点，用户改过的文字会保留，没改过的跟着更新；如果某段改过的文字本身也受到了影响，`doctor` 会报 `CUSTOMIZED_STALE`，提醒用户看看是否还合适。改了这些字段以外的内容会报 `DRIFT_GENERATED`，说明那部分应该回到核心配置里改。

## 填写指南

### plugin.scaffold.json

| 字段 | 怎么填 |
|---|---|
| `plugin.id` | 保留 `AutoBizDevOps_` 前缀，填写后缀，例如 `AutoBizDevOps_Doc_Review`。ID 只含英文字母、数字、短横线和下划线，含前缀共不超过 64 字符。它同时是安装目录名和状态文件里的 `pluginId`，发布后再改，已有项目的状态就对不上了 |
| `plugin.name` | 保留 `AutoBizDevOps_` 前缀，填写在 DevClaw 中显示的插件名，例如 `AutoBizDevOps_文档评审` |
| `plugin.description` | 一句话说明插件做什么 |
| `plugin.version` | 版本号，默认 `0.1.0`。之后由 `package` 自动递增，一般不用手改 |

`workflow`、`modules` 是对其他文件的引用，保持生成时的样子即可。

### workflow.json

顶层只有 `nodes`，按阶段分成 `biz`、`dev`、`ops` 三组。组名只能是这三个，可以只写其中几组。每个节点：

| 字段 | 怎么填 |
|---|---|
| `id` | 小写字母开头，只含小写字母、数字和 `_`，全局不重复，不加阶段前缀（写 `plan`，不写 `dev_plan`）。checkpoint 名由它推出：`plan_in_progress`、`plan_done` |
| `seq` | 执行顺序，正整数，全局不重复，可以跳号（写 10、20、30，以后插节点不用改别的）；要按 biz → dev → ops 递增 |
| `name` | 看板上的显示名，例如“需求澄清” |
| `skill` | 技能目录名，小写字母、数字和连字符。一个技能只绑定一个节点，因为技能开头写着这个节点专属的状态命令。技能会按节点阶段放进 `skills/autobiz/`、`skills/autodev/` 或 `skills/autoops/` |
| `outputs` | 节点产出的文件，路径相对 Feature 目录，可以用 glob（`specs/**/*.md`）；可有可无的写成 `{"path": "PR_BODY.md", "optional": true}`；没有产出（例如编码节点）就删掉这个字段 |
| `terminal` | 可选。`true` 表示终态节点（例如“归档”），只能是 `seq` 最大的节点，不能有 `outputs`，完成后流程进入 `archived` |

填的时候注意：

- 推进到 `_done` 时会检查必需产出都存在且不为空，缺了会被拦下。所以 `outputs` 只写这个节点每次一定会产出的文件，偶尔才有的标成可选；
- 两个节点不要声明同一个产出文件；
- 节点要读哪些上游文件，写在技能正文里，不用写进配置。

例如：

```json
{
  "nodes": {
    "biz": [ { "id": "prd", "seq": 10, "name": "需求", "skill": "my-prd", "outputs": ["PRD.md"] } ],
    "dev": [
      { "id": "plan", "seq": 20, "name": "计划", "skill": "my-plan", "outputs": ["plan.md"] },
      { "id": "code", "seq": 30, "name": "编码", "skill": "my-code" }
    ],
    "ops": [ { "id": "archive", "seq": 40, "name": "归档", "skill": "my-archive", "terminal": true } ]
  }
}
```

### modules/*.json

各模块怎么填，见第 2 步读取的模块指南。

## 边界

- 配置和技能内容归用户。只有用户选了“起草”、明确请你代写某一处，或者是把第 1 步选择题的回答落进骨架时才动手；写之前先让用户看要写什么，写完说明改了哪里；
- `plugin.json`、`board_core/`、`runtime/`、`.scaffold/`、`hooks/artifact_guard.py` 由脚手架生成和维护：手改的内容会在下次生成时被覆盖，或者被检查当作漂移拦下。用户想改行为，就改核心配置；只是调文案，按「之后微调文案」改那几个字段；
- 技能开头的状态维护片段是技能和运行框架之间的约定，改坏了节点就推进不了，不要改，也不要用别的办法绕过检查；
- `doctor` 的 `--force`、`--allow-id-change`、`--allow-layout-change`、`--allow-major-upgrade` 是放行开关：会覆盖被改过的托管文件，或改掉发布后不该改的标识。只在用户看过对应的 issue、明确同意后才加。
