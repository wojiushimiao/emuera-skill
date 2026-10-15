"""
接口层 CLI 测试（重建版）。
命令路由 / 未知命令 / 格式化输出 / capability 动态汇总。
注：原始文件于回滚中丢失，本文件按 interface/cli.py 行为契约重写。
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emuera_skill.interface.cli import (
    route_command,
    format_output,
    cli_main,
    COMMANDS,
)

GAME_DIR = r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus"
OUT_ROOT = str(_ROOT / "out" / "interface_tests")


def test_commands_registry():
    """13 命令全注册且映射到合法管线"""
    expected_cmds = {
        "scan", "snapshot", "graph", "gap", "run", "debug",
        "author", "validate", "impact", "play", "polish", "capability", "kb",
    }
    assert expected_cmds == set(COMMANDS.keys())
    valid_pipelines = {"P-A", "P-B", "P-C", "P-D", "P-E", "P-F", "P-G", "P-H", "capability", "kb"}
    for cmd, p in COMMANDS.items():
        assert p in valid_pipelines, f"{cmd} -> {p} 非法管线"


def test_unknown_command():
    """未知命令返回错误字典而非抛异常"""
    r = route_command("no-such-cmd", GAME_DIR, OUT_ROOT)
    assert "error" in r
    assert "未知命令" in r["error"]


def test_route_capability():
    """capability 为动态汇总结果（非硬编码清单）"""
    result = route_command("capability", GAME_DIR, OUT_ROOT)
    assert "subsystems" in result, "capability 应动态汇总子系统可用性"
    assert "debug_capability" in result, "capability 应含 debug 声明能力"
    assert result["available_count"] > 0, "应检测到可用子系统"


def test_route_kb_mnemonic():
    """kb 按助记符检索：命中与未命中"""
    hit = route_command("kb", GAME_DIR, OUT_ROOT, mnemonic="PRINT")
    assert hit["found"] is True
    assert hit["entry"]["mnemonic"] == "PRINT"

    miss = route_command("kb", GAME_DIR, OUT_ROOT, mnemonic="NO_SUCH_MNEMONIC_YYY")
    assert miss["found"] is False
    assert miss["entry"] is None


def test_route_kb_search():
    """kb 关键词检索返回条数 + 前 20 条清单"""
    r = route_command("kb", GAME_DIR, OUT_ROOT, query="PRINT")
    assert r["results"] >= 1
    assert "entries" in r
    assert len(r["entries"]) <= 20


def test_format_output_json():
    """json 格式可往返"""
    import json
    text = format_output({"a": 1, "b": [1, 2]}, "json")
    back = json.loads(text)
    assert back == {"a": 1, "b": [1, 2]}


def test_format_output_text():
    """text 格式逐层展开"""
    out = format_output({"k": {"a": 1}}, "text")
    assert "k:" in out
    assert "a: 1" in out


def test_format_output_summary():
    """summary 格式只取关键字段"""
    out = format_output({"status": "ok", "node_count": 5, "zzz": "x"}, "summary")
    assert "status: ok" in out
    assert "node_count: 5" in out
    assert "zzz" not in out


def test_cli_main_usage(monkeypatch, capsys):
    """无参数打印用法并返回 1"""
    rc = cli_main([])
    assert rc == 1
    captured = capsys.readouterr().out
    assert "用法" in captured


def test_cli_main_missing_game_dir(monkeypatch, capsys):
    """有命令但缺 --game-dir 返回 1"""
    rc = cli_main(["scan"])
    assert rc == 1
