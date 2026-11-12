# AutoBiz 看板插件修改指南

适用于通过 AutoBiz 引导技能生成的 DevClaw 看板插件。本文中的文件路径均相对于**要修改的插件目录**。通过引导技能操作时，选择 **修改已有插件**，提供插件源目录，再说明你希望改变的行为。

## 想改什么，去哪里改

| 要改的内容 | 文件和字段 |
| --- | --- |
| 新增、删除、改名或调整节点顺序 | `workflow.json` 的 `nodes.<阶段>` |
| 更换节点绑定的技能或修改技能步骤 | `workflow.json` 的 `skill` 和对应的 `skills/**/SKILL.md` |
| 修改产物路径、看板产物卡片和必需产物 | `workflow.json` 的 `outputs` |
| 自定义项目下的 `.autobizdevops` 目录名 | `plugin.scaffold.json` 的 `runtime.metaRoot`，见下文 |
| 修改状态中文名、节点描述、输入框预填内容和提示语 | `runtime/config/board.json` 中允许修改的文字字段，见下文 |
| 改变全局或单个节点的 Agent 运行模式、子代理与工具 | `modules/session.json`，自定义子代理文件放在 `agents/` |
| 添加技能脚本或插件钩子 | 技能内的 `scripts/` 或 `hooks/` 放技能资源。插件级钩子在 `hooks/hooks.json` 注册 |
| 设置发布单元知识来源和组装方 | `modules/knowledge.json` |
| 修改看板默认提示和系统提示词 | `modules/board.json` 的 `display`。单平台文案也可直接改 `board_core/board_config.json` 中对应平台的文字字段 |
| 修改会话中的发布单元知识段 | 使用插件组装知识时，可替换 `runtime/knowledge/render_collected_session_context.py` |

## 1. 增删改节点、技能和产物

`workflow.json` 的 `nodes` 按 `biz`、`dev`、`ops` 分组。把新节点对象放入对应阶段的数组。下面是一个完整的最小流程示例，已有插件只需增改对应项。

```json
{
  "nodes": {
    "dev": [
      {
        "id": "test",
        "name": "测试",
        "skill": "project-test",
        "seq": 30,
        "outputs": ["TEST_REPORT.md"]
      }
    ]
  }
}
```

- `id` 是稳定标识，用来推导节点的 checkpoint。只改显示名称时修改 `name`。改动已发布节点的 `id` 或删除节点，可能导致已有 Feature 找不到原 checkpoint，修改前应核对已有状态。
- `skill` 填技能目录名，一个节点绑定一个技能，同一个技能不能绑定多个节点。`seq` 是全局唯一的正整数，按 `biz → dev → ops` 递增。
- 删除节点时，先检查下游技能是否读取它的产物，以及运行策略、产物同步等配置是否引用它。删除节点对象后可保留原技能作为辅助能力。确认没有引用且确实不需要时，再清理技能目录。
- `outputs` 是相对当前 Feature 产物目录的路径列表，支持 glob，例如 `specs/**/*.md`。它使用文件路径通配符语法。写成 `{"path":"TEST_REPORT.md","optional":true}` 表示可选产物。必需产物缺失或为空时，框架会阻止节点完成。看板产物卡片从这些路径生成，上游文件的读取要求写在消费它的技能正文中。

节点技能的 `SKILL.md` 可以编辑描述和工作步骤。文件顶部由脚手架维护的状态片段负责开始和完成节点，应保留两个标记及其中的命令。普通节点的 checkpoint 由节点 ID 推导，例如 `test_in_progress` 和 `test_done`。终态节点完成时进入 `archived`。看板根据当前 checkpoint 和流程顺序计算节点状态，再用 `stateLabels` 显示相应文案。

## 2.  `runtime`

`runtime/` 是随插件一起分发的运行层。脚手架把源配置转换成运行配置，由 DevClaw 调用其中的适配脚本获取看板数据、创建 Feature、更新状态或注入会话上下文。

| 运行文件或目录 | 改动会影响什么 | 日常修改入口 |
| --- | --- | --- |
| `runtime/config/board.json` | 状态显示名、节点描述、各状态下的技能入口和对话文案 | 只直接编辑下表列出的文字。技能入口由流程生成 |

