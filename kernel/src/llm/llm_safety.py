from __future__ import annotations

import re
import json


class LLMSecurityBoundary:
    ALLOWED_FUNCTION_PREFIXES_GENERATE = ["口上_", "地文_", "COM_ABLE"]
    FORBIDDEN_FUNCTION_PREFIXES_MODIFY = ["SYSTEM_", "EVENT", "SHOW_", "USERCOM", "SOURCE_"]
    MAX_MODIFICATION_LINES = 50
    MAX_SCRIPT_LINES = 200
    BLOCKED_PATTERNS = ["system(", "exec(", "import ", "__"]


class LLMSafetyGuard:
    def __init__(self):
        self._boundary = LLMSecurityBoundary
        self._text_blocked_patterns = [
            r"(?i)ignore\s+(previous|above|all)\s+instructions",
            r"(?i)you\s+are\s+now",
            r"(?i)jailbreak",
            r"(?i)DAN\s+mode",
            r"(?i)developer\s+mode",
        ]

    def validate_generated_text(self, text: str) -> tuple[bool, str]:
        if not text or not text.strip():
            return False, "empty output"
        for pattern in self._text_blocked_patterns:
            if re.search(pattern, text):
                return False, f"blocked pattern detected: {pattern}"
        return True, ""

    def validate_generated_script(self, code: str) -> tuple[bool, str]:
        if not code or not code.strip():
            return False, "empty script"
        lines = code.strip().split("\n")
        if len(lines) > self._boundary.MAX_SCRIPT_LINES:
            return False, f"script exceeds max lines: {len(lines)} > {self._boundary.MAX_SCRIPT_LINES}"
        for pattern in self._boundary.BLOCKED_PATTERNS:
            if pattern in code:
                return False, f"forbidden pattern in script: {pattern}"
        try:
            json.loads(code) if code.strip().startswith("{") else None
        except (json.JSONDecodeError, ValueError):
            pass
        return True, ""

    def sanitize_input(self, prompt: str) -> str:
        sanitized = prompt
        for pattern in self._text_blocked_patterns:
            sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"<[^>]+>", "", sanitized)
        return sanitized.strip()

    def check_state_boundary(self, modified_vars: dict, allowed_patterns: list[str]) -> bool:
        for var_name in modified_vars:
            allowed = False
            for prefix in allowed_patterns:
                if var_name.startswith(prefix):
                    allowed = True
                    break
            if not allowed:
                return False
        return True


class LLMDegradationHandler:
    _FALLBACK_TEMPLATES = {
        "event": {
            0: "事件发生了。",
            -1: "某件事情发生了。",
        },
        "dialogue": {
            0: "……",
            -1: "……",
        },
        "scene": {
            0: "周围一片寂静。",
            -1: "周围一片寂静。",
        },
    }

    _DEGRADATION_MESSAGES = {
        "api_unreachable": "LLM服务不可用，使用默认内容。",
        "timeout": "LLM请求超时，使用默认内容。",
        "safety_violation": "内容安全检查未通过，使用默认内容。",
        "syntax_error": "生成内容格式错误，使用默认内容。",
        "runtime_error": "生成内容执行错误，使用默认内容。",
        "feature_disabled": "该功能未启用，使用默认内容。",
    }

    def __init__(self):
        self._degradation_log: list[dict] = []

    def handle_degradation(self, scenario: str, context: dict) -> str:
        message = self._DEGRADATION_MESSAGES.get(scenario, "未知错误，使用默认内容。")
        self._degradation_log.append({
            "scenario": scenario,
            "context": context,
            "message": message,
        })
        event_type = context.get("event_type", "event")
        character_id = context.get("character_id", -1)
        return self.get_fallback_text(event_type, character_id)

    def get_fallback_text(self, event_type: str, character_id: int) -> str:
        templates = self._FALLBACK_TEMPLATES.get(event_type, self._FALLBACK_TEMPLATES["event"])
        return templates.get(character_id, templates.get(-1, "……"))
