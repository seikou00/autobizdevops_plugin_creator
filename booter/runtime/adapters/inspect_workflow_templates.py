"""DevClaw 的 dynamic_workflow：流程模板、checkpoint 流转与节点定义（interfaces.md §3.3.5）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.adapters import board_view  # noqa: E402
from runtime.common import cli  # noqa: E402


def main(argv=None) -> int:
    parser = cli.ArgumentParser(description="输出流程模板")

    def action():
        parser.parse_args(argv)
        return board_view.templates_payload()

    return cli.run(action)


if __name__ == "__main__":
    sys.exit(main())
