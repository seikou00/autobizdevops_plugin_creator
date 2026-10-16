#!/usr/bin/env python3
"""评审节点的完成校验：REVIEW.md 必须有问题清单和结论行。

退出码 0 表示通过；不通过时把原因打印在最后，框架会把输出末尾返回给模型。
"""

import argparse
import os
import re
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-dir", default=os.environ.get("FEATURE_DIR", "."))
    args = parser.parse_args()
    review = Path(args.feature_dir) / "REVIEW.md"
    if not review.is_file():
        print("校验未通过：REVIEW.md 不存在")
        return 1
    text = review.read_text(encoding="utf-8", errors="replace")
    problems = []
    if "问题清单" not in text:
        problems.append("缺少“问题清单”")
    if not re.search(r"^结论：(通过|需修改)\s*$", text, re.M):
        problems.append("缺少结论行，应单独一行写“结论：通过”或“结论：需修改”")
    if problems:
        print("校验未通过：" + "；".join(problems))
        return 1
    print("校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