项目的实际进度保存在项目元数据目录的 `state.json`，默认位于项目的 `.autobizdevops/state.json`。调整节点或看板文案时，通过流程配置和技能维护状态。
### 自定义 `.autobizdevops` 目录名

`.autobizdevops` 是默认值，可以在插件源目录的 `plugin.scaffold.json` 中修改。打开已有文件，把下面的 `metaRoot` 合并到顶层的 `runtime` 对象中。没有 `runtime` 时新增该对象。

```json
{
  "runtime": {
    "metaRoot": ".my-plugin"
  }
}
```

`metaRoot` 是相对于每个项目的目录路径。上例会让插件在项目下使用 `.my-plugin/state.json` 存储进度，并将 Feature 产物放在 `.my-plugin/features/` 下。如果多个插件用于同一个项目，应为它们设置不同的 `metaRoot`。

- **尚未产生项目数据**。建议首次生成插件前设置。若已经用旧值生成过插件，脚手架可能报 `LAYOUT_CHANGED`。确认没有数据需要迁移后，可运行 `doctor --allow-layout-change` 重新生成。
- **已有项目数据**。改名需要迁移。先备份每个受影响项目的旧目录，规划状态、产物和日志的迁移，并检查技能、钩子和自定义提示中是否写死旧路径。`doctor --allow-layout-change` 只放行重新生成，旧目录的数据需要另行迁移。升级后应验证原有 Feature 的进度和产物都能读取。

### 直接修改看板文案

打开 `runtime/config/board.json`。在 `nodes` 中按阶段和节点 ID 找到对应条目，只更新以下文字。

| 字段 | 修改后的效果 |
| --- | --- |
| `template.label`、`template.description` | 修改流程标题和说明 |
| `stateLabels.not_started`、`in_progress`、`done` | 修改普通节点的「未开始」「进行中」「已完成」显示名 |
| `stateLabels.archived` | 有归档终态时，修改归档显示名 |
| 节点的 `description` | 修改节点在看板上的介绍。生成时默认取自该技能的 `SKILL.md` 描述 |
| 节点的 `nextAction.<状态>.userMessage` | 修改触发对应操作时预填到对话输入框的用户消息 |
| 节点的 `nextAction.<状态>.dialogTips` | 修改对应操作的提示语 |

普通节点在未开始或进行中时，生成的 `slashSkill` 指向当前技能。节点完成后通常指向下一节点的技能，最后一个普通节点没有后继时为空。要调整这个目标，应改流程顺序或节点绑定的技能。修改提示词时也要核对其中提到的技能是否与实际目标一致。

例如，要把「开发」完成后的提示改成「接下来运行测试」，在 `nodes.dev` 里找到开发节点，只修改它的 `nextAction.done.dialogTips`。如果还希望预填「请运行测试并记录失败项」，就在同一个 `done` 对象里改 `userMessage`。已有的 `slashSkill` 保持由流程生成。

重新生成会保留直接修改的受支持文案。如果出现 `CUSTOMIZED_STALE`，请核对保留下来的文字是否仍与新流程匹配。手改 `slashSkill`、节点 ID 或其他受管理内容会触发 `DRIFT_GENERATED`。托管脚本被改动时，`doctor` 也可能拒绝覆盖。

## 3. 配置运行模式和子代理

选择 **自定义运行模式**。如果插件没有 `modules/session.json`，可以请引导技能创建文件并在 `plugin.scaffold.json` 中添加引用。下面的配置让全局默认使用多 Agent，只把开发阶段的 `code` 节点设为 Agent 团队。

```json
{
  "policies": {
    "default": { "agentMode": "multi" },
    "nodes": {
      "dev": [
        { "id": "code", "agentMode": "agent_team" }
      ]
    }
  }
}
```

可选模式为 `multi`（多 Agent）、`solo`（单 Agent）、`agent_team`（Agent 团队）和 `workflow`（工作流）。未设置节点覆盖的字段继承全局策略。配置节点时，阶段和 ID 必须与 `workflow.json` 一致。

