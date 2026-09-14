from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm_bridge import LLMBridge


@dataclass
class DebugAnalysis:
    error_type: str = ""
    root_cause: str = ""
    affected_variables: list = field(default_factory=list)
    suggested_fix: str = ""
    confidence: float = 0.0
    related_code_locations: list = field(default_factory=list)


@dataclass
class FixSuggestion:
    description: str = ""
    code_change: str = ""
    confidence: float = 0.0


class LLMDebugAssistant:
    def __init__(self, bridge: LLMBridge):
        self._bridge = bridge

    async def analyze_error(self, error, call_stack, variable_snapshot) -> DebugAnalysis:
        system_prompt = (
            "你是一个ERA游戏脚本调试分析器。根据提供的错误信息、调用栈和变量快照，"
            "分析错误的类型、根因、受影响的变量，并提供修复建议。"
            "以JSON格式输出分析结果，包含以下字段："
            "error_type, root_cause, affected_variables, suggested_fix, confidence, related_code_locations"
        )
        user_parts = [
            f"错误信息: {error}",
            f"调用栈: {call_stack}",
        ]
        if variable_snapshot:
            user_parts.append(f"变量快照: {variable_snapshot}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        response = await self._bridge._call_api(messages)

        return self._parse_analysis(response)

    async def suggest_fix(self, source_code: str, error_description: str) -> list[FixSuggestion]:
        system_prompt = (
            "你是一个ERA游戏脚本修复建议器。根据提供的源代码和错误描述，"
            "提供多个修复建议。"
            "以JSON数组格式输出，每个元素包含：description, code_change, confidence"
        )
        user_parts = [
            f"源代码:\n{source_code}",
            f"错误描述: {error_description}",
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        response = await self._bridge._call_api(messages)

        return self._parse_suggestions(response)

    async def explain_code(self, source_code: str, question: str) -> str:
        system_prompt = (
            "你是一个ERA游戏脚本解释器。根据提供的源代码和问题，"
            "用清晰易懂的语言解释代码的逻辑和行为。"
        )
        user_parts = [
            f"源代码:\n{source_code}",
            f"问题: {question}",
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return await self._bridge._call_api(messages)

    def _parse_analysis(self, response: str) -> DebugAnalysis:
        try:
            data = json.loads(response)
            return DebugAnalysis(
                error_type=data.get("error_type", ""),
                root_cause=data.get("root_cause", ""),
                affected_variables=data.get("affected_variables", []),
                suggested_fix=data.get("suggested_fix", ""),
                confidence=float(data.get("confidence", 0.0)),
                related_code_locations=data.get("related_code_locations", []),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return DebugAnalysis(
                error_type="parse_error",
                root_cause=response[:200],
                suggested_fix="",
                confidence=0.0,
            )

    def _parse_suggestions(self, response: str) -> list[FixSuggestion]:
        try:
            data = json.loads(response)
            if not isinstance(data, list):
                data = [data]
            suggestions = []
            for item in data:
                suggestions.append(FixSuggestion(
                    description=item.get("description", ""),
                    code_change=item.get("code_change", ""),
                    confidence=float(item.get("confidence", 0.0)),
                ))
            return suggestions
        except (json.JSONDecodeError, ValueError, TypeError):
            return [FixSuggestion(description=response[:200], confidence=0.0)]
