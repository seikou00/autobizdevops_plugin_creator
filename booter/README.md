# booter：AutoBiz 看板插件脚手架

开发期 CLI `autobiz-plugin`：把开发者写的核心配置（`plugin.scaffold.json`、`workflow.json`、`modules/*.json`）和技能资源，生成可以导入 DevClaw 的看板插件。只依赖 Python 3.9+ 标准库，设计文档在仓库根目录的 [docs/](../docs/)。

## 目录

| 目录 | 内容 |
|---|---|
| `scaffold/` | CLI 与构建流水线（Python 包名仍为 `scaffold`）：`lib/` 公共基础，`build/` 流水线，`commands/` 各子命令，`modules/` 五个模块包（其中 `global_hooks/hooks/` 是插件全局钩子目录，每个钩子一个 `hook.json` 加脚本，加目录即可新增），`wizard.py` 初始化向导，`host.py` 模拟 DevClaw |
| `runtime/` | 运行框架模板：随生成的插件发布的 `query`/`engine` 内部库、宿主入口、会话入口和状态变更入口 |
| `schemas/` | 核心配置的 JSON Schema（拷进插件的 `.scaffold/` 供 IDE 补全），以及宿主命令输出结构 `host/outputs.schema.json` |
| `examples/` | `minimal/` 示例的核心配置和金样输出 `output/` |
| `skills/autobiz-plugin-creator/` | 插件开发技能：与开发者对话建模，再调用 CLI |
| `skills/autobiz-plugin-skeleton/` | 骨架引导技能：生成 `new --skeleton` 骨架，让用户自行填写配置和技能，再打包；与上一个技能打在同一个插件包中，共用它的 `.pyz` |
| `tools/make_pyz.py` | 发布：打出 `dist/autobiz-plugin.pyz` 和插件开发技能的插件包（含骨架引导技能） |
| `tests/` | 金样、参考插件基线、运行框架契约、CLI 端到端和单元测试；部分测试用到仓库根目录 `fixtures/` 下的样例，不在时跳过 |
| `usage-quickstart.md`、`usage-advanced.md` | 使用说明：快速上手、进阶用法；改了命令或配置时一起更新 |

## 用法

以下命令都在 `booter/` 下执行，Windows 上把 `python3` 换成 `python`：

```bash
python3 tools/make_pyz.py                                  # 打出 dist/autobiz-plugin.pyz 和 dist/autobiz-plugin-creator-<版本>.zip
python3 dist/autobiz-plugin.pyz new ../../my-plugin        # 初始化向导；--yes --answers a.json 由回答文件生成、不提问
python3 dist/autobiz-plugin.pyz new ../../my-plugin --skeleton --module board  # 只写出带 [TODO: …] 的配置骨架，填完再 lint、doctor、package
python3 dist/autobiz-plugin.pyz -C ../../my-plugin add skills --from ../../my-skills --agents ../../my-agents  # 一次导入技能集合和 agents
python3 dist/autobiz-plugin.pyz -C ../../my-plugin add skill doc-review --from ../../other-skills/doc-review  # 单独导入一个技能
python3 dist/autobiz-plugin.pyz -C ../../my-plugin add node review --name 评审 --skill doc-review --stage dev --seq 5 --output REVIEW.md
python3 dist/autobiz-plugin.pyz -C ../../my-plugin module enable artifactSync --set allowedFrom=plan:done
python3 dist/autobiz-plugin.pyz -C ../../my-plugin hook enable secrets-check performance-check  # 启用插件全局钩子（写 modules/globalHooks.json）；hook list 查看全部
python3 dist/autobiz-plugin.pyz -C ../../my-plugin doctor     # 改了核心配置或更新脚手架后重新生成
python3 dist/autobiz-plugin.pyz -C ../../my-plugin check      # lint + 技能内容 + 漂移 + 契约测试
python3 dist/autobiz-plugin.pyz -C ../../my-plugin simulate   # 在临时目录中按宿主的方式走一遍流程
python3 dist/autobiz-plugin.pyz -C ../../my-plugin package    # 写 dist/<plugin.id>-<version>.zip
python3 -m unittest discover -s tests -t .                 # 脚手架自身的测试
python3 tests/check_schema_defaults.py                     # docs/input-config.md 的默认值与 Schema 是否一致
```

不打 `.pyz` 时，在 `booter/` 下用 `python3 -m scaffold <命令>` 效果相同。各命令的参数和输出见 [docs/interfaces.md §1](../docs/interfaces.md)；上手步骤见 [usage-quickstart.md](usage-quickstart.md)，完整定制见 [usage-advanced.md](usage-advanced.md)。

`add skills` 按插件 `skills/` 的布局导入技能集合，支持一层分组（`<集合>/<分组>/<技能>/SKILL.md`），集合根目录和分组目录下的共享资源（`references/`、`hooks/`、分组自己的 `SKILL.md`）按原路径拷入，例如 `add skills --from ../../my-skills` 一次导入整个集合的全部技能；整批原子写入并只运行一次 doctor。`agents/` 是独立资源，不会自动创建：技能集合旁边有 agents 目录时加 `--agents <目录>` 一并拷入，或在 `new --answers` 中写 `"agents": "<目录>"`。
