"""
无头运行时子系统。

让引擎在无人值守模式下可观测地跑起来——输出进内存缓冲、输入按队列注入、
全程带超时看门狗。

设计要点（对齐 L2 04 §6）：
- 装配阶段只使用内核公开接缝：assemble_engine + BufferedRenderer，
  并把 BufferedRenderer 同时挂到 engine.io_renderer 与 engine.vm.io_renderer，
  使 VM 的所有 PRINT/INPUT 都走内存缓冲（原 headless.py 误写了 engine._renderer，
  导致输出仍流向终端，端到端跑不通）。
- 执行阶段走真实入口 vm.call_function(entry, [])，捕获 BEGIN 状态迁移信号与
  首屏截止（HeadlessAbort），据状态机迁移到 FINISHED / TIMED_OUT / ERROR。
- 看门狗 Watchdog 为真实 threading.Timer：超时即置位 abort_event 与 timed_out，
  驱动线程通过 join(timeout) 判定，渲染器在输入点协作感知 abort_event 完成中断。
"""

import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..kernel_bridge.engine import assemble_engine, capture_snapshot, Snapshot, EngineHandle
    from ..errors import make_error, RT_401
except ImportError:
    from kernel_bridge.engine import assemble_engine, capture_snapshot, Snapshot, EngineHandle
    from errors import make_error, RT_401


# 协作中断信号：渲染器在输入点感知 abort_event 后抛出，使执行线程干净退出
class HeadlessAbort(Exception):
    """无头运行被看门狗/首屏截止中断"""


# ── 引擎运行状态机 ──

class RunState:
    """引擎运行状态"""
    UNASSEMBLED = "unassembled"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"
    TIMED_OUT = "timed_out"


@dataclass
class RuntimeHandle:
    """运行时句柄"""
    engine: Any
    renderer: Any  # HeadlessRenderer (BufferedRenderer 子类)
    state: str = RunState.UNASSEMBLED
    output_buffer: List[str] = field(default_factory=list)
    input_queue: List[Any] = field(default_factory=list)
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timed_out: bool = False
    input_exhausted: bool = False
    # 运行时扩展字段
    abort_event: Any = None          # threading.Event
    default_input: Any = 0
    reached_title: bool = False
    entry_used: str = ""
    begin_mode: Optional[str] = None
    worker: Any = None               # 执行线程
    watchdog: Any = None             # Watchdog 实例


# ── 无头缓冲渲染器 ──

