# AutoBiz 看板插件自行配置使用手册

草稿 · 适用于引导技能 1.3.3

适合已经想好流程、希望自己填写配置和技能的开发者。下面以「起草文档 → 评审文档」为例，从空白骨架做到可以导入 DevClaw 的插件 ZIP。

## 开始使用

1. 解压 `booter-public.zip`，保留完整的 `booter/` 目录。终端需要 Python 3.9 或以上版本。
2. 把 `booter/` 加载到支持技能的 Agent 中，调用 `autobiz-plugin-skeleton`，选择 **自行配置**，提供一个空目录或新目录。也可以在包含 `booter/` 的目录里直接运行下面的命令。

```bash
python3 ./booter new ./doc-review --manual
```

| 文件 | 填什么 |
| --- | --- |
| `plugin.scaffold.json` | 插件 ID、插件显示名称、用途和模块引用。 |
| `workflow.json` | 节点所属阶段、执行顺序、绑定的技能和产物。 |
| `skills/my-skill/SKILL.md` | 第一个节点的技能描述和工作步骤。 |
| `modules/*.json` | 一次生成看板、运行模式、发布单元知识和产物同步四份配置。产物同步默认关闭，配置文件可留作备用。 |

`.scaffold/` 下的 Schema 可供编辑器做字段提示。

## 填写插件信息

