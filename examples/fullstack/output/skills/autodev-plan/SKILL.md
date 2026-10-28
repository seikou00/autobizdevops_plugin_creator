---
name: autodev-plan
description: [TODO: 做什么；在什么情况下使用]
---

# 执行计划

<!-- scaffold:begin state -->
## 技能状态维护

> 由脚手架生成，请勿手改；节点、checkpoint 或校验命令变化后执行 `autobiz-plugin build` 更新。

- 技能开始执行：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint plan_in_progress
  ```
- 本节点必需产物全部写入 `FEATURE_DIR` 后：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint plan_done
  ```
  推进时框架会检查必需产物是否存在，然后执行本节点的校验命令 `${python} ${pluginPath}/hooks/stage_gate.py validate --stage ${nodeId} --feature ${feature} --workspace ${projectPath}`。未通过时按返回的错误修正产物后重试，不需要自己调用校验命令。
- 本节点完成后，询问用户是否执行「详细设计」，按选择推进：
  - 需要，生成详细设计（先进入 autodev-detail-design，生成 DETAIL_DESIGN.md 后再进入代码实现。）：`--checkpoint detail_design_in_progress`
  - 不需要，直接编码（不生成 DETAIL_DESIGN.md，直接进入 autodev-code。）：`--checkpoint code_in_progress`
- 需要修改已完成阶段时：`--checkpoint plan_in_progress --reopen --reason "<原因>"`
- 用户明确要求跳过本节点时：`--skip-node dev.plan --reason "<原因>"`
<!-- scaffold:end state -->

<!-- scaffold:begin artifacts -->
## 输入与产物

| 方向 | 产物 | 路径（相对 FEATURE_DIR） | 必需 |
|---|---|---|---|
| 输入 | 变更提案 | `proposal.md` | 是 |
| 输入 | 行为规格 | `specs/**/*.md` | 是 |
| 输入 | UI范围机器事实源 | `UI_CONTEXT.json` | 是 |
| 输入 | 技术设计 | `design.md` | 是 |
| 输入 | 设计契约锁 | `.design-contract.lock.json` | 是 |
| 输出 | 执行计划 | `PLAN.md` | 是 |
| 输出 | 计划机器结构化内容 | `plan.json` | 是 |
<!-- scaffold:end artifacts -->

（以下为开发者编写的技能正文）

[TODO: 写明本节点的工作步骤、产物要求和完成标准]