class HeadlessRenderer:
    """
    BufferedRenderer 的薄包装。
    在保留内存缓冲语义的同时：
    1. 输入按队列消费，队列空时回退 default_input 并标记 input_exhausted；
    2. 首个输入点抛出 HeadlessAbort，使“标题画面端到端”在首屏即干净截止；
    3. 看门狗置位 abort_event 后，后续输入点协作中断执行。
    """

    def __init__(self, default_input: Any = 0, stop_at_first_input: bool = True):
        # 延迟导入内核 BufferedRenderer，避免无内核时装配失败
        try:
            from io.renderer import BufferedRenderer
        except ImportError:
            from src.io.renderer import BufferedRenderer
        self._base = BufferedRenderer()
        self.input_queue: list = []
        self.default_input = default_input
        self.stop_at_first_input = stop_at_first_input
        self._first_input_done = False
        self.abort_event = threading.Event()
        self._input_exhausted = False
        self.runtime: Any = None

    # —— 输入耗尽透传 ——
    @property
    def input_exhausted(self) -> bool:
        return self._input_exhausted

    def _maybe_abort(self) -> None:
        if self.abort_event.is_set():
            raise HeadlessAbort("watchdog abort")

    def _consume_input(self, as_number: bool):
        self._maybe_abort()
        if self.abort_event.is_set():
            raise HeadlessAbort("watchdog abort")
        raw = None
        if self.input_queue:
            raw = self.input_queue.pop(0)
        else:
            self._input_exhausted = True
        # 首屏截止：首个输入点即中断（优先于输入耗尽检查）
        if not self._first_input_done:
            self._first_input_done = True
            if self.stop_at_first_input:
                raise HeadlessAbort("first screen reached")
        # 引擎上下文中的输入耗尽：抛 EOFError 让引擎主循环退出
        # （单元测试直接调用 renderer 时不抛，保持返回默认值语义）
        if self._input_exhausted and self.runtime is not None:
            raise EOFError("Input exhausted: headless input queue empty")
        if as_number:
            try:
                return int(raw) if raw is not None else int(self.default_input)
            except (ValueError, TypeError):
                return int(self.default_input) if self.default_input is not None else 0
        # 字符串输入：队列耗尽回退空串（EOF 语义），default_input 仅作用于数值菜单
        if raw is None:
            return ""
        return str(raw)

    # —— 转发 BufferedRenderer 输出接口 ——
    def print_text(self, text, newline=False, wait=False):
        self._base.print_text(text, newline=newline, wait=wait)

    def print_formatted(self, segments, newline=False, wait=False):
        self._base.print_formatted(segments, newline=newline, wait=wait)

    def input_number(self, prompt="", timeout=0):
        if prompt:
            self._base.output_buffer.append(prompt)
        return self._consume_input(as_number=True)

    def input_string(self, prompt="", timeout=0):
        if prompt:
            self._base.output_buffer.append(prompt)
        return self._consume_input(as_string=True) if False else self._consume_input(as_number=False)

    def draw_line(self, char="-"):
        self._base.draw_line(char)

    def clear_line(self, count=1):
        self._base.clear_line(count)

    def set_color(self, color):
        self._base.set_color(color)

    def reset_color(self):
        self._base.reset_color()

    def print_button(self, text, value):
        self._base.print_button(text, value)

    def draw_bar(self, current, max_val, length, fill_char="*", empty_char="."):
        self._base.draw_bar(current, max_val, length, fill_char, empty_char)

    def get_output(self):
        return self._base.get_output()

    def clear(self):
        self._base.clear()


# ── 无头装配器 ──

def assemble_headless(
    game_dir: str,
    input_queue: Optional[List[Any]] = None,
    default_input: Any = 0,
    timeout_s: float = 60.0,
    stop_at_first_input: bool = True,
) -> RuntimeHandle:
    """
    无头装配器。
    装配引擎 → 装载全内存缓冲渲染器（同时挂到 engine 与 vm）→ 注入输入队列。

    端口：assemble_headless (L2 04 §6)
    """
    # 1. 装配引擎（复用 P1 内核桥接）
    try:
        handle = assemble_engine(game_dir)
    except Exception as e:
        raise make_error(RT_401, context=f"无头装配失败: {e}")

    engine = handle.engine

    # 2. 装载缓冲渲染器
    renderer = HeadlessRenderer(default_input=default_input, stop_at_first_input=stop_at_first_input)
    renderer.input_queue = list(input_queue) if input_queue is not None else []

    # 3. 同时挂到 engine 与 vm（VM 内部只读 self.io_renderer）
    try:
        engine.io_renderer = renderer
    except Exception:
        pass
    try:
        if engine.vm is not None:
            engine.vm.io_renderer = renderer
    except Exception:
        pass

    # 4. 运行时句柄
    abort_event = threading.Event()
    renderer.abort_event = abort_event

    runtime = RuntimeHandle(
        engine=engine,
        renderer=renderer,
        state=RunState.READY,
        input_queue=renderer.input_queue,
        abort_event=abort_event,
        default_input=default_input,
    )
    renderer.runtime = runtime

    runtime.state_transitions.append({
        "from": RunState.UNASSEMBLED,
        "to": RunState.READY,
        "time": time.time(),
    })

    return runtime


# ── 超时看门狗 ──

