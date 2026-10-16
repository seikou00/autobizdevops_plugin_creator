# autobizdevops_plugin_creator

AutoBiz 看板插件脚手架。三方分工如下：

- **插件开发者**：用 `workflow.json` 定义流程（阶段、节点、技能绑定、输入输出、模板引用、可选校验命令），在入口文件 `plugin.scaffold.json` 中填写基础信息并引用 `modules/` 下的看板、会话、知识模块配置，再提供技能、模板、业务校验器和自定义扩展；
- **脚手架与运行框架**：生成固定入口和编译配置，提供流程查询、状态管理及宿主适配；
- **DevClaw**：展示看板、发起会话、传入运行上下文、调用插件入口。

配置可以由初始化向导问答生成；不改默认值的模块不需要写配置文件，所以入口文件很短。这些核心配置只写决策，由 `autobiz-plugin lint` 在提交前、构建前和 CI 中自动检测；插件运行时只读 build 编译出来的配置。看板配置、三平台宿主命令、状态机、插件清单和模块文件都由脚手架生成。

当前状态：**设计阶段（v1 草案）**，尚无实现代码。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/README.md](docs/README.md) | 整体设计、三方职责、已确认决策、遗留问题、本次调整 |
| [docs/input-config.md](docs/input-config.md) | 用户输入：输入分类、`workflow.json`、入口文件与模块配置文件的字段、默认值、推导规则、校验规则 |
| [docs/output-spec.md](docs/output-spec.md) | 插件标准化输出：目录、清单、board_config、内部配置、运行期数据、技能格式 |
| [docs/interfaces.md](docs/interfaces.md) | 接口：CLI 与初始化向导、模块契约、宿主命令协议、看板事件推送、运行框架入口与内部库 |
| [docs/diagrams.md](docs/diagrams.md) | 框架图与核心机制图（Mermaid） |
| [docs/mods.md](docs/mods.md) | 草案：mods 机制下的插件初始化与热更新 |
| [schemas/](schemas/) | `workflow.schema.json`、`plugin-scaffold.schema.json`、`modules/*.schema.json` |
| [examples/](examples/) | `lite/`（复刻 autobizdevops_lite）、`minimal/` |

## 参考插件

- `autobizdevops_lite`：运行框架与知识模块的起点，也是金样测试（golden test）基线；
- `autobiz_kanban`（全栈版）：产物同步能力的起点（`skills/autobizdevops-artifact-sync`，自 `9411fc3` 起）。

## 计划结构

见 [docs/README.md §3.1](docs/README.md)：`scaffold/`（CLI、初始化向导与模块）、`runtime/`（运行框架模板）、`skills/autobiz-plugin-creator/`、`schemas/`、`examples/`、`docs/`、`tests/`。
