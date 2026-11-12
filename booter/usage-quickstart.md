# 快速上手：四步出一个插件

只讲必要的步骤。需要定制流程、模块或接入 CI 时看 [usage-advanced.md](usage-advanced.md)。

准备：Python 3.9+。以下命令都在 `booter/` 下执行，Windows 上把 `python3` 换成 `python`。示例假设各仓库都在 `~/Documents/GitHub/` 下，换成你自己的路径即可。

## 使用模型引导（推荐）

将 `booter/` 作为技能交给 agent（入口 [SKILL.md](SKILL.md)）。可以直接说明任务，也可以启动技能后从以下三个入口中选择：

- 从头搭建：模型逐步梳理用途、节点和产物，起草配置供确认。
- 有现成技能：提供技能目录，模型分析节点与辅助能力，只追问缺口。
- 修改已有插件：提供插件目录和改动目标，模型展示关联影响与差异后修改、检查。

默认模型起草、用户确认，也支持自行填写。以下是直接使用 CLI 的方式，终端向导仍按字段收集输入。

## 1. 进入脚手架目录

```bash
cd ~/Documents/GitHub/autobizdevops_plugin_creator/booter
```

## 2. 用向导新建插件

**先想好流程。** 从你的技能目录里挑出主流程上要依次执行的技能，每个技能对应看板上的一个节点。只作为辅助调用的技能不用挑，导入时会一起带上；评审是否独立成节点取决于实际流程。比如：

| 顺序 | 节点 | 技能（技能目录的名字） | 产出的文件 |
|---|---|---|---|
| 1 | 需求 | `my-prd` | `PRD.md` |
| 2 | 编码 | `my-code` | （无） |

然后运行向导：

```bash
python3 -m scaffold new ~/Documents/GitHub/my-plugin
```

按下表回答。提示中有默认值的问题可以直接回车：

| 向导问题 | 怎么填 |
|---|---|
| 插件 ID | 英文字母、数字、短横线和下划线。输入 `my-plugin` 会生成 `AutoBizDevOps_my-plugin`，含前缀共不超过 64 字符，发布后不能改 |
| 插件名、一句话描述 | 会显示在 DevClaw 中，插件名自动加 `AutoBizDevOps_` 前缀 |
| 节点 id、显示名 | 每个节点起一个英文 id（如 `prd`）和一个中文名（如 `需求`） |
| 所属阶段 | 需求类选 `biz`，开发类选 `dev`，发布、运维类选 `ops`；顺序必须是 biz → dev → ops |
| 编排顺序 seq | 回车即可，自动递增 |
| 绑定技能 | 填技能目录的名字，例如 `my-code`，不要带分组 `autodev/` |
| 产出产物 | 这个技能生成的文件名，多个用逗号分隔，用来判断节点是否完成；不清楚就留空 |
| 继续添加节点？ | 还有节点就回车，最后一个节点输入 `N` |
| 最后一个节点是终态节点吗？ | 回车（选 N）；只有最后一步是「归档」这种收尾动作时才选 Y |
| 已有技能目录的路径 | 留空回车，下一步统一导入 |
| 要启用哪些可选模块？ | 向导会先介绍各模块，再逐个询问是否启用。回车选 `N` |
| 要不要按发布单元带入知识？ | 选 `Y` 后，选择 Git 仓库、随插件打包或 DevClaw 提供，再选插件或 DevClaw 组装 |
| 要不要自定义节点的 Agent 运行模式？ | 回车沿用 `multi`。选 `Y` 可从 `multi`、`solo`、`agent_team`（team）和 `workflow` 中设置全局默认模式，也可以按节点覆盖 |

