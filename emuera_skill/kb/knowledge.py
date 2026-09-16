"""
知识库子系统（P7）。

承载 Emuera 脚本语言的静态知识：
  - 指令字典（instruction dictionary）：覆盖内核语法分析器 _STATEMENT_STARTERS 的 117 条语句指令
  - 语法手册（syntax manual）
  - 变量系统说明（variable system）
  - 工程结构说明（project structure）
  - 模式库（pattern library）

权威来源：
  - 117 条语句指令取自内核
      emuera-skill/kernel/src/core/parser.py::_STATEMENT_STARTERS (L2 04 §5)
  - 实现状态分类（已实现/静默丢弃/复活候选/NOOP）取自 P2 缺口分析账本的仲裁结果
      src/gap_analysis/analyzer.py::COMMAND_TYPE_GAPS / COMMAND_REVIVAL_CANDIDATES
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..errors import make_error, EmueraError, Subsystem
    from ..errors import KN_001, KN_002, KN_003
    from ..gap_analysis.analyzer import GapLedger, Gap, GapCategory, GapSeverity
    from ..gap_analysis.analyzer import COMMAND_TYPE_GAPS, COMMAND_REVIVAL_CANDIDATES
except ImportError:  # pragma: no cover - 兼容直接以模块方式运行
    from errors import make_error, EmueraError, Subsystem
    from errors import KN_001, KN_002, KN_003
    from gap_analysis.analyzer import GapLedger, Gap, GapCategory, GapSeverity
    from gap_analysis.analyzer import COMMAND_TYPE_GAPS, COMMAND_REVIVAL_CANDIDATES


# ── 实现状态（与 P2 账本分类对齐） ──

IMPL_IMPLEMENTED = "已实现"
IMPL_SILENT_DROP = "静默丢弃"
IMPL_REVIVAL = "复活候选"
IMPL_NOOP = "NOOP"

VALID_IMPL_STATUS = frozenset({
    IMPL_IMPLEMENTED,
    IMPL_SILENT_DROP,
    IMPL_REVIVAL,
    IMPL_NOOP,
})


# ── 权威清单：117 条语句指令 ──
# 逐字取自内核 core/parser.py::_STATEMENT_STARTERS（顺序保持与内核一致）。
# 这是知识库指令字典的权威条目集合，禁止手工增删，需与内核同步。

STATEMENT_STARTERS: List[str] = [
    "IF", "SIF", "SELECTCASE", "FOR", "WHILE", "DO", "REPEAT",
    "CALL", "TRYCALL", "CALLFORM", "TRYCALLFORM", "TRYCCALLFORM",
    "TRYCALLLIST", "CALLFORMF", "TRYCALLFORMF",
    "RETURN", "RETURNF",
    "PRINT", "PRINTL", "PRINTW", "PRINTDL", "PRINTV", "PRINTVL", "PRINTSL",
    "PRINTFORM", "PRINTFORML", "PRINTFORMW", "PRINTFORMC", "PRINTFORMLC",
    "PRINTFORMDC", "PRINTFORMD", "PRINTFORMDL", "PRINTFORMDW", "PRINTFORMS",
    "PRINTDATA", "PRINTDATAL", "DATALIST", "DATAFORM",
    "INPUT", "INPUTS", "ONEINPUT", "ONEINPUTS", "TINPUT", "TINPUTS",
    "TONEINPUT", "TONEINPUTS",
    "GOTO", "LABEL", "TIMES", "THROW", "BEGIN",
    "VARSET", "INVERTBIT", "GETBIT", "SETBIT", "CLEARBIT",
    "ADDCHARA", "DELCHARA", "SAVEDATA", "LOADDATA", "LOADGLOBAL", "SAVEGLOBAL",
    "BREAK", "CONTINUE", "JUMP", "DOTRAIN",
    "WAIT", "TWAIT",
    "DRAWLINE", "DRAWLINEFORM", "CLEARLINE", "REDRAW", "CUSTOMDRAWLINE",
    "SETCOLOR", "RESETCOLOR", "PRINTBUTTON", "PRINTBUTTONC", "BAR",
    "RESTART", "COMMENT", "IF_DEBUG",
    "DEBUGPRINT", "DEBUGPRINTL", "DEBUGPRINTW",
    "DEBUGPRINTFORM", "DEBUGPRINTFORML", "DEBUGPRINTFORMW",
    "PRINTSINGLEFORM", "PRINTSINGLEFORMS",
    "PRINTPLAINFORM", "PRINTPLAIN", "HTML_PRINT", "ALIGNMENT",
    "GETTIME", "RESETDATA", "LOADGAME", "SAVEGAME", "SPLIT",
    "FONTSTYLE", "SETFONT", "SAVECHARA", "LOADCHARA",
    "STRLENFORMU", "STRLENFORM", "PUTFORM", "REUSELASTLINE",
    "PRINTSW", "SPRITEDISPOSE", "SKIPDISP", "SETBGCOLOR", "RESETBGCOLOR",
    "ARRAYCOPY", "SWAP", "ADDCOPYCHARA",
    "SETLINECOUNT", "GETLINECOUNT", "CHKSPEED",
]

# 已知“被识别但运行时无任何副作用”的语句（no-op）。
NOOP_STATEMENTS = frozenset({
    "COMMENT",    # 注释，无运行时作用
    "SKIPDISP",   # 跳过显示标记，无运行时作用
    "BEGIN",      # 块起始标记，无运行时作用
})


# ── 数据结构 ──

@dataclass
class InstructionEntry:
    """单条指令字典条目。"""
    mnemonic: str
    category: str = "语句指令"          # 高层归类：语句指令
    params: List[str] = field(default_factory=list)
    semantics: str = ""
    example: str = ""
    impl_status: str = IMPL_IMPLEMENTED  # 已实现/静默丢弃/复活候选/NOOP
    source_ref: str = ""
    notes: str = ""


@dataclass
class SyntaxEntry:
    """语法手册条目。"""
    topic: str
    content: str
    examples: List[str] = field(default_factory=list)
    differences: List[str] = field(default_factory=list)  # 与官方实现差异


@dataclass
class PatternEntry:
    """模式库条目。"""
    name: str
    description: str
    code_snippet: str
    involved_instructions: List[str] = field(default_factory=list)


# ── 知识库 ──

class KnowledgeBase:
    """
    知识库：管理指令字典、语法手册、模式库。

    端口：KnowledgeBase (L2 04 §13)
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.instructions: Dict[str, InstructionEntry] = {}
        self.syntax: List[SyntaxEntry] = []
        self.patterns: List[PatternEntry] = []

        self._load_data()

    # ── 加载 ──

    def _load_data(self):
        """加载知识数据；文件损坏时归一化为 KN-001 统一错误。"""
        dict_path = self.data_dir / "instructions.json"
        if dict_path.exists():
            try:
                with open(dict_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.instructions = {
                    item["mnemonic"]: InstructionEntry(**item) for item in data
                }
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise make_error(
                    KN_001, context={"path": str(dict_path), "error": str(exc)}
                )

        syntax_path = self.data_dir / "syntax.json"
        if syntax_path.exists():
            try:
                with open(syntax_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.syntax = [SyntaxEntry(**item) for item in data]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise make_error(
                    KN_001, context={"path": str(syntax_path), "error": str(exc)}
                )

        patterns_path = self.data_dir / "patterns.json"
        if patterns_path.exists():
            try:
                with open(patterns_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.patterns = [PatternEntry(**item) for item in data]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise make_error(
                    KN_001, context={"path": str(patterns_path), "error": str(exc)}
                )

    def _save_data(self):
        """保存知识数据。"""
        dict_path = self.data_dir / "instructions.json"
        with open(dict_path, "w", encoding="utf-8") as f:
            json.dump(
                [self._entry_to_dict(e) for e in self.instructions.values()],
                f, ensure_ascii=False, indent=2,
            )

        syntax_path = self.data_dir / "syntax.json"
        with open(syntax_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "topic": s.topic,
                        "content": s.content,
                        "examples": s.examples,
                        "differences": s.differences,
                    }
                    for s in self.syntax
                ],
                f, ensure_ascii=False, indent=2,
            )

        patterns_path = self.data_dir / "patterns.json"
        with open(patterns_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "name": p.name,
                        "description": p.description,
                        "code_snippet": p.code_snippet,
                        "involved_instructions": p.involved_instructions,
                    }
                    for p in self.patterns
                ],
                f, ensure_ascii=False, indent=2,
            )

    @staticmethod
    def _entry_to_dict(e: InstructionEntry) -> Dict[str, Any]:
        return {
            "mnemonic": e.mnemonic,
            "category": e.category,
            "params": e.params,
            "semantics": e.semantics,
            "example": e.example,
            "impl_status": e.impl_status,
            "source_ref": e.source_ref,
            "notes": e.notes,
        }

    # ── 维护 ──

    def rebuild(self):
        """
        以权威骨架重建指令字典并落盘。
        用于首次初始化或内核版本升级后同步。
        """
        self.instructions = generate_instruction_skeleton()
        self._save_data()
        return len(self.instructions)

    def add_syntax(self, entry: SyntaxEntry):
        self.syntax.append(entry)
        self._save_data()

    def add_pattern(self, entry: PatternEntry):
        self.patterns.append(entry)
        self._save_data()

    # ── 检索 ──

    def search(self, query: str, category: Optional[str] = None,
               impl_status: Optional[str] = None) -> List[InstructionEntry]:
        return kb_search(self, query, category, impl_status)

    def lookup(self, mnemonic: str) -> Optional[InstructionEntry]:
        return kb_lookup(self, mnemonic)


