# 看板（modules/board.json）

| | |
|---|---|
| 什么时候要写 | 自定义看板的流程名称、对话提示或目标平台时。沿用默认值可以省略整个文件 |

## 字段

| 字段 | 怎么填 |
|---|---|
| `display.workflowLabel` | 可选，看板上的流程名称，例如“需求开发”。默认取 `plugin.name` |
| `display.workflowDescription` | 可选，流程的一句话说明；不写时按节点名连成“需求 → 计划 → 编码。” |
| `display.dialogTips` | 可选，用户发起对话时的提示语，可以用 `${projectCode}`、`${pluginWorkspace}`、`${projectDir}` |
| `display.systemPromptInject` | 可选，注入系统提示的内容。默认值已经写明 Feature 产物目录 `FEATURE_DIR`，自己写时要保留它 |
| `display.stateLabels` | 可选，状态名：`not_started`、`in_progress`、`done`、`archived`，默认“未开始”“进行中”“已完成”“已归档” |
| `target.platforms` | 可选，插件支持的平台，默认 `darwin`、`linux`、`win32` 全部 |

拿不准时可以先用默认文案，看过生成结果后再调整（见 SKILL.md「之后微调文案」）。