把 `plugin.scaffold.json` 中的 `[TODO: …]` 换成插件信息。保留 `AutoBizDevOps_` 前缀，插件 ID 会用作安装目录名，并写入项目的状态记录，发布前先定好。初始版本可以沿用 `0.1.0`。下面的示例沿用默认看板和运行策略，省略了 `modules` 字段。各模块的取舍方式见[按需配置模块](#按需配置模块)。

```json
{
  "$schema": "./.scaffold/plugin-scaffold.schema.json",
  "scaffoldVersion": 1,
  "plugin": {
    "id": "AutoBizDevOps_doc-review",
    "name": "AutoBizDevOps_文档评审",
    "version": "0.1.0",
    "description": "起草文档并记录评审结论"
  },
  "workflow": "./workflow.json"
}
```

默认在项目下的 `.autobizdevops/` 保存状态、产物和日志。需要给不同插件配置独立目录时，填写 `runtime.metaRoot`。配置方式见[自定义目录名](plugin-customization.md#自定义-autobizdevops-目录名)。

## 写出流程和产物

下面把骨架中的占位节点填成「起草」，再增加一个「评审」节点。两个节点都在 `biz` 阶段，按 `seq` 先后执行。

```json
{
  "$schema": "./.scaffold/workflow.schema.json",
  "nodes": {
    "biz": [
      { "id": "draft", "seq": 10, "name": "起草", "skill": "my-skill", "outputs": ["DRAFT.md"] },
      { "id": "review", "seq": 20, "name": "评审", "skill": "doc-review", "outputs": ["REVIEW.md"] }
    ]
  }
}
```

| 字段 | 怎么填 |
| --- | --- |
| `id` | 小写字母开头，只含小写字母、数字和下划线。所有节点的 ID 都要唯一。 |
| `seq` | 正整数，所有节点的顺序号都要唯一。使用多个阶段时，顺序依次为 `biz`、`dev`、`ops`。 |
| `name` | 看板显示的节点名，例如「评审」。 |
| `skill` | 技能目录名，使用小写字母、数字和连字符。每个节点绑定一个独立技能。 |
| `outputs` | 路径相对当前 Feature 目录。必需产物存在且非空，节点才能完成。偶尔生成的产物可用 `{"path": "NOTES.md", "optional": true}`，没有文件产出时删掉 `outputs`。 |
| `terminal` | 可选。把最后一个节点设为 `true` 时，该节点完成后进入 `archived`。终态节点不能配置产物。 |

评审需要读取 `DRAFT.md`，把这项要求写在评审技能的正文里。字段和路径规则见[配置填写指南](../booter/references/config-guide.md)。

## 填写节点技能

1. **填写起草技能。** 打开 `skills/my-skill/SKILL.md`，把 `description` 改为「需要把用户需求整理成文档初稿时使用」，正文写清如何梳理需求、标出待确认事项，并把初稿保存到当前 Feature 目录下的 `DRAFT.md`。
2. **新增评审技能。** 创建 `skills/doc-review/SKILL.md`，填写下面的内容。已有技能也可以放在对应目录下，模板、脚本和引用资料随技能一起放入。

```markdown
---
name: doc-review
description: 需要审阅文档初稿并给出书面结论时使用。
---

1. 读取当前 Feature 目录下的 `DRAFT.md`。
2. 对照用户需求，检查遗漏、矛盾和待确认事项。
3. 在同一目录写入 `REVIEW.md`，记录评审结论和需要补充的事项。每条意见注明对应段落。
```

如果改技能名，同步更新技能目录名、`SKILL.md` 里的 `name` 和节点的 `skill`。技能正文里的文件名也要与 `outputs` 对得上。

**「技能状态维护」在生成插件时自动写入。** 现在可以直接写正文，无需添加 `<!-- plugin workflow: begin state -->` 或 `<!-- plugin workflow: end state -->`。`doctor` 会按节点 ID 生成完整片段，放在文件头和正文之间，并保留正文。例如 `draft` 节点会得到 `draft_in_progress` 和 `draft_done`。本例中，两个技能都会归到 `skills/autobiz/` 下，之后在归类后的位置继续编辑。

## 按需配置模块

自行配置会生成下表中的四份模块配置，入口默认引用 `board`、`session` 和 `knowledge`。保留需要的模块，填写其中的 `[TODO: …]`。要去掉已有引用的模块配置，可以在第一次运行 `doctor` 前做两步。

1. 删除 `modules/` 下的对应配置文件。例如不用发布单元知识，就删掉 `modules/knowledge.json`。
2. 打开 `plugin.scaffold.json`，从 `modules` 中删掉对应的引用，本例是 `"knowledge": "./modules/knowledge.json"`。把所有引用都删完时，可以去掉整个 `modules` 字段。

省略 `board` 或 `session` 配置后，会使用默认看板或多 Agent 模式。省略 `knowledge` 的引用会关闭发布单元知识功能。

**产物同步默认关闭。** 可以保留 `modules/artifactSync.json` 及其中的占位，直接生成和打包。要启用时，先填好同步范围和产物，再在 `plugin.scaffold.json` 的 `modules` 中加入 `"artifactSync": "./modules/artifactSync.json"`，然后运行 `lint` 和 `doctor`。

| 模块 | 什么时候配置 | 字段说明 |
| --- | --- | --- |
| `board` | 要自定义看板流程名称、文案或目标平台。 | [看板](../booter/scaffold/modules/board/guide.md) |
| `session` | 要设置全局或单节点的 Agent 运行模式、子代理或工具开关。 | [运行策略](../booter/scaffold/modules/session/guide.md) |
| `knowledge` | 希望按发布单元把项目知识带入会话。 | [发布单元知识](../booter/scaffold/modules/knowledge/guide.md) |
| `artifactSync` | 希望把指定节点产物同步到外部服务。 | [产物同步](../booter/scaffold/modules/artifact_sync/guide.md) |

可选运行模式为 `multi`（多 Agent）、`solo`（单 Agent）、`agent_team`（Agent 团队）和 `workflow`（工作流）。例如只保留 `session` 模块时，入口文件里的引用为 `"modules": {"session": "./modules/session.json"}`。下面保留全局 `multi`，只让评审节点用 `solo`。`biz` 和 `review` 对应上面的节点阶段和 ID。

```json
{
  "$schema": "../.scaffold/modules/session.schema.json",
  "policies": {
    "default": { "agentMode": "multi" },
    "nodes": {
      "biz": [{ "id": "review", "agentMode": "solo" }]
    }
  }
}
```

## 检查、生成与打包

填完后依次运行下面的命令。也可以在 Agent 中说「我已填完 `./doc-review`，帮我检查并生成插件」，需要 ZIP 时再说明要打包。

```bash
python3 ./booter -C ./doc-review lint
python3 ./booter -C ./doc-review doctor
python3 ./booter -C ./doc-review check
python3 ./booter -C ./doc-review package
```

1. `lint` 检查源配置，按提示修完错误再继续。
2. `doctor` 生成 `plugin.json`、看板和运行文件，并写入节点技能的状态维护块。
3. `check` 核对技能、文件引用和生成结果。
4. `package` 写出 DevClaw 可以导入的 ZIP。示例首次打包后可在 `doc-review/dist/AutoBizDevOps_doc-review-0.1.1.zip` 找到它，默认每次递增补丁版本。

| 检查提示 | 怎么处理 |
| --- | --- |
| `TODO_FIELD` 或 `TODO_PLACEHOLDER` | 按提示找到对应文件，补齐配置或技能中的占位。 |
| `SKILL_MISSING` 或 `SKILL_NAME_MISMATCH` | 核对节点的 `skill`、技能目录名和 `SKILL.md` 的 `name`。 |
| `SKILL_STATE_BLOCK` 或 `BUILD_STALE` | 配置或技能变动后，重新运行 `doctor`，再检查。 |
| `SKILL_REF_DANGLING` | 检查技能引用的模板、资料或脚本是否存在，以及路径是否正确。 |
| `LEGACY_ENTRY_REF` | 删除正文里的旧状态命令，保留原有业务步骤。状态推进由 `doctor` 生成的片段负责。 |

以后加节点、改产物或改运行方式时，编辑对应的源文件，再运行 `lint`、`doctor` 和 `check`。各项改动的位置见[插件修改指南](plugin-customization.md)。
