# 运行策略（modules/session.json）

| | |
|---|---|
| 作用 | 设置默认和逐节点的运行方式、子代理和工具开关。省略此文件时，各节点沿用 `multi` |
| 什么时候要写 | 想更改全局默认策略、覆盖单个节点的运行方式（例如编码节点用 `agent_team`），或配置内置和自带的子代理 |

会话入口由框架生成。要按发布单元带入知识，配置[发布单元知识](../knowledge/guide.md)。

## 字段

| 字段 | 怎么填 |
|---|---|
| `policies.default.agentMode` | 默认运行方式：`multi`（默认）、`solo`、`agent_team`、`workflow`，由 DevClaw 解释 |
| `policies.nodes.<阶段>[]` | 单独配置的节点，按 `biz`、`dev`、`ops` 分组，组要与节点在 `workflow.json` 中所在的组一致。每项从 `id` 开始，例如 `{"id": "code", "agentMode": "agent_team"}`；只写需要单独配置的节点，没写的字段沿用 `default` |
| `subagentConfig.disabledBuiltinSubagents` | 可选，要禁用的内置子代理名，例如 `["Explore", "critic"]` |
| `subagentConfig.customSubagentFiles` | 可选，插件自带的子代理文件，例如 `agents/explore.md` |
| `toolCustomConfig` | 可选，宿主工具的开关，例如 `{"task": {"enabled": true}}`，原样下发 |

`subagentConfig`、`toolCustomConfig` 可以写在 `default` 里，也可以写在单个节点里。

## 注意

- `customSubagentFiles` 引用的文件要放在插件的 `agents/` 下，导入技能时用 `--agents` 一起拷进来。文件不存在时报 `SUBAGENT_FILE_MISSING`（warning），运行时跳过；
- 节点 id 写错、或放错了分组，报 `POLICY_NODE_UNKNOWN`。
