# 示例

每个示例目录下，根目录的文件是**核心配置**（开发者维护的输入），`output/` 是对这份输入执行 `autobiz-plugin build` 后**应得到的生成内容**（金样）。`output/` 按插件根目录的结构摆放，只收录由输入推导出来的文件：

| 文件 | 归属 | 规则 |
|---|---|---|
| `plugin.json` | generated | output-spec.md §2.1 |
| `board_core/board_config.json` | generated | DevClaw 读取的宿主命令，output-spec.md §3.1 |
| `board_core/modules.json` | generated | DevClaw 读取的模块开启情况与看板入口，output-spec.md §3.3 |
| `runtime/config/runtime.json`、`flow.json`、`board.json`、`session.json`、`knowledge.json` | generated | 只给插件脚本读，output-spec.md §5；看板上的流程数据由 adapter 用它们拼出、通过命令输出 |
| `runtime/build-manifest.json` | generated | output-spec.md §8 |
| `skills/<skill>/SKILL.md` | seeded | 示例中没有技能目录，所以是 build 生成的桩文件，带 `state`、`artifacts` 托管片段（output-spec.md §6.1） |
| `skills/autobizdevops-artifact-sync/config/artifact-sync.json` | generated | 产物同步模块，output-spec.md §7.2 |
| `.gitignore` | seeded | 声明 `knowledge.source` 时追加知识目录等（output-spec.md §7.1） |

不收录内容固定、与输入无关的文件：运行框架入口与内部库（managed）、知识模块和产物同步模块的脚本与文案（module）、`.scaffold/` 下的 Schema、`.githooks/pre-commit`。它们在 `build-manifest.json` 中照常登记，摘要写作 `sha256: "…"`。build-manifest 和 `flow.json` 中输入文件的摘要是真实值，改了输入就要重新生成 `output/`。

| 示例 | 用到的能力 |
|---|---|
| [minimal/](minimal/) | 两个节点、默认分组、isolated 布局、一个校验命令；不写模块配置 |
| [lite/](lite/) | legacy 布局、关闭 `-X utf8`、git 产物、节点 `nextAction` 覆写、知识模块（含仓库同步）、知识沉淀入口、产物同步 |
| [fullstack/](fullstack/) | 在 lite 基础上加：终态节点、动态阶段、跳过节点、可选输入与可选输出、重复输出的产物、阶段标签覆写、`mcpServers`/`hooks` 透传、`extraPaths` 与 `excludeCheckpoints` |
