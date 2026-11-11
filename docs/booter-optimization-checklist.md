# booter 优化清单

2026-11-11 评估 `booter/` 的骨架引导技能（`SKILL.md`、`modeling-guide.md`）和五个模块后整理。评估方式：通读源码，并在临时目录按 `SKILL.md` 实际走了一遍骨架 → 填写 → lint → doctor → package，以及全栈示例的 doctor、check、package。

优先级：P1 会让用户得到错误结果或错误认知，P2 影响体验或维护，P3 可以暂缓。

## P1 建议先修

- [ ] **1. `performance-check` 写死 `code_done`，节点不叫 `code` 时静默失效**
  - 现象：`hook.json` 的命令固定带 `code_done` 参数。编码节点 id 为 `build` 时，钩子照常注册进 `hooks/hooks.json`，但永远不触发，lint 不提示。`SKILL.md` 还推荐“全部启用”。
  - 位置：`booter/scaffold/modules/global_hooks/hooks/performance_check/hook.json`、`booter/scaffold/modules/global_hooks/module.py`
  - 建议：`GlobalHooksModule.validate` 加一条 warning（启用了它但流程里没有 `code` 节点）；更彻底的做法是让 `hook.json` 声明依赖的节点。

- [ ] **2. `SKILL.md` 与 `modeling-guide.md` 对重复产出的说法相反**
  - 现象：`SKILL.md` 写“两个节点不要声明同一个产出文件”；`modeling-guide.md` 写“后面的节点可以再次输出同一个路径”。lint 实际只报 `OUTPUT_REDECLARED` warning，全栈示例自己就这么用。
  - 位置：`booter/SKILL.md`「workflow.json」一节的注意事项、`booter/modeling-guide.md`「产物」一节
  - 建议：以 lint 行为为准统一说法。

- [ ] **3. 产物 id 冲突和保留文件名只写在 `modeling-guide.md`**
  - 现象：`PLAN.md` 与 `plan.md` 推导出同一个产物 id、不能用 `state.json` 等作产物名，这两条只在“你来起草”时才会读到；用户自己填时看不到。
  - 位置：`booter/SKILL.md`「填写指南」
  - 建议：补进填写指南的 `outputs` 说明。

- [ ] **4. 知识模块的选择题和骨架对不上**
  - 现象：选择题有三个选项，`new --skeleton --module knowledge` 只有一种骨架（`assembler: plugin` 加 `source`）。用户选“由 DevClaw 组装”后，`SKILL.md` 没说要把 `assembler` 改成 `devclaw`、要不要删 `source`。
  - 位置：`booter/SKILL.md` 第 1 步的表格、`booter/scaffold/commands/new.py` 的 `SKELETON_MODULES`
  - 建议：“谁组装”和“插件是否拉取知识仓库”是两个独立维度，拆成两问，并写明每个答案对应改哪个字段。

- [ ] **5. 技能没有打包脚本，`booter.zip` 是手工压的**
  - 现象：包里带着 `.DS_Store`、`__MACOSX/`、`.pytest_cache/`、`tests/`、`dist/` 和 3.6M 的 `examples/fullstack-skills`，技能运行时都用不到。`booter.zip` 也没有进 `.gitignore`。
  - 建议：加 `booter/tools/make_skill_zip.py`，显式列出要带的文件（`SKILL.md`、`modeling-guide.md`、`__main__.py`、`scaffold/`、`runtime/`、`schemas/`）；把 `booter.zip` 加进 `.gitignore`。

- [ ] **6. 技能 `name` 与目录名不一致（待确认）**
  - 现象：frontmatter 的 `name` 是 `autobiz-plugin-skeleton`，目录和 zip 顶层叫 `booter`。部分宿主要求两者一致。
  - 待确认：DevClaw 是否有这条要求。

## P2 体验与一致性

- [ ] **7. `request_user_input` 没有兜底**
  - 现象：这是特定宿主的工具名，宿主没有这个工具时 `SKILL.md` 没说怎么办。
  - 建议：加一句“没有这个工具时退回普通提问，仍然给出选项”。

- [ ] **8. `SKILL.md` 的全局钩子表格会过期**
  - 现象：表格与 `hook list` 的输出重复，新增钩子后要同步改。
  - 建议：删掉表格，只留“以 `hook list` 为准”。

- [ ] **9. `-C` 传相对路径时 `package.path` 返回绝对路径**
  - 现象：`-C .` 时返回绝对路径，与 `SKILL.md` 说的“相对插件目录”不符；`-C` 传绝对路径时正常。
  - 位置：`booter/scaffold/commands/package.py` 的 `package()`，`target.relative_to(root)` 前没有把 `root` 解析成绝对路径

- [ ] **10. `doctor` 生成空白技能后仍报 `SKILL_MISSING`**
  - 现象：同一次输出里既有 `changes.skills.created`，又有对应节点的 `SKILL_MISSING` warning；再跑一次才消失。
  - 位置：`booter/scaffold/commands/doctor.py`，warning 来自写盘前的 `analyze`

- [ ] **11. `package` 对同一处占位重复报**
  - 现象：同一个文件同时报 `TODO_PLACEHOLDER`（error，不带位置）和 `TODO_FIELD`（warning，带位置）。
  - 位置：`booter/scaffold/commands/check.py` 的 `resource_rules`
  - 建议：`package` 模式下直接把 `TODO_FIELD` 升为 error，或让 `TODO_PLACEHOLDER` 带上 `pointer`。

- [ ] **12. `module enable` 的帮助文字漏了 globalHooks**
  - 位置：`booter/scaffold/cli.py`，“启用 knowledge 或 artifactSync”

- [ ] **13. 钩子超时取值待确认**
  - 现象：`secrets-check` 是 1000，`performance-check` 是 7200，产物检查是 30。没有查到单位定义；如果是秒，每次写文件都触发的钩子给 1000 秒偏大。
  - 位置：两个 `hook.json`

## P2 测试

- [ ] **14. `test_fullstack` 失败**
  - 现象：全量 123 个测试中 1 个失败，`tests/golden/test_reference.py` 的 `test_fullstack`：`runtimePolicy` 与同级仓库 `autobiz_kanban` 的现状对不上（`multi` 对 `solo`，`customSubagentFiles` 也不同）。
  - 原因：基线取的是外部仓库的当前内容，对方改了就变红。
  - 建议：把参考基线固定成仓库内的快照，或确认是哪一边该改。

- [ ] **15. 全量测试约 98 秒**
  - 现象：主要耗在 `test_cli`、`test_p1`、`test_customized`，各约 14 秒，反复起子进程调 CLI。
  - 建议：能进程内调用 `scaffold.cli.main` 的用例不走子进程。

## P3 可以暂缓

- [ ] **16. 新增模块要改多处**
  - 现象：要同时改 `MODULE_KEYS`、`SCHEMAS`、`PACKAGE_DIRS`、`MERGE_ORDER`、`SKELETON_MODULES`，而全局钩子是加目录即可。
  - 判断：只有五个模块，现在不值得动；要加第六个模块时再收拢到 `module.json`。

- [ ] **17. 知识目录常量重复**
  - 现象：`"sys"` 和 `KNOWLEDGE_ARGS` 在 `modules/knowledge/module.py`、`modules/knowledge/pull.py`、`modules/session/module.py`、`commands/package.py` 各写了一份。
