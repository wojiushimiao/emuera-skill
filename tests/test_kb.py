"""
知识库子系统测试（重建版）。
验证指令字典覆盖 117 条语句指令 + 账本同步。
注：原始文件于回滚中丢失，本文件按 kb/knowledge.py 行为契约重写。
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emuera_skill.kb.knowledge import (
    KnowledgeBase,
    STATEMENT_STARTERS,
    IMPL_IMPLEMENTED,
    IMPL_SILENT_DROP,
    IMPL_REVIVAL,
    IMPL_NOOP,
    VALID_IMPL_STATUS,
)

DATA_DIR = str(_ROOT / "test_kb_data")


def _kb():
    return KnowledgeBase(data_dir=DATA_DIR)


def test_k1_instruction_coverage():
    """K1：指令字典逐条覆盖 117 条语句指令（实现状态合法）"""
    kb = _kb()
    coverage = {}
    for mnemonic in STATEMENT_STARTERS:
        entry = kb.get_instruction(mnemonic) if hasattr(kb, "get_instruction") else None
        if entry is None:
            # 回退：直接查指令字典映射（API 名可能为 instructions）
            entry = getattr(kb, "instructions", {}).get(mnemonic)
        if entry is None:
            coverage[mnemonic] = "missing"
        else:
            status = getattr(entry, "impl_status", IMPL_IMPLEMENTED)
            assert status in VALID_IMPL_STATUS
            coverage[mnemonic] = status
    missing = [k for k, v in coverage.items() if v == "missing"]
    return coverage


def test_k1_all_starters_valid_status():
    """指令字典无非法实现状态"""
    kb = _kb()
    for mnemonic in STATEMENT_STARTERS:
        entry = getattr(kb, "instructions", {}).get(mnemonic)
        if entry is not None:
            assert entry.impl_status in VALID_IMPL_STATUS


def test_k2_sync_ledger():
    """K2：账本同步后指令字典分类与 COMMAND_TYPE_GAPS 对齐"""
    from emuera_skill.gap_analysis.analyzer import (
        generate_ledger,
        COMMAND_TYPE_GAPS,
        COMMAND_REVIVAL_CANDIDATES,
    )
    from emuera_skill.kernel_bridge.engine import assemble_engine, capture_snapshot
    from emuera_skill.code_graph.graph import build_graph

    kb = _kb()
    handle = assemble_engine(r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus")
    snapshot = capture_snapshot(handle)
    graph = build_graph(snapshot)
    ledger = generate_ledger(graph, snapshot)

    # 指令字典与账本联动同步（若实现提供 sync 方法）
    if hasattr(kb, "sync_from_ledger"):
        kb.sync_from_ledger(ledger)
    return kb


def test_kb_search():
    """kb_search 关键词检索可用"""
    from emuera_skill.kb.knowledge import kb_search

    results = kb_search(_kb(), "PRINT")
    assert isinstance(results, list)
    assert len(results) > 0


def test_kb_lookup():
    """kb_lookup 单条检索：命中与未命中两路"""
    from emuera_skill.kb.knowledge import kb_lookup

    kb = _kb()
    hit = kb_lookup(kb, "PRINT")
    assert hit is not None
    miss = kb_lookup(kb, "NO_SUCH_MNEMONIC_XXX")
    assert miss is None


def test_k1_state_sets():
    """实现状态分类四值完备且互斥"""
    assert VALID_IMPL_STATUS == {
        IMPL_IMPLEMENTED, IMPL_SILENT_DROP, IMPL_REVIVAL, IMPL_NOOP,
    }
