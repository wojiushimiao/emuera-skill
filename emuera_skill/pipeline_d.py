"""
P-D 管线：无头运行与痕迹采集。
"""

import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .runtime.headless import (
        assemble_headless, drive_execution, collect_trace, generate_report,
        RuntimeHandle, RunState
    )
    from .output_dir import get_output_path, ensure_output_dir
    from .pipeline_a import run_pipeline_a
    from .config_loader import load_config
except ImportError:
    from runtime.headless import (
        assemble_headless, drive_execution, collect_trace, generate_report,
        RuntimeHandle, RunState
    )
    from output_dir import get_output_path, ensure_output_dir
    from pipeline_a import run_pipeline_a
    from config_loader import load_config


def run_pipeline_d(
    game_dir: str,
    output_root: str,
    fingerprint: str,
    entry: str = "",
    input_queue: Optional[List[Any]] = None,
    default_input: Any = 0,
    timeout_s: float = 60.0,
    run_snapshot: bool = True,
) -> Dict[str, Any]:
    """
    执行 P-D 管线：串联 P-A（快照）+ 无头运行 + 痕迹采集 + 报告生成。

    步骤：
    1. [P-A] 确保同指纹分区的工程快照可用（缺失则生成）
    2. 无头装配
    3. 执行驱动
    4. 痕迹采集
    5. 报告生成

    返回：执行结果摘要
    """
    start_time = time.time()

    # 确保输出目录（与 P-A 同指纹分区）
    output_dir = ensure_output_dir(output_root, fingerprint)

    # ── [P-A] 串联快照：复用同一指纹分区，保证 trace/report 与快照同区 ──
    snapshot_summary: Optional[Dict[str, Any]] = None
    if run_snapshot:
        try:
            cfg = load_config()
            pa_result = run_pipeline_a(game_dir, config=cfg, force_refresh=False)
            snapshot_summary = pa_result.get("summary")
            print(f"[P-D] P-A 快照就绪: {pa_result.get('snapshot_path')}")
        except Exception as e:
            print(f"[P-D] 警告: P-A 快照生成跳过: {e}")

    # ── 步骤1：无头装配 ──
    print("[P-D] 开始无头装配...")
    try:
        runtime = assemble_headless(
            game_dir=game_dir,
            input_queue=input_queue,
            default_input=default_input,
            timeout_s=timeout_s,
        )
        print(f"[P-D] 装配完成，状态: {runtime.state}")
    except Exception as e:
        return {
            "status": "error",
            "phase": "assembly",
            "error": str(e),
        }

    # ── 步骤2：执行驱动 ──
    print("[P-D] 开始执行驱动...")
    exec_result = drive_execution(
        runtime=runtime,
        entry=entry,
        opts={"timeout_s": timeout_s, "default_input": default_input},
    )
    print(f"[P-D] 执行结果: {exec_result['status']}")

    # ── 步骤3：痕迹采集 ──
    print("[P-D] 采集运行痕迹...")
    trace = collect_trace(runtime)

    # ── 步骤4：报告生成 ──
    print("[P-D] 生成运行报告...")
    report = generate_report(runtime, trace)

    # ── 导出 ──
    # 导出痕迹
    trace_path = get_output_path(output_dir, "runtime_trace.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2, default=str)
    print(f"[P-D] 痕迹已导出: {trace_path}")

    # 导出报告
    report_path = get_output_path(output_dir, "runtime_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"[P-D] 报告已导出: {report_path}")

    # ── 总结 ──
    total_time = time.time() - start_time
    result = {
        "status": exec_result["status"],
        "pipeline": "P-D",
        "fingerprint": fingerprint,
        "snapshot": snapshot_summary,
        "runtime": {
            "state": runtime.state,
            "timed_out": runtime.timed_out,
            "input_exhausted": runtime.input_exhausted,
        },
        "execution": exec_result,
        "trace": {
            "final_variables_count": len(trace.get("final_variables", {})),
            "output_length": len(trace.get("output_full", "")),
            "errors_count": len(runtime.errors),
        },
        "report": report,
        "output": {
            "trace_path": trace_path,
            "report_path": report_path,
        },
        "total_time_s": total_time,
    }

    return result