- 目标目录必须不存在或为空；
- 不想回答向导、想自己填配置：见下文[想自己填配置时](#想自己填配置时)。

这一步结束时插件已经可以运行，技能是空白的 `SKILL.md`。

## 3. 放入技能和 agents

导入整个技能目录（可以有分组嵌套，例如 `my-skills/autodev/my-code/SKILL.md`），有 agents 目录就一起导入：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin add skills --from ~/Documents/GitHub/my-skills --agents ~/Documents/GitHub/my-agents
```

分组结构、共享的 `references/` 和 `hooks/` 会原样保留；向导生成的空白技能会自动被同名的真实技能替换。没有 agents 目录就去掉 `--agents …`。

导入时如果提示 `LEGACY_ENTRY_REF`：打开提示中的 `SKILL.md`，删掉旧的「技能状态维护」小节（调用 `hooks/update_state.py` 的那几行）。脚手架已经在文件开头写好了新的状态维护片段，旧的不删，打包时会报错。

想先确认流程能走通，可以先运行 `python3 -m scaffold -C ~/Documents/GitHub/my-plugin simulate`，它会在临时目录里按 DevClaw 的方式把每个节点走一遍。

> 也可以把整个 `booter/` 目录作为技能装进 agent（入口是根目录的 `SKILL.md`），由 agent 用选择题引导你生成骨架、填写配置并执行这些命令。

## 4. 打包

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin package
```

打包前会自动检查。ZIP 中的插件 ID 和显示名称会补齐 `AutoBizDevOps_` 前缀，手改 `plugin.json` 的名称后也一样。生成的 `my-plugin/dist/AutoBizDevOps_<ID 后缀>-<版本>.zip` 可以直接导入 DevClaw。

插件自带一个产物检查钩子：技能执行完成命令时，如果 `workflow.json` 中声明的产物还没生成或是空文件，这条命令会被拦下，模型补齐产物后再推进。不需要额外配置。钩子都在插件根目录的 `hooks/` 下：配置是 `hooks/hooks.json`，想加自己的钩子就照着里面已有的条目写在同一个文件里，重新生成时会原样保留。

## 想自己填配置时

不想回答向导，可以让脚手架只写出配置的骨架，要填的地方都标成 `[TODO: 说明]`：

```bash
python3 -m scaffold new ~/Documents/GitHub/my-plugin --skeleton
```

要启用可选模块，就再加 `--module knowledge` 或 `--module artifactSync`。自定义看板或运行策略时，分别加 `--module board` 或 `--module session`。可以先看每个模块的说明：

```bash
python3 -m scaffold module list
```

各模块的字段说明见[发布单元知识](scaffold/modules/knowledge/guide.md)、[产物同步](scaffold/modules/artifact_sync/guide.md)、[看板](scaffold/modules/board/guide.md)和[运行策略](scaffold/modules/session/guide.md)。

照着说明把 `[TODO: …]` 填好。插件 ID 和名称已预填 `AutoBizDevOps_` 前缀，保留前缀并填写后缀，然后检查还缺什么：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin lint
```

每个没填的地方报一条 `TODO_FIELD`，写明文件和位置。没有 `TODO_FIELD` 之后，从「第 3 步：放入技能和 agents」接着做；导入技能时会自动生成插件。不导入技能的话，运行 `doctor` 生成插件：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin doctor
```

## 之后改了配置

改了 `plugin.scaffold.json`、`workflow.json`、`modules/*.json`，或技能 `SKILL.md` 开头的 `description` 之后，先重新生成，再打包：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin doctor
```

## 常见报错

| 报错 | 怎么办 |
|---|---|
| `LEGACY_ENTRY_REF` | 删掉 `SKILL.md` 里旧的状态维护命令（见第 3 步） |
| 打包提示还有 `[TODO: …]` 占位 | 空白技能还没填写：补上 `SKILL.md` 的 `description` 和正文，或导入真实技能 |
| `SUBAGENT_FILE_MISSING` | `modules/session.json` 引用的 agents 文件不存在：导入技能时加 `--agents <目录>` |
| `TODO_FIELD` | 配置里还有没填的 `[TODO: …]`：按提示的文件和位置填好 |
| `BUILD_STALE` | 改了配置或技能 `description` 但没重新生成：执行 doctor |
| `SKILL_MISSING` | 节点绑定的技能名在技能目录里找不到：检查拼写，技能名就是含 `SKILL.md` 的那个目录的名字 |
| 目标目录必须不存在或为空 | 换一个新目录，或清空它 |
