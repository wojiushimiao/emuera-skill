"""
开发辅助子系统。
面向写新内容的锚点检索 → 骨架生成 → 规范校验 → 影响面评估 → 草案交付链路。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..code_graph.graph import CodeGraph, query_by_name, query_by_type, get_neighbors
    from ..gap_analysis.analyzer import GapLedger
    from ..errors import make_error, AU_601, AU_602, IF_901, EmueraError
except ImportError:
    from code_graph.graph import CodeGraph, query_by_name, query_by_type, get_neighbors
    from gap_analysis.analyzer import GapLedger
    from errors import make_error, AU_601, AU_602, IF_901, EmueraError


# ── 数据结构 ──

@dataclass
class Anchor:
    """锚点"""
    id: str
    kind: str  # function/event/variable/role
    name: str
    file: Optional[str] = None
    line: Optional[int] = None
    relevance: float = 0.0
    reference_code: Optional[str] = None


@dataclass
class Draft:
    """草案"""
    content: str
    anchors: List[Anchor] = field(default_factory=list)
    template_version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """校验结果"""
    valid: bool
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ImpactReport:
    """影响面报告"""
    affected_functions: List[str] = field(default_factory=list)
    affected_events: List[str] = field(default_factory=list)
    risk_areas: List[Dict[str, Any]] = field(default_factory=list)
    traversal_complete: bool = True


# ── 锚点检索 ──

def locate_anchor(
    graph: CodeGraph,
    query: str,
    context: Optional[Dict[str, Any]] = None,
) -> List[Anchor]:
    """
    图谱检索相关函数/事件入口/变量/名称映射。
    挑选风格最接近的既有实现作参照。

    端口：locate_anchor (L2 04 §8)
    """
    anchors = []

    # 按名称查询
    nodes = query_by_name(graph, query)
    for node in nodes[:5]:  # 最多 5 个
        anchor = Anchor(
            id=node.id,
            kind=node.kind,
            name=node.name,
            file=node.file,
            line=node.line,
            relevance=0.8,
        )
        anchors.append(anchor)

    # 如果查询词是事件名，查找相关函数
    if query.upper().startswith("EVENT"):
        event_nodes = query_by_type(graph, "event")
        for event_node in event_nodes:
            if query.upper() in event_node.name.upper():
                # 查找绑定到此事件的函数
                neighbors = get_neighbors(graph, event_node.id, direction="in")
                for neighbor, edge in neighbors[:3]:
                    if neighbor.kind == "function":
                        anchor = Anchor(
                            id=neighbor.id,
                            kind="function",
                            name=neighbor.name,
                            file=neighbor.file,
                            line=neighbor.line,
                            relevance=0.9,
                        )
                        anchors.append(anchor)

    # 按类型补充
    if len(anchors) < 3:
        function_nodes = query_by_type(graph, "function")
        for func_node in function_nodes:
            if query.lower() in func_node.name.lower():
                anchor = Anchor(
                    id=func_node.id,
                    kind="function",
                    name=func_node.name,
                    file=func_node.file,
                    line=func_node.line,
                    relevance=0.6,
                )
                anchors.append(anchor)
                if len(anchors) >= 5:
                    break

    return anchors


# ── 骨架生成 ──

def generate_skeleton(
    anchors: List[Anchor],
    event_name: str = "",
    template_version: str = "1.0",
) -> Draft:
    """
    生成 ERB 骨架。
    含合法事件头与锚点注释。

    端口：generate_skeleton (L2 04 §8)
    """
    lines = []

    # 事件头
    if event_name:
        lines.append(f";{event_name}")
        lines.append("")

    # 锚点注释
    if anchors:
        lines.append("; 参照锚点：")
        for anchor in anchors[:3]:
            lines.append(f"; - {anchor.kind}: {anchor.name} ({anchor.file or 'unknown'}:{anchor.line or '?'})")
        lines.append("")

    # 骨架内容
    lines.append("@JUMP KOJO_START")
    lines.append("")
    lines.append("KOJO_START")
    lines.append("PRINTL 这是自动生成的骨架，请根据锚点参照修改")
    lines.append("PRINTL ")
    lines.append("RETURN")
    lines.append("")

    content = "\n".join(lines)

    return Draft(
        content=content,
        anchors=anchors,
        template_version=template_version,
        metadata={
            "event_name": event_name,
            "anchor_count": len(anchors),
        },
    )


# ── 规范校验 ──

def validate_draft(
    draft: Draft,
    graph: CodeGraph,
    ledger: Optional[GapLedger] = None,
) -> ValidationResult:
    """
    静态检查五项：
    1. 变量已声明
    2. 函数存在
    3. 控制流闭合
    4. 命名约定
    5. 未实现指令引用

    端口：validate_draft (L2 04 §8)
    """
    errors = []
    warnings = []

    content = draft.content

    # 1. 变量已声明（简化：检查 SET/GET 语句中的变量）
    import re
    var_refs = re.findall(r'(?:SET|GET|VAR)\s+(\w+)', content, re.IGNORECASE)
    for var_name in var_refs:
        nodes = query_by_name(graph, var_name)
        if not nodes:
            errors.append({
                "code": "AU-601",
                "message": f"变量未声明: {var_name}",
                "severity": "error",
            })

    # 2. 函数存在（简化：检查 CALL/CALLFORM）
    func_refs = re.findall(r'(?:CALL|CALLFORM)\s+(\w+)', content, re.IGNORECASE)
    for func_name in func_refs:
        nodes = query_by_name(graph, func_name)
        if not nodes:
            errors.append({
                "code": "AU-602",
                "message": f"函数不存在: {func_name}",
                "severity": "error",
            })

    # 3. 控制流闭合（简化：检查 IF/ENDIF 配对）
    if_count = len(re.findall(r'\bIF\b', content, re.IGNORECASE))
    endif_count = len(re.findall(r'\bENDIF\b', content, re.IGNORECASE))
    if if_count != endif_count:
        warnings.append({
            "code": "AU-603",
            "message": f"IF/ENDIF 不匹配: {if_count} IF vs {endif_count} ENDIF",
            "severity": "warning",
        })

    # 4. 命名约定（简化：函数名大写）
    func_names = re.findall(r'^(\w+)', content, re.MULTILINE)
    for name in func_names:
        if name.upper() != name and not name.startswith(";"):
            warnings.append({
                "code": "AU-604",
                "message": f"函数名建议大写: {name}",
                "severity": "warning",
            })

    # 5. 未实现指令引用
    if ledger:
        gap_keywords = set()
        for gap in ledger.gaps:
            if "keyword" in gap.evidence:
                gap_keywords.add(gap.evidence["keyword"].upper())

        stmt_refs = re.findall(r'\b(\w+)\b', content)
        for stmt in stmt_refs:
            if stmt.upper() in gap_keywords:
                warnings.append({
                    "code": "AU-605",
                    "message": f"引用未实现指令: {stmt}",
                    "severity": "warning",
                })

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ── 影响面评估 ──

def assess_impact(
    graph: CodeGraph,
    anchors: List[Anchor],
    max_depth: int = 3,
) -> ImpactReport:
    """
    从锚点反向遍历受影响函数与事件。
    结合账本评估缺口区域风险。

    端口：assess_impact (L2 04 §8)
    """
    affected_functions = set()
    affected_events = set()
    risk_areas = []
    traversal_complete = True

    # BFS 遍历
    visited = set()
    queue = [(anchor.id, 0) for anchor in anchors]

    while queue:
        node_id, depth = queue.pop(0)
        if node_id in visited or depth > max_depth:
            if depth > max_depth:
                traversal_complete = False
            continue

        visited.add(node_id)

        # 获取节点信息
        node = graph.nodes.get(node_id)
        if not node:
            continue

        if node.kind == "function":
            affected_functions.add(node.name)
        elif node.kind == "event":
            affected_events.add(node.name)

        # 获取入边（谁调用了这个节点）
        neighbors = get_neighbors(graph, node_id, direction="in")
        for neighbor, edge in neighbors:
            if neighbor.id not in visited:
                queue.append((neighbor.id, depth + 1))

    return ImpactReport(
        affected_functions=list(affected_functions),
        affected_events=list(affected_events),
        risk_areas=risk_areas,
        traversal_complete=traversal_complete,
    )


# ── 草案交付 ──

def deliver_draft(
    draft: Draft,
    validation: ValidationResult,
    impact: ImpactReport,
    output_root: str,
    fingerprint: str,
    protected_roots: Optional[List[str]] = None,
) -> str:
    """
    草案 + 校验报告 + 影响面报告 + 落盘指引落输出根。
    绝不自动写回游戏目录。

    只读守卫：若落盘目标解析到受保护根（游戏目录），拒绝并抛 IF-901，
    绝不写回游戏目录。

    端口：deliver_draft (L2 04 §8)
    """
    output_dir = Path(output_root) / fingerprint[:8] / "drafts"

    # 只读守卫：解析真实路径后，禁止落入任何受保护根
    resolved = output_dir.resolve()
    if protected_roots:
        protected = [Path(p).resolve() for p in protected_roots]
        for prot in protected:
            try:
                resolved.relative_to(prot)
                # 解析成功 → 落在受保护根内，拒绝
                raise make_error(
                    IF_901,
                    context={"attempted_path": str(resolved), "protected": str(prot)},
                )
            except ValueError:
                # 不在该受保护根内，继续检查
                continue

    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存草案
    # 编码约定：Emuera 依据 BOM 判定 UTF-8，缺 BOM 的非 ASCII 脚本会被按 Shift-JIS 解析
    # 而导致字符串常量乱码（实机运行时报脚本错误），故交付统一写入 UTF-8 BOM。
    draft_path = str(output_dir / "draft.erb")
    with open(draft_path, "w", encoding="utf-8-sig") as f:
        f.write(draft.content)

    # 保存校验报告
    validation_path = str(output_dir / "validation.json")
    with open(validation_path, "w", encoding="utf-8") as f:
        json.dump({
            "valid": validation.valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
        }, f, ensure_ascii=False, indent=2)

    # 保存影响面报告
    impact_path = str(output_dir / "impact.json")
    with open(impact_path, "w", encoding="utf-8") as f:
        json.dump({
            "affected_functions": impact.affected_functions,
            "affected_events": impact.affected_events,
            "risk_areas": impact.risk_areas,
            "traversal_complete": impact.traversal_complete,
        }, f, ensure_ascii=False, indent=2)

    return draft_path
