from __future__ import annotations

from .ast_nodes import (
    ProgramNode,
    FunctionDefNode,
    ParameterNode,
    VarDeclNode,
    AssignNode,
    StringAssignNode,
    IfNode,
    SifNode,
    SelectCaseNode,
    CaseNode,
    ForNode,
    WhileNode,
    DoLoopNode,
    RepeatNode,
    CallNode,
    TrycCallformNode,
    TrycallListNode,
    CallEntryNode,
    ReturnNode,
    PrintNode,
    PrintSegmentNode,
    InputNode,
    GotoNode,
    LabelNode,
    TimesNode,
    ThrowNode,
    BeginNode,
    BreakNode,
    ContinueNode,
    VarsetNode,
    PrintDataNode,
    PrintDataEntryNode,
    BinaryOpNode,
    UnaryOpNode,
    TernaryOpNode,
    VariableAccessNode,
    FunctionCallNode,
    LiteralNode,
    InlineCondNode,
    BitPositionNode,
    ExpressionNode,
    StatementNode,
    StringExpressionNode,
)
from .variable_manager import VariableManager


CHARACTER_VARIABLES: set[str] = {
    "BASE", "MAXBASE", "ABL", "TALENT", "EXP", "MARK", "PALAM", "SOURCE",
    "CUP", "CDOWN", "STAIN", "TEQUIP", "EQUIP", "DOWNBASE", "CFLAG", "CSTR",
    "TCVAR", "JUEL", "NOWEX", "EX", "RELATION", "CDFLAG",
}


