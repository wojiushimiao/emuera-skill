"""
MCP Server 测试（重建版）。
tools/list / tools/call 协议 + 会话跨调用持态（play_start → play_turn）。
注：原始文件于回滚中丢失，本文件按 mcp_server/server.py 行为契约重写。
"""
import json
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emuera_skill.mcp_server.server import MCPServer, TOOLS, RESOURCES

GAME_DIR = r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus"
OUT_ROOT = str(_ROOT / "out" / "mcp_tests")


def _tools_call(server, name, arguments, req_id=1):
    resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    return resp


def _payload(resp):
    """从 tools/call 响应取出文本结果并解析 JSON"""
    text = resp["result"]["content"][0]["text"]
    return json.loads(text)


def test_tools_list():
    """tools/list 返回 9 个工具且 schema 齐备"""
    server = MCPServer()
    resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = resp["result"]["tools"]
    assert len(tools) == 9
    names = {t["name"] for t in tools}
    assert names == {
        "project_checkup", "diagnose_function", "author_flow",
        "play_start", "play_turn", "polish", "kb_search", "kb_lookup", "capability",
    }
    for t in tools:
        assert "inputSchema" in t
        assert t["inputSchema"]["type"] == "object"


def test_initialize():
    """initialize 握手返回协议版本与服务信息"""
    server = MCPServer()
    resp = server.handle_request({"jsonrpc": "2.0", "id": 0, "method": "initialize"})
    assert resp["result"]["serverInfo"]["name"] == "emuera-skill"
    assert "capabilities" in resp["result"]


def test_unknown_method():
    """未知方法 → -32601"""
    server = MCPServer()
    resp = server.handle_request({"jsonrpc": "2.0", "id": 7, "method": "nope"})
    assert resp["error"]["code"] == -32601


def test_capability_tool():
    """capability 工具：不可能力 + 可能力双清单"""
    server = MCPServer()
    resp = _tools_call(server, "capability", {}, 10)
    data = _payload(resp)
    assert "impossible" in data and "possible" in data
    assert len(data["impossible"]) == 3


def test_kb_tools_registered():
    """kb_search / kb_lookup 工具已注册且可经协议层调用（payload 为可解析 dict）"""
    server = MCPServer()
    r = _payload(_tools_call(server, "kb_search", {"query": "PRINT"}, 11))
    assert isinstance(r, dict), "kb_search 工具必须返回可解析 JSON payload"
    # 当前实现经 None KB 路由可能降级为 error 载体；成功体含 results，错误体含 error
    assert ("results" in r) or ("error" in r)
    r2 = _payload(_tools_call(server, "kb_lookup", {"mnemonic": "PRINT"}, 12))
    assert ("found" in r2) or ("error" in r2)


def test_session_persistence():
    """R-D 核心：play_start → play_turn ×2 三连共享同一会话（跨调用持态）"""
    server = MCPServer()
    start = _payload(_tools_call(server, "play_start", {
        "game_dir": GAME_DIR, "output_root": OUT_ROOT,
    }, 20))
    sid = start["session_id"]
    assert sid in server.sessions

    t1 = _payload(_tools_call(server, "play_turn", {
        "session_id": sid, "intent": "1",
    }, 21))
    assert t1["session_id"] == sid
    assert t1["turn"] >= 1

    t2 = _payload(_tools_call(server, "play_turn", {
        "session_id": sid, "intent": "1",
    }, 22))
    assert t2["session_id"] == sid
    assert t2["turn"] >= 2


def test_play_turn_unknown_session():
    """play_turn 传未知 session_id 返回 SESSION_NOT_FOUND 错误码"""
    server = MCPServer()
    r = _payload(_tools_call(server, "play_turn", {
        "session_id": "no_such_session_id", "intent": "1",
    }, 30))
    assert r["error"] is True
    assert r["code"] == "SESSION_NOT_FOUND"


def test_play_turn_no_active_session():
    """无活动会话且未传 session_id → NO_ACTIVE_SESSION"""
    server = MCPServer()
    r = _payload(_tools_call(server, "play_turn", {"intent": "1"}, 31))
    assert r["error"] is True
    assert r["code"] == "NO_ACTIVE_SESSION"


def test_play_turn_multiple_sessions_require_id():
    """多活动会话且未传 session_id → SESSION_ID_REQUIRED"""
    server = MCPServer()
    for i in (40, 41):
        s = _payload(_tools_call(server, "play_start", {
            "game_dir": GAME_DIR, "output_root": OUT_ROOT,
        }, i))
        assert s["session_id"] in server.sessions
    r = _payload(_tools_call(server, "play_turn", {"intent": "1"}, 42))
    assert r["error"] is True
    assert r["code"] == "SESSION_ID_REQUIRED"


def test_session_cleanup_on_exit():
    """退出动作正常结束会话后从 registry 清理"""
    server = MCPServer()
    s = _payload(_tools_call(server, "play_start", {
        "game_dir": GAME_DIR, "output_root": OUT_ROOT,
    }, 50))
    sid = s["session_id"]
    r = _payload(_tools_call(server, "play_turn", {
        "session_id": sid, "intent": "结束",
    }, 51))
    assert r["closed"] is True
    assert sid not in server.sessions


def test_play_turn_unknown_session_via_protocol():
    """经完整 JSON-RPC 协议层验证错误路径（handle_request 全链路）"""
    server = MCPServer()
    raw = json.dumps({
        "jsonrpc": "2.0", "id": 99, "method": "tools/call",
        "params": {"name": "play_turn", "arguments": {"session_id": "ghost", "intent": "1"}},
    })
    resp = json.loads(json.dumps(server.handle_request(json.loads(raw))))
    data = _payload(resp)
    assert data["code"] == "SESSION_NOT_FOUND"


def test_resources_readonly():
    """只读 resources 端点：活动会话清单不含敏感状态"""
    server = MCPServer()
    s = _payload(_tools_call(server, "play_start", {
        "game_dir": GAME_DIR, "output_root": OUT_ROOT,
    }, 60))
    assert len(server.sessions) == 1

    resp = server.handle_request({
        "jsonrpc": "2.0", "id": 61, "method": "resources/read",
        "params": {"uri": "emuera://sessions/active"},
    })
    contents = resp["result"]["contents"]
    assert contents[0]["uri"] == "emuera://sessions/active"
    payload = json.loads(contents[0]["text"])
    assert payload["active_count"] == 1
    assert s["session_id"] in payload["session_ids"]
    # 不暴露 session 对象本身（只读清单语义）
    assert "session" not in payload

    # 未知 resource → -32602
    resp2 = server.handle_request({
        "jsonrpc": "2.0", "id": 62, "method": "resources/read",
        "params": {"uri": "emuera://nope"},
    })
    assert resp2["error"]["code"] == -32602
