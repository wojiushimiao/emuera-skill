from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from typing import Any

from .ast_nodes import (
    AssignNode,
    BinaryOpNode,
    BitPositionNode,
    BreakNode,
    BeginNode,
    CallEntryNode,
    CallNode,
    CaseNode,
    ContinueNode,
    DoLoopNode,
    ForNode,
    FunctionCallNode,
    FunctionDefNode,
    FormatStringNode,
    GotoNode,
    IfNode,
    InlineCondNode,
    InputNode,
    LabelNode,
    LiteralNode,
    PrintDataEntryNode,
    PrintDataNode,
    PrintNode,
    PrintSegmentNode,
    ProgramNode,
    RepeatNode,
    ReturnNode,
    SelectCaseNode,
    SifNode,
    StatementNode,
    StringAssignNode,
    ThrowNode,
    TimesNode,
    TernaryOpNode,
    TrycCallformNode,
    TrycallListNode,
    UnaryOpNode,
    VarDeclNode,
    VarsetNode,
    VariableAccessNode,
    WhileNode,
    ExpressionNode,
)
from .variable_manager import VariableDescriptor, VariableManager


@dataclass
class ExecutionContext:
    function_name: str
    local_vars: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    return_value: Any = None
    return_string: str = ""
    call_depth: int = 0
    instruction_pointer: int = 0
    dynamic_vars: dict[str, Any] = field(default_factory=dict)


class ControlSignal(Exception):
    pass


class ReturnSignal(ControlSignal):
    def __init__(self, value: Any = None, is_returnf: bool = False):
        self.value = value
        self.is_returnf = is_returnf


class BreakSignal(ControlSignal):
    pass


class ContinueSignal(ControlSignal):
    pass


class GotoSignal(ControlSignal):
    def __init__(self, label: str):
        self.label = label


class ThrowSignal(ControlSignal):
    def __init__(self, message: str):
        self.message = message


# --- Emuera 官方 C# 数值语义对齐（基准：v1.821-cn8 OperatorMethod.cs / Emuera.csproj） ---
# 官方整数运算为 unchecked Int64：在 ±2^63 处静默回绕（csproj 未开启
# CheckForOverflowUnderflow）；`/` 为 long 除法（向零截断，精确整数运算）；
# `%` 为 C# 余数（符号随被除数，区别于 Python 取模随除数）；
# 除零与模零抛出 CodeEE("0不能做除数")。
_INT64_WRAP = (1 << 64) - 1
_INT64_SIGN_BIT = 1 << 63


def _is_int(value: Any) -> bool:
    """判断是否为整数（bool 是 int 子类，但 ERB 中按整数参与运算）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _wrap_int64(value: Any) -> Any:
    """按 unchecked C# Int64 语义在 2^64 处静默回绕；非整数原样返回。"""
    if not isinstance(value, int) or isinstance(value, bool):
        return value
    value &= _INT64_WRAP
    if value >= _INT64_SIGN_BIT:
        value -= 1 << 64
    return value


def _emuera_div(left: int, right: int) -> int:
    """对齐 C# long / ：向零截断的精确整数除法（不经浮点，避免大数精度损失）。"""
    if right == 0:
        raise ThrowSignal("0不能做除数")
    quotient = abs(left) // abs(right)
    if (left < 0) != (right < 0):
        quotient = -quotient
    return _wrap_int64(quotient)


def _emuera_mod(left: int, right: int) -> int:
    """对齐 C# long % ：余数，符号随被除数（Python 取模符号随除数，故需改写）。"""
    if right == 0:
        raise ThrowSignal("0不能做除数")
    remainder = abs(left) % abs(right)
    return -remainder if left < 0 else remainder


class BeginSignal(ControlSignal):
    def __init__(self, mode: str):
        self.mode = mode


class RestartSignal(ControlSignal):
    pass


