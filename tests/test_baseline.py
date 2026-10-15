"""
P0 K3: 内核零侵入守护（R-E2 重写：哈希快照硬校验，不依赖 git）。

机制：
- 首次运行：对解释器目录做全量文件清单 + SHA-256 快照，落基线 JSON（tests/.kernel_baseline.json）。
- 后续运行：重算快照与基线逐文件比对，任何新增/删除/内容变化都判定 B1 零侵入违规并 FAIL。
- 内核目录不存在时用 pytest.skip 显式跳过（禁止伪通过）。
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

# 内核路径（相对于 emuera-skill 工作目录）
KERNEL_DIR = Path(__file__).parent.parent / "kernel"
BASELINE_PATH = Path(__file__).parent / ".kernel_baseline.json"

# 忽略 Python 运行时产物（__pycache__ 等），它们不是内核源码变更
IGNORE_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}
IGNORE_SUFFIXES = {".pyc", ".pyo"}


def _snapshot_kernel() -> dict:
    """对内核目录做全量文件 → SHA-256 快照。"""
    snap = {}
    for p in sorted(KERNEL_DIR.rglob("*")):
        if not p.is_file():
            continue
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in IGNORE_SUFFIXES:
            continue
        rel = str(p.relative_to(KERNEL_DIR))
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        snap[rel] = h.hexdigest()
    return snap


def test_kernel_zero_invasion():
    """断言解释器目录与哈希基线完全一致（B1 零侵入的自动化取证）"""
    if not KERNEL_DIR.exists():
        pytest.skip(f"内核目录不存在: {KERNEL_DIR}")

    current = _snapshot_kernel()
    assert len(current) > 0, "内核快照为空，目录可能为空"

    if not BASELINE_PATH.exists():
        # 首次运行：落基线并放行（此时无法判断历史，但从现在起有据可查）
        BASELINE_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=0, sort_keys=True),
            encoding="utf-8",
        )
        print(f"[BASELINE] 首次建立内核基线: {len(current)} 个文件")
        return

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    changed = sorted(k for k in set(current) & set(baseline) if current[k] != baseline[k])

    violations = []
    if added:
        violations.append("新增文件:\n  " + "\n  ".join(added[:10]))
    if removed:
        violations.append("删除文件:\n  " + "\n  ".join(removed[:10]))
    if changed:
        violations.append("内容变更:\n  " + "\n  ".join(changed[:10]))

    assert not violations, (
        "解释器目录存在基线外变更（B1 零侵入违规）:\n" + "\n".join(violations)
    )


if __name__ == "__main__":
    try:
        test_kernel_zero_invasion()
        print("✓ 内核零侵入检查通过")
    except AssertionError as e:
        print(f"✗ 内核零侵入违规:\n{e}")
        sys.exit(1)
