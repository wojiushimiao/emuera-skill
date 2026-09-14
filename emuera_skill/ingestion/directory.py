"""
文档摄取子系统。
负责把 Emuera 游戏目录读干净并建立索引。
包含：结构探测、编码探测、文档枚举、内容规整、文档索引。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..errors import make_error, IN_101, IN_102
except ImportError:
    from errors import make_error, IN_101, IN_102


@dataclass
class Document:
    """文档条目"""
    path: str
    type: str  # script/macro/data/config/docs
    encoding: str
    size: int
    content: Optional[str] = None


@dataclass
class StructureReport:
    """结构探测报告"""
    layout: str
    game_type: str
    missing: List[str]


@dataclass
class DirectoryIndex:
    """目录索引"""
    files: List[Document]
    scripts: List[str]
    csv_tables: List[str]
    roles: List[str]
    names: List[str]


# ── 编码探测（四档回退） ──

ENCODING_FALLBACK = ["utf-8-sig", "utf-8", "shift_jis", "gbk"]


def detect_encoding(file_path: str) -> Tuple[str, bool]:
    """
    四档编码回退探测。
    返回 (encoding, success)
    """
    for enc in ENCODING_FALLBACK:
        try:
            with open(file_path, "r", encoding=enc) as f:
                f.read(4096)  # 试读前 4KB
            return enc, True
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "", False


# ── 结构探测 ──

def probe_structure(game_dir: str) -> StructureReport:
    """
    判定工程布局与类型。

    端口：probe_structure (L2 04 §3)
    """
    game_path = Path(game_dir)
    if not game_path.exists():
        raise make_error(IN_101, context=f"目录不存在: {game_dir}")

    missing = []
    has_erb = (game_path / "ERB").is_dir() if (game_path / "ERB").exists() else False
    has_csv = (game_path / "CSV").is_dir() if (game_path / "CSV").exists() else False

    if not has_erb:
        missing.append("ERB")
    if not has_csv:
        missing.append("CSV")

    if missing:
        raise make_error(IN_101, context=f"缺失关键子目录: {missing}")

    # 判定游戏类型
    game_type = "unknown"
    if has_erb and has_csv:
        game_type = "era_standard"

    return StructureReport(
        layout="standard",
        game_type=game_type,
        missing=missing,
    )


# ── 文档枚举 ──

def _classify_file(ext: str) -> str:
    """按后缀分类文件"""
    ext = ext.lower()
    if ext in (".erb",):
        return "script"
    elif ext in (".csv",):
        return "data"
    elif ext in (".yaml", ".yml", ".json", ".ini", ".cfg", ".conf"):
        return "config"
    elif ext in (".txt", ".md", ".rst"):
        return "docs"
    return "other"


def ingest_directory(game_dir: str) -> DirectoryIndex:
    """
    枚举并分类全部文件，逐文件编码探测。

    端口：ingest_directory (L2 04 §3)
    """
    game_path = Path(game_dir)
    files = []
    scripts = []
    csv_tables = []
    failed = []

    for root, dirs, filenames in os.walk(game_path):
        for fname in filenames:
            fpath = Path(root) / fname
            ext = fpath.suffix
            file_type = _classify_file(ext)

            # 编码探测
            encoding, success = detect_encoding(str(fpath))
            if not success:
                failed.append(str(fpath))
                continue

            doc = Document(
                path=str(fpath.relative_to(game_path)),
                type=file_type,
                encoding=encoding,
                size=fpath.stat().st_size,
            )
            files.append(doc)

            if file_type == "script":
                scripts.append(doc.path)
            elif file_type == "data" and ext == ".csv":
                csv_tables.append(doc.path)

    # 失败率检查（L1 §2.2 步骤2）
    total = len(files) + len(failed)
    if total > 0 and len(failed) / total > 0.01:
        # 告警但不中断
        print(f"[WARN] 编码探测失败率 {len(failed)/total*100:.1f}%（>{1}% 阈值）")

    return DirectoryIndex(
        files=files,
        scripts=scripts,
        csv_tables=csv_tables,
        roles=[],  # 后续从数据字典填充
        names=[],  # 后续从数据字典填充
    )


# ── 编码约定检查（P-A） ──

# 受检脚本/数据类后缀：Emuera 依 BOM 判定 UTF-8，无 BOM 的非 ASCII 文件会被按
# Shift-JIS 解析，导致字符串常量乱码、条件分支失配并抛脚本错误。
_BOM_EXTENSIONS = (".erb", ".erh", ".erd", ".csv")


def check_encoding_convention(game_dir: str) -> List[Dict[str, Any]]:
    """
    编码约定检查：非 ASCII 的脚本/数据文件必须带 UTF-8 BOM。

    判定依据：真实 Emuera（如 Emuera1821 cn v8）以 BOM 选择解码器——
    有 BOM 走 UTF-8，无 BOM 回退 Shift-JIS；而内核侧四档编码回退
    （utf-8-sig/utf-8/shift_jis/gb18030）对无 BOM 的 UTF-8 文件依然解码正确，
    故此类缺陷在静态体检中静默，只在实机运行期爆出。

    端口：check_encoding_convention (L2 04 §3)

    返回：违规清单 [{"path", "reason", "non_ascii_bytes"}]
    """
    game_path = Path(game_dir)
    if not game_path.exists():
        raise make_error(IN_101, context=f"目录不存在: {game_dir}")

    violations: List[Dict[str, Any]] = []
    for root, dirs, filenames in os.walk(game_path):
        for fname in filenames:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in _BOM_EXTENSIONS:
                continue
            try:
                with open(fpath, "rb") as fh:
                    head = fh.read(3)
                    if head == b"\xef\xbb\xbf":
                        continue  # 已带 UTF-8 BOM，合规
                    body = fh.read()
            except OSError:
                continue

            non_ascii = sum(1 for b in body if b > 0x7F)
            if non_ascii:
                violations.append({
                    "path": str(fpath.relative_to(game_path)),
                    "reason": "非 ASCII 脚本/数据文件缺 UTF-8 BOM（实机将按 Shift-JIS 解析）",
                    "non_ascii_bytes": non_ascii,
                })

    return violations


# ── 文档查询 ──

def get_document(index: DirectoryIndex, path: str) -> Optional[Document]:
    """按路径获取文档"""
    for doc in index.files:
        if doc.path == path:
            return doc
    return None


def query_index(index: DirectoryIndex, field: str, value: str) -> List[Document]:
    """按字段查询文档"""
    results = []
    for doc in index.files:
        if field == "path" and value in doc.path:
            results.append(doc)
        elif field == "type" and doc.type == value:
            results.append(doc)
        elif field == "encoding" and doc.encoding == value:
            results.append(doc)
    return results