# ── 指令字典骨架生成 ──

def _classify_impl_status(mnemonic: str) -> str:
    """
    依据 P2 账本仲裁结果对单条语句指令归类。

    优先级：NOOP（无副作用） > 复活候选 > 静默丢弃 > 已实现（默认）。
    """
    if mnemonic in NOOP_STATEMENTS:
        return IMPL_NOOP
    if mnemonic in COMMAND_REVIVAL_CANDIDATES:
        return IMPL_REVIVAL
    if mnemonic in COMMAND_TYPE_GAPS:
        return IMPL_SILENT_DROP
    return IMPL_IMPLEMENTED


def generate_instruction_skeleton() -> Dict[str, InstructionEntry]:
    """
    从内核语法分析器语句集合生成指令条目骨架，覆盖全部 117 条语句指令。

    端口：generate_instruction_skeleton (L2 04 §13)

    返回：以 mnemonic 为键的指令条目字典，长度恒为 117。
    """
    try:
        entries: Dict[str, InstructionEntry] = {}
        for mnemonic in STATEMENT_STARTERS:
            entries[mnemonic] = InstructionEntry(
                mnemonic=mnemonic,
                category="语句指令",
                impl_status=_classify_impl_status(mnemonic),
                source_ref="core/parser.py::_STATEMENT_STARTERS",
            )
        if len(entries) != len(STATEMENT_STARTERS):
            # STATEMENT_STARTERS 内部出现重复，属于知识库自身 bug
            raise make_error(
                KN_003,
                context={"unique": len(entries), "declared": len(STATEMENT_STARTERS)},
            )
        return entries
    except EmueraError:
        raise
    except Exception as exc:  # pragma: no cover
        raise make_error(KN_003, context={"error": str(exc)})


