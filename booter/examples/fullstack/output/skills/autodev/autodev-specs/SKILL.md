---
name: autodev-specs
description: [TODO: 做什么；在什么情况下使用]
---

<!-- plugin workflow: begin state -->
## 技能状态维护

技能开始执行：python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint specs_in_progress

技能完成执行：python -X utf8 "${pluginPath}/runtime/workflow/update_state.py" --feature "${feature}" --checkpoint specs_done
<!-- plugin workflow: end state -->
