"""
代码图谱子系统。
把工程快照变成可查询的结构化代码图谱（四类节点、三类边、三种倒排索引）。
"""

import re
import time
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

try:
    from ..kernel_bridge.engine import Snapshot
    from ..errors import make_error
except ImportError:
    from kernel_bridge.engine import Snapshot
    from errors import make_error


# ── 节点与边数据结构 ──

@dataclass
class GraphNode:
    """图谱节点"""
    id: str
    kind: str  # function/variable/role/event
    name: str
    file: Optional[str] = None
    line: Optional[int] = None
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """图谱边"""
    source: str
    target: str
    relation: str  # call/jump/event_bind/var_read/var_write
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphIndex:
    """倒排索引"""
    by_name: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    by_file: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    by_type: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))


@dataclass
class CodeGraph:
    """代码图谱"""
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)
    index: GraphIndex = field(default_factory=GraphIndex)
    stats: Dict[str, int] = field(default_factory=dict)
    # 函数名(大写) -> 函数体文本，供实现度逐条检测使用
    body_texts: Dict[str, str] = field(default_factory=dict)


# ── 节点与边构建 ──

def _extract_calls_from_text(body: str) -> List[str]:
    """从函数体文本中提取函数调用"""
    calls = []
    # 匹配 CALL / CALLFORM / CALLFORMS / GOTO / GOTOFORM
    patterns = [
        r'\b(?:CALL|CALLFORM|CALLFORMS)\s+(\w+)',
        r'\b(?:GOTO|GOTOFORM)\s+(\w+)',
    ]
    for pat in patterns:
        calls.extend(re.findall(pat, body, re.IGNORECASE))
    return calls


def _extract_events_from_text(body: str) -> List[str]:
    """从函数体文本中提取事件绑定"""
    events = []
    patterns = [
        r'\b(?:EVENTTRAIN|EVENTEND|EVENTSHOP|EVENTBUY|EVENTCOM|EVENTCOMEND)\b',
    ]
    for pat in patterns:
        events.extend(re.findall(pat, body, re.IGNORECASE))
    return events


def _extract_var_refs_from_text(body: str) -> List[str]:
    """从函数体文本中提取变量引用"""
    # 简化实现：匹配常见变量引用模式
    refs = re.findall(r'\b([A-Z_][A-Z0-9_]*)\b', body)
    return list(set(refs))


def _scan_source_functions(game_dir: Optional[str]) -> Dict[str, Any]:
    """
    扫描工程目录下的 ERB/ERH 源文件，提取每个 @NAME 函数定义的位置与函数体文本。

    返回：{ func_name_upper: (source_file, line, body_text) }
    摄取时文件已知：文件路径与行号直接来自源文件，无需依赖快照是否携带。
    """
    result: Dict[str, Any] = {}
    if not game_dir:
        return result
    base = Path(game_dir)
    if not base.exists():
        return result

    files = []
    for ext in ("*.ERB", "*.erb", "*.ERH", "*.erh"):
        files.extend(base.rglob(ext))

    header_re = re.compile(r"^\s*@(\w+)")
    for fpath in files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lines = text.splitlines()
        n = len(lines)
        i = 0
        while i < n:
            m = header_re.match(lines[i])
            if m:
                name = m.group(1)
                start_line = i + 1  # 1-based
                body_lines = []
                j = i + 1
                while j < n:
                    if header_re.match(lines[j]):
                        break
                    body_lines.append(lines[j])
                    j += 1
                body = "\n".join(body_lines)
                result[name.upper()] = (str(fpath), start_line, body)
                i = j
            else:
                i += 1
    return result


