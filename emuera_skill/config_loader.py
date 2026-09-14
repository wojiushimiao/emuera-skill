"""
配置加载器。
读 default.yaml → 命令行覆盖 → 校验取值 → 分发。
对应端口 load_config，KB-010 失败回退最小默认值。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .errors import make_error, KB_010
except ImportError:
    from errors import make_error, KB_010


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.yaml"


@dataclass
class Config:
    """配置结构，对齐 COMMON §2.4"""
    encoding_fallback: List[str] = field(default_factory=lambda: ["utf-8", "shift-jis", "gbk"])
    run_timeout_s: int = 60
    output_root: str = "./emuera-skill-out"
    default_input: str = ""
    render_text_len: int = 2000


# 最小默认值（KB-010 回退用）
_MINIMAL_DEFAULTS = Config()


def _load_yaml(path: Path) -> Dict[str, Any]:
    """简易 YAML 解析（仅支持 COMMON §2.4 的五个字段，不引入第三方依赖）"""
    text = path.read_text(encoding="utf-8")
    result: Dict[str, Any] = {}
    current_key = None
    current_list: Optional[List[str]] = None

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            # 列表项
            if current_list is not None:
                current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue

        if ":" in stripped:
            parts = stripped.split(":", 1)
            key = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ""

            # 结束上一个列表
            if current_list is not None:
                result[current_key] = current_list
                current_list = None

            if value.startswith("["):
                # 内联列表
                items = value.strip("[]").split(",")
                result[key] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
            elif value.startswith('"') or value.startswith("'"):
                result[key] = value.strip('"').strip("'")
            elif value.replace(".", "", 1).isdigit():
                result[key] = int(value) if "." not in value else float(value)
            elif value == "true":
                result[key] = True
            elif value == "false":
                result[key] = False
            elif value == "":
                # 可能是列表的开始（下一行有 - ）
                current_key = key
                current_list = []
            else:
                result[key] = value

    # 收尾最后一个列表
    if current_list is not None:
        result[current_key] = current_list

    return result


def load_config(
    config_path: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Config:
    """
    加载配置。
    1. 读 default.yaml（或指定路径）
    2. 应用命令行覆盖
    3. 校验取值
    4. 返回 Config 实例

    KB-010 失败时回退最小默认值并标注。
    """
    raw: Dict[str, Any] = {}

    # 1. 读取 YAML
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    try:
        if path.exists():
            raw = _load_yaml(path)
        else:
            # 文件不存在，用最小默认值
            return Config()
    except Exception:
        raise make_error(KB_010, context=f"路径: {path}", recoverable=True)

    # 2. 应用覆盖
    if overrides:
        raw.update(overrides)

    # 3. 校验并构建 Config
    config = Config()
    if "encoding_fallback" in raw:
        config.encoding_fallback = raw["encoding_fallback"]
    if "run_timeout_s" in raw:
        val = raw["run_timeout_s"]
        if isinstance(val, (int, float)) and val > 0:
            config.run_timeout_s = int(val)
    if "output_root" in raw:
        config.output_root = str(raw["output_root"])
    if "default_input" in raw:
        config.default_input = str(raw["default_input"])
    if "render_text_len" in raw:
        val = raw["render_text_len"]
        if isinstance(val, (int, float)) and val > 0:
            config.render_text_len = int(val)

    return config
