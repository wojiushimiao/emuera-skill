from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .llm_safety import LLMSecurityBoundary

if TYPE_CHECKING:
    from .llm_bridge import LLMBridge


@dataclass
class FunctionSpec:
    function_name: str = ""
    parameters: list = field(default_factory=list)
    description: str = ""
    constraints: list = field(default_factory=list)
    reference_functions: list = field(default_factory=list)
    output_type: str = ""


class LLMScriptGenerator:
    def __init__(self, bridge: LLMBridge):
        self._bridge = bridge

    async def generate_function(self, function_spec: FunctionSpec) -> str:
        prefix_allowed = False
        for prefix in LLMSecurityBoundary.ALLOWED_FUNCTION_PREFIXES_GENERATE:
            if function_spec.function_name.startswith(prefix):
                prefix_allowed = True
                break
        if not prefix_allowed:
            raise ValueError(
                f"Function name '{function_spec.function_name}' does not match "
                f"allowed prefixes: {LLMSecurityBoundary.ALLOWED_FUNCTION_PREFIXES_GENERATE}"
            )

        system_prompt = (
            "你是一个ERA游戏脚本生成器。根据提供的函数规格，生成符合ERA语法的函数代码。"
            "只输出代码，不要添加任何解释或注释。"
            "使用ERA脚本语法，不要使用Python语法。"
        )
        user_parts = [
            f"函数名: {function_spec.function_name}",
            f"参数: {function_spec.parameters}",
            f"描述: {function_spec.description}",
        ]
        if function_spec.constraints:
            user_parts.append(f"约束: {function_spec.constraints}")
        if function_spec.reference_functions:
            user_parts.append(f"参考函数: {function_spec.reference_functions}")
        if function_spec.output_type:
            user_parts.append(f"输出类型: {function_spec.output_type}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return await self._bridge._call_api(messages)

    async def generate_kojo(self, character_id: int, command_ids: list[int]) -> str:
        system_prompt = (
            "你是一个ERA游戏口上生成器。根据角色ID和指令ID列表，"
            "生成符合角色性格的口上脚本代码。"
            "只输出代码，不要添加任何解释或注释。"
            "使用ERA脚本语法，不要使用Python语法。"
        )
        user_parts = [
            f"角色ID: {character_id}",
            f"指令ID列表: {command_ids}",
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return await self._bridge._call_api(messages)


class LLMScriptModifier:
    def __init__(self, bridge: LLMBridge):
        self._bridge = bridge

    async def modify_function(self, source_code: str, modification_request: str) -> str:
        for prefix in LLMSecurityBoundary.FORBIDDEN_FUNCTION_PREFIXES_MODIFY:
            for line in source_code.strip().split("\n"):
                stripped = line.strip()
                if stripped.startswith("@") or stripped.startswith(";"):
                    continue
                if stripped.upper().startswith(prefix):
                    raise ValueError(
                        f"Cannot modify function with forbidden prefix: {prefix}"
                    )

        lines = source_code.strip().split("\n")
        if len(lines) > LLMSecurityBoundary.MAX_MODIFICATION_LINES:
            raise ValueError(
                f"Source code exceeds max modification lines: "
                f"{len(lines)} > {LLMSecurityBoundary.MAX_MODIFICATION_LINES}"
            )

        system_prompt = (
            "你是一个ERA游戏脚本修改器。根据提供的源代码和修改请求，"
            "生成修改后的完整函数代码。"
            "只输出修改后的代码，不要添加任何解释或注释。"
            "使用ERA脚本语法，不要使用Python语法。"
        )
        user_parts = [
            f"源代码:\n{source_code}",
            f"修改请求: {modification_request}",
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return await self._bridge._call_api(messages)

    async def fix_bug(self, source_code: str, error_message: str, context: dict) -> str:
        system_prompt = (
            "你是一个ERA游戏脚本调试器。根据提供的源代码、错误信息和上下文，"
            "生成修复后的完整函数代码。"
            "只输出修复后的代码，不要添加任何解释或注释。"
            "使用ERA脚本语法，不要使用Python语法。"
        )
        user_parts = [
            f"源代码:\n{source_code}",
            f"错误信息: {error_message}",
        ]
        if context:
            user_parts.append(f"上下文: {context}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return await self._bridge._call_api(messages)
