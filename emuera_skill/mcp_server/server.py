"""
MCP Server - stdio 本地进程，供宿主 LLM 直接发现与调用。
"""

import json
import sys
from typing import Any, Dict, List, Optional

try:
    from ..preset.aggregator import run_preset, PRESETS
    from ..interface.cli import route_command, format_output
    from ..kb.knowledge import kb_search, kb_lookup
    from ..errors import EmueraError
    from ..player_session.session import SessionManager, SessionState
    from ..kernel_bridge.engine import compute_fingerprint
except ImportError:
    from preset.aggregator import run_preset, PRESETS
    from interface.cli import route_command, format_output
    from kb.knowledge import kb_search, kb_lookup
    from errors import EmueraError
    from player_session.session import SessionManager, SessionState
    from kernel_bridge.engine import compute_fingerprint


# ── MCP 工具定义 ──

TOOLS = [
    {
        "name": "project_checkup",
        "description": "工程体检：扫描结构、构建图谱、分析缺口，返回摘要 + 账本指针",
        "inputSchema": {
            "type": "object",
            "properties": {
                "game_dir": {"type": "string", "description": "游戏目录路径"},
            },
            "required": ["game_dir"],
        },
    },
    {
        "name": "diagnose_function",
        "description": "函数诊断：定位函数 + 调用链上下文 + 实现状态",
        "inputSchema": {
            "type": "object",
            "properties": {
                "game_dir": {"type": "string", "description": "游戏目录路径"},
                "func_name": {"type": "string", "description": "函数名"},
            },
            "required": ["game_dir", "func_name"],
        },
    },
    {
        "name": "author_flow",
        "description": "开发流程：锚点检索 + 骨架生成 + 校验 + 影响面",
        "inputSchema": {
            "type": "object",
            "properties": {
                "game_dir": {"type": "string", "description": "游戏目录路径"},
                "query": {"type": "string", "description": "检索查询"},
                "event_name": {"type": "string", "description": "事件名", "default": ""},
            },
            "required": ["game_dir", "query"],
        },
    },
    {
        "name": "play_start",
        "description": "开局游玩：装配引擎 + 标题态 + 首屏动作清单",
        "inputSchema": {
            "type": "object",
            "properties": {
                "game_dir": {"type": "string", "description": "游戏目录路径"},
                "load_session": {"type": "string", "description": "恢复会话路径", "default": ""},
            },
            "required": ["game_dir"],
        },
    },
    {
        "name": "play_turn",
        "description": "回合推进：翻译意图 + 派发动作 + 状态同步 + 持久化（续玩需传 session_id）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "play_start 返回的会话 ID；缺省时复用唯一活动会话", "default": ""},
                "intent": {"type": "string", "description": "玩家意图"},
                "game_dir": {"type": "string", "description": "游戏目录路径（仅新建会话时需要）", "default": ""},
            },
            "required": ["intent"],
        },
    },
    {
        "name": "polish",
        "description": "润色文本：压缩上下文 + 模板渲染 + 契约校验",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "enum": ["translate", "polish", "generate"], "description": "任务类型"},
                "context": {"type": "object", "description": "上下文"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "kb_search",
        "description": "知识库搜索：按关键词检索指令",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词"},
                "category": {"type": "string", "description": "类别过滤"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb_lookup",
        "description": "知识库单条检索：按助记符查询指令详情",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mnemonic": {"type": "string", "description": "指令助记符"},
            },
            "required": ["mnemonic"],
        },
    },
    {
        "name": "capability",
        "description": "能力声明：列出可能与不可能力",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ── 只读资源定义（MCP resources 能力，可选增强） ──

RESOURCES = [
    {
        "uri": "emuera://sessions/active",
        "name": "active_sessions",
        "description": "当前 MCP 进程内活动游玩会话的只读清单（不暴露任何敏感状态）",
        "mimeType": "application/json",
    },
]


# ── MCP Server ──

class MCPServer:
    """MCP Server 实现"""

    def __init__(self):
        self.sessions: Dict[str, Any] = {}

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理 MCP 请求"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        if method == "initialize":
            return self._handle_initialize(request_id, params)
        elif method == "tools/list":
            return self._handle_tools_list(request_id)
        elif method == "tools/call":
            return self._handle_tools_call(request_id, params)
        elif method == "resources/list":
            return self._handle_resources_list(request_id)
        elif method == "resources/read":
            return self._handle_resources_read(request_id, params)
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    def _handle_initialize(self, request_id: Any, params: Dict) -> Dict:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "emuera-skill", "version": "1.2.2"},
            },
        }

    def _handle_tools_list(self, request_id: Any) -> Dict:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS},
        }

    def _handle_resources_list(self, request_id: Any) -> Dict:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"resources": RESOURCES},
        }

    def _handle_resources_read(self, request_id: Any, params: Dict) -> Dict:
        uri = params.get("uri")
        if uri == "emuera://sessions/active":
            payload = {
                "active_count": len(self.sessions),
                "session_ids": list(self.sessions.keys()),
            }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "contents": [
                        {"uri": uri, "mimeType": "application/json", "text": format_output(payload, "json")}
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": f"Unknown resource: {uri}"},
        }

    def _handle_tools_call(self, request_id: Any, params: Dict) -> Dict:
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            result = self._call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": format_output(result, "json")}],
                },
            }
        except EmueraError as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": format_output({"error": True, "code": e.code, "message": str(e)}, "json")}],
                    "isError": True,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": format_output({"error": True, "message": str(e)}, "json")}],
                    "isError": True,
                },
            }

    def _call_tool(self, tool_name: str, arguments: Dict) -> Any:
        """调用工具"""
        if tool_name == "project_checkup":
            return run_preset("project-checkup", game_dir=arguments["game_dir"], output_root=arguments.get("output_root", "./emuera-skill-out")).summary
        elif tool_name == "diagnose_function":
            return run_preset("diagnose-function", game_dir=arguments["game_dir"], func_name=arguments["func_name"]).summary
        elif tool_name == "author_flow":
            return run_preset("author-flow", game_dir=arguments["game_dir"], query=arguments["query"], event_name=arguments.get("event_name", ""), output_root=arguments.get("output_root", "./emuera-skill-out")).summary
        elif tool_name == "play_start":
            game_dir = arguments["game_dir"]
            output_root = arguments.get("output_root", "./emuera-skill-out")
            load_session = arguments.get("load_session") or None
            fingerprint = compute_fingerprint(game_dir)
            manager = SessionManager(output_root)
            session = manager.start_session(
                game_dir=game_dir,
                fingerprint=fingerprint,
                restore_path=load_session,
            )
            # 跨调用持态：把会话对象与上下文登记到 self.sessions
            self.sessions[session.session_id] = {
                "session": session,
                "manager": manager,
                "game_dir": game_dir,
                "fingerprint": fingerprint,
                "output_root": output_root,
            }
            # 预跑首屏：无头驱动到第一个输入点，使画面可解析出可用动作，
            # 否则 list_actions 读到空缓冲，会话停在 initializing 无法推进。
            try:
                from ..runtime.headless import drive_execution
            except ImportError:
                from runtime.headless import drive_execution

            drive_result = drive_execution(
                session.runtime,
                entry="",
                opts={"timeout_s": 30, "default_input": 0},
            )
            actions = manager.list_actions(session)
            return {
                "session_id": session.session_id,
                "state": session.state,
                "actions_count": len(actions),
                "restored": load_session is not None,
                "screen": drive_result.get("status"),
            }
        elif tool_name == "play_turn":
            session_id = arguments.get("session_id") or None
            intent = arguments["intent"]

            # 解析目标会话：缺省时复用唯一活动会话
            if session_id is None:
                if len(self.sessions) == 1:
                    session_id = next(iter(self.sessions))
                elif not self.sessions:
                    return {
                        "error": True,
                        "code": "NO_ACTIVE_SESSION",
                        "message": "No active session. Call play_start first or pass a valid session_id.",
                    }
                else:
                    return {
                        "error": True,
                        "code": "SESSION_ID_REQUIRED",
                        "message": "Multiple active sessions; pass session_id to identify which one to advance.",
                    }

            if session_id not in self.sessions:
                return {
                    "error": True,
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session not found: {session_id}",
                }

            entry = self.sessions[session_id]
            session = entry["session"]
            manager = entry["manager"]

            action = manager.translate_intent(session, intent)

            # 续玩：重置运行状态机为 READY（保留引擎变量态），再驱动执行本轮
            try:
                from ..runtime.headless import reset_runtime
            except ImportError:
                from runtime.headless import reset_runtime
            reset_runtime(session.runtime)

            result = manager.dispatch_action(session, action)

            # 会话正常结束（退出动作）后从 registry 清理
            closed = session.state == SessionState.TERMINATED
            if closed:
                self.sessions.pop(session_id, None)

            return {
                "session_id": session.session_id,
                "turn": result.get("turn", 0),
                "action_type": action.get("action_type"),
                "status": result.get("status"),
                "state": session.state,
                "closed": closed,
            }
        elif tool_name == "polish":
            return run_preset("polish-deliver", task=arguments["task"], context=arguments.get("context", {})).summary
        elif tool_name == "kb_search":
            results = kb_search(None, arguments["query"], category=arguments.get("category"))
            return {"results": len(results), "query": arguments["query"]}
        elif tool_name == "kb_lookup":
            entry = kb_lookup(None, arguments["mnemonic"])
            return {"mnemonic": arguments["mnemonic"], "found": entry is not None}
        elif tool_name == "capability":
            return {
                "impossible": ["语句级断点", "行号定位", "指令指针追踪"],
                "possible": ["函数粒度软断点", "变量表快照", "调用栈查看", "错误定位"],
            }
        else:
            raise ValueError(f"未知工具: {tool_name}")


# ── stdio Server ──

def run_stdio_server():
    """运行 stdio MCP Server"""
    server = MCPServer()

    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = server.handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            }))
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
