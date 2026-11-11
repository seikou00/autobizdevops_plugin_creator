"""python <booter 目录> <命令>：不打 .pyz，直接从源码运行脚手架，与 python autobiz-plugin.pyz <命令> 等价。

Python 执行目录时把该目录放进 sys.path[0]，再运行其中的 __main__.py，所以这里能直接导入 scaffold 包；
runtime/、schemas/ 由 scaffold/resources.py 从本目录读取。
"""

import sys

from scaffold.cli import main

sys.exit(main())
