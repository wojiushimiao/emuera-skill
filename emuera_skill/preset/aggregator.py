"""
预设聚合层 - 一键式调用覆盖完整管线。
六个预设：project-checkup, diagnose-function, author-flow, play-start, play-turn, polish-deliver。
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from ..pipeline_a import run_pipeline_a
    from ..pipeline_bc import run_pipeline_bc
    from ..pipeline_d import run_pipeline_d
    from ..kernel_bridge.engine import assemble_engine, capture_snapshot, compute_fingerprint
    from ..code_graph.graph import build_graph, query_by_name
    from ..gap_analysis.analyzer import generate_ledger
    from ..player_session.session import SessionManager
    from ..authoring.generator import locate_anchor, generate_skeleton, validate_draft, assess_impact, deliver_draft
    from ..llm_orchestration.orchestrator import orchestrate, compress_context
except ImportError:
    from pipeline_a import run_pipeline_a
    from pipeline_bc import run_pipeline_bc
    from pipeline_d import run_pipeline_d
    from kernel_bridge.engine import assemble_engine, capture_snapshot, compute_fingerprint
    from code_graph.graph import build_graph, query_by_name
    from gap_analysis.analyzer import generate_ledger
    from player_session.session import SessionManager
    from authoring.generator import locate_anchor, generate_skeleton, validate_draft, assess_impact, deliver_draft
    from llm_orchestration.orchestrator import orchestrate, compress_context


@dataclass
class PresetResult:
    """预设结果"""
    preset: str
    status: str
    summary: Dict[str, Any]
    artifacts: List[str] = field(default_factory=list)
    degraded: bool = False


def project_checkup(game_dir: str, output_root: str) -> PresetResult:
    """工程体检：P-A→P-B→P-C 全链"""
    start = time.time()
    fingerprint = compute_fingerprint(game_dir)

    # P-A: 快照（强制刷新，确保拿到最新 SEMA 语义诊断）
    pa = run_pipeline_a(game_dir, force_refresh=True)

    # P-B + P-C: 图谱与缺口
    handle = assemble_engine(game_dir)
    snapshot = capture_snapshot(handle)
    snapshot.fingerprint = fingerprint
    bc = run_pipeline_bc(snapshot, output_root, fingerprint)

    elapsed = time.time() - start
    summary = {
        "functions": pa.get("summary", {}).get("functions", 0),
        "variables": pa.get("summary", {}).get("variables", 0),
        "files": pa.get("summary", {}).get("files", 0),
        "parse_errors": pa.get("summary", {}).get("parse_errors", 0),
        "semantic_warnings": pa.get("summary", {}).get("semantic_warnings", 0),
        "semantic_warnings_sample": (pa.get("semantic_warnings") or [])[:10],
        "graph_nodes": bc.get("graph", {}).get("node_count", 0),
        "gaps_total": bc.get("gaps", {}).get("total", 0),
        "implementation_ratio": bc.get("gaps", {}).get("implementation_ratio", 0),
        "elapsed_s": round(elapsed, 2),
    }

    return PresetResult(
        preset="project-checkup",
        status="success",
        summary=summary,
    )


def diagnose_function(game_dir: str, func_name: str) -> PresetResult:
    """函数诊断：定位 + 调用链 + 实现状态"""
    start = time.time()
    fingerprint = compute_fingerprint(game_dir)

    handle = assemble_engine(game_dir)
    snapshot = capture_snapshot(handle)
    snapshot.fingerprint = fingerprint
    graph = build_graph(snapshot)

    # 查找函数
    nodes = query_by_name(graph, func_name)
    elapsed = time.time() - start

    summary = {
        "function": func_name,
        "found": len(nodes) > 0,
        "elapsed_s": round(elapsed, 2),
    }

    # 利用 build_graph 补的节点 source_file / line 元数据回填
    if nodes:
        node = nodes[0]
        summary["file"] = node.file
        summary["line"] = node.line
        # 当前函数的出边数（调用/事件绑定/变量引用），辅助诊断
        out_edges = [e for e in graph.edges if e.source == node.id]
        summary["out_edge_count"] = len(out_edges)
        summary["resolved_calls"] = sum(
            1 for e in out_edges if e.relation == "call" and e.attrs.get("resolved")
        )
        summary["unresolved_calls"] = sum(
            1 for e in out_edges if e.relation == "call" and not e.attrs.get("resolved")
        )

    return PresetResult(preset="diagnose-function", status="success", summary=summary)


def author_flow(game_dir: str, query: str, event_name: str = "", output_root: str = "./emuera-skill-out") -> PresetResult:
    """开发流程：锚点 + 骨架 + 校验 + 影响面"""
    start = time.time()
    fingerprint = compute_fingerprint(game_dir)

    handle = assemble_engine(game_dir)
    snapshot = capture_snapshot(handle)
    snapshot.fingerprint = fingerprint
    graph = build_graph(snapshot)

    anchors = locate_anchor(graph, query)
    draft = generate_skeleton(anchors, event_name)
    impact = assess_impact(graph, anchors)

    # 校验草案
    validation = validate_draft(draft, graph)

    elapsed = time.time() - start

    summary = {
        "query": query,
        "anchors_found": len(anchors),
        "draft_length": len(draft.content),
        "affected_functions": len(impact.affected_functions),
        "elapsed_s": round(elapsed, 2),
    }

    # 交付草案
    draft_path = deliver_draft(draft, validation, impact, output_root, fingerprint)

    return PresetResult(
        preset="author-flow",
        status="success",
        summary=summary,
        artifacts=[draft_path],
    )


def play_start(game_dir: str, output_root: str, load_session: Optional[str] = None) -> PresetResult:
    """开局游玩：快照 + 无头装配 + 标题态"""
    start = time.time()
    fingerprint = compute_fingerprint(game_dir)
    manager = SessionManager(output_root)

    session = manager.start_session(
        game_dir=game_dir,
        fingerprint=fingerprint,
        restore_path=load_session,
    )

    actions = manager.list_actions(session)
    elapsed = time.time() - start

    summary = {
        "session_id": session.session_id,
        "state": session.state,
        "actions_count": len(actions),
        "elapsed_s": round(elapsed, 2),
    }

    return PresetResult(preset="play-start", status="success", summary=summary)


def play_turn(game_dir: str, output_root: str, intent: str) -> PresetResult:
    """回合推进：翻译 + 派发 + 持久化"""
    start = time.time()
    fingerprint = compute_fingerprint(game_dir)
    manager = SessionManager(output_root)

    session = manager.start_session(game_dir, fingerprint)
    action = manager.translate_intent(session, intent)
    result = manager.dispatch_action(session, action)

    elapsed = time.time() - start

    summary = {
        "session_id": session.session_id,
        "turn": result.get("turn", 0),
        "action_type": action.get("action_type"),
        "status": result.get("status"),
        "elapsed_s": round(elapsed, 2),
    }

    return PresetResult(preset="play-turn", status="success", summary=summary)


def polish_deliver(task: str, context: Dict[str, Any]) -> PresetResult:
    """润色交付：压缩 + 模板 + 校验"""
    start = time.time()

    result = orchestrate(task=task, context=context)

    elapsed = time.time() - start

    summary = {
        "task": task,
        "degraded": result.get("degraded", False),
        "elapsed_s": round(elapsed, 2),
    }

    return PresetResult(preset="polish-deliver", status="success", summary=summary)


# ── 预设路由 ──

PRESETS = {
    "project-checkup": project_checkup,
    "diagnose-function": diagnose_function,
    "author-flow": author_flow,
    "play-start": play_start,
    "play-turn": play_turn,
    "polish-deliver": polish_deliver,
}


def run_preset(preset_name: str, **kwargs) -> PresetResult:
    """运行预设"""
    func = PRESETS.get(preset_name)
    if not func:
        return PresetResult(
            preset=preset_name,
            status="error",
            summary={"error": f"未知预设: {preset_name}"},
        )

    try:
        return func(**kwargs)
    except Exception as e:
        return PresetResult(
            preset=preset_name,
            status="error",
            summary={"error": str(e)},
        )
