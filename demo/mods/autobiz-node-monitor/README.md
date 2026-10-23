# autobiz-node-monitor（演示 mod）

按 [docs/mods.md](../../../docs/mods.md) §2.3、§2.8 的规则，从会话里发生的事推断节点技能**何时开始、何时完成**，并用状态栏、提示消息（toast）、对话里的日志行和“节点监控”面板提醒。

只做监控：不写 `state.json`，不改项目里已有的文件。监控记录存在 mod 自己的存储里，按会话目录区分。

## 安装

三种方式任选其一。

**Claude Code（本地 marketplace）**：在终端执行

```bash
claude plugin marketplace add /Users/seikou/Documents/GitHub/autobizdevops_plugin_creator/demo/mods
```

```bash
claude plugin install autobiz-node-monitor@autobiz-demo-mods
```

装好后新开的会话就会生效；已经开着的会话执行 `/reload-plugins`。marketplace 是本地目录，所以直接读这个目录：改了文件后 `/reload-plugins` 即可，不用重装。桌面应用里也可以点输入框旁的 +，选 Plugins → Add marketplace，填上面的目录，再添加插件。

**DevClaw（导入 zip）**：导入 `demo/dist/autobiz-node-monitor-0.1.0.zip`，方式与导入其他插件相同。zip 里根目录的 `plugin.json` 声明了 `skills` 和 `hooks`，`hooks/hooks.json` 指向钩子模块 `register.tsx`。

**临时试用（不安装）**：

```bash
claude --plugin-dir /Users/seikou/Documents/GitHub/autobizdevops_plugin_creator/demo/mods/autobiz-node-monitor
```

## 生效了没有

在一个 **git 仓库**里打开会话（默认把会话目录当作代码仓库）：

1. 输入 `/node-monitor`，能看到“○ 增量编码”“○ 代码评审”两行，说明 mod 已加载；
2. 调用 `/demo-code`（作为插件技能，名字可能显示为 `/autobiz-node-monitor:demo-code`），例如“给 README 加一行说明，然后提交”。会弹出提示“增量编码开始，基线 main@xxxxxxx”，并打开“节点监控”面板；
3. 模型每做完一轮，面板和状态栏刷新预检查结果，例如“还没有新提交”“有 1 个文件未提交”；
4. 调用 `/demo-review`：编码没做完时会被拦下，原因附在评审技能正文后；做完时提示“增量编码完成”“代码评审开始”，评审拿到提交范围；
5. 评审写出 `.autobiz-demo/REVIEW.md` 后，这一轮结束，评审完成；
6. `/node-monitor reset` 清空记录，从头再来。

`.autobiz-demo/` 是演示用的 Feature 目录，检查“有没有未提交的改动”时会跳过它。

## 判断规则

| 时机 | 怎么发现 | 做什么 |
|---|---|---|
| 节点开始 | 节点技能展开（斜杠命令，或模型调用 Skill 工具） | 前一步已完成、输入齐全时开始，并为 git 产物记下基线：每个仓库的分支、HEAD、已有的工作树 |
| 每轮结束 | 主会话一轮结束，且没有子代理在运行 | 预检查产物。只有文件产物的节点（`turnEnd`），产物齐全就算完成；有 git 产物的节点（`handoff`）只提醒“可以进入下一步” |
| 交接 | 主会话调用**下一个**节点的技能 | 判定上一节点：通过就连推两步；不通过则下一节点不开始，原因附在下一节点的技能正文后 |
| 手动 | 面板上的“标记完成”，或 `/node-monitor done` | 判定当前节点 |
| 会话结束 | 会话结束事件 | 判定当前的 `handoff` 节点 |

git 产物的齐全条件（`require`，默认前三项）：

- `commits`：基线分支上至少有一个新提交；
- `clean`：仓库没有未提交的改动；
- `merged`：基线之后新建的工作树（例如子代理的独立工作树），其分支上的提交都已合并回基线分支；
- `pushed`：基线分支的提交都已推送。

子代理调用节点技能只会让节点开始，不触发交接；子代理还在运行时，主会话一轮结束不做检查。

`annotateSkill` 为 `true`（默认）时，节点技能展开时会在正文后附上产物约定（输入、输出在哪里，上一步的提交范围），对应设计中的 R2，里面没有任何状态操作。

## 命令

| 命令 | 作用 |
|---|---|
| `/node-monitor` 或 `/node-monitor status` | 打印流程状态和最近一次预检查 |
| `/node-monitor open` | 打开面板 |
| `/node-monitor check` | 立即预检查（不等一轮结束） |
| `/node-monitor done` | 手动判定当前节点 |
| `/node-monitor reset` | 清空本目录的监控记录 |

## 换成自己的流程

按顺序查找配置，用第一个找到的：

1. 环境变量 `AUTOBIZ_NODE_MONITOR_FLOW` 指向的文件；
2. 会话目录下的 `.autobiz-demo/flow.json`；
3. 插件自带的 `flow.json`。

格式与 `workflow.json` 一致，只读用到的字段：

| 字段 | 说明 |
|---|---|
| `featureDir` | 文件产物所在的目录，相对会话目录，默认 `.autobiz-demo` |
| `annotateSkill` | 是否在技能正文后附上产物约定，默认 `true` |
| `nodes[].skill` | 技能名，插件前缀可省略。换成自己插件的技能名，就能监控那个插件 |
| `nodes[].outputs.<id>` | 文件路径，或 `{ "git": { "repos": "project" 或路径数组, "branch": "current", "require": [...] } }` |
| `nodes[].inputs` | 读取的上游产物 id |
| `nodes[].completeOn` | `turnEnd` 或 `handoff`；不写时，有 git 产物或没有产物的节点为 `handoff` |

## 与设计的差别

- 不执行校验命令，不支持人工关口（`humanGate`）；
- `repos` 不支持 `"deployUnits"`，要写 `"project"` 或路径；
- 文件产物不支持 glob；
- 子代理计数在 mod 重载后会归零。

## 开发

```bash
claude plugin validate demo/mods/autobiz-node-monitor
```

```bash
claude plugin test demo/mods/autobiz-node-monitor
```

```bash
python3 demo/mods/package.py
```

最后一条重新打包 `demo/dist/` 下的 zip。
