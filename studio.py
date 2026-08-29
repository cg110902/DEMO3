# -*- coding: utf-8 -*-
"""
Universal Novel Studio - 统一总控 CLI 入口 (studio.py)

本文件只是一个薄壳：真正实现位于 🔴 禁读区 tools/studio_cli.py。
AI 只需命令地图时，请运行 `python studio.py help --json`，
不要阅读本文件或 tools/ 源码。

用法：
    python studio.py hello          # 入口导览
    python studio.py help --json    # 机器可读命令目录
    python studio.py <命令> ...     # 见 help --json 或 AGENTS.md
"""

import sys
from pathlib import Path

_root_dir = Path(__file__).resolve().parent
_tools_dir = _root_dir / "tools"
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from studio_cli import main  # noqa: E402

if __name__ == "__main__":
    main()
