# 全局钩子模块（modules/globalHooks.json）

| 什么时候需要 | 要先准备什么 | 最少要填哪些字段 |
|---|---|---|
| 团队希望自动执行明文密码检查、前端性能检查等规则。 | 用 `hook list` 确认要启用的钩子及触发条件。 | 在 `hooks` 中列出选中的钩子 ID。 |

## 字段

| 字段 | 怎么填 |
|---|---|
| `hooks` | 要启用的钩子 ID 数组。手动生成的骨架会列出全部候选，编辑时只保留选中的 ID |

例如，只启用明文密码检查：

```json
{ "hooks": ["secrets-check"] }
```

## 注意

- 有的钩子只在特定节点上触发。例如 `performance-check` 只在 id 为 `code` 的节点完成时检查，编码节点叫别的名字时它不会生效；启用前先看 `hook list` 的说明；
- 产物检查钩子始终启用，不在这里列；
- 一个都不要时，删掉入口文件 `modules` 中的 `globalHooks` 引用。以后用 `hook enable <id>`、`hook disable <id>` 增减，全部关掉后模块自动关闭；
- 自己写的钩子直接写进 `hooks/hooks.json`，重新生成时原样保留。
