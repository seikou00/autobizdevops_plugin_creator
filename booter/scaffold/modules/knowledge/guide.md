# 知识模块（modules/knowledge.json）

| 什么时候需要 | 要先准备什么 | 最少要填哪些字段 |
|---|---|---|
| 团队希望按发布单元把相关知识带入会话。 | 一份按系统和发布单元整理、带 `agents.manifest.json` 的知识目录。 | 从 Git 拉取时填 `source.url`。交给 DevClaw 组装时填 `assembly.assembler` 为 `devclaw`，其余场景沿用默认的 `plugin`。 |

## 要定的两件事

| 要定什么 | 选项 | 怎么写 |
|---|---|---|
| 知识从哪来 | 从 Git 仓库拉取 | 保留 `source`，填写 `source.url`。 |
| | 随插件一起打包 | 省略 `source`。打包前把带清单的知识目录放进插件根目录的 `sys/`。 |
| | 由 DevClaw 提供 | 省略 `source`，在 DevClaw 给项目绑定知识库。 |
| 谁把知识放进会话上下文 | 插件（默认） | `assembly.assembler` 写 `plugin`，由插件按所选发布单元组装。 |
| | DevClaw | `assembly.assembler` 写 `devclaw`，由 DevClaw 组装。 |

运行时优先使用 DevClaw 传入的项目绑定知识库，其次使用插件的 `sys/`。

## 字段

| 字段 | 怎么填 |
|---|---|
| `assembly.assembler` | `plugin`（默认）或 `devclaw`，见上表 |
| `source.url` | 知识仓库的 HTTPS 地址。知识不从 Git 仓库拉取时，删掉整个 `source` |
| `source.sshUrl` | 可选，HTTPS 克隆失败时改用的 SSH 地址 |
| `source.ref` | 可选，分支、标签或 commit，默认 `master` |
| `manifest.path` | 可选，清单文件相对知识目录的路径，默认 `agents.manifest.json` |
| `assembly.timeoutSec` | 可选，组装脚本的超时秒数，默认 30；超时后这次会话不带知识 |
| `assembly.enabled` | 可选，写 `false` 时会话不带知识，只保留发布单元的选择 |

例如，从 Git 拉取并使用插件组装时，模块配置可写成：

```json
{
  "source": { "url": "https://example.com/team/knowledge.git" },
  "assembly": { "assembler": "plugin" }
}
```

## 生成和检查时可能看到

`doctor` 生成插件后会准备本地环境。以下告警允许继续打包：

- `KNOWLEDGE_PULL`：配置了 `source` 且本地还没有清单时，`doctor` 把仓库拉到 `sys/` 供本地检查。拉取失败时检查网络、仓库权限和 `source.ref`。这份 `sys/` 只供本地检查，运行时由 DevClaw 调用插件的 `pull_knowledge` 拉取；
- `KNOWLEDGE_NODE_DEPS`：由插件组装时，`doctor` 在 `runtime/knowledge/` 下执行 `npm install`。装不上时，会话退回按清单映射加载知识；
- `KNOWLEDGE_MANIFEST_MISSING`（`check`、`package`）：本地检查读取清单失败。按告警里的具体原因检查文件位置或内容。知识由 DevClaw 提供、本地尚无清单时，在 DevClaw 中确认项目绑定和清单即可。
