---
name: autobiz-requirement-discuss
description: [TODO: 做什么；在什么情况下使用]
---

# 需求澄清与 PRD

<!-- scaffold:begin state -->
## 技能状态维护

> 由脚手架生成，请勿手改；节点、checkpoint 或校验命令变化后执行 `autobiz-plugin build` 更新。

- 技能开始执行：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint prd_in_progress
  ```
- 本节点必需产物全部写入 `FEATURE_DIR` 后：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint prd_done
  ```
  推进时框架会检查必需产物是否存在，然后执行本节点的校验命令 `${python} ${pluginPath}/hooks/stage_gate.py validate --stage ${nodeId} --feature ${feature} --workspace ${projectPath}`。未通过时按返回的错误修正产物后重试，不需要自己调用校验命令。
- 需要修改已完成阶段时：`--checkpoint prd_in_progress --reopen --reason "<原因>"`
- 用户明确要求跳过本节点时：`--skip-node biz.prd --reason "<原因>"`
<!-- scaffold:end state -->

<!-- scaffold:begin artifacts -->
## 输入与产物

| 方向 | 产物 | 路径（相对 FEATURE_DIR） | 必需 |
|---|---|---|---|
| 输出 | PRD文档 | `PRD.md` | 是 |
| 输出 | UI范围机器事实源 | `UI_CONTEXT.json` | 是 |
<!-- scaffold:end artifacts -->

（以下为开发者编写的技能正文）

[TODO: 写明本节点的工作步骤、产物要求和完成标准]
