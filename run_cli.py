#!/usr/bin/env python3
"""Emuera-SKILL CLI 入口 — 无需安装即可直接运行。

用法:
    python run_cli.py <命令> --game-dir <游戏目录> [选项]

命令:
    scan, snapshot, graph, gap, run, debug, author, validate, impact, play, polish, capability, kb
"""
import sys
import os

# 将工程根加入 sys.path，使 emuera_skill 成为可导入包
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from emuera_skill.interface.cli import cli_main

if __name__ == "__main__":
    sys.exit(cli_main())
