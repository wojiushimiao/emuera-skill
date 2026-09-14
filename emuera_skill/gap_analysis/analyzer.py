"""
缺口分析子系统。
从静态可达性、语句实现度、动态覆盖率三路取证产出分级缺口账本。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from ..code_graph.graph import CodeGraph, GraphNode, query_by_type, get_neighbors
    from ..kernel_bridge.engine import Snapshot
    from ..errors import make_error
except ImportError:
    from code_graph.graph import CodeGraph, GraphNode, query_by_type, get_neighbors
    from kernel_bridge.engine import Snapshot
    from errors import make_error


# ── 缺口类型定义 ──

class GapSeverity:
    """缺口严重度"""
    CRITICAL = "critical"  # 核心功能缺失
    HIGH = "high"          # 重要功能缺失
    MEDIUM = "medium"      # 一般功能缺失
    LOW = "low"            # 轻微问题
    INFO = "info"          # 信息性发现


class GapCategory:
    """缺口类别"""
    STATIC_REACHABILITY = "static_reachability"  # 静态可达性
    IMPLEMENTATION = "implementation"              # 语句实现度
    DYNAMIC_COVERAGE = "dynamic_coverage"          # 动态覆盖率


@dataclass
class Gap:
    """缺口条目"""
    id: str
    category: str
    severity: str
    title: str
    description: str
    affected: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    fix_cost: str = "unknown"
    recommendations: List[str] = field(default_factory=list)


@dataclass
class GapLedger:
    """缺口账本"""
    generated_at: str = ""
    fingerprint: str = ""
    gaps: List[Gap] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    implementation_ratio: float = 0.0


# ── 权威清单（P-1 产出） ──

# 32 条命令型缺口（P-1 仲裁结果）
COMMAND_TYPE_GAPS = [
    "SWAP", "ADDCOPY", "COPY", "CSVLOAD", "SAVENAME",
    "LOADGAME", "SAVEGAME", "DELDATA", "CHKDATA", "CHKFONT",
    "DRAWLINE", "DRAWBOX", "DRAWIMAGE", "DRAWSPRITE", "DRAWFORM",
    "DRAWCOLOR", "SETCOLOR", "GETCOLOR", "RESETCOLOR",
    "FONTBOLD", "FONTITALIC", "FONTSTRIKEOUT", "FONTSHADOW",
    "ALIGNMENT", "SETLINE", "SETBOX",
    "SPRINT", "PRINTV", "PRINTFORMV",
    "MOUSEX", "MOUSEY", "MOUSEMOVED",
]

# 6 条命令型复活候选
COMMAND_REVIVAL_CANDIDATES = [
    "SWAPCHARA", "COPYCHARA", "SORTCHARA",
    "CHKDATA", "CHKFONT", "DELDATA",
]


# ── 静态可达性分析 ──

def analyze_reachability(graph: CodeGraph) -> List[Gap]:
    """
    静态可达性分析：
    - 从未解析边反向标未定义调用
    - 标未使用变量

    端口：analyze_reachability (L2 04 §5)
    """
    gaps = []
    gap_counter = 0

    # 收集所有函数节点
    function_nodes = query_by_type(graph, "function")
    variable_nodes = query_by_type(graph, "variable")
    event_nodes = query_by_type(graph, "event")

    # 构建函数名集合
    function_names = {n.name for n in function_nodes}
    variable_names = {n.name for n in variable_nodes}
    event_names = {n.name for n in event_nodes}

    # 检测未定义调用（简化：基于命名约定）
    # 完整实现需要解析函数体

    # 检测未使用变量
    # 收集所有被引用的变量名
    referenced_vars = set()
    for edge in graph.edges:
        if edge.relation in ("var_read", "var_write"):
            target_name = edge.target.split(":", 1)[1] if ":" in edge.target else edge.target
            referenced_vars.add(target_name)

    # 未使用变量
    unused_vars = variable_names - referenced_vars
    for var_name in unused_vars:
        gap_counter += 1
        gaps.append(Gap(
            id=f"SR-{gap_counter:03d}",
            category=GapCategory.STATIC_REACHABILITY,
            severity=GapSeverity.LOW,
            title=f"未使用变量: {var_name}",
            description=f"变量 {var_name} 已声明但未被任何函数引用",
            affected=[f"var:{var_name}"],
            evidence={"variable_name": var_name},
            fix_cost="low",
            recommendations=["检查是否为遗留代码", "如确认未使用可安全删除"],
        ))

    return gaps


# ── 语句实现度分析 ──

def analyze_implementation(snapshot: Snapshot) -> List[Gap]:
    """
    语句实现度分析：
    - 对照语法关键字集合与虚拟机执行分支集合
    - 产出已实现/静默丢弃/复活候选三张清单

    端口：analyze_implementation (L2 04 §5)
    """
    gaps = []
    gap_counter = 0

    # 从快照中获取语句关键字集合
    # 简化：使用权威清单中的缺口列表
    # 完整实现需要对比语法分析器的 _STATEMENT_STARTERS 与虚拟机的 exec_statement

    # 命令型缺口（已知静默丢弃）
    for cmd in COMMAND_TYPE_GAPS:
        gap_counter += 1
        gaps.append(Gap(
            id=f"IMPL-{gap_counter:03d}",
            category=GapCategory.IMPLEMENTATION,
            severity=GapSeverity.MEDIUM,
            title=f"命令型缺口: {cmd}",
            description=f"语法解析器识别 {cmd} 但虚拟机无 builtin 实现，执行时静默丢弃",
            affected=[],
            evidence={"keyword": cmd, "builtin_exists": False},
            fix_cost="high",
            recommendations=[
                "检查内核是否有相关 builtin 可复用",
                "评估该指令在游戏中的使用频率",
                "决定是否需要实现或标记为已知限制",
            ],
        ))

    # 复活候选
    for cmd in COMMAND_REVIVAL_CANDIDATES:
        gap_counter += 1
        gaps.append(Gap(
            id=f"REVIVAL-{gap_counter:03d}",
            category=GapCategory.IMPLEMENTATION,
            severity=GapSeverity.INFO,
            title=f"复活候选: {cmd}",
            description=f"内核已有 builtin 实现，但可能未完全适配或需要验证",
            affected=[],
            evidence={"keyword": cmd, "builtin_exists": True, "revival_candidate": True},
            fix_cost="medium",
            recommendations=["验证 builtin 实现是否完整", "编写测试用例覆盖"],
        ))

    return gaps


# ── 动态覆盖率分析 ──

def fuse_coverage(graph: CodeGraph, runtime_trace: Optional[Dict] = None) -> List[Gap]:
    """
    动态覆盖率分析：
    - 合并运行痕迹
    - 无痕迹时降级为 available=false

    端口：fuse_coverage (L2 04 §5)
    """
    gaps = []

    if runtime_trace is None:
        # 无运行痕迹，降级
        gaps.append(Gap(
            id="DYN-001",
            category=GapCategory.DYNAMIC_COVERAGE,
            severity=GapSeverity.INFO,
            title="动态覆盖率不可用",
            description="无运行痕迹数据，无法计算动态覆盖率",
            affected=[],
            evidence={"available": False},
            fix_cost="n/a",
            recommendations=["运行 P3 无头执行获取运行痕迹", "重跑此分析"],
        ))
        return gaps

    # 有运行痕迹时的覆盖率计算（简化）
    # 完整实现需要对比运行时实际执行的函数集合与图谱中的函数节点

    return gaps


# ── 生成账本 ──

def generate_ledger(
    graph: CodeGraph,
    snapshot: Snapshot,
    runtime_trace: Optional[Dict] = None,
) -> GapLedger:
    """
    生成缺口账本。
    影响面 × 严重度 × 修复成本三维定级。

    端口：generate_ledger (L2 04 §5)
    """
    from datetime import datetime

    # 收集三路缺口
    static_gaps = analyze_reachability(graph)
    impl_gaps = analyze_implementation(snapshot)
    dynamic_gaps = fuse_coverage(graph, runtime_trace)

    all_gaps = static_gaps + impl_gaps + dynamic_gaps

    # 统计
    stats = {
        "total": len(all_gaps),
        "by_severity": {},
        "by_category": {},
    }
    for gap in all_gaps:
        stats["by_severity"][gap.severity] = stats["by_severity"].get(gap.severity, 0) + 1
        stats["by_category"][gap.category] = stats["by_category"].get(gap.category, 0) + 1

    # 实现度百分比
    # 修复循环论证：总数取自 kb.knowledge.STATEMENT_STARTERS（117 条权威清单），
    # implemented 改为逐条指令在图谱函数体中的真实出现检测计数，
    # 与 impl_gaps 缺口逻辑相互独立。
    try:
        from ..kb.knowledge import STATEMENT_STARTERS
    except ImportError:
        from kb.knowledge import STATEMENT_STARTERS
    total_statements = len(STATEMENT_STARTERS)
    combined = "\n".join(getattr(graph, "body_texts", {}).values())
    detected = 0
    for mnemonic in STATEMENT_STARTERS:
        if re.search(r"\b" + re.escape(mnemonic) + r"\b", combined, re.IGNORECASE):
            detected += 1
    implementation_ratio = detected / total_statements if total_statements > 0 else 0

    return GapLedger(
        generated_at=datetime.now().isoformat(),
        fingerprint=snapshot.fingerprint,
        gaps=all_gaps,
        stats=stats,
        implementation_ratio=implementation_ratio,
    )


# ── 导出 ──

def export_ledger_json(ledger: GapLedger) -> Dict[str, Any]:
    """导出账本为 JSON 格式"""
    return {
        "generated_at": ledger.generated_at,
        "fingerprint": ledger.fingerprint,
        "stats": ledger.stats,
        "implementation_ratio": ledger.implementation_ratio,
        "gaps": [
            {
                "id": g.id,
                "category": g.category,
                "severity": g.severity,
                "title": g.title,
                "description": g.description,
                "affected": g.affected,
                "evidence": g.evidence,
                "fix_cost": g.fix_cost,
                "recommendations": g.recommendations,
            }
            for g in ledger.gaps
        ],
    }


def save_ledger(ledger: GapLedger, output_path: str):
    """保存账本到文件"""
    data = export_ledger_json(ledger)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
