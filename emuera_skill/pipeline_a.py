"""
P-A 管线：工程摄取与快照。
串联 kernel-bridge + ingestion，产出可复用的工程快照 + 文档索引。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from .kernel_bridge.engine import assemble_engine, capture_snapshot, compute_fingerprint, Snapshot, EngineHandle
    from .ingestion.directory import probe_structure, ingest_directory, DirectoryIndex, check_encoding_convention
    from .output_dir import resolve_output_dir
    from .config_loader import load_config, Config
    from .errors import make_error, KB_003
except ImportError:
    from kernel_bridge.engine import assemble_engine, capture_snapshot, compute_fingerprint, Snapshot, EngineHandle
    from ingestion.directory import probe_structure, ingest_directory, DirectoryIndex, check_encoding_convention
    from output_dir import resolve_output_dir
    from config_loader import load_config, Config
    from errors import make_error, KB_003


def run_pipeline_a(
    game_dir: str,
    config: Optional[Config] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    执行 P-A 管线。

    步骤：
    1. 计算指纹
    2. 检查缓存（指纹命中且非强制刷新 → 直接加载）
    3. 结构探测
    4. 引擎装配
    5. 快照抓取
    6. 文档摄取
    7. 序列化落盘
    8. 返回摘要

    返回：包含 snapshot_path, index_path, summary 的字典
    """
    if config is None:
        config = load_config()

    t0 = time.time()

    # 1. 计算指纹
    fingerprint = compute_fingerprint(game_dir)

    # 1.5 编码约定检查（BOM 合规）——与缓存无关，始终执行
    violations = check_encoding_convention(game_dir)
    encoding_convention = {
        "ok": len(violations) == 0,
        "code": None if not violations else "IN-102",
        "violation_count": len(violations),
        "violations": violations,
    }
    if violations:
        print(f"[WARN] 编码约定违规 {len(violations)} 项（IN-102）：非 ASCII 脚本缺 UTF-8 BOM，实机将按 Shift-JIS 解析")

    # 2. 缓存判定
    output_dir = resolve_output_dir(fingerprint, config.output_root)
    snapshot_path = output_dir / "snapshot" / "snapshot.json"

    if not force_refresh and snapshot_path.exists():
        # 缓存命中，直接加载
        with open(snapshot_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        elapsed = time.time() - t0
        return {
            "fingerprint": fingerprint,
            "snapshot_path": str(snapshot_path),
            "cached": True,
            "elapsed_sec": elapsed,
            "encoding_convention": encoding_convention,
            "summary": {
                "functions": cached.get("function_count", 0),
                "variables": cached.get("variable_count", 0),
                "parse_errors": len(cached.get("parse_errors") or []),
                "encoding_violations": len(violations),
            },
        }

    # 3. 结构探测
    probe_structure(game_dir)

    # 4. 引擎装配
    handle = assemble_engine(game_dir)

    # 5. 快照抓取
    snapshot = capture_snapshot(handle)
    snapshot.fingerprint = fingerprint

    # 6. 文档摄取
    index = ingest_directory(game_dir)

    # 7. 序列化落盘
    snapshot_data = {
        "fingerprint": fingerprint,
        "game_dir": game_dir,
        "function_count": len(snapshot.functions),
        "variable_count": len(snapshot.variables),
        "parse_errors": snapshot.parse_errors,
        "semantic_warnings": snapshot.semantic_warnings,
        "programs_count": snapshot.programs_count,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

    # 保存索引
    index_path = output_dir / "snapshot" / "index.json"
    index_data = {
        "files_count": len(index.files),
        "scripts": index.scripts,
        "csv_tables": index.csv_tables,
        "file_types": {},
    }
    for doc in index.files:
        t = doc.type
        index_data["file_types"][t] = index_data["file_types"].get(t, 0) + 1
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    return {
        "fingerprint": fingerprint,
        "snapshot_path": str(snapshot_path),
        "index_path": str(index_path),
        "cached": False,
        "elapsed_sec": elapsed,
        "encoding_convention": encoding_convention,
        "summary": {
            "functions": len(snapshot.functions),
            "variables": len(snapshot.variables),
            "parse_errors": len(snapshot.parse_errors),
            "files": len(index.files),
            "scripts": len(index.scripts),
            "csv_tables": len(index.csv_tables),
            "encoding_violations": len(violations),
        },
    }