# ── 实现状态回写 ──

def sync_ledger(kb: KnowledgeBase, ledger: GapLedger) -> int:
    """
    把 P2 缺口账本的实现状态映射回指令字典。

    映射规则：
      - severity == medium                       -> 静默丢弃
      - severity == info 且 revival_candidate    -> 复活候选
      - title 含 "NOOP"                          -> NOOP
      - 其余 implementation 类缺口默认            -> 静默丢弃
    不在字典中的 keyword 将被跳过。

    端口：sync_ledger (L2 04 §13)

    返回：成功回写的条目数。
    """
    if kb is None or ledger is None:
        raise make_error(KN_002, context={"kb": kb is not None, "ledger": ledger is not None})

    updated_count = 0
    for gap in ledger.gaps:
        if gap.category != GapCategory.IMPLEMENTATION:
            continue

        keyword = (gap.evidence or {}).get("keyword")
        if not keyword or keyword not in kb.instructions:
            continue

        entry = kb.instructions[keyword]
        new_status = None

        if "NOOP" in (gap.title or "").upper():
            new_status = IMPL_NOOP
        elif gap.severity == GapSeverity.INFO and (gap.evidence or {}).get("revival_candidate"):
            new_status = IMPL_REVIVAL
        elif gap.severity == GapSeverity.MEDIUM:
            new_status = IMPL_SILENT_DROP
        elif gap.category == GapCategory.IMPLEMENTATION:
            # implementation 类缺口缺省视为静默丢弃
            new_status = IMPL_SILENT_DROP

        if new_status is not None and entry.impl_status != new_status:
            entry.impl_status = new_status
            updated_count += 1

    if updated_count:
        kb._save_data()

    return updated_count


# ── 检索接口 ──

def kb_search(
    kb: KnowledgeBase,
    query: str,
    category: Optional[str] = None,
    impl_status: Optional[str] = None,
) -> List[InstructionEntry]:
    """
    按关键词检索指令（mnemonic / semantics / notes 模糊匹配）。

    端口：kb_search (L2 04 §13)
    """
    results: List[InstructionEntry] = []
    query_lower = (query or "").lower()

    for entry in kb.instructions.values():
        if category and entry.category != category:
            continue
        if impl_status and entry.impl_status != impl_status:
            continue
        if query_lower and not (
            query_lower in entry.mnemonic.lower()
            or query_lower in entry.semantics.lower()
            or query_lower in entry.notes.lower()
        ):
            continue
        results.append(entry)

    return results


def kb_lookup(kb: KnowledgeBase, mnemonic: str) -> Optional[InstructionEntry]:
    """
    按助记符精确检索单条指令（O(1) 字典查找）。

    端口：kb_lookup (L2 04 §13)
    """
    if mnemonic is None:
        return None
    return kb.instructions.get(mnemonic.upper())