class SemanticAnalyzer:

    def __init__(self, variable_mgr: VariableManager) -> None:
        self._variable_mgr = variable_mgr
        self._warnings: list[str] = []

    def analyze(self, program: ProgramNode) -> ProgramNode:
        self._warnings.clear()
        return self._visit_program(program)

    def resolve_implicit_target(self, node: VariableAccessNode) -> VariableAccessNode:
        if node.var_name not in CHARACTER_VARIABLES:
            return node
        descriptor = self._variable_mgr.get_descriptor(node.var_name)
        if descriptor is None:
            return node
        if len(node.indices) < descriptor.dimensions:
            target_ref = VariableAccessNode("TARGET", [], implicit_target=False)
            return VariableAccessNode(
                var_name=node.var_name,
                indices=[target_ref] + list(node.indices),
                implicit_target=True,
            )
        return node

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    def _visit_program(self, node: ProgramNode) -> ProgramNode:
        new_functions = [self._visit_function_def(f) for f in node.functions]
        return ProgramNode(functions=new_functions, source_file=node.source_file)

    def _visit_function_def(self, node: FunctionDefNode) -> FunctionDefNode:
        new_body = [self._visit_statement(s) for s in node.body]
        return FunctionDefNode(
            name=node.name,
            parameters=node.parameters,
            body=new_body,
            is_function=node.is_function,
            is_functions=node.is_functions,
            line=node.line,
            source_file=node.source_file,
        )

    def _visit_statement(self, node: StatementNode) -> StatementNode:
        if isinstance(node, AssignNode):
            return self._visit_assign(node)
        if isinstance(node, StringAssignNode):
            return self._visit_string_assign(node)
        if isinstance(node, IfNode):
            return self._visit_if(node)
        if isinstance(node, SifNode):
            return self._visit_sif(node)
        if isinstance(node, SelectCaseNode):
            return self._visit_selectcase(node)
        if isinstance(node, ForNode):
            return self._visit_for(node)
        if isinstance(node, WhileNode):
            return self._visit_while(node)
        if isinstance(node, DoLoopNode):
            return self._visit_do_loop(node)
        if isinstance(node, RepeatNode):
            return self._visit_repeat(node)
        if isinstance(node, CallNode):
            return self._visit_call(node)
        if isinstance(node, TrycCallformNode):
            return self._visit_tryc_callform(node)
        if isinstance(node, TrycallListNode):
            return self._visit_trycall_list(node)
        if isinstance(node, ReturnNode):
            return self._visit_return(node)
        if isinstance(node, PrintNode):
            return self._visit_print(node)
        if isinstance(node, InputNode):
            return self._visit_input(node)
        if isinstance(node, TimesNode):
            return self._visit_times(node)
        if isinstance(node, ThrowNode):
            return self._visit_throw(node)
        if isinstance(node, VarsetNode):
            return self._visit_varset(node)
        if isinstance(node, PrintDataNode):
            return self._visit_print_data(node)
        if isinstance(node, (GotoNode, LabelNode, BeginNode, BreakNode, ContinueNode)):
            return node
        return node

    def _visit_expression(self, node: ExpressionNode) -> ExpressionNode:
        if isinstance(node, BinaryOpNode):
            return self._visit_binary_op(node)
        if isinstance(node, UnaryOpNode):
            return self._visit_unary_op(node)
        if isinstance(node, TernaryOpNode):
            return self._visit_ternary_op(node)
        if isinstance(node, VariableAccessNode):
            return self._visit_variable_access(node)
        if isinstance(node, FunctionCallNode):
            return self._visit_function_call(node)
        if isinstance(node, InlineCondNode):
            return self._visit_inline_cond(node)
        if isinstance(node, (LiteralNode, BitPositionNode)):
            return node
        return node

    def _visit_variable_access(self, node: VariableAccessNode) -> VariableAccessNode:
        new_indices = [self._visit_expression(idx) for idx in node.indices]
        temp_node = VariableAccessNode(
            var_name=node.var_name,
            indices=new_indices,
            implicit_target=node.implicit_target,
        )
        result = self.resolve_implicit_target(temp_node)
        if self._variable_mgr.get_descriptor(result.var_name) is None:
            self._warnings.append(f"Variable '{result.var_name}' is not registered")
        return result

    def _visit_assign(self, node: AssignNode) -> AssignNode:
        new_target = self._visit_variable_access(node.target)
        new_value = self._visit_expression(node.value)
        return AssignNode(target=new_target, value=new_value, op=node.op)

    def _visit_string_assign(self, node: StringAssignNode) -> StringAssignNode:
        new_target = self._visit_variable_access(node.target)
        new_value = self._visit_string_expression(node.value)
        return StringAssignNode(target=new_target, value=new_value, is_raw=node.is_raw)

    def _visit_string_expression(self, node: StringExpressionNode) -> StringExpressionNode:
        if isinstance(node, str):
            return node
        if isinstance(node, VariableAccessNode):
            return self._visit_variable_access(node)
        if isinstance(node, InlineCondNode):
            return self._visit_inline_cond(node)
        return node

    def _visit_if(self, node: IfNode) -> IfNode:
        new_branches = [
            (self._visit_expression(cond), [self._visit_statement(s) for s in body])
            for cond, body in node.branches
        ]
        new_else = (
            [self._visit_statement(s) for s in node.else_body]
            if node.else_body is not None
            else None
        )
        return IfNode(branches=new_branches, else_body=new_else)

    def _visit_sif(self, node: SifNode) -> SifNode:
        new_condition = self._visit_expression(node.condition)
        new_then = self._visit_statement(node.then_body)
        return SifNode(condition=new_condition, then_body=new_then)

    def _visit_selectcase(self, node: SelectCaseNode) -> SelectCaseNode:
        new_scrutinee = self._visit_expression(node.scrutinee)
        new_cases = [self._visit_case(c) for c in node.cases]
        new_else = (
            [self._visit_statement(s) for s in node.case_else]
            if node.case_else is not None
            else None
        )
        return SelectCaseNode(scrutinee=new_scrutinee, cases=new_cases, case_else=new_else)

    def _visit_case(self, node: CaseNode) -> CaseNode:
        new_values = [self._visit_expression(v) for v in node.values]
        new_ranges = [
            (self._visit_expression(lo), self._visit_expression(hi))
            for lo, hi in node.ranges
        ]
        new_body = [self._visit_statement(s) for s in node.body]
        return CaseNode(values=new_values, ranges=new_ranges, body=new_body)

    def _visit_for(self, node: ForNode) -> ForNode:
        new_start = self._visit_expression(node.start)
        new_end = self._visit_expression(node.end)
        new_step = self._visit_expression(node.step) if node.step is not None else None
        new_body = [self._visit_statement(s) for s in node.body]
        return ForNode(
            var_name=node.var_name,
            start=new_start,
            end=new_end,
            step=new_step,
            body=new_body,
        )

    def _visit_while(self, node: WhileNode) -> WhileNode:
        new_condition = self._visit_expression(node.condition)
        new_body = [self._visit_statement(s) for s in node.body]
        return WhileNode(condition=new_condition, body=new_body)

    def _visit_do_loop(self, node: DoLoopNode) -> DoLoopNode:
        new_condition = (
            self._visit_expression(node.condition) if node.condition is not None else None
        )
        new_body = [self._visit_statement(s) for s in node.body]
        return DoLoopNode(
            condition=new_condition,
            condition_position=node.condition_position,
            body=new_body,
        )

    def _visit_repeat(self, node: RepeatNode) -> RepeatNode:
        new_count = self._visit_expression(node.count)
        new_body = [self._visit_statement(s) for s in node.body]
        return RepeatNode(count=new_count, body=new_body)

    def _visit_call(self, node: CallNode) -> CallNode:
        new_name = (
            self._visit_expression(node.function_name)
            if not isinstance(node.function_name, str)
            else node.function_name
        )
        new_args = [self._visit_expression(a) for a in node.arguments]
        return CallNode(
            function_name=new_name,
            arguments=new_args,
            call_type=node.call_type,
            has_catch=node.has_catch,
        )

    def _visit_tryc_callform(self, node: TrycCallformNode) -> TrycCallformNode:
        new_format = self._visit_expression(node.format_expression)
        new_args = [self._visit_expression(a) for a in node.arguments]
        new_try = [self._visit_statement(s) for s in node.try_body]
        new_catch = [self._visit_statement(s) for s in node.catch_body]
        return TrycCallformNode(
            format_expression=new_format,
            arguments=new_args,
            try_body=new_try,
            catch_body=new_catch,
        )

    def _visit_trycall_list(self, node: TrycallListNode) -> TrycallListNode:
        new_entries = [self._visit_call_entry(e) for e in node.entries]
        return TrycallListNode(entries=new_entries, endfunc=node.endfunc)

    def _visit_call_entry(self, node: CallEntryNode) -> CallEntryNode:
        new_name = (
            self._visit_expression(node.function_name)
            if not isinstance(node.function_name, str)
            else node.function_name
        )
        new_args = [self._visit_expression(a) for a in node.arguments]
        return CallEntryNode(function_name=new_name, arguments=new_args)

    def _visit_return(self, node: ReturnNode) -> ReturnNode:
        new_value = self._visit_expression(node.value) if node.value is not None else None
        return ReturnNode(value=new_value, is_returnf=node.is_returnf)

    def _visit_print(self, node: PrintNode) -> PrintNode:
        new_content = [self._visit_print_segment(s) for s in node.content]
        return PrintNode(
            content=new_content,
            print_type=node.print_type,
            alignment=node.alignment,
        )

    def _visit_print_segment(self, node: PrintSegmentNode) -> PrintSegmentNode:
        if isinstance(node.value, str):
            return node
        new_value = self._visit_expression(node.value)
        return PrintSegmentNode(segment_type=node.segment_type, value=new_value, width=node.width, alignment=node.alignment)

    def _visit_input(self, node: InputNode) -> InputNode:
        new_timeout = (
            self._visit_expression(node.timeout) if node.timeout is not None else None
        )
        return InputNode(
            input_type=node.input_type,
            timeout=new_timeout,
            timeout_var=node.timeout_var,
            mouse_support=node.mouse_support,
        )

    def _visit_times(self, node: TimesNode) -> TimesNode:
        new_target = self._visit_variable_access(node.target)
        return TimesNode(target=new_target, multiplier=node.multiplier)

    def _visit_throw(self, node: ThrowNode) -> ThrowNode:
        new_message = self._visit_expression(node.message)
        return ThrowNode(message=new_message)

    def _visit_varset(self, node: VarsetNode) -> VarsetNode:
        new_target = self._visit_variable_access(node.target)
        new_value = self._visit_expression(node.value) if node.value is not None else None
        new_start = (
            self._visit_expression(node.start_index) if node.start_index is not None else None
        )
        new_end = (
            self._visit_expression(node.end_index) if node.end_index is not None else None
        )
        return VarsetNode(
            target=new_target,
            value=new_value,
            start_index=new_start,
            end_index=new_end,
        )

    def _visit_print_data(self, node: PrintDataNode) -> PrintDataNode:
        new_entries = [self._visit_print_data_entry(e) for e in node.entries]
        return PrintDataNode(entries=new_entries, is_random=node.is_random)

    def _visit_print_data_entry(self, node: PrintDataEntryNode) -> PrintDataEntryNode:
        if isinstance(node.value, str):
            return node
        # DEV-012: 处理value不是list的情况（如VariableAccessNode）
        if not isinstance(node.value, list):
            return node
        new_value = [self._visit_print_segment(s) for s in node.value]
        return PrintDataEntryNode(entry_type=node.entry_type, value=new_value)

    def _visit_binary_op(self, node: BinaryOpNode) -> BinaryOpNode:
        new_left = self._visit_expression(node.left)
        new_right = self._visit_expression(node.right)
        return BinaryOpNode(op=node.op, left=new_left, right=new_right)

    def _visit_unary_op(self, node: UnaryOpNode) -> UnaryOpNode:
        new_operand = self._visit_expression(node.operand)
        return UnaryOpNode(op=node.op, operand=new_operand)

    def _visit_ternary_op(self, node: TernaryOpNode) -> TernaryOpNode:
        new_condition = self._visit_expression(node.condition)
        new_true = self._visit_expression(node.true_expr)
        new_false = self._visit_expression(node.false_expr)
        return TernaryOpNode(
            condition=new_condition,
            true_expr=new_true,
            false_expr=new_false,
        )

    def _visit_function_call(self, node: FunctionCallNode) -> FunctionCallNode:
        new_args = [self._visit_expression(a) for a in node.arguments]
        return FunctionCallNode(function_name=node.function_name, arguments=new_args)

    def _visit_inline_cond(self, node: InlineCondNode) -> InlineCondNode:
        new_condition = self._visit_expression(node.condition)
        new_true = self._visit_expression(node.true_expr)
        new_false = self._visit_expression(node.false_expr)
        return InlineCondNode(
            condition=new_condition,
            true_expr=new_true,
            false_expr=new_false,
        )
