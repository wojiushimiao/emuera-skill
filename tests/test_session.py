"""
玩家会话子系统测试（重建版）。
会话生命周期：开局 / 动作清单 / 意图翻译 / 保存装载 / 恢复 / 越界拒绝。
注：原始文件于回滚中丢失，本文件按 player_session/session.py 行为契约重写。
"""
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emuera_skill.player_session.session import (
    SessionManager,
    SessionState,
    build_io_digest,
    validate_session_state,
)
from emuera_skill.kernel_bridge.engine import compute_fingerprint
from emuera_skill.errors import EmueraError, PS_702

GAME_DIR = r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus"
OUT_ROOT = str(_ROOT / "out" / "session_tests")


@pytest.fixture(scope="module")
def manager():
    return SessionManager(OUT_ROOT)


def test_session_start(manager):
    """开局：返回会话与初始状态"""
    fingerprint = compute_fingerprint(GAME_DIR)
    session = manager.start_session(
        game_dir=GAME_DIR,
        fingerprint=fingerprint,
    )
    assert session.session_id
    assert session.state in (SessionState.INITIALIZING, SessionState.WAITING_INPUT)
    return session.session_id, session


def test_list_actions(manager):
    """动作清单返回结构化列表（可为空，但类型必须正确）"""
    fingerprint = compute_fingerprint(GAME_DIR)
    session = manager.start_session(game_dir=GAME_DIR, fingerprint=fingerprint)
    actions = manager.list_actions(session)
    assert isinstance(actions, list)
    for a in actions:
        assert "index" in a and "text" in a and a["type"] == "select"
    return actions


def test_translate_intent(manager):
    """意图翻译：数字命中 / 关键词命中 / 默认列选项三路"""
    fingerprint = compute_fingerprint(GAME_DIR)
    session = manager.start_session(game_dir=GAME_DIR, fingerprint=fingerprint)
    session.current_actions = [
        {"index": 0, "text": "a", "type": "select"},
        {"index": 1, "text": "b", "type": "select"},
    ]
    ok = manager.translate_intent(session, "0")
    assert ok["action_type"] == "select" and ok["target_index"] == 0
    kw = manager.translate_intent(session, "开始游戏")
    assert kw["action_type"] == "select" and kw["confidence"] == 0.8
    default = manager.translate_intent(session, "随机意图xyz")
    assert default["action_type"] == "list_options"
    return ok


def test_session_save_load(manager):
    """保存 → 装载往返：契约字段齐备、指纹一致"""
    fingerprint = compute_fingerprint(GAME_DIR)
    session = manager.start_session(game_dir=GAME_DIR, fingerprint=fingerprint)
    save_path = manager.save_session(session)
    assert save_path and Path(save_path).exists()

    data = json.loads(Path(save_path).read_text(encoding="utf-8"))
    assert validate_session_state(data) == []
    assert data["io_digest"] is not None and isinstance(data["io_digest"], dict)

    loaded = manager.load_session(save_path, expect_fingerprint=fingerprint)
    assert loaded.fingerprint == fingerprint
    assert loaded.session_context.get("session_id") == session.session_id
    return True


def test_session_restore(manager):
    """恢复模式：自存档重建会话（历史/轮次还原）"""
    fingerprint = compute_fingerprint(GAME_DIR)
    s1 = manager.start_session(game_dir=GAME_DIR, fingerprint=fingerprint)
    s1.turn_count = 3
    s1.history = [{"turn": 0, "action": {}, "result": {}}]
    s1.current_actions = [{"index": 0, "text": "x", "type": "select"}]
    save_path = manager.save_session(s1)

    s2 = manager.start_session(
        game_dir=GAME_DIR,
        fingerprint=fingerprint,
        restore_path=save_path,
    )
    assert s2.turn_count == 3
    assert len(s2.history) == 1
    assert s2.save_path == save_path
    assert s2.state == SessionState.WAITING_INPUT
    return True


def test_bad_session(manager, tmp_path):
    """损坏会话文件 → PS-702"""
    bad = tmp_path / "bad_session.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(EmueraError) as ei:
        manager.load_session(str(bad))
    assert ei.value.code == PS_702[0]

    # 指纹不符同样 PS-702
    fingerprint = compute_fingerprint(GAME_DIR)
    s = manager.start_session(game_dir=GAME_DIR, fingerprint=fingerprint)
    p = manager.save_session(s)
    wrong_fp = p + "_wrong"
    Path(wrong_fp).write_text(Path(p).read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(EmueraError):
        manager.load_session(wrong_fp, expect_fingerprint=fingerprint + "x")
    return True


def test_session_validate_contract():
    """契约校验：缺字段 / io_digest 类型错误均报错"""
    errs = validate_session_state({})
    assert len(errs) >= 5
    good = {
        "path": "p", "fingerprint": "f", "session_context": {},
        "final_variables": {}, "game_stage": "s",
        "io_digest": {"output_md5": "m", "output_length": 0, "input_count": 0},
        "format_version": "1.0",
    }
    assert validate_session_state(good) == []
    good["io_digest"] = "should-be-object"
    assert len(validate_session_state(good)) == 1
    return True


def test_build_io_digest(manager):
    """io_digest 摘要三字段齐备"""
    fingerprint = compute_fingerprint(GAME_DIR)
    session = manager.start_session(game_dir=GAME_DIR, fingerprint=fingerprint)
    digest = build_io_digest(session)
    for k in ("output_md5", "output_length", "input_count"):
        assert k in digest
    return digest


def test_debug_session(manager):
    """调试会话（DebugManager）与游玩会话同目录隔离落盘"""
    from emuera_skill.debug.debugger import DebugManager

    dm = DebugManager(OUT_ROOT)
    fingerprint = compute_fingerprint(GAME_DIR)
    ds = dm.create_session(GAME_DIR, fingerprint)
    assert ds.session_id.startswith("debug_")
    assert ds.state == "ready"
    wp = dm.set_watchpoint(ds, "SYSTEM")
    assert wp["status"] == "success"
    return True


def test_status_consistency(manager):
    """会话状态取值合法（状态机封闭集）"""
    valid = {
        SessionState.INITIALIZING, SessionState.WAITING_INPUT,
        SessionState.EXECUTING, SessionState.TERMINATED,
    }
    fingerprint = compute_fingerprint(GAME_DIR)
    s = manager.start_session(game_dir=GAME_DIR, fingerprint=fingerprint)
    assert s.state in valid
    return s.state in valid


def test_reject_out_of_range(manager):
    """编号越界 → reject 且 dispatch 返回 rejected"""
    fingerprint = compute_fingerprint(GAME_DIR)
    s = manager.start_session(game_dir=GAME_DIR, fingerprint=fingerprint)
    s.current_actions = [{"index": 0, "text": "a", "type": "select"}]
    action = manager.translate_intent(s, "99")
    assert action["action_type"] == "reject"
    result = manager.dispatch_action(s, action)
    assert result["status"] == "rejected"
    return True


def test_session_state_contract():
    """session_state 契约必填字段与代码常量对齐"""
    from emuera_skill.player_session.session import _SESSION_STATE_REQUIRED
    assert _SESSION_STATE_REQUIRED == [
        "path", "fingerprint", "session_context",
        "final_variables", "game_stage", "io_digest", "format_version",
    ]
    return True
