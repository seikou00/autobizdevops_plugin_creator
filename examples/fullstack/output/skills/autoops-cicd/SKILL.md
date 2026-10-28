---
name: autoops-cicd
description: [TODO: 做什么；在什么情况下使用]
---

# CI/CD

<!-- scaffold:begin state -->
## 技能状态维护

> 由脚手架生成，请勿手改；节点、checkpoint 或校验命令变化后执行 `autobiz-plugin build` 更新。

- 技能开始执行：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint cicd_in_progress
  ```
- 本节点必需产物全部写入 `FEATURE_DIR` 后：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint cicd_done
  ```
  推进时框架会检查必需产物是否存在。
- 需要修改已完成阶段时：`--checkpoint cicd_in_progress --reopen --reason "<原因>"`
- 用户明确要求跳过本节点时：`--skip-node ops.cicd --reason "<原因>"`
<!-- scaffold:end state -->

<!-- scaffold:begin artifacts -->
## 输入与产物

| 方向 | 产物 | 路径（相对 FEATURE_DIR） | 必需 |
|---|---|---|---|
| 输入 | 证据流 | `evidence/EVIDENCE.jsonl` | 是 |
| 输入 | 计划机器结构化内容 | `plan.json` | 否 |
| 输出 | CI/CD 清单 | `CICD_CHECKLIST.md` | 是 |
| 输出 | PR 描述 | `PR_BODY.md` | 否 |
<!-- scaffold:end artifacts -->

（以下为开发者编写的技能正文）

[TODO: 写明本节点的工作步骤、产物要求和完成标准]
