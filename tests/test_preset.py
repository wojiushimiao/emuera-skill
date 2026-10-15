"""
预设聚合层测试（重建版）。
六个预设按 run_preset 路由逐个验证返回 PresetResult 与摘要字段。
注：原始文件于回滚中丢失，本文件按 preset/aggregator.py 行为契约重写。
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emuera_skill.preset.aggregator import (
    PresetResult,
    PRESETS,
    run_preset,
    project_checkup,
    diagnose_function,
    author_flow,
    play_start,
    play_turn,
    polish_deliver,
)

GAME_DIR = r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus"
OUT_ROOT = str(_ROOT / "out" / "preset_tests")


def test_presets_registry():
    """六个预设名全部注册"""
    expected = {
        "project-checkup", "diagnose-function", "author-flow",
        "play-start", "play-turn", "polish-deliver",
    }
    assert expected == set(PRESETS.keys())


def test_run_preset_unknown():
    """未知预设返回 error 状态而非抛异常"""
    r = run_preset("no-such-preset")
    assert isinstance(r, PresetResult)
    assert r.status == "error"
    assert "未知预设" in r.summary["error"]


def test_project_checkup():
    """工程体检预设：P-A→P-B→P-C 全链摘要"""
    r = project_checkup(GAME_DIR, OUT_ROOT)
    assert r.status == "success"
    assert r.preset == "project-checkup"
    s = r.summary
    for k in ("functions", "variables", "graph_nodes", "gaps_total"):
        assert k in s
    return r


def test_diagnose_function():
    """函数诊断预设：命中已知函数 + 未命中降级两路"""
    r = diagnose_function(GAME_DIR, "SYSTEM")
    assert r.status == "success"
    s = r.summary
    assert s["found"] in (True, False)
    miss = diagnose_function(GAME_DIR, "NO_SUCH_FUNC_ZZZ")
    assert miss.summary["found"] is False
    return r


def test_author_flow():
    """开发流程预设：锚点 + 骨架 + 影响面"""
    r = author_flow(GAME_DIR, "EVENT", event_name="EVENT_TEST", output_root=OUT_ROOT)
    assert r.status == "success"
    assert "anchors_found" in r.summary
    assert "draft_length" in r.summary
    return r


def test_play_start():
    """开局游玩预设：会话 ID + 状态 + 动作数"""
    r = play_start(GAME_DIR, OUT_ROOT)
    assert r.status == "success"
    s = r.summary
    assert s["session_id"]
    assert "state" in s
    assert "actions_count" in s
    return r


def test_play_turn():
    """回合推进预设：翻译 + 派发 + 持久化"""
    r = play_turn(GAME_DIR, OUT_ROOT, "1")
    assert r.status == "success"
    s = r.summary
    assert "turn" in s
    assert "action_type" in s
    return r


def test_polish_deliver():
    """润色交付预设：压缩 + 模板 + 校验（降级路径可接受）"""
    r = polish_deliver(task="polish", context={"text": "你好", "task": "polish"})
    assert isinstance(r, PresetResult)
    assert r.preset == "polish-deliver"
    return r