需要自定义子代理时，在全局或对应节点的策略中配置 `subagentConfig.customSubagentFiles`，例如 `["agents/review-helper.md"]`。用 `disabledBuiltinSubagents` 填入希望禁用的内置角色名。需要配置任务工具时，可按宿主支持情况使用 `toolCustomConfig`，例如 `{"task":{"enabled":true}}`。脚手架负责传递这些设置。角色名称、权限及不同模式下的实际支持范围由所用 DevClaw 版本决定。

## 4. 放置技能脚本与注册插件钩子

由单个技能主动调用的资源可以放在该技能目录的 `scripts/` 或 `hooks/` 下，并在技能正文中引用。文件放入这些目录后，由技能按需要调用。

需要 DevClaw 按事件自动触发的插件钩子，应在插件的 `hooks/hooks.json` 对应事件中登记，并把脚本一同放入插件。比如 `PreToolUse` 按工具匹配条件在工具执行前调用钩子。脚手架会添加自己的产物检查条目，并保留开发者自定义条目。已有插件若使用 `persistAfterInterrupt`，它的作用范围由宿主决定，请在目标 DevClaw 版本中验证。

## 5. 设置知识来源与会话注入

**知识来源**在 `modules/knowledge.json` 配置。Git 来源填写 `source.url`，按需指定分支、标签或提交 `source.ref`，以及 HTTPS 失败时回退的 `source.sshUrl`。随插件分发时省略 `source`，将带清单的知识目录放入 `sys/`。使用 DevClaw 项目绑定的知识库时同样省略 `source`，并在宿主设置项目绑定。

**组装方**通过 `assembly.assembler` 选择。`plugin` 让插件按所选发布单元组装知识段，`devclaw` 交给宿主。插件组装时优先在平台传入的知识库中查找与所选发布单元匹配的目录，再查找插件的 `sys/`。

**静态系统提示**可在 `modules/board.json` 的 `display.systemPromptInject` 修改。只想为某个平台微调时，可以直接编辑 `board_core/board_config.json` 的 `inspectCommands.<平台>.system_prompt_inject`。同一平台的 `dialog_tips` 也可改。三个平台是 `darwin`、`linux` 和 `win32`。

| 系统提示中可用的占位符 | 含义 |
| --- | --- |
| `${pluginPath}` | 插件安装目录 |
| `${pluginWorkspace}` | 项目集合所在的工作区 |
| `${projectDir}` | 当前项目的目录名 |
| `${feature}` | 当前 Feature |

如果重写系统提示，保留准确的 `FEATURE_DIR`。默认目录是项目下的 `.autobizdevops/features/<当前 Feature>`，自定义元数据根目录时要与 `runtime.metaRoot` 一致。修改提示中的文字只会改变模型收到的说明。实际目录由运行框架按源配置和项目状态计算。

**动态会话上下文**由宿主调用 `session_context_inject`，入口脚本是 `runtime/session/render_session_context.py`。它提供当前 Feature、流程位置、目标技能和 Agent 配置。需要自定义动态知识段时，在启用插件组装知识后替换 `runtime/knowledge/render_collected_session_context.py`。这是允许替换的扩展文件，`doctor` 会保留你的实现。脚本从标准输入读取 JSON，向标准输出返回包含 `sessionContext` 的 JSON，日志写标准错误。返回的知识段会追加在流程上下文之后。需要接入时参照[知识组装脚本协议](interfaces.md#45-知识组装脚本render_collected_session_contextpy)。

## 6. 修改完成后

1. 请引导技能列出改动及受影响的节点，先检查源配置（`lint`），再重新生成（`doctor`）并检查生成结果（`check`）。可用测试 Feature 验证节点推进、看板文案和运行策略。
2. 仅改插件自有钩子条目时，构建不要求重新生成，仍应检查配置并在宿主验证触发行为。
3. 需要交付新版时，再请模型打包（`package`）。打包会递增补丁版本，生成的 ZIP 在插件目录的 `dist/` 下。

可直接对引导技能说：“读取这个插件，修改测试节点的报告路径和完成后的提示。先给我看受影响的文件和下游节点，确认后重新生成并检查。”
