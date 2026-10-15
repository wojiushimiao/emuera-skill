# -*- coding: utf-8 -*-
"""tests 目录公共夹具：把工程根加入 sys.path（包模式导入 emuera_skill）。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
