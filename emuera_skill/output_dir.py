"""
输出根目录管理器。
resolve_output_dir(fingerprint) 按 <输出根>/<指纹前8位>/ 建分区。
"""

import os
from pathlib import Path
from typing import Optional


# 六个标准子目录（对齐 L2 00 §5.2）
_SUBDIRS = ["snapshot", "graph", "reports", "drafts", "saves", "logs"]


def resolve_output_dir(
    fingerprint: str,
    output_root: str = "./emuera-skill-out",
) -> Path:
    """
    解析输出目录路径。
    按 <output_root>/<fingerprint[:8]>/ 建分区，
    自动创建六个标准子目录。
    """
    dir_name = fingerprint[:8] if len(fingerprint) >= 8 else fingerprint
    base = Path(output_root) / dir_name
    base.mkdir(parents=True, exist_ok=True)

    for subdir in _SUBDIRS:
        (base / subdir).mkdir(exist_ok=True)

    return base


def get_output_path(output_dir: str, filename: str) -> str:
    """获取输出文件完整路径"""
    return str(Path(output_dir) / filename)


def ensure_output_dir(output_root: str, fingerprint: str) -> str:
    """确保输出目录存在并返回路径"""
    return str(resolve_output_dir(fingerprint, output_root))
