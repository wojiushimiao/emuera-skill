#!/usr/bin/env python3
"""Emuera-SKILL MCP Server 入口（stdio 模式）— 无需安装即可直接运行。

用法:
    python run_mcp_server.py

配置到 MCP 客户端:
    {
      "mcpServers": {
        "emuera-skill": {
          "command": "python",
          "args": ["D:/ERA红魔馆改/emuera-skill/run_mcp_server.py"]
        }
      }
    }
"""
import sys
import os

# 将工程根加入 sys.path，使 emuera_skill 成为可导入包
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from emuera_skill.mcp_server.server import run_stdio_server

if __name__ == "__main__":
    run_stdio_server()
