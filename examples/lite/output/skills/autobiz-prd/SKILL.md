---
name: autobiz-prd
description: [TODO: 做什么；在什么情况下使用]
---

# 需求清洗

<!-- scaffold:begin state -->
## 技能状态维护

> 由脚手架生成，请勿手改；节点、checkpoint 或校验命令变化后执行 `autobiz-plugin build` 更新。

- 技能开始执行：
  ```
  python "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint prd_in_progress
  ```
- 本节点必需产物全部写入 `FEATURE_DIR` 后：
  ```
  python "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint prd_done
  ```
  推进时框架会检查必需产物是否存在。
- 需要修改已完成阶段时：`--checkpoint prd_in_progress --reopen --reason "<原因>"`
<!-- scaffold:end state -->

<!-- scaffold:begin artifacts -->
## 输入与产物

| 方向 | 产物 | 路径（相对 FEATURE_DIR） | 必需 |
|---|---|---|---|
| 输出 | 结构化需求 | `PRD.md` | 是 |
<!-- scaffold:end artifacts -->

（以下为开发者编写的技能正文）

[TODO: 写明本节点的工作步骤、产物要求和完成标准]
