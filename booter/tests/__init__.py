import os

# 测试不联网：doctor 不执行 npm install，只报 KNOWLEDGE_NODE_DEPS warning；tests/test_node_deps.py 用假的 npm 单独测
# doctor 也不拉取知识仓库；tests/test_knowledge_pull.py 用本地 git 仓库单独测
os.environ.setdefault("AUTOBIZ_SKIP_NPM_INSTALL", "1")
os.environ.setdefault("AUTOBIZ_SKIP_KNOWLEDGE_PULL", "1")
