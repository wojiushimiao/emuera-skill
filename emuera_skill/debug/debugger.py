"""
调试子系统。
提供变量检查、调用栈查看、错误定位和无侵入的软断点。
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

try:
    from ..runtime.headless import assemble_headless, drive_execution, collect_trace, RuntimeHandle, RunState
    from ..player_session.session import SessionManager, Session, SessionFile
    from ..errors import make_error
except ImportError:
    from runtime.headless import assemble_headless, drive_execution, collect_trace, RuntimeHandle, RunState
    from player_session.session import SessionManager, Session, SessionFile
    from errors import make_error


# ── 调试会话 ──

@dataclass
class DebugSession:
    """调试会话"""
    session_id: str
    game_dir: str
    fingerprint: str
    runtime: RuntimeHandle
    state: str = "initialized"
    watchpoints: List[Dict[str, Any]] = field(default_factory=list)
    snapshots: List[Dict[str, Any]] = field(default_factory=list)
    step_count: int = 0


# ── 调试管理器 ──

class DebugManager:
    """调试会话管理器"""

    def __init__(self, output_root: str):
        self.output_root = output_root
        self._sessions: Dict[str, DebugSession] = {}

    def create_session(
        self,
        game_dir: str,
        fingerprint: str,
    ) -> DebugSession:
        """
        创建调试会话。

        端口：create_session (L2 04 §7)
        """
        session_id = f"debug_{fingerprint[:8]}_{int(time.time())}"

        runtime = assemble_headless(
            game_dir=game_dir,
            input_queue=[],
            default_input=0,
            timeout_s=300.0,  # 调试会话超时更长
        )

        session = DebugSession(
            session_id=session_id,
            game_dir=game_dir,
            fingerprint=fingerprint,
            runtime=runtime,
            state="ready",
        )

        self._sessions[session_id] = session
        return session

    def set_watchpoint(
        self,
        session: DebugSession,
        func_name: str,
        condition: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        设置软断点。

        端口：set_watchpoint (L2 04 §7)
        """
        watchpoint = {
            "id": len(session.watchpoints) + 1,
            "func_name": func_name,
            "condition": condition,
            "hit_count": 0,
            "created_at": time.time(),
        }
        session.watchpoints.append(watchpoint)

        return {
            "status": "success",
            "watchpoint_id": watchpoint["id"],
            "func_name": func_name,
            "condition": condition,
        }

    def step(
        self,
        session: DebugSession,
        steps: int = 1,
    ) -> Dict[str, Any]:
        """
        单步执行（函数粒度）。

        端口：step (L2 04 §7)
        """
        if session.state == "terminated":
            return {"status": "error", "error": "调试会话已终止"}

        session.state = "stepping"
        results = []

        for i in range(steps):
            # 执行一步
            exec_result = drive_execution(
                runtime=session.runtime,
                entry="",
                opts={"timeout_s": 30.0, "default_input": 0},
            )

            session.step_count += 1

            # 检查断点
            hit_watchpoint = None
            for wp in session.watchpoints:
                if self._check_watchpoint(session, wp):
                    wp["hit_count"] += 1
                    hit_watchpoint = wp
                    break

            results.append({
                "step": session.step_count,
                "status": exec_result["status"],
                "hit_watchpoint": hit_watchpoint["id"] if hit_watchpoint else None,
            })

            if hit_watchpoint or exec_result["status"] != "success":
                break

        session.state = "paused"

        return {
            "status": "success",
            "steps_executed": len(results),
            "results": results,
            "current_state": session.state,
        }

    def snapshot_state(self, session: DebugSession) -> Dict[str, Any]:
        """
        状态快照。
        返回当前变量表与调用栈。

        端口：snapshot_state (L2 04 §7)
        """
        trace = collect_trace(session.runtime)

        snapshot = {
            "timestamp": time.time(),
            "step_count": session.step_count,
            "state": session.state,
            "variables": trace.get("final_variables", {}),
            "call_stack": trace.get("call_stack", []),
            "output_preview": trace.get("output_full", "")[:500],
        }

        session.snapshots.append(snapshot)
        return snapshot

    def conclude(self, session: DebugSession) -> Dict[str, Any]:
        """
        结束调试会话。

        端口：conclude (L2 04 §7)
        """
        session.state = "terminated"

        # 保存会话
        save_path = self._save_debug_session(session)

        return {
            "status": "success",
            "session_id": session.session_id,
            "total_steps": session.step_count,
            "snapshots_count": len(session.snapshots),
            "save_path": save_path,
        }

    def declare_capability(self) -> Dict[str, Any]:
        """
        声明不可能力。
        语句级断点 / 行号定位 / 指令指针追踪。

        端口：declare_capability (L2 04 §7)
        """
        return {
            "impossible_capabilities": [
                {
                    "name": "语句级断点",
                    "reason": "内核 VM 不提供单步执行接口",
                },
                {
                    "name": "行号级定位",
                    "reason": "函数体 AST 节点不含行号字段",
                },
                {
                    "name": "指令指针追踪",
                    "reason": "VM 不暴露程序计数器",
                },
            ],
            "possible_capabilities": [
                "函数粒度软断点",
                "变量表快照",
                "调用栈查看",
                "错误定位",
            ],
        }

    def _check_watchpoint(self, session: DebugSession, watchpoint: Dict[str, Any]) -> bool:
        """
        检查断点是否命中。

        真实判定：
        1. 按 watchpoint 记录的函数名与 session 当前执行函数做精确/前缀匹配；
        2. 可选 condition 字段存在时做简单比较求值（如 "VAR>0"），
           解析或求值失败一律安全返回 False（视为未命中）。
        未命中必须返回 False，使 step 在未命中时继续执行而非中断。
        """
        func_name = watchpoint.get("func_name") or ""
        if not func_name:
            return False

        # 当前执行函数：取最近一次 drive_execution 选定的入口函数名
        current_func = getattr(session.runtime, "entry_used", "") or ""

        # 精确匹配或前缀匹配（任一方向均可，覆盖 "A" 命中 "A_SUB"/"PRE_A" 的情形）
        matched = (
            func_name == current_func
            or current_func.startswith(func_name)
            or func_name.startswith(current_func)
        )
        if not matched:
            return False

        # 可选条件字段：形如 "VAR>0" 的简单比较，失败安全返回 False
        condition = watchpoint.get("condition")
        if condition:
            if not self._eval_simple_condition(session, condition):
                return False

        return True

    def _eval_simple_condition(self, session: DebugSession, condition: str) -> bool:
        """
        对 "VAR>0" 形式的简单比较做求值。

        支持运算符：>= <= == != > <
        变量取值来自 session.runtime.engine.variable_mgr。
        任何解析/取值/比较异常都安全返回 False（未命中）。
        """
        import re

        m = re.match(
            r"^\s*([A-Za-z_]\w*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)\s*$",
            condition,
        )
        if not m:
            return False

        var_name, op, raw_val = m.group(1), m.group(2), m.group(3)

        try:
            vmgr = getattr(session.runtime.engine, "variable_mgr", None)
            if vmgr is None:
                return False
            actual = vmgr.get_value(var_name)
            expected = float(raw_val) if "." in raw_val else int(raw_val)
            actual = float(actual)
        except Exception:
            return False

        try:
            if op == ">":
                return actual > expected
            if op == "<":
                return actual < expected
            if op == ">=":
                return actual >= expected
            if op == "<=":
                return actual <= expected
            if op == "==":
                return actual == expected
            if op == "!=":
                return actual != expected
        except Exception:
            return False

        return False

    def _save_debug_session(self, session: DebugSession) -> str:
        """保存调试会话"""
        output_dir = Path(self.output_root) / session.fingerprint[:8] / "debug_saves"
        output_dir.mkdir(parents=True, exist_ok=True)

        save_path = str(output_dir / f"{session.session_id}.json")

        # 采集状态
        snapshot = self.snapshot_state(session)

        data = {
            "session_id": session.session_id,
            "fingerprint": session.fingerprint,
            "state": session.state,
            "step_count": session.step_count,
            "watchpoints": session.watchpoints,
            "snapshots_count": len(session.snapshots),
            "last_snapshot": snapshot,
        }

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return save_path
        except Exception as e:
            print(f"[WARN] 调试会话保存失败: {e}")
            return ""
