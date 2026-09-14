from __future__ import annotations

import re
import sys
from abc import ABC, abstractmethod
from typing import Any, Callable


_ANSI_COLORS: dict[int, str] = {
    0: "\033[30m",
    1: "\033[34m",
    2: "\033[32m",
    3: "\033[36m",
    4: "\033[31m",
    5: "\033[35m",
    6: "\033[33m",
    7: "\033[37m",
    8: "\033[90m",
    9: "\033[94m",
    10: "\033[92m",
    11: "\033[96m",
    12: "\033[91m",
    13: "\033[95m",
    14: "\033[93m",
    15: "\033[97m",
}
_ANSI_RESET: str = "\033[0m"


class IORenderer(ABC):

    @abstractmethod
    def print_text(self, text: str, newline: bool = False, wait: bool = False) -> None:
        ...

    @abstractmethod
    def print_formatted(self, segments: list, newline: bool = False, wait: bool = False) -> None:
        ...

    @abstractmethod
    def input_number(self, prompt: str = "", timeout: int = 0) -> int:
        ...

    @abstractmethod
    def input_string(self, prompt: str = "", timeout: int = 0) -> str:
        ...

    @abstractmethod
    def draw_line(self, char: str = "-") -> None:
        ...

    @abstractmethod
    def clear_line(self, count: int = 1) -> None:
        ...

    @abstractmethod
    def set_color(self, color: int) -> None:
        ...

    @abstractmethod
    def reset_color(self) -> None:
        ...

    @abstractmethod
    def print_button(self, text: str, value: Any) -> None:
        ...

    @abstractmethod
    def draw_bar(self, current: int, max_val: int, length: int, fill_char: str = "*", empty_char: str = ".") -> None:
        ...


class TerminalRenderer(IORenderer):

    MAX_EOF_COUNT = 3

    def __init__(self) -> None:
        self._current_color: int = -1
        self._eof_count: int = 0

    def _check_eof(self) -> None:
        self._eof_count += 1
        if self._eof_count >= self.MAX_EOF_COUNT:
            raise EOFError("Input exhausted: too many EOF signals")

    def _reset_eof(self) -> None:
        self._eof_count = 0

    def print_text(self, text: str, newline: bool = False, wait: bool = False) -> None:
        ending = "\n" if newline else ""
        try:
            print(text, end=ending, flush=True)
        except UnicodeEncodeError:
            safe_text = text.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8', errors='replace')
            print(safe_text, end=ending, flush=True)
        if wait:
            input()

    def print_formatted(self, segments: list, newline: bool = False, wait: bool = False) -> None:
        parts: list[str] = []
        for seg in segments:
            seg_type = seg.get("type", "text")
            seg_value = seg.get("value", "")
            if seg_type == "text":
                parts.append(str(seg_value))
            elif seg_type == "variable":
                parts.append(str(seg_value))
            elif seg_type == "expression":
                parts.append(str(seg_value))
            elif seg_type == "inline_cond":
                parts.append(str(seg_value))
        output = "".join(parts)
        ending = "\n" if newline else ""
        try:
            print(output, end=ending, flush=True)
        except UnicodeEncodeError:
            safe_output = output.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8', errors='replace')
            print(safe_output, end=ending, flush=True)
        if wait:
            input()

    def input_number(self, prompt: str = "", timeout: int = 0) -> int:
        if prompt:
            print(prompt, end="", flush=True)
        try:
            raw = input()
            self._reset_eof()
        except EOFError:
            self._check_eof()
            return -1
        try:
            return int(raw)
        except ValueError:
            return 0

    def input_string(self, prompt: str = "", timeout: int = 0) -> str:
        if prompt:
            print(prompt, end="", flush=True)
        try:
            result = input()
            self._reset_eof()
            return result
        except EOFError:
            self._check_eof()
            return ""

    def draw_line(self, char: str = "-") -> None:
        width = 80
        try:
            width = 80
        except Exception:
            pass
        print(char * width)

    def clear_line(self, count: int = 1) -> None:
        for _ in range(count):
            sys.stdout.write("\033[2K\033[1G")
        sys.stdout.flush()

    def set_color(self, color: int) -> None:
        self._current_color = color
        ansi = _ANSI_COLORS.get(color)
        if ansi is not None:
            sys.stdout.write(ansi)
            sys.stdout.flush()

    def reset_color(self) -> None:
        self._current_color = -1
        sys.stdout.write(_ANSI_RESET)
        sys.stdout.flush()

    def print_button(self, text: str, value: Any) -> None:
        print(f"[{text}]", end="", flush=True)

    def draw_bar(self, current: int, max_val: int, length: int, fill_char: str = "*", empty_char: str = ".") -> None:
        if max_val <= 0:
            ratio = 0.0
        else:
            ratio = current / max_val
        if ratio < 0.0:
            ratio = 0.0
        if ratio > 1.0:
            ratio = 1.0
        fill_count = int(ratio * length)
        empty_count = length - fill_count
        bar_str = fill_char * fill_count + empty_char * empty_count
        print(f"[{bar_str}]", end="", flush=True)


