from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass(frozen=True)
class ProgramNode:
    functions: list[FunctionDefNode]
    source_file: str


@dataclass(frozen=True)
class FunctionDefNode:
    name: str
    parameters: list[ParameterNode]
    body: list[StatementNode]
    is_function: bool = False
    is_functions: bool = False
    line: int = 0
    source_file: str = ""


@dataclass(frozen=True)
class ParameterNode:
    name: str
    is_ref: bool = False
    default_value: Any = None


@dataclass(frozen=True)
class VarDeclNode:
    var_type: str
    name: str
    dimensions: list[int] = field(default_factory=list)
    initial_values: list[Any] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    is_chara_data: bool = False


@dataclass(frozen=True)
class AssignNode:
    target: VariableAccessNode
    value: ExpressionNode
    op: str = "="


@dataclass(frozen=True)
class StringAssignNode:
    target: VariableAccessNode
    value: StringExpressionNode
    is_raw: bool = False
    op: str = "+="
    format_segments: list | None = None


@dataclass(frozen=True)
class IfNode:
    branches: list[tuple[ExpressionNode, list[StatementNode]]]
    else_body: list[StatementNode] | None


@dataclass(frozen=True)
class SifNode:
    condition: ExpressionNode
    then_body: StatementNode


@dataclass(frozen=True)
class SelectCaseNode:
    scrutinee: ExpressionNode
    cases: list[CaseNode]
    case_else: list[StatementNode] | None


@dataclass(frozen=True)
class CaseNode:
    values: list[ExpressionNode] = field(default_factory=list)
    ranges: list[tuple[ExpressionNode, ExpressionNode]] = field(default_factory=list)
    body: list[StatementNode] = field(default_factory=list)


@dataclass(frozen=True)
class ForNode:
    var_name: str
    var_index: ExpressionNode | None = None
    start: ExpressionNode = None
    end: ExpressionNode = None
    step: ExpressionNode | None = None
    body: list[StatementNode] = None


@dataclass(frozen=True)
class WhileNode:
    condition: ExpressionNode
    body: list[StatementNode]


@dataclass(frozen=True)
class DoLoopNode:
    condition: ExpressionNode | None
    condition_position: str
    body: list[StatementNode]


@dataclass(frozen=True)
class RepeatNode:
    count: ExpressionNode
    body: list[StatementNode]


@dataclass(frozen=True)
class CallNode:
    function_name: str | ExpressionNode
    arguments: list[ExpressionNode] = field(default_factory=list)
    call_type: str = "CALL"
    has_catch: bool = False
    format_expression: list | None = None


@dataclass(frozen=True)
class TrycCallformNode:
    format_expression: ExpressionNode | list
    arguments: list[ExpressionNode] = field(default_factory=list)
    try_body: list[StatementNode] = field(default_factory=list)
    catch_body: list[StatementNode] = field(default_factory=list)


@dataclass(frozen=True)
class TrycallListNode:
    entries: list[CallEntryNode] = field(default_factory=list)
    endfunc: bool = True


@dataclass(frozen=True)
class CallEntryNode:
    function_name: str | ExpressionNode
    arguments: list[ExpressionNode] = field(default_factory=list)


@dataclass(frozen=True)
class ReturnNode:
    value: ExpressionNode | None
    is_returnf: bool = False


@dataclass(frozen=True)
class PrintNode:
    content: list[PrintSegmentNode] = field(default_factory=list)
    print_type: str = "PRINTL"
    alignment: str | None = None


@dataclass(frozen=True)
class PrintSegmentNode:
    segment_type: str
    value: str | ExpressionNode
    width: ExpressionNode | None = None
    alignment: ExpressionNode | None = None


@dataclass(frozen=True)
class InputNode:
    input_type: str
    timeout: ExpressionNode | None = None
    timeout_var: str | None = None
    mouse_support: bool = False


@dataclass(frozen=True)
class GotoNode:
    label: str


@dataclass(frozen=True)
class LabelNode:
    name: str


@dataclass(frozen=True)
class TimesNode:
    target: VariableAccessNode
    multiplier: float


@dataclass(frozen=True)
class ThrowNode:
    message: ExpressionNode
    format_segments: list | None = None


@dataclass(frozen=True)
class BeginNode:
    mode: str


@dataclass(frozen=True)
class BreakNode:
    pass


@dataclass(frozen=True)
class ContinueNode:
    pass


@dataclass(frozen=True)
class VarsetNode:
    target: VariableAccessNode
    value: ExpressionNode | None
    start_index: ExpressionNode | None
    end_index: ExpressionNode | None


@dataclass(frozen=True)
class PrintDataNode:
    entries: list[PrintDataEntryNode] = field(default_factory=list)
    is_random: bool = True


@dataclass(frozen=True)
class PrintDataEntryNode:
    entry_type: str
    value: str | list[PrintSegmentNode]


@dataclass(frozen=True)
class BinaryOpNode:
    op: str
    left: ExpressionNode
    right: ExpressionNode


@dataclass(frozen=True)
class UnaryOpNode:
    op: str
    operand: ExpressionNode
    is_postfix: bool = False


@dataclass(frozen=True)
class TernaryOpNode:
    condition: ExpressionNode
    true_expr: ExpressionNode
    false_expr: ExpressionNode


@dataclass(frozen=True)
class VariableAccessNode:
    var_name: str
    indices: list[ExpressionNode] = field(default_factory=list)
    implicit_target: bool = False


@dataclass(frozen=True)
class FunctionCallNode:
    function_name: str
    arguments: list[ExpressionNode] = field(default_factory=list)


@dataclass(frozen=True)
class LiteralNode:
    value: int | float | str


@dataclass(frozen=True)
class InlineCondNode:
    condition: ExpressionNode
    true_expr: ExpressionNode
    false_expr: ExpressionNode


@dataclass(frozen=True)
class BitPositionNode:
    position: int


@dataclass(frozen=True)
class FormatStringNode:
    segments: list[PrintSegmentNode]


ExpressionNode = Union[
    BinaryOpNode,
    UnaryOpNode,
    TernaryOpNode,
    VariableAccessNode,
    FunctionCallNode,
    LiteralNode,
    InlineCondNode,
    BitPositionNode,
    FormatStringNode,
]

StatementNode = Union[
    AssignNode,
    StringAssignNode,
    IfNode,
    SifNode,
    SelectCaseNode,
    ForNode,
    WhileNode,
    DoLoopNode,
    RepeatNode,
    CallNode,
    TrycCallformNode,
    TrycallListNode,
    ReturnNode,
    PrintNode,
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
]

StringExpressionNode = Union[
    str,
    VariableAccessNode,
    InlineCondNode,
]
