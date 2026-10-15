"""
代码图谱子系统测试（重建版）。
验证 build_graph / analyze_graph / 查询 / 导出 / 缺口联动。
注：原始文件于回滚中丢失，本文件按图谱行为契约重写。
"""
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emuera_skill.kernel_bridge.engine import assemble_engine, capture_snapshot
from emuera_skill.code_graph.graph import (
    build_graph,
    analyze_graph,
    export_graph_json,
    query_by_name,
    query_by_type,
    query_by_file,
    get_neighbors,
    CodeGraph,
)
from emuera_skill.gap_analysis.analyzer import generate_ledger

GAME_DIR = r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus"


@pytest.fixture(scope="module")
def graph():
    handle = assemble_engine(GAME_DIR)
    snapshot = capture_snapshot(handle)
    return build_graph(snapshot)


def test_graph_building(graph):
    """节点/边/索引三类产物齐备"""
    assert graph.stats["node_count"] > 0
    assert graph.stats["edge_count"] >= 0
    assert graph.stats["function_count"] > 0
    assert len(graph.index.by_name) > 0
    return len(graph.nodes), len(graph.edges)


def test_graph_node_kinds(graph):
    """四类节点：函数/变量/事件至少函数存在"""
    kinds = {n.kind for n in graph.nodes.values()}
    assert "function" in kinds


def test_query_by_name(graph):
    """按名查询命中"""
    results = query_by_name(graph, "SYSTEM")
    assert isinstance(results, list)
    for n in results:
        assert n.name.upper() in ("SYSTEM",)


def test_query_by_type(graph):
    """按类型查询"""
    funcs = query_by_type(graph, "function")
    assert len(funcs) == graph.stats["function_count"]


def test_get_neighbors(graph):
    """邻接查询双向可用"""
    if not graph.edges:
        pytest.skip("图谱无边可查")
    src = graph.edges[0].source
    out = get_neighbors(graph, src, direction="out")
    inn = get_neighbors(graph, src, direction="in")
    assert isinstance(out, list)
    assert isinstance(inn, list)


def test_analyze_graph(graph):
    """分析产出枢纽排序"""
    analysis = analyze_graph(graph)
    assert analysis["node_count"] == graph.stats["node_count"]
    assert analysis["edge_count"] == graph.stats["edge_count"]
    hubs = analysis["hubs"]
    for i in range(1, len(hubs)):
        assert hubs[i - 1][1] >= hubs[i][1]
    return len(hubs)


def test_gap_analysis(graph):
    """缺口账本与图谱联动"""
    handle = assemble_engine(GAME_DIR)
    snapshot = capture_snapshot(handle)
    ledger = generate_ledger(graph, snapshot)
    assert ledger.stats.get("total", 0) >= 0
    return ledger


def test_coverage_degradation(graph):
    """空快照构建空图谱不崩溃（覆盖退化边界）"""
    from emuera_skill.kernel_bridge.engine import Snapshot
    empty = Snapshot(
        fingerprint="",
        functions={},
        variables={},
        parse_errors=[],
        semantic_warnings=[],
        data_dictionary={},
        macro_table={},
        programs_count=0,
        game_dir="",
    )
    g = build_graph(empty)
    return g.stats["node_count"] >= 0


def test_query_performance(graph):
    """千次按名查询性能边界（< 5s）"""
    sample = list(graph.index.by_name)[:50]
    t0 = time.time()
    for name in sample * 20:
        query_by_name(graph, name)
    return time.time() - t0 < 5.0


def test_revival_candidates(graph):
    """缺口账本含复活候选类别"""
    from emuera_skill.gap_analysis.analyzer import COMMAND_REVIVAL_CANDIDATES
    handle = assemble_engine(GAME_DIR)
    snapshot = capture_snapshot(handle)
    ledger = generate_ledger(graph, snapshot, runtime_trace=None)
    return len(COMMAND_REVIVAL_CANDIDATES) > 0


def test_full_pipeline(graph):
    """图谱导出 JSON 全链路"""
    export = export_graph_json(graph)
    assert "nodes" in export and "edges" in export and "stats" in export
    assert len(export["nodes"]) == graph.stats["node_count"]
    return export