class BufferedRenderer(IORenderer):

    def __init__(self) -> None:
        self.output_buffer: list[str] = []
        self.input_queue: list[Any] = []

    def print_text(self, text: str, newline: bool = False, wait: bool = False) -> None:
        self.output_buffer.append(text)
        if newline:
            self.output_buffer.append("\n")

    def print_formatted(self, segments: list, newline: bool = False, wait: bool = False) -> None:
        parts: list[str] = []
        for seg in segments:
            seg_type = seg.get("type", "text")
            seg_value = seg.get("value", "")
            if seg_type == "text":
                parts.append(str(seg_value))
            elif seg_type == "variable":
                parts.append(str(seg_value))
            elif seg_type == "expression":
                parts.append(str(seg_value))
            elif seg_type == "inline_cond":
                parts.append(str(seg_value))
        self.output_buffer.append("".join(parts))
        if newline:
            self.output_buffer.append("\n")

    def input_number(self, prompt: str = "", timeout: int = 0) -> int:
        if prompt:
            self.output_buffer.append(prompt)
        if self.input_queue:
            raw = self.input_queue.pop(0)
            try:
                return int(raw)
            except (ValueError, TypeError):
                return 0
        return 0

    def input_string(self, prompt: str = "", timeout: int = 0) -> str:
        if prompt:
            self.output_buffer.append(prompt)
        if self.input_queue:
            raw = self.input_queue.pop(0)
            return str(raw)
        return ""

    def draw_line(self, char: str = "-") -> None:
        self.output_buffer.append(char * 80)

    def clear_line(self, count: int = 1) -> None:
        pass

    def set_color(self, color: int) -> None:
        pass

    def reset_color(self) -> None:
        pass

    def print_button(self, text: str, value: Any) -> None:
        self.output_buffer.append(f"[{text}]")

    def draw_bar(self, current: int, max_val: int, length: int, fill_char: str = "*", empty_char: str = ".") -> None:
        if max_val <= 0:
            ratio = 0.0
        else:
            ratio = current / max_val
        if ratio < 0.0:
            ratio = 0.0
        if ratio > 1.0:
            ratio = 1.0
        fill_count = int(ratio * length)
        empty_count = length - fill_count
        bar_str = fill_char * fill_count + empty_char * empty_count
        self.output_buffer.append(f"[{bar_str}]")

    def get_output(self) -> str:
        return "".join(self.output_buffer)

    def clear(self) -> None:
        self.output_buffer.clear()
        self.input_queue.clear()


_RE_PERCENT_VAR = re.compile(r"%([^%]+)%")
_RE_BRACE_VAR = re.compile(r"\{([^}]+)\}")
_RE_INLINE_COND = re.compile(r"\\\@\s*(.+?)\s*\?\s*(.*?)\s*#\s*(.*?)\s*\\\@")


class PrintFormEngine:

    def format_string(self, template: str, context_getter: Callable) -> str:
        result = _RE_INLINE_COND.sub(
            lambda m: self._replace_inline_cond(m, context_getter),
            template,
        )
        result = _RE_PERCENT_VAR.sub(
            lambda m: self._replace_percent_var(m, context_getter),
            result,
        )
        result = _RE_BRACE_VAR.sub(
            lambda m: self._replace_brace_var(m, context_getter),
            result,
        )
        return result

    def _replace_percent_var(self, match: re.Match, context_getter: Callable) -> str:
        var_name = match.group(1).strip()
        value = context_getter(var_name, "str")
        return str(value)

    def _replace_brace_var(self, match: re.Match, context_getter: Callable) -> str:
        inner = match.group(1).strip()
        if "," in inner:
            parts = inner.split(",", 1)
            var_name = parts[0].strip()
            width_str = parts[1].strip()
            value = context_getter(var_name, "int")
            try:
                width = int(width_str)
                return f"{int(value):>{width}d}"
            except (ValueError, TypeError):
                return str(value)
        value = context_getter(inner, "int")
        return str(value)

    def _replace_inline_cond(self, match: re.Match, context_getter: Callable) -> str:
        condition_str = match.group(1).strip()
        true_str = match.group(2).strip()
        false_str = match.group(3).strip()
        try:
            condition_value = context_getter(condition_str, "int")
            if condition_value:
                return true_str
            return false_str
        except Exception:
            return false_str