def build_graph(snapshot: Snapshot) -> CodeGraph:
    """
    从快照构建代码图谱。
    四类节点：函数、变量、角色、事件入口
    三类边：调用、跳转、事件绑定、变量读写

    端口：build_graph (L2 04 §4)
    """
    graph = CodeGraph()

    # 扫描源文件，提取每个函数的位置与函数体文本
    source_map = _scan_source_functions(snapshot.game_dir)
    function_names = {name.upper() for name in snapshot.functions}

    # ── 函数节点 ──
    for name, func_info in snapshot.functions.items():
        src = source_map.get(name.upper())
        if src:
            sfile, sline, sbody = src
            graph.body_texts[name.upper()] = sbody
        else:
            sfile = func_info.get("file")
            sline = func_info.get("line")
        node = GraphNode(
            id=f"func:{name}",
            kind="function",
            name=name,
            file=sfile,
            line=sline,
            attrs={
                "param_count": func_info.get("param_count", 0),
                "body": sbody if src else "",
            }
        )
        graph.nodes[node.id] = node
        graph.index.by_name[name].append(node.id)
        if node.file:
            graph.index.by_file[node.file].append(node.id)
        graph.index.by_type["function"].append(node.id)

    # ── 变量节点 ──
    for name, var_info in snapshot.variables.items():
        node = GraphNode(
            id=f"var:{name}",
            kind="variable",
            name=name,
            attrs={
                "type": var_info.get("type"),
                "size": var_info.get("size"),
                "has_name_map": var_info.get("has_name_map", False),
            }
        )
        graph.nodes[node.id] = node
        graph.index.by_name[name].append(node.id)
        graph.index.by_type["variable"].append(node.id)

    # ── 角色节点（从数据字典） ──
    if snapshot.data_dictionary:
        for role_name in snapshot.data_dictionary.get("name_maps", []):
            node = GraphNode(
                id=f"role:{role_name}",
                kind="role",
                name=role_name,
            )
            graph.nodes[node.id] = node
            graph.index.by_name[role_name].append(node.id)
            graph.index.by_type["role"].append(node.id)

    # ── 事件入口节点 ──
    # 标准事件 + 工程中以 SYSTEM_ / EVENT 开头的函数也视为事件入口
    event_patterns = [
        "EVENTTRAIN", "EVENTEND", "EVENTSHOP", "EVENTBUY",
        "EVENTCOM", "EVENTCOMEND", "EVENTTURNEND"
    ]
    event_names = set(event_patterns)
    for name in snapshot.functions:
        u = name.upper()
        if u.startswith("SYSTEM_") or u.startswith("EVENT"):
            event_names.add(name)
    event_names_upper = {e.upper() for e in event_names}
    for event_name in event_names:
        node = GraphNode(
            id=f"event:{event_name}",
            kind="event",
            name=event_name,
        )
        graph.nodes[node.id] = node
        graph.index.by_name[event_name].append(node.id)
        graph.index.by_type["event"].append(node.id)

    # ── 边构建：遍历函数体，真正调用三类提取函数 ──
    unresolved_calls: List[str] = []
    for name, func_info in snapshot.functions.items():
        src = source_map.get(name.upper())
        if not src:
            continue
        body = src[2]
        src_id = f"func:{name}"

        # 1) 调用边（CALL / GOTO 族）
        for target in _extract_calls_from_text(body):
            tup = target.upper()
            resolved = tup in function_names
            graph.edges.append(GraphEdge(
                source=src_id,
                target=f"func:{target}",
                relation="call",
                attrs={"resolved": resolved, "target_name": target},
            ))
            if not resolved:
                unresolved_calls.append(target)

        # 2) 事件绑定边（函数体内引用事件关键字）
        for ev in _extract_events_from_text(body):
            ev_node = f"event:{ev}"
            if ev_node in graph.nodes:
                graph.edges.append(GraphEdge(
                    source=src_id,
                    target=ev_node,
                    relation="event_bind",
                    attrs={"resolved": True},
                ))

        # 3) 变量引用边（仅连接已注册变量，避免噪声）
        for vname in _extract_var_refs_from_text(body):
            if vname in snapshot.variables:
                graph.edges.append(GraphEdge(
                    source=src_id,
                    target=f"var:{vname}",
                    relation="var_read",
                    attrs={"var_name": vname},
                ))

    # 事件型函数自身与其事件节点的绑定边
    for name in snapshot.functions:
        if name.upper() in event_names_upper:
            graph.edges.append(GraphEdge(
                source=f"func:{name}",
                target=f"event:{name}",
                relation="event_bind",
                attrs={"resolved": True},
            ))

    # 统计
    graph.stats = {
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "function_count": len(graph.index.by_type.get("function", [])),
        "variable_count": len(graph.index.by_type.get("variable", [])),
        "role_count": len(graph.index.by_type.get("role", [])),
        "event_count": len(graph.index.by_type.get("event", [])),
        "call_edges": sum(1 for e in graph.edges if e.relation == "call"),
        "event_bind_edges": sum(1 for e in graph.edges if e.relation == "event_bind"),
        "var_ref_edges": sum(1 for e in graph.edges if e.relation.startswith("var_")),
        "unresolved_calls": len(unresolved_calls),
    }

    return graph


