"""
P-B / P-C 管线：代码图谱构建与缺口分析。
"""

import time
import json
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from code_graph.graph import build_graph, analyze_graph, export_graph_json, CodeGraph
    from gap_analysis.analyzer import generate_ledger, save_ledger, GapLedger
    from kernel_bridge.engine import Snapshot
    from output_dir import get_output_path, ensure_output_dir
except ImportError:
    from .code_graph.graph import build_graph, analyze_graph, export_graph_json, CodeGraph
    from .gap_analysis.analyzer import generate_ledger, save_ledger, GapLedger
    from .kernel_bridge.engine import Snapshot
    from .output_dir import get_output_path, ensure_output_dir


def run_pipeline_bc(
    snapshot: Snapshot,
    output_root: str,
    fingerprint: str,
    runtime_trace: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    执行 P-B + P-C 管线：
    1. 构建代码图谱
    2. 分析图结构
    3. 三路缺口取证
    4. 生成缺口账本

    返回：执行结果摘要
    """
    start_time = time.time()

    # 确保输出目录
    output_dir = ensure_output_dir(output_root, fingerprint)

    # ── P-B: 代码图谱构建 ──
    print("[P-B] 开始构建代码图谱...")
    graph_start = time.time()

    graph = build_graph(snapshot)

    graph_time = time.time() - graph_start
    print(f"[P-B] 图谱构建完成: {graph.stats['node_count']} 节点, {graph.stats['edge_count']} 边, {graph_time:.2f}s")

    # ── 图结构分析 ──
    print("[P-B] 分析图结构...")
    analysis = analyze_graph(graph)
    print(f"[P-B] 枢纽节点: {len(analysis['hubs'])} 个")

    # ── 导出图谱 ──
    graph_json = export_graph_json(graph)
    graph_path = get_output_path(output_dir, "code_graph.json")
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph_json, f, ensure_ascii=False, indent=2)
    print(f"[P-B] 图谱已导出: {graph_path}")

    # ── P-C: 缺口分析 ──
    print("[P-C] 开始缺口分析...")
    gap_start = time.time()

    ledger = generate_ledger(graph, snapshot, runtime_trace)

    gap_time = time.time() - gap_start
    print(f"[P-C] 缺口分析完成: {ledger.stats['total']} 个缺口, {gap_time:.2f}s")

    # ── 导出账本 ──
    ledger_path = get_output_path(output_dir, "gap_ledger.json")
    save_ledger(ledger, ledger_path)
    print(f"[P-C] 账本已导出: {ledger_path}")

    # ── 总结 ──
    total_time = time.time() - start_time
    result = {
        "status": "success",
        "graph": {
            "node_count": graph.stats["node_count"],
            "edge_count": graph.stats["edge_count"],
            "function_count": graph.stats["function_count"],
            "variable_count": graph.stats["variable_count"],
            "role_count": graph.stats["role_count"],
            "event_count": graph.stats["event_count"],
            "graph_time_s": graph_time,
        },
        "analysis": {
            "hubs_count": len(analysis["hubs"]),
            "top_hubs": analysis["hubs"][:5],
        },
        "gaps": {
            "total": ledger.stats["total"],
            "by_severity": ledger.stats["by_severity"],
            "by_category": ledger.stats["by_category"],
            "implementation_ratio": ledger.implementation_ratio,
            "gap_time_s": gap_time,
        },
        "output": {
            "graph_path": graph_path,
            "ledger_path": ledger_path,
        },
        "total_time_s": total_time,
    }

    return result
