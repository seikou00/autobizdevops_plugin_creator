# 快速上手：四步出一个插件

只讲必要的步骤。需要定制流程、模块或接入 CI 时看 [usage-advanced.md](usage-advanced.md)。

准备：Python 3.9+。以下命令都在 `booter/` 下执行，Windows 上把 `python3` 换成 `python`。示例假设各仓库都在 `~/Documents/GitHub/` 下，换成你自己的路径即可。

## 1. 进入脚手架目录

```bash
cd ~/Documents/GitHub/autobizdevops_plugin_creator/booter
```

## 2. 以样例为起点新建插件

```bash
python3 -m scaffold new ~/Documents/GitHub/my-plugin --from lite --yes
```

- `lite`：需求 → 规格 → 计划 → 编码四个节点；要 Biz→Dev→Ops 全流程，换成 `fullstack`；
- 不想用样例、想边问边填：去掉 `--from lite --yes`，向导会逐项提问；
- 目标目录必须不存在或为空。

这一步结束时插件已经可以运行，技能是空白的 `SKILL.md`。

## 3. 放入技能和 agents

lite：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin add skills --from ~/Documents/GitHub/autobizdevops_lite/skills --agents ~/Documents/GitHub/autobizdevops_lite/agents
```

fullstack 的技能按 `autobiz/`、`autodev/`、`autoops/` 分了组，直接导入整个 `skills/` 目录即可，分组结构和共享的 `references/`、`hooks/` 会原样保留：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin add skills --from ~/Documents/GitHub/autobiz_kanban/skills --agents ~/Documents/GitHub/autobiz_kanban/agents
```

导入时如果提示 `LEGACY_ENTRY_REF`：打开提示中的 `SKILL.md`，删掉旧的「技能状态维护」小节（调用 `hooks/update_state.py` 的那几行）。脚手架已经在文件开头写好了新的状态维护片段，旧的不删，打包时会报错。

## 4. 打包

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin package
```

打包前会自动检查。通过后生成 `my-plugin/dist/<插件 id>-<版本>.zip`，导入 DevClaw 即可。

## 之后改了配置

改了 `plugin.scaffold.json`、`workflow.json`、`modules/*.json`，或技能 `SKILL.md` 开头的 `description` 之后，先重新生成，再打包：

```bash
python3 -m scaffold -C ~/Documents/GitHub/my-plugin doctor
```

## 常见报错

| 报错 | 怎么办 |
|---|---|
| `LEGACY_ENTRY_REF` | 删掉 `SKILL.md` 里旧的状态维护命令（见第 3 步） |
| 打包提示还有 `[TODO: …]` 占位 | 空白技能还没填写：补上 `SKILL.md` 的 `description` 和正文，或导入真实技能 |
| `SUBAGENT_FILE_MISSING` | `modules/session.json` 引用的 agents 文件不存在：导入技能时加 `--agents <目录>` |
| `BUILD_STALE` | 改了配置或技能 `description` 但没重新生成：执行 doctor |
| 目标目录必须不存在或为空 | 换一个新目录，或清空它 |
