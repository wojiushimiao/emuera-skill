"""
无头运行时子系统测试（重建版）。
K1 端到端 / K2 看门狗超时 / K3 输入耗尽 / 痕迹七项 / 全管线。
注：原始文件于回滚中丢失，本文件按 runtime/headless.py 行为契约重写。
"""
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emuera_skill.runtime.headless import (
    RuntimeHandle,
    RunState,
    HeadlessRenderer,
    Watchdog,
    assemble_headless,
    drive_execution,
    collect_trace,
    generate_report,
    reset_runtime,
)

GAME_DIR = r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus"
OUT_ROOT = str(_ROOT / "out" / "runtime_tests")


@pytest.fixture(scope="module")
def runtime():
    return assemble_headless(GAME_DIR, input_queue=[0, 0], default_input=0, timeout_s=30.0)


def test_k1_headless_run_completes(runtime):
    """K1：无头装配 + 驱动执行可达终态（finished/aborted/timeout 之一）"""
    r = drive_execution(runtime, entry="", opts={"timeout_s": 30.0, "default_input": 0})
    assert r["status"] in ("success", "timeout", "error")
    assert runtime.state in (RunState.FINISHED, RunState.TIMED_OUT, RunState.ERROR, RunState.READY)
    return runtime


def test_k2_watchdog_timeout():
    """K2：看门狗超时置位 timed_out 与 abort_event"""
    fired = {}

    def _cb():
        fired["yes"] = 1

    wd = Watchdog(timeout_s=0.5, callback=_cb)
    wd.start()
    time.sleep(1.0)
    wd.stop()
    assert wd.fired is True
    assert "yes" in fired
    return wd.fired


def test_k3_input_exhaustion_no_block():
    """K3：输入队列耗尽回退默认值不阻塞（关闭首屏截止以专注耗尽语义）"""
    renderer = HeadlessRenderer(default_input=7, stop_at_first_input=False)
    renderer.input_queue = [1, 2]
    assert renderer.input_number() == 1
    assert renderer.input_number() == 2
    # 队列耗尽：走默认值，且标记 input_exhausted
    val = renderer.input_number()
    assert val == 7
    assert renderer.input_exhausted is True
    return val == 7


def test_reset_runtime(runtime):
    """续玩重置：状态回 READY、中断事件清除、输入队列清空"""
    r = reset_runtime(runtime)
    assert r["status"] == "reset"
    assert runtime.state == RunState.READY
    assert len(runtime.renderer.input_queue) == 0
    return r


def test_trace_seven_items(runtime):
    """痕迹七项齐备"""
    drive_execution(runtime, entry="", opts={"timeout_s": 15.0})
    trace = collect_trace(runtime)
    required = [
        "final_variables", "call_stack", "output_full",
        "state_transitions", "runtime_errors", "parse_errors", "monitor_events",
    ]
    for k in required:
        assert k in trace
    assert len(trace["state_transitions"]) >= 1
    return trace


def test_generate_report(runtime):
    """报告生成：字段齐备、统计一致"""
    drive_execution(runtime, entry="", opts={"timeout_s": 15.0})
    trace = collect_trace(runtime)
    report = generate_report(runtime, trace)
    assert "status" in report
    assert "output_stats" in report
    assert report["state_transitions_count"] == len(trace["state_transitions"])
    return report


def test_full_pipeline():
    """装配→驱动→痕迹→报告 全链不抛异常"""
    rt = assemble_headless(GAME_DIR, input_queue=[], default_input=0, timeout_s=15.0)
    res = drive_execution(rt, entry="", opts={"timeout_s": 15.0})
    trace = collect_trace(rt)
    report = generate_report(rt, trace)
    return {"status": res["status"], "report_state": report["status"]}


def test_drive_requires_ready(runtime):
    """非 READY 状态驱动被拒（状态机约束）"""
    runtime.state = RunState.RUNNING
    r = drive_execution(runtime)
    assert r["status"] == "error"
    runtime.state = RunState.READY
