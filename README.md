# autobizdevops_plugin_creator

AutoBiz 看板插件脚手架。三方分工如下：

- **插件开发者**：用 `workflow.json` 定义流程（按 biz/dev/ops 分组的节点、技能绑定、输出），在入口文件 `plugin.scaffold.json` 中填写基础信息并引用 `modules/` 下的看板、会话、知识、产物同步模块配置，再提供技能、模板、业务校验器和自定义扩展；
- **脚手架与运行框架**：生成固定入口和编译配置，提供流程查询、状态管理及宿主适配；
- **DevClaw**：展示看板、发起会话、传入运行上下文、调用插件入口。

配置可以由初始化向导问答生成；不改默认值的模块不需要写配置文件，所以入口文件很短。这些核心配置只写决策，由 `autobiz-plugin lint` 检测：build 前自动执行，开发者也可以随时手动执行；改了 `workflow.json` 或模块配置后，用 `autobiz-plugin doctor` 重新生成插件。插件运行时只读 build 编译出来的配置。看板配置、三平台宿主命令、状态机、插件清单、模块文件，以及每个技能 `SKILL.md` 开头的状态维护片段都由脚手架生成；开发者没有提供技能时，生成只带状态维护片段的空白 `SKILL.md`。

当前状态：**v1 的 P0、P1 功能已实现**（分期与实现状态见 [docs/priorities.md](docs/priorities.md)），v2 预留和 mods、RPC 草案未实现。只依赖 Python 3.9+ 标准库。

```bash
python3 tools/make_pyz.py                               # 打出 dist/autobiz-plugin.pyz 和插件开发技能的插件包
python3 dist/autobiz-plugin.pyz new my-plugin                     # 初始化向导；--from lite --yes 跳过问答
python3 dist/autobiz-plugin.pyz -C my-plugin add skill autodev-plan --from ../autobizdevops_lite/skills/autodev-plan
python3 dist/autobiz-plugin.pyz -C my-plugin doctor     # 改了核心配置后重新生成
python3 dist/autobiz-plugin.pyz -C my-plugin add node review --name 评审 --skill doc-review --stage dev --seq 5 --output REVIEW.md
python3 dist/autobiz-plugin.pyz -C my-plugin module enable artifactSync --set allowedFrom=plan:done
python3 dist/autobiz-plugin.pyz -C my-plugin check      # lint + 技能内容 + 漂移 + 契约测试
python3 dist/autobiz-plugin.pyz -C my-plugin simulate   # 在临时目录中按宿主的方式走一遍流程
python3 dist/autobiz-plugin.pyz -C my-plugin package    # 写 dist/<plugin.id>-<version>.zip
python3 -m unittest discover -s tests -t .              # 脚手架自身的测试
```

在仓库中也可以直接用 `python3 -m scaffold <命令>`。Windows 上把 `python3` 换成 `python`。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/README.md](docs/README.md) | 整体设计、三方职责、已确认决策、遗留问题、本次调整 |
| [docs/input-config.md](docs/input-config.md) | 用户输入：输入分类、`workflow.json`、入口文件与模块配置文件的字段、默认值、推导规则、校验规则 |
| [docs/output-spec.md](docs/output-spec.md) | 插件标准化输出：目录、清单、宿主接口 board_core、内部配置、运行期数据、技能格式 |
| [docs/interfaces.md](docs/interfaces.md) | 接口：CLI 与初始化向导、模块契约、宿主命令协议、看板事件推送、运行框架入口与内部库 |
| [docs/scaffold.md](docs/scaffold.md) | 草案（已评审）：脚手架自身的模块拆分与模块间接口 |
| [docs/diagrams.md](docs/diagrams.md) | 框架图与核心机制图（Mermaid） |
| [docs/mods.md](docs/mods.md) | 草案：mods 机制下的插件初始化与热更新 |
| [docs/rpc.md](docs/rpc.md) | 草案：DevClaw 与插件的 JSON-RPC 双向通信 |
| [docs/priorities.md](docs/priorities.md) | 草案：v1 功能分期（P0 / P1） |
| [schemas/](schemas/) | `workflow.schema.json`、`plugin-scaffold.schema.json`、`modules/*.schema.json` |
| [examples/](examples/) | `minimal/`、`lite/`（复刻 autobizdevops_lite）、`fullstack/`（全栈版）；每个示例的 `output/` 是 build 应生成的内容 |

## 参考插件

- `autobizdevops_lite`：运行框架与知识模块的起点，也是金样测试（golden test）基线；
- `autobiz_kanban`（全栈版）：产物同步能力的起点（`skills/autobizdevops-artifact-sync`，自 `9411fc3` 起）。

## 计划结构

见 [docs/README.md §3.1](docs/README.md)：`scaffold/`（CLI、初始化向导与模块）、`runtime/`（运行框架模板）、`skills/autobiz-plugin-creator/`、`schemas/`、`examples/`、`docs/`、`tests/`。
