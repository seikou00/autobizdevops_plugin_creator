# 快速上手：四步出一个插件

只讲必要的步骤。需要定制流程、模块或接入 CI 时看 [usage-advanced.md](usage-advanced.md)。

准备：Python 3.9+。以下命令都在 `booter/` 下执行，Windows 上把 `python3` 换成 `python`。示例假设各仓库都在 `~/Documents/GitHub/` 下，换成你自己的路径即可。

## 1. 进入脚手架目录

```bash
cd ~/Documents/GitHub/autobizdevops_plugin_creator/booter
```

## 2. 以样例为起点新建插件

```bash
python3 -m scaffold new ~/Documents/GitHub/my-plugin --from lite --yes
```

- `lite`：需求 → 规格 → 计划 → 编码四个节点；要 Biz→Dev→Ops 全流程，换成 `fullstack`；
- 流程和 lite、fullstack 都不一样，手里只有一个技能目录：见下文[只有技能目录时](#只有技能目录时)；
- 目标目录必须不存在或为空。

这一步结束时插件已经可以运行，技能是空白的 `SKILL.md`。

## 3. 放入技能和 agents

lite：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin add skills --from ~/Documents/GitHub/autobizdevops_lite/skills --agents ~/Documents/GitHub/autobizdevops_lite/agents
```

fullstack 的技能按 `autobiz/`、`autodev/`、`autoops/` 分了组，直接导入整个 `skills/` 目录即可，分组结构和共享的 `references/`、`hooks/` 会原样保留：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin add skills --from ~/Documents/GitHub/autobiz_kanban/skills --agents ~/Documents/GitHub/autobiz_kanban/agents
```

导入时如果提示 `LEGACY_ENTRY_REF`：打开提示中的 `SKILL.md`，删掉旧的「技能状态维护」小节（调用 `hooks/update_state.py` 的那几行）。脚手架已经在文件开头写好了新的状态维护片段，旧的不删，打包时会报错。

## 4. 打包

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin package
```

打包前会自动检查。通过后生成 `my-plugin/dist/<插件 id>-<版本>.zip`，导入 DevClaw 即可。

插件自带一个产物检查钩子：技能执行完成命令时，如果 `workflow.json` 中声明的产物还没生成或是空文件，这条命令会被拦下，模型补齐产物后再推进。不需要额外配置。钩子都在插件根目录的 `hooks/` 下：配置是 `hooks/hooks.json`，想加自己的钩子就照着里面已有的条目写在同一个文件里，重新生成时会原样保留。

还想加明文密码检查、前端性能检查（插件全局钩子模块 `globalHooks`，配置在 `modules/globalHooks.json`）：用向导新建时会逐个询问；已经建好的插件运行下面的命令（`hook list` 查看全部全局钩子）：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin hook enable secrets-check performance-check
```

## 只有技能目录时

手里只有一个技能目录，可以有分组嵌套，例如 `my-skills/autodev/autodev-code/SKILL.md`；也完全不了解配置文件。这种情况不用手写任何 JSON：用向导回答几个问题，再导入技能目录。

**先想好流程。** 从技能目录里挑出主流程上要依次执行的技能，每个技能对应看板上的一个节点。评审、回滚这类辅助技能不用挑，导入时会一起带上。比如：

| 顺序 | 节点 | 技能（技能目录的名字） | 产出的文件 |
|---|---|---|---|
| 1 | 需求 | `autobiz-requirement-discuss` | `PRD.md` |
| 2 | 编码 | `autodev-code` | （无） |

**第 2 步换成运行向导**（不加 `--from`）：

```bash
python3 -m scaffold new ~/Documents/GitHub/my-plugin
```

按下表回答，没提到的问题直接回车，用默认值：

| 向导问题 | 怎么填 |
|---|---|
| 插件 ID | 英文小写加连字符，如 `my-plugin`，发布后不能改 |
| 插件名、一句话描述 | 随意填写，会显示在 DevClaw 中 |
| 节点 id、显示名 | 每个节点起一个英文 id（如 `prd`）和一个中文名（如 `需求`） |
| 所属阶段 | 需求类选 `biz`，开发类选 `dev`，发布、运维类选 `ops`；顺序必须是 biz → dev → ops |
| 编排顺序 seq | 回车即可，自动递增 |
| 绑定技能 | 填技能目录的名字，例如 `autodev-code`，不要带分组 `autodev/` |
| 产出产物 | 这个技能生成的文件名，多个用逗号分隔，用来判断节点是否完成；不清楚就留空 |
| 继续添加节点？ | 还有节点就回车，最后一个节点输入 `N` |
| 最后一个节点是终态节点吗？ | 回车（选 N）；只有最后一步是「归档」这种收尾动作时才选 Y |
| 已有技能目录的路径 | 留空回车，下一步统一导入 |
| 启用明文密码检查 / 前端性能检查？ | 需要就输入 `Y`；前端性能检查在编码节点 `code_done` 时检查变动的前端文件 |

**第 3 步导入整个技能目录**，有 agents 目录就一起导入：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin add skills --from ~/Documents/GitHub/my-skills --agents ~/Documents/GitHub/my-agents
```

分组结构、共享的 `references/` 和 `hooks/` 会原样保留；向导生成的空白技能会自动被同名的真实技能替换。没有 agents 目录就去掉 `--agents …`。

第 4 步照常打包。想先确认流程能走通，可以先运行 `python3 -m scaffold -C ~/Documents/GitHub/my-plugin simulate`，它会在临时目录里按 DevClaw 的方式把每个节点走一遍。

> 也可以把插件开发技能 `autobiz-plugin-creator` 装进 agent，用对话描述流程，由 agent 填写配置并执行这些命令。

## 想自己填配置时

不想回答向导、也不想从样例改起，可以让脚手架只写出配置的骨架，要填的地方都标成 `[TODO: 说明]`：

```bash
python3 -m scaffold new ~/Documents/GitHub/my-plugin --skeleton --module board
```

要启用知识、产物同步、全局钩子，就再加 `--module knowledge`、`--module artifactSync`、`--module globalHooks`。

照着说明把 `[TODO: …]` 填好，然后检查还缺什么：

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