class Watchdog:
    """
    超时看门狗（真实 threading.Timer 实现）。

    start() 后经过 timeout_s 触发 on_timeout 回调：置位 runtime.timed_out 与
    abort_event，使协作式的执行线程在输入点干净退出。stop() 取消定时器。
    """

    def __init__(self, timeout_s: float, callback=None):
        self.timeout_s = timeout_s
        self.callback = callback
        self._timer: Optional[threading.Timer] = None
        self._start_time: Optional[float] = None
        self.fired: bool = False

    def start(self) -> None:
        self._start_time = time.time()
        self._timer = threading.Timer(self.timeout_s, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _on_timeout(self) -> None:
        self.fired = True
        if self.callback:
            try:
                self.callback()
            except Exception:
                pass

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def elapsed(self) -> float:
        if self._start_time is not None:
            return time.time() - self._start_time
        return 0.0

    def is_alive(self) -> bool:
        return self._timer is not None and self._timer.is_alive()


# ── 执行驱动器 ──

def _select_entry(engine: Any) -> str:
    """挑选标题入口函数：优先 SYSTEM_TITLE，其次 TITLE / EVENTFIRST"""
    candidates = ["SYSTEM_TITLE", "TITLE", "EVENTFIRST"]
    fd = getattr(engine, "function_dispatch", None)
    if fd is not None:
        funcs = getattr(fd, "_functions", {})
        for name in candidates:
            if name in funcs:
                return name
    # 退化：取首个已注册函数
    if fd is not None and funcs:
        return next(iter(funcs))
    return ""


def _is_signal(exc: Exception, *names: str) -> bool:
    """按类名判定内核控制信号（BeginSignal/ThrowSignal），避免直接 import 内核内部。"""
    return type(exc).__name__ in names


def _run_entry(runtime: RuntimeHandle, entry: str, default_input: Any) -> Dict[str, Any]:
    """
    在执行线程内运行游戏主循环。
    优先使用 engine.run() 处理完整游戏循环（BEGIN 迁移等）。
    若引擎无 run 方法（mock），回退到直接调用 call_function。
    捕获：首屏截止(HeadlessAbort)、看门狗中断、游戏异常。
    """
    engine = runtime.engine
    result: Dict[str, Any] = {"entry": entry, "begin_mode": None}

    try:
        # 优先使用 engine.run() 进入完整游戏主循环
        if hasattr(engine, 'run') and callable(engine.run):
            engine.run()
        else:
            # 回退：直接调用入口函数（mock 引擎兼容）
            engine.vm.call_function(entry, [])
        result["kind"] = "finished"
    except HeadlessAbort:
        # 首屏截止或看门狗中断——对无头运行属正常终态
        result["kind"] = "aborted"
    except Exception as e:  # 内核控制/运行信号
        if _is_signal(e, "BeginSignal"):
            mode = getattr(e, "mode", None)
            runtime.begin_mode = mode
            result["begin_mode"] = mode
            result["kind"] = "begin_transition"
        elif _is_signal(e, "ThrowSignal"):
            runtime.errors.append(f"ThrowSignal: {e}")
            result["kind"] = "throw"
        else:
            runtime.errors.append(f"{type(e).__name__}: {e}")
            result["kind"] = "error"
    return result


def reset_runtime(runtime: RuntimeHandle) -> Dict[str, Any]:
    """
    会话续玩重置：把运行时状态复位为 READY，便于 drive_execution 再次驱动。

    保留引擎内部状态（变量表、VM 上下文），仅复位外层执行状态机与输入队列。
    用于多轮会话（play_turn 逐轮续玩），单次无头运行无需调用。
    """
    runtime.state = RunState.READY
    runtime.entry_used = ""
    runtime.timed_out = False
    runtime.input_exhausted = False
    if runtime.abort_event is not None:
        runtime.abort_event.clear()
    # 清空输入队列，避免上一轮残留输入干扰本轮
    if runtime.renderer is not None and hasattr(runtime.renderer, "input_queue"):
        runtime.renderer.input_queue.clear()
    return {"status": "reset", "state": runtime.state}


def drive_execution(
    runtime: RuntimeHandle,
    entry: str = "",
    opts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    执行驱动器。
    在执行线程中跑入口函数，看门狗管控总时长；join(timeout) 判定是否超时。

    端口：drive_execution (L2 04 §6)
    """
    if runtime.state != RunState.READY:
        return {"status": "error", "error": f"当前状态 {runtime.state} 不允许执行"}

    opts = opts or {}
    timeout_s = float(opts.get("timeout_s", 60.0))
    default_input = opts.get("default_input", runtime.default_input)

    # 选定入口
    entry_func = entry or _select_entry(runtime.engine)
    if not entry_func:
        runtime.errors.append("未找到入口函数")
        runtime.state = RunState.ERROR
        runtime.state_transitions.append({
            "from": RunState.READY, "to": RunState.ERROR, "time": time.time(),
        })
        return {"status": "error", "error": "未找到入口函数"}

    runtime.entry_used = entry_func
    runtime.state = RunState.RUNNING
    runtime.state_transitions.append({
        "from": RunState.READY, "to": RunState.RUNNING, "time": time.time(),
    })

    start_time = time.time()

    # 看门狗回调：超时即置位中断
    def _on_timeout():
        runtime.timed_out = True
        if runtime.abort_event is not None:
            runtime.abort_event.set()

    watchdog = Watchdog(timeout_s, callback=_on_timeout)
    runtime.watchdog = watchdog

    # 在执行线程中运行入口（daemon，避免无限循环阻塞进程退出）
    result_box: Dict[str, Any] = {}

    def _target():
        try:
            result_box["result"] = _run_entry(runtime, entry_func, default_input)
        except Exception as e:  # 最后兜底
            runtime.errors.append(f"{type(e).__name__}: {e}")
            result_box["result"] = {"kind": "error"}

    worker = threading.Thread(target=_target, daemon=True)
    runtime.worker = worker

    watchdog.start()
    worker.start()
    worker.join(timeout=timeout_s + 0.5)  # 略宽于看门狗，确保定时器先触发
    watchdog.stop()

    run_result = result_box.get("result", {"kind": "unknown"})
    elapsed = time.time() - start_time

    # 状态判定：看门狗已置位 → 一律判超时（执行线程可能因协作中断恰好退出）
    if runtime.timed_out:
        runtime.state = RunState.TIMED_OUT
        status = "timeout"
        runtime.state_transitions.append({
            "from": RunState.RUNNING, "to": RunState.TIMED_OUT, "time": time.time(),
        })
    else:
        kind = run_result.get("kind")
        if kind == "error":
            runtime.state = RunState.ERROR
            status = "error"
        else:
            runtime.state = RunState.FINISHED
            status = "success"
            if kind in ("begin_transition", "aborted"):
                runtime.reached_title = True
            # engine.run() 完成时，根据输出内容检测标题画面
            elif kind == "finished":
                output = getattr(runtime.renderer, '_base', None)
                if output is not None and hasattr(output, 'get_output'):
                    output_text = output.get_output() or ""
                else:
                    output_text = ""
                if "新游戏" in output_text or "SYSTEM_TITLE" in output_text.upper():
                    runtime.reached_title = True
        runtime.state_transitions.append({
            "from": RunState.RUNNING, "to": runtime.state, "time": time.time(),
        })

    # 输入耗尽标记（来自渲染器）
    if runtime.renderer is not None and getattr(runtime.renderer, "input_exhausted", False):
        runtime.input_exhausted = True

    return {
        "status": status,
        "elapsed_s": elapsed,
        "entry": entry_func,
        "kind": run_result.get("kind"),
        "begin_mode": run_result.get("begin_mode"),
        "timed_out": runtime.timed_out,
        "input_exhausted": runtime.input_exhausted,
    }


# ── 痕迹采集 ──

def _truncate_var(value: Any) -> Any:
    """对大数组做预览截断，保证 JSON 可序列化且体积可控。"""
    if isinstance(value, list):
        total = 0
        try:
            total = sum(len(row) if isinstance(row, list) else 1 for row in value)
        except Exception:
            total = len(value)
        if total > 128:
            preview = value[:64]
            return {"__preview__": True, "total": total, "head": preview}
        return value
    return value


def collect_trace(runtime: RuntimeHandle) -> Dict[str, Any]:
    """
    采集运行痕迹（七项）：
    1. 终态变量表  2. 调用栈残留  3. 输出缓冲全文  4. 状态迁移时间线
    5. 运行时错误清单  6. 解析错误清单  7. 事件监控记录

    端口：collect_trace (L2 04 §6)
    """
    trace: Dict[str, Any] = {}

    # 1. 终态变量表（优先用真实取值接口）
    try:
        vmgr = getattr(runtime.engine, "variable_mgr", None)
        final_vars: Dict[str, Any] = {}
        if vmgr is not None:
            for name in vmgr._descriptors:
                try:
                    val = vmgr.get_value(name)
                    final_vars[name] = _truncate_var(val)
                except Exception:
                    final_vars[name] = None
        trace["final_variables"] = final_vars
    except Exception:
        trace["final_variables"] = {}

    # 2. 调用栈残留
    try:
        vm = getattr(runtime.engine, "vm", None)
        if vm is not None and hasattr(vm, "call_stack"):
            trace["call_stack"] = [
                getattr(c, "function_name", str(c)) for c in vm.call_stack
            ]
        else:
            trace["call_stack"] = []
    except Exception:
        trace["call_stack"] = []

    # 3. 输出缓冲全文
    try:
        if runtime.renderer is not None and hasattr(runtime.renderer, "get_output"):
            trace["output_full"] = runtime.renderer.get_output()
        else:
            trace["output_full"] = ""
    except Exception:
        trace["output_full"] = ""

    # 4. 状态迁移时间线
    trace["state_transitions"] = runtime.state_transitions

    # 5. 运行时错误清单
    trace["runtime_errors"] = list(runtime.errors)

    # 6. 解析错误清单
    try:
        if hasattr(runtime.engine, "_parse_errors"):
            trace["parse_errors"] = list(runtime.engine._parse_errors)
        else:
            trace["parse_errors"] = []
    except Exception:
        trace["parse_errors"] = []

    # 7. 事件监控记录
    try:
        if hasattr(runtime.engine, "_monitor_events"):
            trace["monitor_events"] = [
                {
                    "category": getattr(e, "category", "unknown"),
                    "message": getattr(e, "message", ""),
                }
                for e in runtime.engine._monitor_events
            ]
        else:
            trace["monitor_events"] = []
    except Exception:
        trace["monitor_events"] = []

    return trace


# ── 报告生成 ──

def generate_report(
    runtime: RuntimeHandle,
    trace: Dict[str, Any],
) -> Dict[str, Any]:
    """
    生成运行报告：结束状态、输入输出统计、错误清单、终态关键变量。

    端口：generate_report (L2 04 §6)
    """
    output_text = trace.get("output_full", "") or ""
    output_lines = output_text.split("\n") if output_text else []

    return {
        "status": runtime.state,
        "timed_out": runtime.timed_out,
        "input_exhausted": runtime.input_exhausted,
        "reached_title": runtime.reached_title,
        "entry_used": runtime.entry_used,
        "begin_mode": runtime.begin_mode,
        "state_transitions_count": len(runtime.state_transitions),
        "output_stats": {
            "total_chars": len(output_text),
            "total_lines": len(output_lines),
        },
        "error_count": len(runtime.errors),
        "errors": runtime.errors[:10],
        "final_variables_count": len(trace.get("final_variables", {})),
        "key_variables": {
            k: v for k, v in trace.get("final_variables", {}).items()
            if k in ("TARGET", "SELECTCASE", "RESULT", "CHARANUM", "NOWORD_JUMP")
        },
    }
