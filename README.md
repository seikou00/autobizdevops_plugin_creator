# autobizdevops_plugin_creator

AutoBiz 看板插件脚手架。插件开发者只需填写阶段、节点和产物，勾选可选模块（知识沉淀与解析、产物同步），再编写各节点的技能。看板配置、三平台宿主命令、状态机、插件清单和模块文件都由脚手架生成。

当前状态：**设计阶段（v1 草案）**，尚无实现代码。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/README.md](docs/README.md) | 整体设计、已确认决策、遗留问题 |
| [docs/input-config.md](docs/input-config.md) | 用户输入配置 `plugin.scaffold.json`：字段、默认值、推导规则、校验规则 |
| [docs/output-spec.md](docs/output-spec.md) | 插件标准化输出：目录、清单、board_config、运行期数据、技能格式 |
| [docs/interfaces.md](docs/interfaces.md) | 接口：CLI、插件开发技能、模块契约、宿主命令协议、运行时 API |
| [schemas/plugin-scaffold.schema.json](schemas/plugin-scaffold.schema.json) | 输入配置 JSON Schema |
| [examples/](examples/) | `lite.plugin.scaffold.json`（复刻 autobizdevops_lite）、`minimal.plugin.scaffold.json` |

## 参考插件

- `autobizdevops_lite`：内核与知识模块的起点，也是金样测试（golden test）基线；
- `autobiz_kanban`（全栈版）：产物同步模块的起点（`skills/autobizdevops-artifact-sync`，自 `9411fc3` 起）。

## 计划结构

见 [docs/README.md §3.1](docs/README.md)：`scaffold/`（CLI 与模块）、`runtime/`（内核模板）、`skills/autobiz-plugin-creator/`、`schemas/`、`examples/`、`docs/`、`tests/`。
