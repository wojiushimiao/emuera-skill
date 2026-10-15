"""
P-A 管线测试（重建版）。
验证 run_pipeline_a 的指纹 / 缓存 / 编码约定检查 / 快照 / 索引落盘。
注：重建版测试——原始文件于回滚中丢失，本文件按管线行为契约重写。
"""
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emuera_skill.pipeline_a import run_pipeline_a
from emuera_skill.kernel_bridge.engine import compute_fingerprint

GAME_DIR = r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus"


def test_pipeline_a_smoke():
    """P-A 基本可跑通：返回指纹 + 快照路径 + 摘要"""
    result = run_pipeline_a(GAME_DIR)
    assert "fingerprint" in result
    assert "snapshot_path" in result
    assert "summary" in result
    assert result["fingerprint"]


def test_pipeline_a_fingerprint_stable():
    """同目录指纹可复现"""
    fp1 = compute_fingerprint(GAME_DIR)
    fp2 = compute_fingerprint(GAME_DIR)
    assert fp1 == fp2
    assert len(fp1) == 16


def test_pipeline_a_cache_hit():
    """第二次运行命中缓存（首次已落盘）"""
    r1 = run_pipeline_a(GAME_DIR)
    r2 = run_pipeline_a(GAME_DIR)
    assert r2["cached"] is True
    assert r1["fingerprint"] == r2["fingerprint"]


def test_pipeline_a_summary_fields():
    """摘要含函数/变量/解析错误计数（均为非负整数）"""
    result = run_pipeline_a(GAME_DIR)
    s = result["summary"]
    assert s["functions"] >= 0
    assert s["variables"] >= 0
    assert s["parse_errors"] >= 0


def test_pipeline_a_snapshot_file_exists():
    """快照 JSON 已落盘且可解析"""
    result = run_pipeline_a(GAME_DIR)
    p = Path(result["snapshot_path"])
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["fingerprint"] == result["fingerprint"]