class VirtualMachine:

    max_call_depth: int = 250  # K-04: 低于 Python 原生递归限制，确保 ThrowSignal 先于 RecursionError 触发

    def __init__(
        self,
        variable_mgr: VariableManager,
        function_dispatch: Any,
        io_renderer: Any,
        llm_bridge: Any | None = None,
        game_dir: str | None = None,
    ):
        self.variable_mgr = variable_mgr
        self.function_dispatch = function_dispatch
        self.io_renderer = io_renderer
        self.llm_bridge = llm_bridge
        self.game_dir = game_dir or ""
        self.call_stack: list[ExecutionContext] = []
        self._label_cache: dict[str, dict[str, int]] = {}

    def execute(self, program: ProgramNode) -> None:
        for func_def in program.functions:
            self._register_labels(func_def)
        for func_def in program.functions:
            if func_def.name == "SYSTEM_TITLE":
                self.call_function("SYSTEM_TITLE", [])
                break

    def call_function(self, name: str, args: list[Any]) -> Any:
        func_def = self.function_dispatch.get_function(name)
        if func_def is None:
            return 0
        if name not in self._label_cache:
            self._register_labels(func_def)
        if len(self.call_stack) >= self.max_call_depth:
            raise ThrowSignal(f"Call depth exceeded {self.max_call_depth} in '{name}'")
        ctx = ExecutionContext(
            function_name=name,
            call_depth=len(self.call_stack),
        )
        for i, param in enumerate(func_def.parameters):
            if i < len(args):
                ctx.parameters[param.name] = args[i]
                ctx.local_vars[param.name] = args[i]
        self.call_stack.append(ctx)
        self.variable_mgr.push_scope()
        for param_name, param_val in ctx.parameters.items():
            self.variable_mgr._scope_stack[-1][param_name] = param_val
            if ':' in param_name:
                base_name, idx_str = param_name.split(':', 1)
                try:
                    idx = int(idx_str)
                    base_desc = self.variable_mgr.get_descriptor(base_name)
                    if base_desc is not None and base_desc.dimensions >= 1:
                        self.variable_mgr.set_value(base_name, [idx], param_val)
                    else:
                        if base_name not in self.variable_mgr._scope_stack[-1]:
                            self.variable_mgr._scope_stack[-1][base_name] = {}
                        base_val = self.variable_mgr._scope_stack[-1][base_name]
                        if isinstance(base_val, dict):
                            base_val[idx] = param_val
                except ValueError:
                    pass
            else:
                base_desc = self.variable_mgr.get_descriptor(param_name)
                if base_desc is not None and base_desc.dimensions >= 1:
                    self.variable_mgr.set_value(param_name, [0], param_val)
        try:
            restart_count = 0
            max_restarts = 1000
            while True:
                try:
                    self.exec_block(list(func_def.body))
                    break
                except RestartSignal:
                    restart_count += 1
                    if restart_count >= max_restarts:
                        raise ThrowSignal(f"RESTART limit ({max_restarts}) exceeded in '{name}'")
                    continue
        except ReturnSignal as sig:
            if sig.is_returnf:
                if func_def.is_functions:
                    ctx.return_string = str(sig.value) if sig.value is not None else ""
                    self.variable_mgr.set_value("RESULTS", [0], ctx.return_string)
                    return ctx.return_string
                else:
                    ctx.return_value = sig.value
                    self.variable_mgr.set_value("RESULT", [0], sig.value if sig.value is not None else 0)
                    return sig.value
            else:
                ctx.return_value = sig.value if sig.value is not None else 0
                self.variable_mgr.set_value("RESULT", [0], ctx.return_value)
                return ctx.return_value
        except GotoSignal as sig:
            self._handle_goto_in_function(func_def, sig.label, ctx)
        except RecursionError:
            # K-04: Python 原生栈溢出先于 VM 深度检查触发时，转为 ThrowSignal
            raise ThrowSignal(f"Recursion limit exceeded in '{name}'")
        finally:
            self.variable_mgr.pop_scope()
            self.call_stack.pop()
        if func_def.is_functions:
            return ctx.return_string
        # H3: 函数体自然结束（无 RETURN）时，返回值取 0，
        # 但**不写 RESULT** —— 与 Emuera 语义一致，避免清掉函数体内对 RESULT 的写入。
        return ctx.return_value if ctx.return_value is not None else 0

    # --- Save / Load support ---
    def _get_save_dir(self) -> str:
        save_dir = os.path.join(self.game_dir, "SAVE") if self.game_dir else "SAVE"
        os.makedirs(save_dir, exist_ok=True)
        return save_dir

    def save_game(self) -> None:
        """SAVEGAME - save to default slot."""
        self.save_data(0)

    def load_game(self) -> None:
        """LOADGAME - load from default slot."""
        self.load_data(0)

    def save_data(self, slot: int) -> int:
        """SAVEDATA slot - save game state to a numbered slot."""
        import time as _time
        save_dir = self._get_save_dir()
        save_path = os.path.join(save_dir, f"save_{slot:03d}.json")
        data = self.variable_mgr.serialize()
        data["save_slot"] = slot
        data["save_timestamp"] = _time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return 0
        except Exception:
            return -1

    def load_data(self, slot: int) -> int:
        """LOADDATA slot - load game state from a numbered slot."""
        save_dir = self._get_save_dir()
        save_path = os.path.join(save_dir, f"save_{slot:03d}.json")
        if not os.path.isfile(save_path):
            return -1
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.variable_mgr.deserialize(data)
            return 0
        except Exception:
            return -1

    def _handle_goto_in_function(
        self, func_def: FunctionDefNode, label: str, ctx: ExecutionContext
    ) -> None:
        labels = self._label_cache.get(func_def.name, {})
        if label not in labels:
            raise ThrowSignal(f"Label '{label}' not found in function '{func_def.name}'")
        # DEV-14: Find enclosing loop for the target label, so GOTO can jump
        # into the middle of a DO/FOR/WHILE/REPEAT loop body
        target_idx = labels[label]
        enclosing_loop = self._find_enclosing_loop(func_def.body, target_idx)
        if enclosing_loop is not None:
            # Re-execute the enclosing loop from its body; the GOTO will
            # naturally arrive at the target label within that loop body
            self._reenter_loop_from_label(enclosing_loop, label, labels, func_def)
            return
        # No enclosing loop: execute from the statement after the label
        current_label = label
        while True:
            target_idx = labels[current_label]
            try:
                self.exec_block(func_def.body[target_idx + 1:])
                break
            except GotoSignal as sig:
                if sig.label not in labels:
                    raise ThrowSignal(f"Label '{sig.label}' not found in function '{func_def.name}'")
                current_label = sig.label
            except ReturnSignal:
                return

    def _find_enclosing_loop(self, body: list[StatementNode], target_idx: int) -> StatementNode | None:
        """Find the innermost loop (DO/FOR/WHILE/REPEAT) that encloses target_idx."""
        for i, stmt in enumerate(body):
            loop_body = None
            if isinstance(stmt, DoLoopNode):
                loop_body = stmt.body
            elif isinstance(stmt, ForNode):
                loop_body = stmt.body
            elif isinstance(stmt, WhileNode):
                loop_body = stmt.body
            elif isinstance(stmt, RepeatNode):
                loop_body = stmt.body
            if loop_body is not None:
                # Check if target_idx falls within this loop's body
                # The loop body starts after the loop header statement
                loop_start = i + 1  # statements after the loop header
                loop_end = loop_start + len(loop_body)
                if loop_start <= target_idx < loop_end:
                    # Check nested loops first
                    nested = self._find_enclosing_loop(loop_body, target_idx - loop_start)
                    if nested is not None:
                        return nested
                    return stmt
        return None

    def _reenter_loop_from_label(
        self, loop_node: StatementNode, target_label: str,
        labels: dict[str, int], func_def: FunctionDefNode
    ) -> None:
        """Re-execute a loop body, allowing GOTO to reach the target label."""
        if isinstance(loop_node, DoLoopNode):
            self._exec_do_loop_with_goto(loop_node, target_label, labels, func_def)
        elif isinstance(loop_node, ForNode):
            self._exec_for_with_goto(loop_node, target_label, labels, func_def)
        elif isinstance(loop_node, WhileNode):
            self._exec_while_with_goto(loop_node, target_label, labels, func_def)
        elif isinstance(loop_node, RepeatNode):
            self._exec_repeat_with_goto(loop_node, target_label, labels, func_def)

    def _exec_do_loop_with_goto(self, node: DoLoopNode, target_label: str,
                                 labels: dict[str, int], func_def: FunctionDefNode) -> None:
        """Execute DO loop body, restarting from target_label on GOTO."""
        # Execute the loop body; if GOTO targets a label within it,
        # the GotoSignal will be caught and we restart the body
        if node.condition_position == "until":
            while True:
                try:
                    self.exec_block(node.body)
                    # After normal completion, check if GOTO would re-enter
                    break
                except GotoSignal as sig:
                    if sig.label in labels:
                        # Check if target is inside this loop's body
                        target_idx = labels[sig.label]
                        loop_start = 0
                        loop_end = len(node.body)
                        if loop_start <= target_idx < loop_end:
                            # Restart the loop body from the label
                            continue
                    raise
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass
                if node.condition is not None and self.eval_expression(node.condition):
                    break
        elif node.condition_position in ("while", "post"):
            while True:
                try:
                    self.exec_block(node.body)
                except GotoSignal as sig:
                    if sig.label in labels:
                        target_idx = labels[sig.label]
                        loop_start = 0
                        loop_end = len(node.body)
                        if loop_start <= target_idx < loop_end:
                            continue
                    raise
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass
                if node.condition is not None and not self.eval_expression(node.condition):
                    break
        else:
            while True:
                try:
                    self.exec_block(node.body)
                except GotoSignal as sig:
                    if sig.label in labels:
                        target_idx = labels[sig.label]
                        loop_start = 0
                        loop_end = len(node.body)
                        if loop_start <= target_idx < loop_end:
                            continue
                    raise
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass
                break

    def _exec_for_with_goto(self, node: ForNode, target_label: str,
                             labels: dict[str, int], func_def: FunctionDefNode) -> None:
        """Execute FOR loop body, restarting from target_label on GOTO."""
        start_val = int(self.eval_expression(node.start))
        end_val = int(self.eval_expression(node.end))
        step_val = int(self.eval_expression(node.step)) if node.step else 1
        if step_val == 0:
            raise ThrowSignal("FOR step cannot be zero")
        desc = self.variable_mgr.get_descriptor(node.var_name)
        if desc is not None and desc.dimensions > 0:
            indices = [0] * desc.dimensions
        else:
            indices = []
        if desc is not None:
            self.variable_mgr.set_value(node.var_name, indices, start_val)
        else:
            stored = False
            if self.variable_mgr._scope_stack:
                if node.var_name in self.variable_mgr._scope_stack[-1]:
                    self.variable_mgr._scope_stack[-1][node.var_name] = start_val
                    stored = True
            if not stored:
                ctx = self.call_stack[-1] if self.call_stack else None
                if ctx is not None:
                    ctx.local_vars[node.var_name] = start_val
        current = start_val
        while True:
            if step_val > 0 and current > end_val:
                break
            if step_val < 0 and current < end_val:
                break
            if desc is not None:
                self.variable_mgr.set_value(node.var_name, indices, current)
            else:
                stored = False
                if self.variable_mgr._scope_stack:
                    if node.var_name in self.variable_mgr._scope_stack[-1]:
                        self.variable_mgr._scope_stack[-1][node.var_name] = current
                        stored = True
                if not stored:
                    ctx = self.call_stack[-1] if self.call_stack else None
                    if ctx is not None:
                        ctx.local_vars[node.var_name] = current
            try:
                self.exec_block(node.body)
            except GotoSignal as sig:
                if sig.label in labels:
                    target_idx = labels[sig.label]
                    if 0 <= target_idx < len(node.body):
                        continue
                raise
            except BreakSignal:
                break
            except ContinueSignal:
                pass
            current += step_val

    def _exec_while_with_goto(self, node: WhileNode, target_label: str,
                               labels: dict[str, int], func_def: FunctionDefNode) -> None:
        """Execute WHILE loop body, restarting from target_label on GOTO."""
        while self.eval_expression(node.condition):
            try:
                self.exec_block(node.body)
            except GotoSignal as sig:
                if sig.label in labels:
                    target_idx = labels[sig.label]
                    if 0 <= target_idx < len(node.body):
                        continue
                raise
            except BreakSignal:
                break
            except ContinueSignal:
                pass

    def _exec_repeat_with_goto(self, node: RepeatNode, target_label: str,
                                labels: dict[str, int], func_def: FunctionDefNode) -> None:
        """Execute REPEAT loop body, restarting from target_label on GOTO."""
        count = int(self.eval_expression(node.count))
        for _ in range(count):
            try:
                self.exec_block(node.body)
            except GotoSignal as sig:
                if sig.label in labels:
                    target_idx = labels[sig.label]
                    if 0 <= target_idx < len(node.body):
                        continue
                raise
            except BreakSignal:
                break
            except ContinueSignal:
                pass

    def _register_labels(self, func_def: FunctionDefNode) -> None:
        labels: dict[str, int] = {}
        self._register_labels_in_body(func_def.body, labels, 0)
        self._label_cache[func_def.name] = labels

    def _register_labels_in_body(self, body: list[StatementNode],
                                  labels: dict[str, int], offset: int) -> int:
        """Recursively register labels in body and nested loop bodies.
        Returns the number of statements consumed (for offset tracking)."""
        for i, stmt in enumerate(body):
            if isinstance(stmt, LabelNode):
                labels[stmt.name] = offset + i
            # Recurse into loop bodies so labels inside loops are found
            loop_body = None
            if isinstance(stmt, DoLoopNode):
                loop_body = stmt.body
            elif isinstance(stmt, ForNode):
                loop_body = stmt.body
            elif isinstance(stmt, WhileNode):
                loop_body = stmt.body
            elif isinstance(stmt, RepeatNode):
                loop_body = stmt.body
            elif isinstance(stmt, IfNode):
                for _, branch_body in stmt.branches:
                    self._register_labels_in_body(branch_body, labels, offset + i + 1)
                if stmt.else_body:
                    self._register_labels_in_body(stmt.else_body, labels, offset + i + 1)
            if loop_body is not None:
                self._register_labels_in_body(loop_body, labels, offset + i + 1)
        return len(body)

    def eval_expression(self, expr: ExpressionNode) -> Any:
        if isinstance(expr, BinaryOpNode):
            return self._eval_binary_op(expr)
        elif isinstance(expr, UnaryOpNode):
            return self._eval_unary_op(expr)
        elif isinstance(expr, TernaryOpNode):
            return self._eval_ternary_op(expr)
        elif isinstance(expr, VariableAccessNode):
            return self._eval_variable_access(expr)
        elif isinstance(expr, FunctionCallNode):
            return self._eval_function_call(expr)
        elif isinstance(expr, LiteralNode):
            return self._eval_literal(expr)
        elif isinstance(expr, InlineCondNode):
            return self._eval_inline_cond(expr)
        elif isinstance(expr, BitPositionNode):
            return self._eval_bit_position(expr)
        elif isinstance(expr, FormatStringNode):
            # K-02: 格式化字符串作为表达式求值 (INFO_CLOCK_IMAGE / INFO_TIME_WATCH)
            return self._format_print_segments(expr.segments)
        else:
            raise ThrowSignal(f"Unknown expression type: {type(expr).__name__}")

    def exec_statement(self, stmt: StatementNode) -> None:
        if isinstance(stmt, AssignNode):
            self._exec_assign(stmt)
        elif isinstance(stmt, StringAssignNode):
            self._exec_string_assign(stmt)
        elif isinstance(stmt, IfNode):
            self._exec_if(stmt)
        elif isinstance(stmt, SifNode):
            self._exec_sif(stmt)
        elif isinstance(stmt, SelectCaseNode):
            self._exec_selectcase(stmt)
        elif isinstance(stmt, ForNode):
            self._exec_for(stmt)
        elif isinstance(stmt, WhileNode):
            self._exec_while(stmt)
        elif isinstance(stmt, DoLoopNode):
            self._exec_do_loop(stmt)
        elif isinstance(stmt, RepeatNode):
            self._exec_repeat(stmt)
        elif isinstance(stmt, CallNode):
            self._exec_call(stmt)
        elif isinstance(stmt, TrycCallformNode):
            self._exec_tryc_callform(stmt)
        elif isinstance(stmt, TrycallListNode):
            self._exec_trycall_list(stmt)
        elif isinstance(stmt, ReturnNode):
            self._exec_return(stmt)
        elif isinstance(stmt, PrintNode):
            self._exec_print(stmt)
        elif isinstance(stmt, InputNode):
            self._exec_input(stmt)
        elif isinstance(stmt, GotoNode):
            self._exec_goto(stmt)
        elif isinstance(stmt, LabelNode):
            pass
        elif isinstance(stmt, TimesNode):
            self._exec_times(stmt)
        elif isinstance(stmt, ThrowNode):
            self._exec_throw(stmt)
        elif isinstance(stmt, BeginNode):
            self._exec_begin(stmt)
        elif isinstance(stmt, BreakNode):
            raise BreakSignal()
        elif isinstance(stmt, ContinueNode):
            raise ContinueSignal()
        elif isinstance(stmt, VarsetNode):
            self._exec_varset(stmt)
        elif isinstance(stmt, PrintDataNode):
            self._exec_printdata(stmt)
        elif isinstance(stmt, VarDeclNode):
            self._exec_vardecl(stmt)
        else:
            raise ThrowSignal(f"Unknown statement type: {type(stmt).__name__}")

    def exec_block(self, stmts: list[StatementNode]) -> None:
        for stmt in stmts:
            self.exec_statement(stmt)

    def _eval_binary_op(self, node: BinaryOpNode) -> Any:
        op = node.op
        if op == "&&":
            left = self.eval_expression(node.left)
            if not left:
                return 0
            right = self.eval_expression(node.right)
            return 1 if right else 0
        if op == "||":
            left = self.eval_expression(node.left)
            if left:
                return 1
            right = self.eval_expression(node.right)
            return 1 if right else 0
        left = self.eval_expression(node.left)
        right = self.eval_expression(node.right)
        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return str(left) + str(right)
            return _wrap_int64(left + right)
        elif op == "-":
            return _wrap_int64(left - right)
        elif op == "*":
            return _wrap_int64(left * right)
        elif op == "/":
            if right == 0:
                # DEV-018: Return 0 on division by zero instead of crashing
                # This matches practical ERB patterns like status bar calculations
                # where max value is 0 before initialization
                return 0
            if _is_int(left) and _is_int(right):
                return _emuera_div(left, right)
            return int(left / right)
        elif op == "%":
            if right == 0:
                return 0
            if _is_int(left) and _is_int(right):
                return _emuera_mod(left, right)
            return left % right
        elif op == "**":
            return _wrap_int64(left ** right)
        elif op == "&":
            return _wrap_int64(int(left) & int(right))
        elif op == "|":
            return _wrap_int64(int(left) | int(right))
        elif op == "^":
            return _wrap_int64(int(left) ^ int(right))
        elif op == "<<":
            return _wrap_int64(int(left) << int(right))
        elif op == ">>":
            return int(left) >> int(right)
        elif op == "==":
            return 1 if left == right else 0
        elif op == "!=":
            return 1 if left != right else 0
        elif op == "<":
            return 1 if left < right else 0
        elif op == ">":
            return 1 if left > right else 0
        elif op == "<=":
            return 1 if left <= right else 0
        elif op == ">=":
            return 1 if left >= right else 0
        else:
            raise ThrowSignal(f"Unknown binary operator: {op}")

    def _eval_unary_op(self, node: UnaryOpNode) -> Any:
        op = node.op
        # K-01: 前缀 ++ / -- (Emuera PREINCREMENT/PREDECREMENT)
        # 语义: 读变量 → 加减1 → 写回 → 表达式结果为新值
        if op in ("++", "--") and isinstance(node.operand, VariableAccessNode):
            current = self._get_variable_value(node.operand)
            if current is None:
                current = 0
            try:
                current_int = int(current)
            except (ValueError, TypeError):
                current_int = 0
            new_val = _wrap_int64(current_int + 1) if op == "++" else _wrap_int64(current_int - 1)
            self._set_variable_value(node.operand, new_val)
            return new_val
        operand = self.eval_expression(node.operand)
        if op == "-":
            return -operand
        elif op == "!":
            return 1 if not operand else 0
        elif op == "~":
            return ~int(operand)
        else:
            raise ThrowSignal(f"Unknown unary operator: {op}")

    def _eval_ternary_op(self, node: TernaryOpNode) -> Any:
        cond = self.eval_expression(node.condition)
        if cond:
            return self.eval_expression(node.true_expr)
        else:
            return self.eval_expression(node.false_expr)

    def _eval_variable_access(self, node: VariableAccessNode) -> Any:
        return self._get_variable_value(node)

    def _eval_function_call(self, node: FunctionCallNode) -> Any:
        args = [self.eval_expression(arg) for arg in node.arguments]
        func_name = node.function_name
        if isinstance(func_name, str):
            upper_name = func_name.upper()
        else:
            upper_name = str(self.eval_expression(func_name)).upper()
        if upper_name in self.function_dispatch._builtins:
            return self.function_dispatch.call_builtin(upper_name, args)
        func_def = self.function_dispatch.get_function(upper_name)
        if func_def is not None:
            return self.call_function(upper_name, args)
        return 0

    def _eval_literal(self, node: LiteralNode) -> Any:
        return node.value

    def _eval_inline_cond(self, node: InlineCondNode) -> Any:
        cond = self.eval_expression(node.condition)
        if cond:
            return self.eval_expression(node.true_expr)
        else:
            return self.eval_expression(node.false_expr)

    def _eval_bit_position(self, node: BitPositionNode) -> int:
        return 1 << node.position

    def _exec_assign(self, node: AssignNode) -> None:
        value = self.eval_expression(node.value)
        op = node.op
        if op != "=":
            current = self._get_variable_value(node.target)
            if op == "+=":
                if isinstance(current, str) or isinstance(value, str):
                    value = str(current) + str(value)
                else:
                    value = _wrap_int64(current + value)
            elif op == "-=":
                value = _wrap_int64(current - value)
            elif op == "*=":
                value = _wrap_int64(current * value)
            elif op == "/=":
                if _is_int(current) and _is_int(value):
                    value = _emuera_div(current, value)
                elif value == 0:
                    value = 0
                else:
                    value = int(current / value)
            elif op == "%=":
                if _is_int(current) and _is_int(value):
                    value = _emuera_mod(current, value)
                elif value == 0:
                    value = 0
                else:
                    value = current % value
            elif op == "|=":
                value = _wrap_int64(int(current) | int(value))
            elif op == "&=":
                value = _wrap_int64(int(current) & int(value))
            elif op == "^=":
                value = _wrap_int64(int(current) ^ int(value))
            elif op == "<<=":
                value = _wrap_int64(int(current) << int(value))
            elif op == ">>=":
                value = int(current) >> int(value)
            else:
                raise ThrowSignal(f"Unknown assignment operator: {op}")
        desc = self.variable_mgr.get_descriptor(node.target.var_name)
        if desc is not None and desc.var_type == "int":
            if value is None:
                value = 0
            else:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = 0
        self._set_variable_value(node.target, value)

    def _exec_string_assign(self, node: StringAssignNode) -> None:
        value = self._eval_string_expression(node.value)
        self._set_variable_value(node.target, value)

    def _exec_if(self, node: IfNode) -> None:
        for condition, body in node.branches:
            if self.eval_expression(condition):
                self.exec_block(body)
                return
        if node.else_body is not None:
            self.exec_block(node.else_body)

    def _exec_sif(self, node: SifNode) -> None:
        if self.eval_expression(node.condition):
            self.exec_statement(node.then_body)

    def _exec_selectcase(self, node: SelectCaseNode) -> None:
        scrutinee = self.eval_expression(node.scrutinee)
        for case in node.cases:
            matched = False
            for val_expr in case.values:
                val = self.eval_expression(val_expr)
                if scrutinee == val:
                    matched = True
                    break
            if not matched:
                for low_expr, high_expr in case.ranges:
                    low = self.eval_expression(low_expr)
                    high = self.eval_expression(high_expr)
                    if low <= scrutinee <= high:
                        matched = True
                        break
            if matched:
                self.exec_block(case.body)
                return
        if node.case_else is not None:
            self.exec_block(node.case_else)

    def _exec_for(self, node: ForNode) -> None:
        start_val = int(self.eval_expression(node.start))
        end_val = int(self.eval_expression(node.end))
        step_val = int(self.eval_expression(node.step)) if node.step else 1
        if step_val == 0:
            raise ThrowSignal("FOR step cannot be zero")
        desc = self.variable_mgr.get_descriptor(node.var_name)
        if desc is not None and desc.dimensions > 0:
            indices = [0] * desc.dimensions
        else:
            indices = []
        if desc is not None:
            self.variable_mgr.set_value(node.var_name, indices, start_val)
        else:
            stored = False
            if self.variable_mgr._scope_stack:
                if node.var_name in self.variable_mgr._scope_stack[-1]:
                    self.variable_mgr._scope_stack[-1][node.var_name] = start_val
                    stored = True
            if not stored:
                ctx = self.call_stack[-1] if self.call_stack else None
                if ctx is not None:
                    ctx.local_vars[node.var_name] = start_val
        current = start_val
        while True:
            if step_val > 0 and current > end_val:
                break
            if step_val < 0 and current < end_val:
                break
            if desc is not None:
                self.variable_mgr.set_value(node.var_name, indices, current)
            else:
                stored = False
                if self.variable_mgr._scope_stack:
                    if node.var_name in self.variable_mgr._scope_stack[-1]:
                        self.variable_mgr._scope_stack[-1][node.var_name] = current
                        stored = True
                if not stored:
                    ctx = self.call_stack[-1] if self.call_stack else None
                    if ctx is not None:
                        ctx.local_vars[node.var_name] = current
            try:
                self.exec_block(node.body)
            except BreakSignal:
                break
            except ContinueSignal:
                pass
            current += step_val

    def _exec_while(self, node: WhileNode) -> None:
        while self.eval_expression(node.condition):
            try:
                self.exec_block(node.body)
            except BreakSignal:
                break
            except ContinueSignal:
                pass

    def _exec_do_loop(self, node: DoLoopNode) -> None:
        if node.condition_position == "until":
            while True:
                try:
                    self.exec_block(node.body)
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass
                if node.condition is not None and self.eval_expression(node.condition):
                    break
        elif node.condition_position in ("while", "post"):
            while True:
                try:
                    self.exec_block(node.body)
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass
                if node.condition is not None and not self.eval_expression(node.condition):
                    break
        else:
            while True:
                try:
                    self.exec_block(node.body)
                except BreakSignal:
                    break
                except ContinueSignal:
                    pass
                break

    def _exec_repeat(self, node: RepeatNode) -> None:
        count = int(self.eval_expression(node.count))
        for _ in range(count):
            try:
                self.exec_block(node.body)
            except BreakSignal:
                break
            except ContinueSignal:
                pass

    def _exec_call(self, node: CallNode) -> Any:
        args = [self.eval_expression(arg) for arg in node.arguments]
        if isinstance(node.function_name, str):
            func_name = node.function_name
        else:
            func_name = str(self.eval_expression(node.function_name))
        call_type = node.call_type
        if call_type == "RESTART":
            raise RestartSignal()
        elif call_type == "ADDCHARA":
            char_id = args[0] if args else self.variable_mgr.get_value("CHARANUM", [])
            self.variable_mgr.ensure_character(int(char_id))
            return
        elif call_type == "DELCHARA":
            char_id = args[0] if args else self.variable_mgr.get_value("CHARANUM", []) - 1
            self.variable_mgr.remove_character(int(char_id))
            return
        elif call_type in ("TRYCALL", "TRYCALLFORM"):
            func_def = self.function_dispatch.get_function(func_name)
            if func_def is None:
                return 0
            return self.call_function(func_name, args)
        elif call_type == "CALLFORM":
            return self.call_function(func_name, args)
        elif call_type == "JUMP":
            return self.call_function(func_name, args)
        else:
            return self.call_function(func_name, args)

    def _exec_tryc_callform(self, node: TrycCallformNode) -> Any:
        # DEV-009: 修复format_expression为list类型时的处理
        if isinstance(node.format_expression, list):
            # 如果是list，处理各种节点类型
            parts = []
            for e in node.format_expression:
                if hasattr(e, 'segment_type'):
                    # PrintSegmentNode
                    if hasattr(e, 'value') and e.value is not None:
                        if hasattr(e.value, 'value'):
                            parts.append(str(e.value.value))
                        else:
                            parts.append(str(e.value))
                elif hasattr(e, 'value'):
                    # LiteralNode或其他有value属性的节点
                    parts.append(str(e.value))
                elif hasattr(e, 'var_name'):
                    # VariableAccessNode
                    parts.append(str(self.eval_expression(e)))
                else:
                    parts.append(str(self.eval_expression(e)))
            format_result = "".join(parts)
        else:
            format_result = str(self.eval_expression(node.format_expression))
        args = [self.eval_expression(arg) for arg in node.arguments]
        func_def = self.function_dispatch.get_function(format_result)
        if func_def is not None:
            try:
                result = self.call_function(format_result, args)
                self.exec_block(node.try_body)
                return result
            except ThrowSignal:
                self.exec_block(node.catch_body)
                return 0
        else:
            self.exec_block(node.catch_body)
            return 0

    def _exec_trycall_list(self, node: TrycallListNode) -> Any:
        for entry in node.entries:
            if isinstance(entry.function_name, str):
                func_name = entry.function_name
            else:
                func_name = str(self.eval_expression(entry.function_name))
            args = [self.eval_expression(arg) for arg in entry.arguments]
            func_def = self.function_dispatch.get_function(func_name)
            if func_def is not None:
                return self.call_function(func_name, args)
        return 0

    def _exec_return(self, node: ReturnNode) -> None:
        value = None
        if node.value is not None:
            value = self.eval_expression(node.value)
        raise ReturnSignal(value=value, is_returnf=node.is_returnf)

    def _exec_print(self, node: PrintNode) -> None:
        text = self._format_print_segments(node.content)
        print_type = node.print_type
        newline = print_type.endswith("L") or print_type.endswith("W")
        wait = print_type.endswith("W")
        if print_type.startswith("PRINTV"):
            text = str(text)
        elif print_type.startswith("PRINTSL"):
            text = str(text)
        if node.alignment == "LEFT":
            pass
        elif node.alignment == "RIGHT":
            pass
        elif node.alignment == "CENTER":
            pass
        self.io_renderer.print_text(text, newline=newline, wait=wait)

    def _exec_input(self, node: InputNode) -> Any:
        timeout = None
        if node.timeout is not None:
            timeout = int(self.eval_expression(node.timeout))
        if node.input_type in ("INPUT", "ONEINPUT", "TINPUT", "TONEINPUT"):
            result = self.io_renderer.input_number(timeout=timeout)
            self.variable_mgr.set_value("RESULT", [], result)
            if node.timeout_var is not None:
                self.variable_mgr.set_value(node.timeout_var, [], 0)
            return result
        else:
            result = self.io_renderer.input_string(timeout=timeout)
            self.variable_mgr.set_value("RESULTS", [], result)
            if node.timeout_var is not None:
                self.variable_mgr.set_value(node.timeout_var, [], 0)
            return result

    def _exec_goto(self, node: GotoNode) -> None:
        raise GotoSignal(node.label)

    def _exec_times(self, node: TimesNode) -> None:
        current = self._get_variable_value(node.target)
        result = int(current * node.multiplier)
        self._set_variable_value(node.target, result)

    def _exec_throw(self, node: ThrowNode) -> None:
        message = str(self.eval_expression(node.message))
        raise ThrowSignal(message)

    def _exec_begin(self, node: BeginNode) -> None:
        raise BeginSignal(node.mode)

    def _exec_vardecl(self, node: VarDeclNode) -> None:
        var_name = node.name
        var_type = node.var_type
        is_str = var_type.upper() in ("DIMS", "STR", "SAVEDATA:STR")
        dims = node.dimensions
        # K-03: 求值所有维度（支持 #DIM X, A, B 多维声明）
        def _eval_dim(dim: Any) -> int:
            if isinstance(dim, int):
                return dim
            if isinstance(dim, LiteralNode) and dim.value is None:
                return 100  # 空维度槽位（连续逗号）
            try:
                return int(self.eval_expression(dim))
            except (TypeError, ValueError):
                return 100
        size_vals: list[int] = []
        if dims:
            size_vals = [_eval_dim(d) for d in dims]
        # DEV-16: Register #DIM declared variables as global variables
        # so they persist across function calls and can be accessed by other functions
        existing_desc = self.variable_mgr.get_descriptor(var_name)
        if existing_desc is None:
            if size_vals:
                desc = VariableDescriptor(
                    name=var_name,
                    var_type="str" if is_str else "int",
                    dimensions=len(size_vals),
                    default_size=size_vals,
                    is_temporary=False,
                )
                self.variable_mgr.register_variable(desc)
                self.variable_mgr._init_array_storage(desc)
            else:
                desc = VariableDescriptor(
                    name=var_name,
                    var_type="str" if is_str else "int",
                    dimensions=0,
                    is_temporary=False,
                )
                self.variable_mgr.register_variable(desc)
                default = "" if is_str else 0
                self.variable_mgr._scalar_storage[var_name] = default

        if size_vals:
            # 递归填充嵌套列表
            storage = self.variable_mgr._array_storage.get(var_name)
            if storage is not None and node.initial_values:
                self._fill_multidim(storage, size_vals, node.initial_values, is_str)
            # Also store in scope for immediate access
            if self.variable_mgr._scope_stack:
                self.variable_mgr._scope_stack[-1][var_name] = storage
        else:
            # DEV-17: When there are multiple initial_values but no explicit dimensions,
            # infer dimensions from the number of initial_values (Emuera behavior)
            if node.initial_values and len(node.initial_values) > 1:
                # Create array from initial values
                size = len(node.initial_values)
                if is_str:
                    storage = [""] * size
                else:
                    storage = [0] * size
                for i, val in enumerate(node.initial_values):
                    try:
                        evaled = self.eval_expression(val)
                    except Exception:
                        evaled = val
                    if is_str:
                        storage[i] = str(evaled) if not isinstance(evaled, str) else evaled
                    else:
                        try:
                            storage[i] = int(evaled)
                        except (TypeError, ValueError):
                            storage[i] = 0
                self.variable_mgr._array_storage[var_name] = storage
                if self.variable_mgr._scope_stack:
                    self.variable_mgr._scope_stack[-1][var_name] = storage
                # Register as array if not already registered with dimensions
                existing = self.variable_mgr.get_descriptor(var_name)
                if existing is not None and existing.dimensions == 0:
                    existing.dimensions = 1
                    existing.default_size = [size]
            else:
                default = "" if is_str else 0
                if node.initial_values:
                    try:
                        evaled = self.eval_expression(node.initial_values[0])
                    except Exception:
                        evaled = node.initial_values[0]
                    default = str(evaled) if is_str else int(evaled)
                self.variable_mgr._scalar_storage[var_name] = default
                if self.variable_mgr._scope_stack:
                    self.variable_mgr._scope_stack[-1][var_name] = default

    def _fill_multidim(self, storage: Any, size_vals: list[int], initial_values: list[Any], is_str: bool) -> None:
        """K-03: 按行主序将 initial_values 填充进多维嵌套列表。"""
        evaled: list[Any] = []
        for val in initial_values:
            try:
                v = self.eval_expression(val)
            except Exception:
                v = val
            if is_str:
                evaled.append(str(v) if not isinstance(v, str) else v)
            else:
                try:
                    evaled.append(int(v))
                except (TypeError, ValueError):
                    evaled.append(0)
        it = iter(evaled)
        self._fill_recursive(storage, size_vals, it)

    def _fill_recursive(self, node_list: Any, size_vals: list[int], it: Any) -> None:
        if len(size_vals) == 1:
            count = min(size_vals[0], len(node_list))
            for i in range(count):
                try:
                    node_list[i] = next(it)
                except StopIteration:
                    return
        else:
            count = min(size_vals[0], len(node_list))
            for i in range(count):
                self._fill_recursive(node_list[i], size_vals[1:], it)

    def _exec_varset(self, node: VarsetNode) -> None:
        var_name = node.target.var_name
        desc = self.variable_mgr.get_descriptor(var_name)
        value = 0
        if node.value is not None:
            value = self.eval_expression(node.value)
        else:
            if desc is not None:
                value = 0 if desc.var_type == "int" else ""
            else:
                value = 0
        start_idx = 0
        if node.start_index is not None:
            start_idx = int(self.eval_expression(node.start_index))
        end_idx = None
        if node.end_index is not None:
            end_idx = int(self.eval_expression(node.end_index))
        if desc is not None:
            if desc.dimensions == 0:
                self.variable_mgr.set_value(var_name, [], value)
            elif desc.dimensions >= 1:
                if end_idx is None:
                    storage = self.variable_mgr._array_storage.get(var_name)
                    if storage is not None:
                        if desc.dimensions == 1:
                            end_idx = len(storage)
                        elif desc.dimensions == 2 and desc.is_character_var:
                            target_val = self.variable_mgr.get_value("TARGET", [])
                            if target_val in storage:
                                end_idx = len(storage[target_val])
                            else:
                                end_idx = desc.default_size[0]
                        else:
                            end_idx = desc.default_size[0]
                    else:
                        end_idx = 0
                indices = self._resolve_variable_indices(node.target)
                base_indices = indices[:-1] if indices else []
                for i in range(start_idx, end_idx):
                    full_idx = base_indices + [i]
                    self.variable_mgr.set_value(var_name, full_idx, value)
        else:
            for scope in reversed(self.variable_mgr._scope_stack):
                if var_name in scope:
                    val = scope[var_name]
                    if isinstance(val, list):
                        for i in range(start_idx, len(val)):
                            val[i] = value
                    else:
                        scope[var_name] = value
                    break
            else:
                ctx = self.call_stack[-1] if self.call_stack else None
                if ctx is not None and var_name in ctx.local_vars:
                    ctx.local_vars[var_name] = value

    def _exec_printdata(self, node: PrintDataNode) -> None:
        if not node.entries:
            return
        if node.is_random:
            entry = random.choice(node.entries)
        else:
            entry = node.entries[0]
        if entry.entry_type == "DATA":
            text = str(entry.value)
        elif entry.entry_type == "DATAFORM":
            if isinstance(entry.value, list):
                text = self._format_print_segments(entry.value)
            else:
                text = str(entry.value)
        else:
            text = str(entry.value)
        self.io_renderer.print_text(text, newline=True, wait=False)

    def _resolve_variable_indices(self, node: VariableAccessNode) -> list[int]:
        indices: list[int] = []
        for idx_expr in node.indices:
            if isinstance(idx_expr, VariableAccessNode) and idx_expr.var_name not in self.variable_mgr._descriptors:
                is_local = False
                for scope in self.variable_mgr._scope_stack:
                    if idx_expr.var_name in scope:
                        is_local = True
                        break
                if not is_local:
                    resolved = self.variable_mgr.resolve_name(node.var_name, idx_expr.var_name)
                    indices.append(resolved)
                    continue
            val = self.eval_expression(idx_expr)
            if isinstance(val, str):
                try:
                    resolved = self.variable_mgr.resolve_name(node.var_name, val)
                    indices.append(resolved)
                except KeyError:
                    indices.append(0)
            else:
                indices.append(int(val))
        return indices

    def _get_variable_value(self, node: VariableAccessNode) -> Any:
        var_name = node.var_name
        desc = self.variable_mgr.get_descriptor(var_name)
        if desc is not None and desc.dimensions == 0 and not node.indices:
            return self.variable_mgr.get_value(var_name, [])
        indices = self._resolve_variable_indices(node)
        if desc is not None:
            if desc.dimensions >= 1 and not indices:
                indices = [0] * desc.dimensions
            return self.variable_mgr.get_value(var_name, indices)
        for scope in reversed(self.variable_mgr._scope_stack):
            if var_name in scope:
                val = scope[var_name]
                if isinstance(val, dict) and indices:
                    key = tuple(indices) if len(indices) > 1 else indices[0]
                    return val.get(key, 0)
                return val
        ctx = self.call_stack[-1] if self.call_stack else None
        if ctx is not None and var_name in ctx.local_vars:
            val = ctx.local_vars[var_name]
            if isinstance(val, dict) and indices:
                key = tuple(indices) if len(indices) > 1 else indices[0]
                return val.get(key, 0)
            return val
        if ctx is not None and var_name in ctx.parameters:
            return ctx.parameters[var_name]
        try:
            return self.variable_mgr.get_value(var_name, indices)
        except KeyError:
            return 0

    def _set_variable_value(self, node: VariableAccessNode, value: Any) -> None:
        var_name = node.var_name
        desc = self.variable_mgr.get_descriptor(var_name)
        if desc is not None and desc.is_readonly:
            raise ThrowSignal(f"Cannot assign to read-only variable '{var_name}'")
        # DEV-15: 只在值是数字类型时才转换为int，字符串保持原样
        if desc is not None and desc.var_type == "int" and not isinstance(value, str):
            try:
                value = int(value)
            except (ValueError, TypeError):
                pass  # 无法转换时保持原值
        if desc is not None and desc.dimensions == 0 and not node.indices:
            self.variable_mgr.set_value(var_name, [], value)
            return
        indices = self._resolve_variable_indices(node)
        if desc is not None:
            self.variable_mgr.set_value(var_name, indices, value)
        else:
            found_in_scope = False
            for scope in reversed(self.variable_mgr._scope_stack):
                if var_name in scope:
                    val = scope[var_name]
                    if isinstance(val, dict) and indices:
                        key = tuple(indices) if len(indices) > 1 else indices[0]
                        val[key] = value
                    elif not indices:
                        scope[var_name] = value
                    else:
                        new_dict: dict[Any, Any] = {}
                        key = tuple(indices) if len(indices) > 1 else indices[0]
                        new_dict[key] = value
                        scope[var_name] = new_dict
                    found_in_scope = True
                    break
            if not found_in_scope:
                ctx = self.call_stack[-1] if self.call_stack else None
                if ctx is not None:
                    if var_name not in ctx.local_vars:
                        ctx.local_vars[var_name] = {}
                    val = ctx.local_vars[var_name]
                    if isinstance(val, dict) and indices:
                        key = tuple(indices) if len(indices) > 1 else indices[0]
                        val[key] = value
                    elif not indices:
                        ctx.local_vars[var_name] = value
                    else:
                        new_dict2: dict[Any, Any] = {}
                        key = tuple(indices) if len(indices) > 1 else indices[0]
                        new_dict2[key] = value
                        ctx.local_vars[var_name] = new_dict2

    def _eval_string_expression(self, node: Any) -> str:
        if isinstance(node, str):
            return self._replace_percent_vars(node)
        elif isinstance(node, VariableAccessNode):
            val = self._get_variable_value(node)
            return str(val)
        elif isinstance(node, InlineCondNode):
            cond = self.eval_expression(node.condition)
            if cond:
                return str(self.eval_expression(node.true_expr))
            else:
                return str(self.eval_expression(node.false_expr))
        else:
            return str(self.eval_expression(node))

    def _replace_percent_vars(self, text: str) -> str:
        result: list[str] = []
        i = 0
        length = len(text)
        while i < length:
            if text[i] == "%" and i + 1 < length:
                end = text.find("%", i + 1)
                if end != -1:
                    var_name = text[i + 1:end]
                    try:
                        desc = self.variable_mgr.get_descriptor(var_name)
                        if desc is not None:
                            val = self.variable_mgr.get_value(var_name, [])
                            result.append(str(val))
                        else:
                            result.append(str(val) if (val := self._lookup_dynamic_var(var_name)) is not None else text[i:end + 1])
                    except (KeyError, ValueError):
                        result.append(text[i:end + 1])
                    i = end + 1
                    continue
            result.append(text[i])
            i += 1
        return "".join(result)

    def _lookup_dynamic_var(self, name: str) -> Any | None:
        ctx = self.call_stack[-1] if self.call_stack else None
        if ctx is not None:
            if name in ctx.local_vars:
                return ctx.local_vars[name]
            if name in ctx.parameters:
                return ctx.parameters[name]
            if name in ctx.dynamic_vars:
                return ctx.dynamic_vars[name]
        return None

    def _format_print_segments(self, segments: list[PrintSegmentNode]) -> str:
        parts: list[str] = []
        for seg in segments:
            seg_type = seg.segment_type
            if seg_type == "text":
                # DEV-17: seg.value may be a LiteralNode instead of a string
                if hasattr(seg.value, 'value'):
                    parts.append(str(seg.value.value))
                else:
                    parts.append(str(seg.value))
            elif seg_type == "variable":
                if isinstance(seg.value, VariableAccessNode):
                    val = self._get_variable_value(seg.value)
                    parts.append(str(val))
                else:
                    val = self.eval_expression(seg.value)
                    parts.append(str(val))
            elif seg_type == "expression":
                val = self.eval_expression(seg.value)
                parts.append(str(val))
            elif seg_type == "inline_cond":
                val = self.eval_expression(seg.value)
                parts.append(str(val))
            else:
                parts.append(str(seg.value))
        return "".join(parts)
