# 演示：在 DevClaw 中用对话把技能组装成看板插件

`autobiz-plugin-creator-demo/` 是一个可以装进 DevClaw 的插件，只包含技能 `autobiz-plugin-creator`（演示版）。演示的完整链路：

```text
现场准备的技能目录 ──对话──▶ 核心配置 ──检查──▶ build ──▶ 插件 ──simulate──▶ 打包 ──▶ 导入 DevClaw
```

| 步骤 | 脚本（在技能的 `scripts/` 下） | 产出 |
|---|---|---|
| 盘点、导入技能 | `demo_skills.py list / import` | `<插件>/skills/<技能>/` |
| 检查 | `demo_lint.py`：JSON Schema + lint 语义规则 | Issue 列表 |
| 生成插件 | `demo_build.py` | `plugin.json`、`board_core/board_config.json`、`runtime/`、技能状态片段 |
| 模拟 DevClaw | `demo_simulate.py` | 每个节点的状态推进结果 |
| 打包 | `demo_package.py` | `<插件>/dist/<插件 ID>-<版本>.zip` |

生成的插件使用设计中的目录结构（`runtime/`、isolated 布局、产物存在性检查加节点校验命令）。它的看板配置与 lite 的格式一致：用 lite 的配置和技能 build 后，`workflow` 部分与 lite 现有的 `board_config.json` 只差 `legacyPaths` 一项（v1 已去掉）。

演示版的限制：

- 不支持知识模块和产物同步（build 报 `DEMO_UNSUPPORTED`）；会话上下文只含流程信息，不含知识；
- 不生成看板事件推送声明 `boardEvents`（DevClaw 尚未支持）；
- 不检查依赖构建记录以外的 `check` 级规则，例如 `OPENAI_YAML`、`TODO_PLACEHOLDER`。

## 准备

1. 打包演示插件并导入 DevClaw：

   ```bash
   python3 demo/package.py
   ```

   得到 `demo/dist/autobiz-plugin-creator-demo-0.1.0.zip`，按导入其他插件的方式导入。这个插件没有看板配置；如果 DevClaw 只接受带看板的插件，需要先确认插件技能的加载方式。

2. 准备技能目录。可以用自己的技能，也可以用 `demo/sample-skills/`：

   | 技能 | 内容 |
   |---|---|
   | `doc-draft` | 按 `templates/DRAFT.md` 起草文档初稿 |
   | `doc-review` | 评审初稿，`scripts/check_review.py` 检查 `REVIEW.md` 有问题清单和结论行 |

   想演示旧技能的迁移提示，可以加上 lite 的技能（例如 `autodev-plan`）：build 会报 `LEGACY_ENTRY_REF`，提示正文中旧的状态维护段落要删掉。

3. 机器上要有 Python 3.9+：macOS/Linux 用 `python3`，Windows 用 `python`。

## 演示脚本（约 15 分钟）

引用是演示者在 DevClaw 会话中输入的内容。

**1. 发起**

> /autobiz-plugin-creator 帮我把准备好的技能做成一个看板插件

**2. 基础信息**

> 插件 ID 叫 Doc Review，名字 Doc-Review-Kanban，描述"文档起草与评审"，版本默认

看点：ID 规范化为 `doc-review`，并提醒发布后不能修改。

**3. 盘点技能**

> 技能在 <路径>/demo/sample-skills 下，两个都导入

看点：列出技能的 description、模板和脚本，导入到 `doc-review/skills/`。

**4. 建模**

> 先用 doc-draft 起草，产出 DRAFT.md，用它自带的模板；然后用 doc-review 评审，读取草稿，产出 REVIEW.md，完成时用它自带的 check_review.py 检查

看点：整理成"节点 → 技能 → 读取 → 产出 → 模板 → 校验"表格，确认后才写 `workflow.json`，然后自动检查。

**5. 故意制造一个错误**

> 起草的时候也要参考评审意见

看点：检查报 `INPUT_FORWARD`，技能原样转述并给出修改建议，由演示者决定怎么改。

**6. 模块**

> 产物显示名改成"文档草稿""评审意见"，开启知识沉淀入口，其他默认

看点：只生成 `modules/board.json` 并在入口文件中引用。

**7. 生成插件**

> 生成插件

看点：按归属列出生成的文件；打开 `skills/doc-review/SKILL.md`，展示 build 插入的"技能状态维护"和"输入、产物与模板"两个托管片段，开发者写的正文没有被改动。

**8. 模拟 DevClaw**

> 模拟跑一遍

看点：起草节点通过；评审节点推进到完成时，`check_review.py` 因为桩产物没有结论行而拒绝推进，说明校验确实在起作用。再说：

> 跳过校验再跑一遍

看点：所有节点都推进到已完成。

**9. 打包并导入**

> 打包

把生成的 `doc-review/dist/doc-review-0.1.0.zip` 导入 DevClaw：看板上出现"起草""评审"两个节点；创建 Feature 后，按节点带出 `/doc-draft`、`/doc-review` 发起会话。

## 不经过 DevClaw 彩排

```bash
python3 demo/rehearse.py
```

在临时目录中按上面的脚本走一遍（导入示例技能 → 写配置 → 检查 → 制造 `INPUT_FORWARD` → build → simulate → 打包），打印每一步的输出，结束后删除临时目录（加 `--keep` 保留）。
