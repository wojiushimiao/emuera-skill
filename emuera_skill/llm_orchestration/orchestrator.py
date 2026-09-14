"""
模型编排子系统。
上下文压缩 → 提示编排 → 契约校验 → 降级兜底链路。
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from ..errors import make_error, LL_801, EmueraError
except ImportError:
    from errors import make_error, LL_801, EmueraError


# ── 数据结构 ──

@dataclass
class PromptTemplate:
    """提示模板"""
    name: str
    version: str
    content: str
    variables: List[str] = field(default_factory=list)


@dataclass
class CompressedContext:
    """压缩后的上下文"""
    original_length: int
    compressed_length: int
    compression_ratio: float
    content: str
    dropped_sections: List[str] = field(default_factory=list)


@dataclass
class ModelOutput:
    """模型输出"""
    raw: str
    parsed: Optional[Dict[str, Any]] = None
    valid: bool = False
    error: Optional[str] = None
    error_code: Optional[str] = None          # 归一化错误码，如 "801" (LL-801)
    error_obj: Optional[EmueraError] = None     # 统一错误结构


# ── 上下文压缩 ──

def compress_context(
    context: Dict[str, Any],
    budget: int = 2000,
    priority_keys: Optional[List[str]] = None,
) -> CompressedContext:
    """
    按预算裁剪角色/阶段/变量变化/近期事件。
    标注裁剪比例与已丢弃内容。

    端口：compress_context (L2 04 §10)
    """
    if priority_keys is None:
        priority_keys = ["stage", "variables", "recent_events", "characters"]

    # 序列化完整上下文
    full_content = json.dumps(context, ensure_ascii=False, indent=2)
    original_length = len(full_content)

    if original_length <= budget:
        return CompressedContext(
            original_length=original_length,
            compressed_length=original_length,
            compression_ratio=1.0,
            content=full_content,
            dropped_sections=[],
        )

    # 按优先级裁剪
    compressed = {}
    dropped = []
    current_length = 0

    for key in priority_keys:
        if key in context:
            section = json.dumps({key: context[key]}, ensure_ascii=False)
            if current_length + len(section) <= budget * 0.8:
                compressed[key] = context[key]
                current_length += len(section)
            else:
                dropped.append(key)

    # 补充其他键
    for key, value in context.items():
        if key not in compressed and key not in dropped:
            section = json.dumps({key: value}, ensure_ascii=False)
            if current_length + len(section) <= budget * 0.9:
                compressed[key] = value
                current_length += len(section)
            else:
                dropped.append(key)

    compressed_content = json.dumps(compressed, ensure_ascii=False, indent=2)

    return CompressedContext(
        original_length=original_length,
        compressed_length=len(compressed_content),
        compression_ratio=len(compressed_content) / original_length,
        content=compressed_content,
        dropped_sections=dropped,
    )


# ── 提示模板 ──

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"

_TEMPLATES: Dict[str, PromptTemplate] = {}


def _load_templates():
    """加载模板"""
    global _TEMPLATES

    template_files = {
        "play_translate": "play_translate.yaml",
        "narrative_polish": "narrative_polish.yaml",
        "content_generate": "content_generate.yaml",
        "error_diagnose": "error_diagnose.yaml",
    }

    for name, filename in template_files.items():
        path = _TEMPLATE_DIR / filename
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                # 简化 YAML 解析
                _TEMPLATES[name] = PromptTemplate(
                    name=name,
                    version="1.0",
                    content=content,
                    variables=[],
                )
            except Exception:
                pass


def render_prompt(
    template_name: str,
    variables: Dict[str, Any],
    context: Optional[CompressedContext] = None,
) -> str:
    """
    从 templates/ 加载模板，带版本号。

    端口：render_prompt (L2 04 §10)
    """
    if not _TEMPLATES:
        _load_templates()

    template = _TEMPLATES.get(template_name)
    if not template:
        # 返回默认模板
        return f"请处理以下内容：\n{json.dumps(variables, ensure_ascii=False, indent=2)}"

    # 替换变量
    content = template.content
    for key, value in variables.items():
        placeholder = f"{{{key}}}"
        if placeholder in content:
            content = content.replace(placeholder, str(value))

    # 添加上下文
    if context:
        content += f"\n\n上下文（已压缩 {context.compression_ratio:.1%}）：\n{context.content}"

    return content


# ── 契约校验 ──

def validate_output(
    raw_output: str,
    contract_name: str,
    required_fields: Optional[List[str]] = None,
) -> ModelOutput:
    """
    按契约校验返回结构。
    字段齐、类型对、枚举合法。
    契约不符时归一为 LL-801（LLM_ORCHESTRATION 输出不符契约）。

    端口：validate_output (L2 04 §10)
    """
    output = ModelOutput(raw=raw_output)

    def _fail(message: str) -> ModelOutput:
        """契约不符：归一为 LL-801 错误结构"""
        err = make_error(LL_801, context={
            "contract": contract_name,
            "detail": message,
        }, recoverable=True)
        output.valid = False
        output.error = f"[{err.subsystem.value}-{err.code}] {message}"
        output.error_code = err.code
        output.error_obj = err
        return output

    try:
        parsed = json.loads(raw_output)
        output.parsed = parsed
    except json.JSONDecodeError as e:
        return _fail(f"JSON 解析失败: {e}")

    # 检查必要字段
    if required_fields:
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            return _fail(f"缺少必要字段: {missing}")

    # 合约特定校验
    if contract_name == "action_sequence":
        # 校验动作序列
        if "actions" not in parsed:
            return _fail("缺少 actions 字段")

        actions = parsed["actions"]
        if not isinstance(actions, list):
            return _fail("actions 应为数组")

        for i, action in enumerate(actions):
            if "action_type" not in action:
                return _fail(f"动作 {i} 缺少 action_type")

    elif contract_name == "polished_narrative":
        # 校验润色叙事
        if "narrative" not in parsed:
            return _fail("缺少 narrative 字段")

        # 不臆造数值检查
        narrative = parsed["narrative"]
        if isinstance(narrative, str):
            import re
            numbers = re.findall(r'\d+', narrative)
            # 简化：检查是否有异常大的数字
            for num in numbers:
                if int(num) > 10000:
                    return _fail(f"叙事中包含异常数字: {num}")

    elif contract_name == "content_draft":
        # 校验内容草案（开发辅助生成物）
        if "content" not in parsed:
            return _fail("缺少 content 字段")
        if not isinstance(parsed["content"], str):
            return _fail("content 应为字符串")

    output.valid = True
    return output


# ── 降级兜底 ──

def fallback_translate(options: List[Dict[str, Any]]) -> Dict[str, Any]:
    """翻译降级：列选项"""
    return {
        "action_type": "list_options",
        "options": options,
        "confidence": 0.5,
        "degraded": True,
    }


def fallback_polish(raw_text: str) -> Dict[str, Any]:
    """润色降级：原样回显"""
    return {
        "narrative": raw_text,
        "degraded": True,
    }


def fallback_generate() -> Dict[str, Any]:
    """生成降级：骨架模板"""
    return {
        "content": "; 自动生成骨架\n; 请根据需求修改\n\nPRINTL 内容待填充\nRETURN",
        "degraded": True,
    }


# ── 编排层 ──

def orchestrate(
    task: str,
    context: Dict[str, Any],
    model_invoke: Optional[Callable] = None,
    budget: int = 2000,
    max_retries: int = 1,
) -> Dict[str, Any]:
    """
    压缩→渲染→校验串联。
    重试一次后降级。

    端口：orchestrate (L2 04 §10)
    """
    # 1. 压缩上下文
    compressed = compress_context(context, budget)

    # 2. 渲染提示
    template_name = {
        "translate": "play_translate",
        "polish": "narrative_polish",
        "generate": "content_generate",
        "diagnose": "error_diagnose",
    }.get(task, "content_generate")

    prompt = render_prompt(template_name, {"task": task}, compressed)

    # 3. 调用模型（或降级）
    if model_invoke is None:
        # 无模型，降级
        if task == "translate":
            return fallback_translate([])
        elif task == "polish":
            return fallback_polish(prompt)
        elif task == "generate":
            return fallback_generate()
        else:
            return {"error": "无模型可用", "degraded": True}

    # 有模型，调用并校验
    for attempt in range(max_retries + 1):
        try:
            raw_output = model_invoke(prompt)

            # 校验输出
            contract_name = {
                "translate": "action_sequence",
                "polish": "polished_narrative",
                "generate": "content_draft",
            }.get(task, "content_draft")

            result = validate_output(raw_output, contract_name)

            if result.valid:
                return result.parsed
            else:
                if attempt < max_retries:
                    continue
                # 重试用尽，降级并透传契约错误码（LL-801）
                degraded = {
                    "error": result.error,
                    "error_code": result.error_code,
                    "degraded": True,
                }
                if task == "translate":
                    return {**fallback_translate([]), **degraded}
                elif task == "polish":
                    return {**fallback_polish(raw_output), **degraded}
                elif task == "generate":
                    return {**fallback_generate(), **degraded}

        except Exception as e:
            if attempt < max_retries:
                continue
            # 重试用尽，降级
            if task == "translate":
                return fallback_translate([])
            elif task == "polish":
                return fallback_polish("")
            elif task == "generate":
                return fallback_generate()

    # 不应到达这里
    return {"error": "编排失败", "degraded": True}
