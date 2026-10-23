---
name: demo-review
description: 演示用的评审技能：查看上一步的代码提交，写评审意见 REVIEW.md。用于试用 autobiz-node-monitor 节点监控。
---

# 演示评审

1. 用 `git -C <仓库> diff <提交范围>` 查看上一步的改动，仓库和提交范围以正文后附加的产物约定为准；
2. 写评审意见：问题清单（没有就写“无”）和一行结论；
3. 保存到产物约定里给出的 REVIEW.md 路径。
