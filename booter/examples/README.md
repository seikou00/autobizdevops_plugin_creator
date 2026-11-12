# 示例

每套示例都有一份开发者维护的输入和一份用当前脚手架生成的输出。

| 示例 | 输入 | 输出 |
|---|---|---|
| 最小示例 | [minimal/input/](minimal/input/)。起草、评审两个节点，使用默认看板和运行策略。 | [minimal/output/](minimal/output/)。包含生成的插件配置、产物检查钩子和待填写的节点技能。 |
| 全栈技能示例 | [fullstack-skills/input/](fullstack-skills/input/)。包含 Biz、Dev、Ops 流程、看板、运行策略、发布单元知识、产物同步，以及原有的技能、子代理和自定义钩子。 | [fullstack-skills/output/](fullstack-skills/output/)。包含看板宿主命令、编译配置、合并后的钩子和插入状态维护片段的节点技能。 |

全栈示例中，流程脚本位于 `skills/scripts/flowlib/`，节点与产物定义取自生成的 `runtime/config/flow.json`，额外的节点校验规则取自 `node_contracts.json`。`hooks/` 放由 `hooks/hooks.json` 注册的宿主钩子。

全栈示例的规格技能根据 `FEATURE_DIR` 定位项目词汇表。默认路径为项目下的 `.autobizdevops/CONTEXT.md`，由技能在首次确认术语时写入，属于业务项目的数据。 [词汇表维护协议](fullstack-skills/input/skills/references/domain-context.md) · [生成后的规格技能](fullstack-skills/output/skills/autodev/autodev-specs/SKILL.md)

## 复现生成结果

从仓库根目录运行下面的命令，把示例输入复制到临时目录，再运行 `doctor`。将 `minimal` 换成 `fullstack-skills` 可以复现全栈输出。全栈示例配置了知识仓库，在离线环境下可以像下面这样跳过拉取知识和安装 Node 依赖。

```bash
example_dir=$(mktemp -d)
cp -R booter/examples/minimal/input/. "$example_dir/"
AUTOBIZ_SKIP_KNOWLEDGE_PULL=1 AUTOBIZ_SKIP_NPM_INSTALL=1 \
  python3 booter -C "$example_dir" doctor
python3 booter -C "$example_dir" check
```

`output/` 按插件根目录的结构存放便于对照的生成文件。可直接比较入口清单、看板配置、运行配置、合并后的钩子和节点技能。通用运行脚本、模块资源和 `.scaffold/` Schema 由 `doctor` 补齐，未收录的这些文件在预览构建清单中以 `sha256: "…"` 标记。要验证或打包完整插件，请在 `doctor` 生成的目录操作。最小示例需要先补全技能描述和正文。
