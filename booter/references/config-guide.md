# 配置填写指南

## plugin.scaffold.json

| 字段 | 怎么填 |
|---|---|
| `plugin.id` | 保留 `AutoBizDevOps_` 前缀，填写后缀，例如 `AutoBizDevOps_Doc_Review`。ID 只含英文字母、数字、短横线和下划线，含前缀共不超过 64 字符。它同时是安装目录名和状态文件里的 `pluginId`，发布后再改，已有项目的状态就对不上了 |
| `plugin.name` | 保留 `AutoBizDevOps_` 前缀，填写在 DevClaw 中显示的插件名，例如 `AutoBizDevOps_文档评审` |
| `plugin.description` | 一句话说明插件做什么 |
| `plugin.version` | 版本号，默认 `0.1.0`。之后由 `package` 自动递增，一般不用手改 |

`workflow`、`modules` 是对其他文件的引用，保持生成时的样子即可。

## workflow.json

顶层只有 `nodes`，按阶段分成 `biz`、`dev`、`ops` 三组。组名只能是这三个，可以只写其中几组。每个节点：

| 字段 | 怎么填 |
|---|---|
| `id` | 小写字母开头，只含小写字母、数字和 `_`，全局不重复，不加阶段前缀（写 `plan`，不写 `dev_plan`）。checkpoint 名由它推出：`plan_in_progress`、`plan_done` |
| `seq` | 执行顺序，正整数，全局不重复，可以跳号（写 10、20、30，以后插节点不用改别的）；要按 biz → dev → ops 递增 |
| `name` | 看板上的显示名，例如“需求澄清” |
| `skill` | 技能目录名，小写字母、数字和连字符。一个技能只绑定一个节点，因为技能开头写着这个节点专属的状态命令。技能会按节点阶段放进 `skills/autobiz/`、`skills/autodev/` 或 `skills/autoops/` |
| `outputs` | 节点产出的文件，路径相对 Feature 目录，可以用 glob（`specs/**/*.md`）；可有可无的写成 `{"path": "PR_BODY.md", "optional": true}`；没有产出（例如编码节点）就删掉这个字段 |
| `terminal` | 可选。`true` 表示终态节点（例如“归档”），只能是 `seq` 最大的节点，不能有 `outputs`，完成后流程进入 `archived` |

填的时候注意：

- 推进到 `_done` 时会检查必需产出都存在且不为空，缺了会被拦下。所以 `outputs` 只写这个节点每次一定会产出的文件，偶尔才有的标成可选；
- 两个节点不要声明同一个产出文件；
- 节点要读哪些上游文件，写在技能正文里，不用写进配置。

例如：

```json
{
  "nodes": {
    "biz": [ { "id": "prd", "seq": 10, "name": "需求", "skill": "my-prd", "outputs": ["PRD.md"] } ],
    "dev": [
      { "id": "plan", "seq": 20, "name": "计划", "skill": "my-plan", "outputs": ["plan.md"] },
      { "id": "code", "seq": 30, "name": "编码", "skill": "my-code" }
    ],
    "ops": [ { "id": "archive", "seq": 40, "name": "归档", "skill": "my-archive", "terminal": true } ]
  }
}
```

## modules/*.json

各模块的字段说明见 [SKILL.md](../SKILL.md) 第 2 步读取的模块指南。
