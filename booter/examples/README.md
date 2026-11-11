# 示例

每个示例目录下，根目录的文件是**核心配置**（开发者维护的输入），`output/` 是对这份输入执行 `autobiz-plugin build` 后**应得到的生成内容**（金样）。`output/` 按插件根目录的结构摆放，只收录由输入推导出来的文件：

| 文件 | 归属 | 规则 |
|---|---|---|
| `plugin.json` | generated | output-spec.md §2.1 |
| `board_core/board_config.json` | generated | DevClaw 读取的宿主命令，output-spec.md §3.1 |
| `board_core/modules.json` | generated | DevClaw 读取的模块开启情况与看板入口，output-spec.md §3.3 |
| `runtime/config/runtime.json`、`flow.json`、`board.json`、`session.json`、`knowledge.json` | generated | 只给插件脚本读，output-spec.md §5；看板上的流程数据由 adapter 用它们拼出、通过命令输出 |
| `runtime/build-manifest.json` | generated | output-spec.md §8 |
| `hooks/hooks.json` | seeded | 产物检查钩子（和启用的全局钩子）的条目，开发者的条目写在同一文件，interfaces.md §4.7 |
| `skills/autobiz\|autodev\|autoops/<skill>/SKILL.md` | seeded | 按节点阶段分组（D64）；示例中没有技能目录，所以是 build 生成的空白 `SKILL.md`：只有 frontmatter 和状态维护片段，checkpoint 与 `workflow.json` 的节点一一对应（output-spec.md §6.1） |
| `skills/autobizdevops-artifact-sync/config/artifact-sync.json` | generated | 产物同步模块，output-spec.md §7.2 |

不收录内容固定、与输入无关的文件：运行框架入口与内部库（managed）、知识模块和产物同步模块的脚本与文案（module）、`.scaffold/` 下的 Schema。它们在 `build-manifest.json` 中照常登记，摘要写作 `sha256: "…"`。build-manifest 和 `flow.json` 中输入文件的摘要是真实值，改了输入就要重新生成 `output/`（相当于对示例执行 `doctor`）。节点技能 `description` 的摘要按 `output/skills/` 下生成的空白 SKILL.md 计算（示例目录本身没有技能）。

| 示例 | 用到的能力 |
|---|---|
| [minimal/](minimal/) | 两个节点（都在 `biz` 组，`seq` 为 1、2）；不写模块配置 |
| [fullstack-skills/](fullstack-skills/) | 全栈版的核心配置和技能（产物同步技能由模块生成，不收录），以及按新目录结构重构后的流程脚本：`hooks/` 只放 `hooks.json` 注册的宿主钩子（新增 `state_write_guard.py`、`stage_gate_guard.py` 取代原 `state_checkpoint.py`）；原插件根目录 `hooks/` 下由技能调用的流程脚本和共用库放在 `skills/scripts/flowlib/`，原 `board_core` 由其中的 `contracts.py`、`state_store.py` 取代（节点、产物、checkpoint 读运行框架的 `flow.json`，校验器清单等读 `node_contracts.json`，状态变更只走运行框架）；已被运行框架、知识模块、globalHooks 取代的脚本删除。v1 运行框架只有 standard 流程，阶段回退只保留 `target_in_progress`。用来验证搬入已有技能后的悬空引用和绝对路径检查（`SKILL_REF_DANGLING`、`SKILL_REF_ABSOLUTE`，D71），以及流程脚本能在新结构下运行（`tests/test_fullstack_skills.py`）。没有 `output/` 金样 |
