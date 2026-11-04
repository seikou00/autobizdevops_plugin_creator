---
name: autobiz-plugin-skeleton
description: 以配置骨架引导用户自己完成 AutoBiz 看板插件：先用 autobiz-plugin new --skeleton 生成带 [TODO] 占位的 workflow.json 和模块配置，停下来让用户自行填写，检查通过后导入已有技能或引导填写空白 SKILL.md，最后打包。当用户想自己动手写插件配置、要一份可以照着填的配置模板，或说“先给我骨架、我自己填”时使用；想通过对话由助手建模时改用 autobiz-plugin-creator。
metadata:
  version: 1.0.0
---

# 看板插件骨架引导

带用户走完：**生成骨架 → 用户填配置 → 检查 → 技能（导入或填写空白）→ 打包**。配置和技能内容由用户自己填，你负责生成骨架、解释占位、调用 CLI、转述检查结果。

## 调用 CLI

本技能与 `autobiz-plugin-creator` 在同一个插件包中，共用它的 CLI：

```bash
python3 "${pluginPath}/skills/autobiz-plugin-creator/scripts/autobiz-plugin.pyz" <命令> --json
```

- 对已有插件目录的命令加 `-C "<插件目录>"`；Windows 上把 `python3` 换成 `python`；
- `${pluginPath}` 没有被替换时，按本文件所在目录的同级目录定位 `../autobiz-plugin-creator/scripts/autobiz-plugin.pyz`；
- 退出码：`0` 成功（可能有 warning）；`1` 有 error，没有写入任何文件；`2` 用法错误；
- `--json` 输出 `{"ok", "issues": [{level, code, file, pointer, message, hint}], "written": [...]}`。判断一律以退出码和 `issues` 为准，不要自己宣称“检查通过”。

## 流程

一次只做一步，需要用户动手的地方必须停下来等用户回复。

### 1. 生成骨架

先问清楚两件事，一次问完：

- 插件目录放在哪里（必须不存在或为空）；
- 要不要这些可选模块，逐个说明后让用户选：

| 模块 | 用途 | 不选时 |
|---|---|---|
| `board` | 看板上的流程名称、描述、对话提示 | 全部取默认值（建议选上，至少要填流程名称） |
| `session` | 默认运行策略（`agentMode`）、节点单独的策略和子代理 | 取默认值 `multi` |
| `knowledge` | 按所选发布单元加载知识，可以由插件拉取知识仓库 | 不启用知识模块 |
| `artifactSync` | 把节点产物上传到外部服务，看板上生成同步入口 | 不启用 |
| `globalHooks` | 脚手架自带的公共钩子，如明文密码检查、前端性能检查（可用 `hook list` 查看全部） | 只有默认的产物检查钩子 |

然后生成骨架，每个选中的模块加一个 `--module`：

```bash
python3 "<pyz>" new "<插件目录>" --skeleton --module board --module artifactSync --json
```

### 2. 停下来，让用户填写配置

告诉用户要填哪些文件、每个文件里有哪些 `[TODO: …]`，然后**停下来**，等用户说填好了再继续。不要替用户填写，也不要猜测流程；用户问某个字段怎么填时，按下表解释，必要时给一个例子让用户自己决定。

| 文件 | 要填的内容 |
|---|---|
| `plugin.scaffold.json` | `plugin.id`：插件 ID，小写字母、数字和连字符，**发布后不能改**；`name`：插件名；`description`：一句话描述；`version` 已填 `0.1.0`，可以改 |
| `workflow.json` | 骨架里 `biz`、`dev` 各有一个节点，按实际流程增删：节点 `id`（小写字母开头，只含小写字母、数字和 `_`，全局不重复）、`name`（看板上的显示名）、`skill`（技能目录名，小写字母、数字和连字符，一个技能只绑定一个节点）、`outputs`（节点产出的文件名，没有产出就删掉这个字段）。`seq` 是执行顺序，全局不重复，要按 biz → dev → ops 递增；需要 `ops` 组就自己加 |
| `modules/board.json` | `display.workflowLabel`：看板上的流程名称 |
| `modules/knowledge.json` | `source.url`：知识仓库 HTTPS 地址；插件不负责拉取知识仓库就删掉整个 `source` |
| `modules/artifactSync.json` | `allowedFrom`：从哪个节点完成起允许同步，写成 `<节点 id>:done`；`artifacts`：键是要上传的产物路径，必须与 `workflow.json` 某个节点 `outputs` 中的写法完全一致，值是简述 |
| `modules/globalHooks.json` | `hooks`：要启用的钩子 id，例如 `secrets-check`、`performance-check`（`hook list` 可查）；一个都不要就去掉入口文件 `modules` 中的 `globalHooks` 引用 |

