---
name: autoops-archive
description: [TODO: 做什么；在什么情况下使用]
---

# 归档

<!-- scaffold:begin state -->
## 技能状态维护

> 由脚手架生成，请勿手改；节点、checkpoint 或校验命令变化后执行 `autobiz-plugin build` 更新。

- 「CI/CD」完成后执行本节点，归档当前 Feature：
  ```
  python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint archived
  ```
  推进时框架会检查本节点的必需输入是否存在，不执行校验命令。到达 `archived` 后流程结束，不能重开或跳过。
<!-- scaffold:end state -->

<!-- scaffold:begin artifacts -->
## 输入与产物

| 方向 | 产物 | 路径（相对 FEATURE_DIR） | 必需 |
|---|---|---|---|
| — | 无 | — | — |
<!-- scaffold:end artifacts -->

（以下为开发者编写的技能正文）

[TODO: 写明本节点的工作步骤、产物要求和完成标准]
