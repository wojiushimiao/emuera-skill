"""
内核桥接子系统。
封装解释器内核的装配、初始化、快照抓取与指纹计算。
只使用内核公开接缝，不 import 未公开模块（D1）。
"""

import sys
import os
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# 内核路径解析：优先部署包内 kernel/src/，回退原工程路径
# 部署包：emuera_skill/kernel_bridge/engine.py → parent.parent.parent / kernel / src
# 开发版：src/kernel_bridge/engine.py → parent.parent.parent.parent / era红魔馆NTRplusplus/解释器/src
#
# 注意：内核内部使用 `from src.engine import ...` 与 `from .core.xxx` 相对导入，
# 因此必须把 src 的**父目录**加入 sys.path，使 src 成为可导入包，
# 否则 engine.py 的相对导入会因"无父包"而失败。
_pkg_root = Path(__file__).parent.parent.parent
_release_kernel = _pkg_root / "kernel" / "src"
if _release_kernel.is_dir() and (_release_kernel / "engine.py").exists():
    _kernel_src = _release_kernel
else:
    _kernel_src = _pkg_root.parent / "era红魔馆NTRplusplus" / "解释器" / "src"

# src 的父目录（使 src 成为包，支撑 from src.engine import ...）
_kernel_parent = _kernel_src.parent
if str(_kernel_parent) not in sys.path:
    sys.path.insert(0, str(_kernel_parent))

# 备份：src 本身（兼容直接以顶层模块方式导入的场景）
if str(_kernel_src) not in sys.path:
    sys.path.insert(0, str(_kernel_src))

try:
    from ..errors import make_error, KB_001, KB_003
except ImportError:
    from errors import make_error, KB_001, KB_003


@dataclass
class EngineHandle:
    """引擎句柄，包含已装配的引擎实例与元数据"""
    engine: Any
    metadata: Dict[str, Any]


@dataclass
class Snapshot:
    """工程快照，包含内核初始化产物"""
    fingerprint: str
    functions: Dict[str, Any]
    variables: Dict[str, Any]
    parse_errors: List[str]
    semantic_warnings: List[str]
    data_dictionary: Dict[str, Any]
    macro_table: Dict[str, Any]
    programs_count: int
    game_dir: str


def assemble_engine(game_dir: str) -> EngineHandle:
    """
    装配引擎。
    按内核实际初始化顺序：实例化 → 初始化。
    只调用 ERBEngine 公开方法。

    端口：assemble_engine (L2 04 §2)
    """
    game_path = Path(game_dir)
    if not game_path.exists():
        raise make_error(KB_001, context=f"游戏目录不存在: {game_dir}")

    # 导入内核公开类
    try:
        from src.engine import ERBEngine
    except ImportError:
        from engine import ERBEngine

    try:
        # 实例化引擎
        engine = ERBEngine(game_dir)

        # 执行初始化（加载 CSV、解析 ERB、注册函数）
        engine.initialize()

        # 收集元数据
        metadata = {
            "game_dir": game_dir,
            "function_count": len(engine.function_dispatch._functions) if engine.function_dispatch else 0,
            "program_count": len(engine._programs) if hasattr(engine, '_programs') else 0,
            "parse_error_count": len(engine._parse_errors) if hasattr(engine, '_parse_errors') else 0,
            "variable_count": len(engine.variable_mgr._descriptors) if engine.variable_mgr else 0,
        }

        return EngineHandle(engine=engine, metadata=metadata)

    except Exception as e:
        raise make_error(KB_003, context=f"装配失败: {e}")


def capture_snapshot(handle: EngineHandle) -> Snapshot:
    """
    抓取快照。
    纯读取，不改引擎状态。

    端口：capture_snapshot (L2 04 §2)
    """
    engine = handle.engine

    # 抓取函数表
    functions = {}
    if engine.function_dispatch:
        for name, desc in engine.function_dispatch._functions.items():
            functions[name] = {
                "name": name,
                "file": getattr(desc, 'file', None),
                "line": getattr(desc, 'line', None),
                "param_count": getattr(desc, 'param_count', 0),
            }

    # 抓取变量描述符表
    variables = {}
    if engine.variable_mgr:
        for name, desc in engine.variable_mgr._descriptors.items():
            variables[name] = {
                "name": name,
                "type": getattr(desc, 'type', None),
                "size": getattr(desc, 'default_size', None),
                "has_name_map": bool(getattr(desc, 'name_map', None)),
            }

    # 抓取解析错误
    parse_errors = list(engine._parse_errors) if hasattr(engine, '_parse_errors') else []

    # 语义告警（从监控事件中提取）
    semantic_warnings = []
    if hasattr(engine, '_monitor_events'):
        for event in engine._monitor_events:
            if hasattr(event, 'category') and event.category == "WARNING":
                semantic_warnings.append(event.message)

    # 数据字典
    data_dictionary = {}
    if engine.csv_loader:
        data_dictionary = {
            "name_maps": list(engine.csv_loader.name_maps.keys()) if hasattr(engine.csv_loader, 'name_maps') else [],
            "variable_sizes": list(engine.csv_loader.variable_sizes.keys()) if hasattr(engine.csv_loader, 'variable_sizes') else [],
        }

    # 宏表（从 ERH 处理结果中提取）
    macro_table = {}
    if engine.erh_processor and hasattr(engine.erh_processor, '_macros'):
        macro_table = dict(engine.erh_processor._macros)

    return Snapshot(
        fingerprint="",  # 后续填充
        functions=functions,
        variables=variables,
        parse_errors=parse_errors,
        semantic_warnings=semantic_warnings,
        data_dictionary=data_dictionary,
        macro_table=macro_table,
        programs_count=handle.metadata.get("program_count", 0),
        game_dir=handle.metadata.get("game_dir", ""),
    )


def compute_fingerprint(game_dir: str) -> str:
    """
    计算工程指纹。
    收集全部 .ERB/.csv/配置文件相对路径 + 内容全量摘要，排序后整体哈希。

    端口：compute_fingerprint (L2 04 §2)

    注意：必须哈希文件全量内容。早期实现只读前 1KB，导致超过 1KB 之后的改动
    不改变指纹，从而命中陈旧快照/图谱（表现为 scan 报旧数据、图谱缺新函数）。
    """
    game_path = Path(game_dir)
    if not game_path.exists():
        raise make_error(KB_001, context=f"游戏目录不存在: {game_dir}")

    files = []
    for ext in ["*.ERB", "*.erb", "*.csv", "*.TXT", "*.txt", "*.yaml", "*.yml", "*.json"]:
        for f in game_path.rglob(ext):
            if f.is_file():
                try:
                    # 全量内容哈希（分块读取，避免大文件一次性载入内存）
                    digest = hashlib.md5()
                    with open(f, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            digest.update(chunk)
                    rel_path = str(f.relative_to(game_path))
                    files.append(f"{rel_path}:{digest.hexdigest()}")
                except Exception:
                    pass

    # 排序后整体哈希
    files.sort()
    combined = "|".join(files)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]
