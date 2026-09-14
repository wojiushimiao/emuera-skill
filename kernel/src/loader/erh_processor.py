from __future__ import annotations

import csv
import os
import codecs
import re
from typing import Any

from src.core.variable_manager import VariableDescriptor, VariableManager


class ERHProcessor:

    def __init__(self, variable_mgr: VariableManager) -> None:
        self.variable_mgr: VariableManager = variable_mgr
        # 宏字典：name.upper() → (arg_list, body)
        # arg_list 为空表示简单文本替换宏；非空表示带参宏（#DEFINE NAME(a,b) body）
        self.macros: dict[str, tuple[list[str], str]] = {}
        self.constants: dict[str, Any] = {}
        self._max_macro_depth: int = 10

    def process_file(self, erh_path: str) -> None:
        if not os.path.isfile(erh_path):
            return
        lines = self._read_erh(erh_path)
        self._first_pass(lines)
        expanded_lines: list[str] = []
        for line in lines:
            expanded_lines.append(self.expand_macro(line))
        self._second_pass(expanded_lines)

    def process_all(self, erb_dir: str) -> None:
        erh_files: list[str] = []
        for root, _dirs, files in os.walk(erb_dir):
            for f in files:
                if f.lower().endswith(".erh"):
                    erh_files.append(os.path.join(root, f))
        all_lines: list[str] = []
        for erh_path in erh_files:
            if not os.path.isfile(erh_path):
                continue
            lines = self._read_erh(erh_path)
            all_lines.extend(lines)
        self._first_pass(all_lines)
        expanded_lines: list[str] = []
        for line in all_lines:
            expanded_lines.append(self.expand_macro(line))
        self._second_pass(expanded_lines)

    def expand_macro(self, source: str) -> str:
        return self._expand_macro_recursive(source, 0)

    def _expand_macro_recursive(self, source: str, depth: int) -> str:
        if depth >= self._max_macro_depth:
            return source
        changed = False
        for macro_name, (arg_list, replacement) in self.macros.items():
            if arg_list:
                # 带参宏：匹配 NAME(actual1, actual2) 并替换形参
                new_source = self._substitute_function_macro(
                    source, macro_name, arg_list, replacement,
                )
            else:
                # 简单宏：大小写不敏感的词边界替换（对齐 Emuera Config.IgnoreCase=true）
                pattern = r'\b' + re.escape(macro_name) + r'\b'
                new_source, _ = re.subn(pattern, replacement, source, flags=re.IGNORECASE)
            if new_source != source:
                source = new_source
                changed = True
        if changed:
            return self._expand_macro_recursive(source, depth + 1)
        return source

    def _substitute_function_macro(
        self, source: str, name: str, arg_list: list[str], body: str,
    ) -> str:
        """在 source 中查找 NAME(actual1, actual2) 并将形参替换为实参，大小写不敏感。"""
        out: list[str] = []
        i = 0
        # 大小写不敏感匹配 NAME(
        pattern = re.compile(r'\b' + re.escape(name) + r'\s*\(', re.IGNORECASE)
        while True:
            m = pattern.search(source, i)
            if not m:
                out.append(source[i:])
                break
            out.append(source[i:m.start()])
            paren_start = m.end() - 1  # '(' 的位置
            # 匹配平衡括号
            depth = 1
            j = paren_start + 1
            while j < len(source) and depth > 0:
                if source[j] == '(':
                    depth += 1
                elif source[j] == ')':
                    depth -= 1
                j += 1
            if depth != 0:
                # 括号未闭合，原样保留
                out.append(source[m.start():j])
                i = j
                continue
            arg_src = source[paren_start + 1:j - 1]
            actuals = self._split_macro_args(arg_src)
            if len(actuals) != len(arg_list):
                # 参数数量不匹配，原样保留
                out.append(source[m.start():j])
                i = j
                continue
            # 形参 → 实参替换（大小写不敏感）
            expanded = body
            for formal, actual in zip(arg_list, actuals):
                expanded = re.sub(
                    r'\b' + re.escape(formal) + r'\b', actual, expanded,
                    flags=re.IGNORECASE,
                )
            out.append(expanded)
            i = j
        return ''.join(out)

    @staticmethod
    def _split_macro_args(arg_src: str) -> list[str]:
        """拆分逗号分隔的宏参数，支持嵌套括号（如 FOO(A(1,2), B)）。"""
        args: list[str] = []
        depth = 0
        cur: list[str] = []
        for ch in arg_src:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            if ch == ',' and depth == 0:
                args.append(''.join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        tail = ''.join(cur).strip()
        if tail:
            args.append(tail)
        return args

    def _read_erh(self, filepath: str) -> list[str]:
        encodings: list[str] = ["utf-8", "utf-8-sig", "shift_jis", "gb18030"]
        for enc in encodings:
            try:
                with codecs.open(filepath, "r", encoding=enc) as f:
                    return [line.rstrip("\n\r") for line in f.readlines()]
            except (UnicodeDecodeError, UnicodeError):
                continue
        return []

    def _first_pass(self, lines: list[str]) -> None:
        for line in lines:
            stripped = line.strip()
            if not stripped.upper().startswith("#DEFINE"):
                continue
            rest = stripped[len("#DEFINE"):].strip()
            if not rest:
                continue
            self._process_define_raw(rest)

    def _second_pass(self, lines: list[str]) -> None:
        for line in lines:
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("#DIM ") or upper.startswith("#DIMS "):
                self._process_dim_line(stripped)
            elif upper.startswith("#FUNCTION") :
                pass

    def _process_define_raw(self, rest: str) -> None:
        """解析 #DEFINE 后的内容，支持带参宏与简单宏。宏名统一大写以对齐 Emuera 大小写不敏感语义。"""
        # 检测带参宏：在首个空格之前出现 '(' → #DEFINE NAME(a, b) body
        paren_idx = rest.find('(')
        space_idx = rest.find(' ')
        if paren_idx >= 0 and (space_idx < 0 or paren_idx < space_idx):
            # 带参宏
            macro_name = rest[:paren_idx].strip().upper()
            rest_args_body = rest[paren_idx + 1:]
            close_paren = rest_args_body.find(')')
            if close_paren < 0:
                # 畸形定义，退化为简单宏
                parts = rest.split(None, 1)
                if len(parts) >= 2:
                    self.macros[parts[0].upper()] = ([], parts[1])
                return
            arg_part = rest_args_body[:close_paren]
            body = rest_args_body[close_paren + 1:].strip()
            arg_list = [a.strip().upper() for a in arg_part.split(',') if a.strip()]
            self.macros[macro_name] = (arg_list, body)
        else:
            # 简单宏：#DEFINE NAME replacement
            parts = rest.split(None, 1)
            if len(parts) < 2:
                return
            self.macros[parts[0].upper()] = ([], parts[1])

    def _process_dim_line(self, line: str) -> None:
        upper_line = line.upper()
        is_str = upper_line.startswith("#DIMS")
        var_type = "str" if is_str else "int"
        rest = line.split(None, 1)
        if len(rest) < 2:
            return
        decl_part = rest[1].strip()
        modifiers: set[str] = set()
        modifier_keywords = {"CONST", "SAVEDATA", "GLOBAL", "CHARA", "CHARADATA", "DYNAMIC", "REF"}
        while True:
            found = False
            for kw in modifier_keywords:
                if decl_part.upper().startswith(kw):
                    modifiers.add(kw)
                    decl_part = decl_part[len(kw):].strip()
                    found = True
                    break
            if not found:
                break
        if "=" in decl_part:
            name_part, init_part = decl_part.split("=", 1)
            name_part = name_part.strip()
            init_part = init_part.strip()
            name_str = name_part.rstrip(",")
            dimensions = 0
            default_size: list[int] = []
            initial_values: list[Any] = []
            for v in init_part.split(","):
                v = v.strip()
                if not v:
                    continue
                if is_str:
                    initial_values.append(v.strip('"').strip("'"))
                else:
                    try:
                        initial_values.append(int(v))
                    except ValueError:
                        initial_values.append(0)
            if initial_values:
                dimensions = 1
                default_size = [len(initial_values)]
            self._register_variable(name_str, var_type, dimensions, default_size, modifiers, initial_values)
        elif "," in decl_part:
            parts = [p.strip() for p in decl_part.split(",")]
            name_str = parts[0]
            size_dims: list[int] = []
            for p in parts[1:]:
                try:
                    size_dims.append(int(p))
                except ValueError:
                    break
            dimensions = len(size_dims)
            default_size = size_dims if size_dims else [1]
            if not size_dims:
                dimensions = 0
            self._register_variable(name_str, var_type, dimensions, default_size, modifiers, [])
        else:
            name_str = decl_part.strip()
            self._register_variable(name_str, var_type, 0, [], modifiers, [])

    def _register_variable(
        self,
        name: str,
        var_type: str,
        dimensions: int,
        default_size: list[int],
        modifiers: set[str],
        initial_values: list[Any],
    ) -> None:
        is_const = "CONST" in modifiers
        is_savedata = "SAVEDATA" in modifiers
        is_global = "GLOBAL" in modifiers
        is_chara = "CHARA" in modifiers or "CHARADATA" in modifiers
        is_dynamic = "DYNAMIC" in modifiers
        is_ref = "REF" in modifiers
        if is_const:
            if initial_values:
                self.constants[name] = initial_values[0]
            else:
                self.constants[name] = 0 if var_type == "int" else ""
            desc = VariableDescriptor(
                name=name,
                var_type=var_type,
                dimensions=dimensions,
                is_readonly=True,
                default_size=default_size,
            )
            self.variable_mgr.register_variable(desc)
            return
        is_temporary = is_dynamic
        reset_timing: str | None = None
        if is_dynamic:
            reset_timing = "function_exit"
        desc = VariableDescriptor(
            name=name,
            var_type=var_type,
            dimensions=dimensions,
            is_character_var=is_chara,
            is_readonly=False,
            is_savedata=is_savedata,
            is_global=is_global,
            is_temporary=is_temporary,
            default_size=default_size,
            reset_timing=reset_timing,
        )
        self.variable_mgr.register_variable(desc)
        if initial_values and dimensions == 1:
            for i, val in enumerate(initial_values):
                try:
                    self.variable_mgr.set_value(name, [i], val)
                except (KeyError, IndexError):
                    pass
