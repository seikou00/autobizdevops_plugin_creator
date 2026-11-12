# 产物同步模块（modules/artifactSync.json）

| 什么时候需要 | 要先准备什么 | 最少要填哪些字段 |
|---|---|---|
| 节点产物需要交给外部系统评审或归档。 | 可访问的上传服务，以及要同步的产物清单。 | 填 `artifacts`，再用 `allowedFrom` 或 `allowedCheckpoints` 指定何时允许同步。 |

## 字段

| 字段 | 怎么填 |
|---|---|
| `allowedFrom` | 从哪一步起允许同步，写成 `<节点 id>:done`，例如 `plan:done`，之后到流程结束都可以同步；要在节点进行中就允许，写 `<节点 id>:in_progress` |
| `artifacts` | 要上传的产物：键是 `workflow.json` 中某个节点 `outputs` 里的路径，写法要完全一致；值是一句简述，会写进同步目录。没列出的产物不上传，以后节点新增产出也不会自动加进来 |
| `excludeCheckpoints` | 可选，在允许范围里再排除的 checkpoint，例如 `["code_in_progress"]` |
| `extraPaths` | 可选，节点产出以外要一起上传的文件：路径（可以用 glob，相对 Feature 目录）→ 简述 |
| `uploadUrl`、`maxFileSizeMiB` | 可选。上传地址默认是 `https://tscode-cos-plugin.paasuat.cmbchina.cn/file/upload`。单个文件的大小上限默认是 5 MiB，超过的跳过并报告 |
| `skillName` | 可选，同步技能的名字，不能与节点技能重名 |
| `entry` | 可选，看板入口：`enabled` 写 `false` 时不显示入口；`userMessage`、`dialogTips` 是入口的文案 |

例如，`plan` 节点的 `outputs` 包含 `PLAN.md`，并且从该节点完成起允许同步：

```json
{
  "allowedFrom": "plan:done",
  "artifacts": { "PLAN.md": "实施计划" }
}
```

也可以用 `allowedCheckpoints` 列出允许同步的 checkpoint，例如 `["plan_done"]`，此时省略 `allowedFrom`。

## 注意

- 发起同步后，技能会先确认工号和上传目录，再根据实际代码生成接口文档，上传有变化的产物；
- 接口文档 `FEATURE_API_DETAIL.md` 总会同步，不用配置。它不是节点产出，写进 `artifacts` 会报 `ARTIFACT_REF_UNKNOWN`；只想改它的简述时，在 `extraPaths` 里写 `"FEATURE_API_DETAIL.md": "<简述>"`；
- `artifacts` 的简述可以先留着 `[TODO: 简述]` 生成插件（报 `TODO_FIELD` warning），打包前必须填完；
- 同步配置 `skills/<同步技能>/config/artifact-sync.json` 由这个文件生成，不要手改。
