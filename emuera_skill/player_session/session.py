"""
玩家会话子系统。
管理一次游玩会话的完整状态机，把自然语言意图翻译成游戏内的输入序列，
支持跨对话持久化——完整会话状态落盘，任意后续对话可装载恢复。
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..runtime.headless import assemble_headless, drive_execution, collect_trace, RuntimeHandle, RunState
    from ..kernel_bridge.engine import Snapshot
    from ..errors import make_error, PS_702
except ImportError:
    from runtime.headless import assemble_headless, drive_execution, collect_trace, RuntimeHandle, RunState
    from kernel_bridge.engine import Snapshot
    from errors import make_error, PS_702


# ── 会话状态 ──

class SessionState:
    """会话状态"""
    INITIALIZING = "initializing"
    WAITING_INPUT = "waiting_input"
    EXECUTING = "executing"
    TERMINATED = "terminated"


# ── 会话数据结构 ──

@dataclass
class Session:
    """会话实例"""
    session_id: str
    game_dir: str
    fingerprint: str
    runtime: RuntimeHandle
    state: str = SessionState.INITIALIZING
    history: List[Dict[str, Any]] = field(default_factory=list)
    save_path: Optional[str] = None
    turn_count: int = 0
    current_actions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SessionFile:
    """会话文件（跨对话持久化）

    字段严格对齐 contracts/session_state.json 契约（COMMON §2.3 v1）：
    - io_digest 必须为 object（输入输出缓冲摘要），不得是字符串。
    """
    path: str
    fingerprint: str
    session_context: Dict[str, Any]
    final_variables: Dict[str, Any]
    game_stage: str
    io_digest: Dict[str, Any]
    format_version: str = "1.0"
    timestamp: float = field(default_factory=time.time)


# 契约文件中的必填字段（与 session_state.json 的 required 对齐）
_SESSION_STATE_REQUIRED = [
    "path", "fingerprint", "session_context",
    "final_variables", "game_stage", "io_digest", "format_version",
]


def build_io_digest(session: "Session") -> Dict[str, Any]:
    """构建 io_digest 对象（契约要求为 object 而非字符串）。

    摘要内容：输出缓冲 MD5 前 16 位、输出长度、输入队列长度。
    """
    output = ""
    if hasattr(session.runtime.renderer, 'get_output'):
        output = session.runtime.renderer.get_output()
    elif hasattr(session.runtime.renderer, 'output_buffer'):
        output = "".join(session.runtime.renderer.output_buffer)

    input_count = 0
    if hasattr(session.runtime.renderer, 'input_queue'):
        input_count = len(session.runtime.renderer.input_queue)

    return {
        "output_md5": hashlib.md5(output.encode("utf-8", "replace")).hexdigest()[:16],
        "output_length": len(output),
        "input_count": input_count,
    }


def validate_session_state(data: Dict[str, Any]) -> List[str]:
    """校验会话文件是否符合 session_state.json 契约。

    返回错误列表；空列表表示合规。
    端口：validate_session_state (L2 04 §9)
    """
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["顶层结构必须是对象"]

    for key in _SESSION_STATE_REQUIRED:
        if key not in data:
            errors.append(f"缺失必填字段: {key}")

    # io_digest 必须为 object（契约 §properties.io_digest.type == object）
    io_digest = data.get("io_digest")
    if "io_digest" in data and not isinstance(io_digest, dict):
        errors.append(f"io_digest 必须为 object，实际为 {type(io_digest).__name__}")

    return errors


# ── 会话管理器 ──

class SessionManager:
    """会话生命周期管理器"""

    def __init__(self, output_root: str):
        self.output_root = output_root
        self._sessions: Dict[str, Session] = {}

    def start_session(
        self,
        game_dir: str,
        fingerprint: str,
        input_queue: Optional[List[Any]] = None,
        default_input: Any = 0,
        restore_path: Optional[str] = None,
    ) -> Session:
        """
        启动会话。
        支持全新开局与恢复模式。

        端口：start_session (L2 04 §9)
        """
        session_id = f"{fingerprint[:8]}_{int(time.time())}"

        # 恢复模式
        if restore_path:
            return self._restore_session(session_id, game_dir, fingerprint, restore_path)

        # 全新开局
        runtime = assemble_headless(
            game_dir=game_dir,
            input_queue=input_queue,
            default_input=default_input,
            timeout_s=60.0,
        )

        session = Session(
            session_id=session_id,
            game_dir=game_dir,
            fingerprint=fingerprint,
            runtime=runtime,
            state=SessionState.INITIALIZING,
        )

        self._sessions[session_id] = session
        return session

    def _restore_session(
        self,
        session_id: str,
        game_dir: str,
        fingerprint: str,
        restore_path: str,
    ) -> Session:
        """恢复会话"""
        # 加载会话文件
        session_file = self.load_session(restore_path, fingerprint)

        # 创建运行时
        runtime = assemble_headless(
            game_dir=game_dir,
            input_queue=[],
            default_input=0,
            timeout_s=60.0,
        )

        # 终态装载：设置变量
        if hasattr(runtime.engine, 'variable_mgr') and runtime.engine.variable_mgr:
            for name, value in session_file.final_variables.items():
                if name in runtime.engine.variable_mgr._descriptors:
                    runtime.engine.variable_mgr._descriptors[name].value = value

        session = Session(
            session_id=session_id,
            game_dir=game_dir,
            fingerprint=fingerprint,
            runtime=runtime,
            state=SessionState.WAITING_INPUT,
            save_path=restore_path,
            turn_count=session_file.session_context.get("turn_count", 0),
            history=list(session_file.session_context.get("history", [])),
            current_actions=list(session_file.session_context.get("current_actions", [])),
        )

        self._sessions[session_id] = session
        return session

    def list_actions(self, session: Session) -> List[Dict[str, Any]]:
        """
        列出当前可用动作。
        从画面识别动作编号与文案。

        端口：list_actions (L2 04 §9)
        """
        # 简化实现：从输出缓冲中提取动作
        output = ""
        if hasattr(session.runtime.renderer, 'get_output'):
            output = session.runtime.renderer.get_output()
        elif hasattr(session.runtime.renderer, 'output_buffer'):
            output = "".join(session.runtime.renderer.output_buffer)

        # 提取动作（简化：查找 [数字] 模式）
        import re
        actions = []
        matches = re.findall(r'\[(\d+)\]\s*(.*?)(?:\n|$)', output)
        for idx, text in matches:
            actions.append({
                "index": int(idx),
                "text": text.strip(),
                "type": "select",
            })

        session.current_actions = actions
        return actions

    def translate_intent(
        self,
        session: Session,
        intent: str,
    ) -> Dict[str, Any]:
        """
        意图翻译。
        把自然语言意图翻译成结构化动作。

        端口：translate_intent (L2 04 §9)
        """
        # 简化实现：基于关键词匹配
        # 完整实现需要调用 LLM（P5 交付后接真实模板）

        intent_lower = intent.lower()

        # 检查是否是数字选择
        try:
            idx = int(intent)
            # 验证索引在范围内
            valid_indices = [a["index"] for a in session.current_actions]
            if idx in valid_indices:
                return {
                    "action_type": "select",
                    "target_index": idx,
                    "confidence": 1.0,
                }
            else:
                # 编号越界，拒绝执行
                return {
                    "action_type": "reject",
                    "reason": f"索引 {idx} 越界，有效范围: {valid_indices}",
                    "confidence": 1.0,
                }
        except ValueError:
            pass

        # 关键词匹配
        if any(kw in intent_lower for kw in ["开始", "start", "进入", "新游戏", "新开", "游戏开始", "new game"]):
            return {
                "action_type": "select",
                "target_index": 0,
                "confidence": 0.8,
            }
        elif any(kw in intent_lower for kw in ["继续", "continue", "下一步"]):
            return {
                "action_type": "select",
                "target_index": 1,
                "confidence": 0.7,
            }
        elif any(kw in intent_lower for kw in ["结束", "quit", "exit"]):
            return {
                "action_type": "exit",
                "confidence": 0.9,
            }

        # 默认：列出选项让用户指定
        return {
            "action_type": "list_options",
            "options": session.current_actions,
            "confidence": 0.5,
        }

    def dispatch_action(
        self,
        session: Session,
        action: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        派发动作。
        动作值压入输入队列驱动推进。

        端口：dispatch_action (L2 04 §9)
        """
        if session.state == SessionState.TERMINATED:
            return {"status": "error", "error": "会话已终止"}

        # 检查动作类型
        if action.get("action_type") == "reject":
            return {"status": "rejected", "reason": action.get("reason")}

        if action.get("action_type") == "exit":
            session.state = SessionState.TERMINATED
            return {"status": "terminated"}

        if action.get("action_type") != "select":
            return {"status": "error", "error": f"未知动作类型: {action.get('action_type')}"}

        target_index = action.get("target_index")
        if target_index is None:
            return {"status": "error", "error": "缺少 target_index"}

        # 压入输入队列
        session.runtime.renderer.input_queue.append(target_index)

        # 驱动执行
        exec_result = drive_execution(
            runtime=session.runtime,
            entry="",
            opts={"timeout_s": 60.0, "default_input": 0},
        )

        # 记录历史
        session.history.append({
            "turn": session.turn_count,
            "action": action,
            "result": exec_result,
            "output_preview": self._get_output_preview(session),
        })

        session.turn_count += 1

        # 自动持久化
        save_path = self.save_session(session)

        return {
            "status": exec_result["status"],
            "turn": session.turn_count,
            "save_path": save_path,
        }

    def save_session(self, session: Session) -> str:
        """
        保存会话。
        每轮推进结束自动写入。

        端口：save_session (L2 04 §9)
        """
        output_dir = Path(self.output_root) / session.fingerprint[:8] / "saves"
        output_dir.mkdir(parents=True, exist_ok=True)

        save_path = str(output_dir / f"{session.session_id}.json")

        # 采集变量表
        final_variables = {}
        if hasattr(session.runtime.engine, 'variable_mgr') and session.runtime.engine.variable_mgr:
            for name, desc in session.runtime.engine.variable_mgr._descriptors.items():
                final_variables[name] = getattr(desc, 'value', None)

        # 计算 IO 摘要（契约要求为 object）
        io_digest = build_io_digest(session)

        session_file = SessionFile(
            path=save_path,
            fingerprint=session.fingerprint,
            session_context={
                "session_id": session.session_id,
                "turn_count": session.turn_count,
                "history_length": len(session.history),
                "history": session.history,
                "current_actions": session.current_actions,
                "state": session.state,
            },
            final_variables=final_variables,
            game_stage="waiting_input",
            io_digest=io_digest,
        )

        # 写入文件
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump({
                    "path": session_file.path,
                    "fingerprint": session_file.fingerprint,
                    "session_context": session_file.session_context,
                    "final_variables": session_file.final_variables,
                    "game_stage": session_file.game_stage,
                    "io_digest": session_file.io_digest,
                    "format_version": session_file.format_version,
                    "timestamp": session_file.timestamp,
                }, f, ensure_ascii=False, indent=2)
            session.save_path = save_path
            return save_path
        except Exception as e:
            # 写入失败，保留上一份有效会话文件
            print(f"[WARN] 会话保存失败: {e}")
            return session.save_path or ""

    def load_session(
        self,
        path: str,
        expect_fingerprint: Optional[str] = None,
    ) -> SessionFile:
        """
        加载会话。
        校验存在性/指纹/完整性。

        端口：load_session (L2 04 §9)
        """
        # 检查文件存在
        if not Path(path).exists():
            raise make_error(PS_702, context=f"会话文件不存在: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise make_error(PS_702, context=f"会话文件损坏: {e}")

        # 契约校验：不符合 session_state.json 视为坏会话
        contract_errors = validate_session_state(data)
        if contract_errors:
            raise make_error(
                PS_702,
                context=f"会话文件不符合 session_state.json 契约: {'; '.join(contract_errors)}",
            )

        # 指纹校验
        if expect_fingerprint and data.get("fingerprint") != expect_fingerprint:
            raise make_error(PS_702, context=f"指纹不匹配: 期望 {expect_fingerprint}, 实际 {data.get('fingerprint')}")

        return SessionFile(
            path=data.get("path", path),
            fingerprint=data.get("fingerprint", ""),
            session_context=data.get("session_context", {}),
            final_variables=data.get("final_variables", {}),
            game_stage=data.get("game_stage", ""),
            io_digest=data.get("io_digest", ""),
            format_version=data.get("format_version", "1.0"),
            timestamp=data.get("timestamp", 0),
        )

    def _get_output_preview(self, session: Session, max_len: int = 200) -> str:
        """获取输出预览"""
        output = ""
        if hasattr(session.runtime.renderer, 'get_output'):
            output = session.runtime.renderer.get_output()
        elif hasattr(session.runtime.renderer, 'output_buffer'):
            output = "".join(session.runtime.renderer.output_buffer)
        return output[:max_len] if output else ""