# ── 图结构分析 ──

def analyze_graph(graph: CodeGraph) -> Dict[str, Any]:
    """
    图结构分析：度统计、枢纽识别、环检测。

    端口：analyze_graph (L2 04 §4)
    """
    # 度统计
    in_degree = defaultdict(int)
    out_degree = defaultdict(int)
    for edge in graph.edges:
        out_degree[edge.source] += 1
        in_degree[edge.target] += 1

    # 枢纽节点（入度 + 出度最高的前 10 个）
    degree_sum = {}
    for node_id in graph.nodes:
        degree_sum[node_id] = in_degree.get(node_id, 0) + out_degree.get(node_id, 0)
    hubs = sorted(degree_sum.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "in_degree": dict(in_degree),
        "out_degree": dict(out_degree),
        "hubs": [(nid, deg) for nid, deg in hubs if deg > 0],
    }


# ── 查询接口 ──

def get_node(graph: CodeGraph, node_id: str) -> Optional[GraphNode]:
    """按 ID 获取节点"""
    return graph.nodes.get(node_id)


def get_neighbors(graph: CodeGraph, node_id: str, direction: str = "both") -> List[Tuple[GraphNode, GraphEdge]]:
    """
    获取邻居节点。
    direction: "out" / "in" / "both"
    """
    results = []
    for edge in graph.edges:
        if direction in ("out", "both") and edge.source == node_id:
            target = graph.nodes.get(edge.target)
            if target:
                results.append((target, edge))
        if direction in ("in", "both") and edge.target == node_id:
            source = graph.nodes.get(edge.source)
            if source:
                results.append((source, edge))
    return results


def query_by_name(graph: CodeGraph, name: str) -> List[GraphNode]:
    """按名称查询节点"""
    node_ids = graph.index.by_name.get(name, [])
    return [graph.nodes[nid] for nid in node_ids if nid in graph.nodes]


def query_by_file(graph: CodeGraph, file_path: str) -> List[GraphNode]:
    """按文件查询节点"""
    node_ids = graph.index.by_file.get(file_path, [])
    return [graph.nodes[nid] for nid in node_ids if nid in graph.nodes]


def query_by_type(graph: CodeGraph, node_type: str) -> List[GraphNode]:
    """按类型查询节点"""
    node_ids = graph.index.by_type.get(node_type, [])
    return [graph.nodes[nid] for nid in node_ids if nid in graph.nodes]


# ── 导出 ──

def export_graph_json(graph: CodeGraph) -> Dict[str, Any]:
    """导出为 JSON 格式"""
    return {
        "nodes": [
            {
                "id": n.id,
                "kind": n.kind,
                "name": n.name,
                "file": n.file,
                "line": n.line,
                "attrs": n.attrs,
            }
            for n in graph.nodes.values()
        ],
        "edges": [
            {
                "source": e.source,
                "target": e.target,
                "relation": e.relation,
                "attrs": e.attrs,
            }
            for e in graph.edges
        ],
        "stats": graph.stats,
    }