提示用户：阶段名只能是 `biz`、`dev`、`ops`；编辑器支持 JSON Schema 时，字段会有补全和校验（Schema 在插件目录的 `.scaffold/` 下）。

### 3. 检查配置

用户说填好后运行：

```bash
python3 "<pyz>" -C "<插件目录>" lint --json
```

- 有 `TODO_FIELD`：按 `file` 和 `pointer` 告诉用户哪些占位还没填，原样转述 `message` 中的说明；
- 有其他 error（`INPUT_SCHEMA`、`SEQ_DUP`、`SEQ_STAGE_ORDER`、`NODE_DUP`、`SKILL_SHARED`、`ARTIFACT_REF_UNKNOWN` 等）：转述 `message` 和 `hint`，指出要改的文件和位置；
- 只剩 `SKILL_MISSING` 这类 warning 时可以继续：技能在下一步处理；
- `modules/artifactSync.json` 中简述（`artifacts` 的值）还是 `[TODO: …]` 时只报 warning，可以继续，但打包前必须填完。

有 error 就**停下来**让用户修改，用户说改好后再 `lint`，直到没有 error。

### 4. 技能

问用户：**是否已有写好的技能？**

**已有技能**：问技能所在的目录，以及有没有配套的 agents 目录（`modules/session.json` 中引用子代理文件时需要），然后导入：

```bash
python3 "<pyz>" -C "<插件目录>" add skills --from "<技能集合目录>" [--agents "<agents 目录>"] --json
```

- `<技能集合目录>` 下一级是各个技能目录，也可以多一层分组（`<集合>/<分组>/<技能>/SKILL.md`），分组结构和共享的 `references/`、`hooks/` 会原样保留；只有一个技能时用 `add skill <技能名> --from "<技能目录>"`；
- 技能目录名就是技能名，要与 `workflow.json` 中节点的 `skill` 一致；导入后仍报 `SKILL_MISSING` 的节点，说明名字对不上或者缺技能，告诉用户；
- 这条命令会同时生成插件，没有技能的节点自动生成空白 `SKILL.md`；
- 报出 `LEGACY_ENTRY_REF` 时，是技能正文里残留的旧状态命令（调用 `update_state.py`、`hooks/update_checkpoint.py` 等）：把行号和所在小节告诉用户，用户确认后再删，或由用户自己删。状态只由文件开头的状态维护片段维护。

**没有技能**：先生成插件，为每个节点生成空白 `SKILL.md`：

```bash
python3 "<pyz>" -C "<插件目录>" doctor --json
```

然后列出生成的空白文件（`changes.skills.created`），引导用户逐个填写，**停下来**等用户填完：

- frontmatter 的 `description`：写清楚“做什么、在什么情况下使用”，看板上的节点描述也取自这里；
- 正文：这个节点的工作步骤、产出要求、完成前要满足的条件（例如测试通过、评审结论明确）；
- `<!-- plugin workflow: begin state -->` 到 `<!-- plugin workflow: end state -->` 之间是状态维护片段，**不能改也不能删**；正文里不要再写调用 `update_state.py` 的命令；
- 可以把参考资料放进技能目录的 `references/`，脚本放进 `scripts/`，并在正文中写明什么时候用哪个文件。

导入的技能里有些节点仍是空白 `SKILL.md` 时，同样按上面引导用户填写。

### 5. 打包

用户说技能都填好后，先重新生成（改了技能的 `description` 不重新生成会报 `BUILD_STALE`），再打包：

```bash
python3 "<pyz>" -C "<插件目录>" doctor --json
python3 "<pyz>" -C "<插件目录>" package --json
```

- `package` 会先做完整检查；报 `TODO_PLACEHOLDER` 说明还有没填的 `[TODO: …]`（空白技能的 `description`、artifactSync 的简述等），报 `LEGACY_ENTRY_REF` 说明技能正文里还有旧状态命令：转述位置，**停下来**让用户改完，再从 `doctor` 重来；
- 成功时把生成的 zip 告诉用户：`package.path` 是相对插件目录的路径（默认 `dist/<plugin.id>-<version>.zip`），这个 zip 可以直接导入 DevClaw。

## 规则

- `workflow.json`、`modules/*.json`、`plugin.scaffold.json` 和技能内容都由用户自己填写；只有用户明确要求你代填某一处时才改，改完把改动告诉用户；
- 不得修改 `plugin.json`、`board_core/`、`runtime/`、`.scaffold/`、`hooks/artifact_guard.py`，也不得改 `SKILL.md` 中的状态维护片段，或用其他方式绕过检查；
- `doctor` 的 `--force`、`--allow-id-change` 等放行参数只在用户看过对应 Issue 并明确同意后才加；
- Issue 按原文转述，带上文件和位置；不要自行判断“没问题”。
