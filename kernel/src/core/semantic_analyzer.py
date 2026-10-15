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
        self._registered_names: set[str] | None = None

    def _ensure_registered_names(self) -> set[str]:
        """收集已注册全局变量名 + CSV 名表键（合法数据表列名，免 #DIM）。

        惰性收集：装配阶段 semantic_analyzer 创建时 CSV 尚未加载，
        首次 check_programs 时（CSV 已入 variable_mgr）才真正收集。
        """
        if self._registered_names is not None:
            return self._registered_names
        self._registered_names = set()
        descs = getattr(self._variable_mgr, "_descriptors", None)
        if descs:
            for _n, _d in descs.items():
                self._registered_names.add(_n.upper())
                _nm = getattr(_d, "name_map", None)
                if _nm:
                    for _k in _nm.keys():
                        self._registered_names.add(str(_k).upper())
        return self._registered_names

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

    # ── 跨函数语义校验（对齐 C# 引擎 ErbLoader / LogicalLineParser /
    #    Process.CalledFunction / IdentifierDictionary / FunctionIdentifier 的 7 条硬规则）。
    #    目的：保证实机测试前把"编译 0 错、加载即中止"的语义问题完整暴露。
    #
    # 规则码 → C# 取证：
    #   SEMA-01 参数名必须是 ARG/ARGS/私有变量          ErbLoader.cs:556-599
    #   SEMA-02 普通 CALL 调 #FUNCTION 函数            Process.CalledFunction.cs:119
    #   SEMA-03 #FUNCTION 函数体内使用普通 CALL        ErbLoader.cs:873
    #   SEMA-04 无 #FUNCTION 函数作表达式项            IdentifierDictionary.cs:590-592
    #   SEMA-05 同函数内 #DIM 重复声明                 LogicalLineParser.cs:254-264
    #   SEMA-06 使用未 #DIM 声明的局部变量             （Emuera 局部作用域语义）
    #   SEMA-07 #FUNCTION 内使用非 METHOD_SAFE 指令    ErbLoader.cs:869-875 /
    #           （输入等待类 INPUT/WAIT、跨函数跳转 BEGIN）  FunctionIdentifier.cs:16

    # SEMA-07：非 METHOD_SAFE 指令（#FUNCTION 内使用即被 C# 判为 isError 行 → 加载中止）
    # 取证：INPUT 族 flag = IS_PRINT|IS_INPUT（Instraction.Child.cs:621/647/674/709/742/778）；
    #       WAIT=TWAIT/WAITANYKEY flag 均无 METHOD_SAFE（:562/580/593）；BEGIN = FLOW_CONTROL（:1674）。
    # 注：控制流（IF/FOR/RETURN）与 SETCOLOR 等属 METHOD_SAFE，不在此列——避免误报。
    _METHOD_UNSAFE_IN_FUNCTION: set[str] = {
        "INPUT", "INPUTS", "ONEINPUT", "ONEINPUTS",
        "TINPUT", "TINPUTS", "TONEINPUT", "TONEINPUTS",
        "WAIT", "TWAIT", "WAITANYKEY", "FORCEWAIT",
        "BEGIN",
    }

    # 合法函数参数名（与 C# VariableCode.ARG/ARGS 对齐）
    _LEGIT_PARAM_NAMES: set[str] = {"ARG", "ARGS"}
    # 私有局部变量前缀（#DIM 声明的本地变量）
    _LOCAL_PREFIXES: tuple[str, ...] = ("LOCAL", "LOCALS", "MEMO", "MEMOS", "VAR", "VARS")
    # 内置/全局变量与目标变量（免 #DIM 声明，对齐 C# 全局命名空间）
    _BUILTIN_GLOBAL_NAMES: set[str] = {
        "ARG", "ARGS", "TARGET", "PLAYER", "SOURCE", "RESULT", "SELECT",
        "SELECTCASE", "NOWORD_JUMP", "GLOBAL", "CHARANUM", "LINENO",
        "LOCAL", "LOCALS", "MEMO", "MEMOS", "VAR", "VARS",
        # ALIGNMENT 指令的取值关键词（非变量，但会出现在表达式位置）
        "LEFT", "CENTER", "RIGHT", "DEFAULT",
    }

    def check_programs(self, programs: list[ProgramNode]) -> list[str]:
        """跨函数语义校验，返回诊断清单（每行一条：规则码 + 说明 + 定位）。

        设计原则：
        - 只读，不改 AST（与 _visit_* 一致）；
        - 命中规则即记录，不抛异常（对齐 C# ParserMediator.Warn 语义，
          硬错误类在实机加载时才会中止——本校验的职责是"提前暴露"）；
        - 返回纯文本行，由 engine 侧按 WARNING 类别落 _monitor_events。
        """
        diagnostics: list[str] = []
        func_names: set[str] = set()
        is_function_names: set[str] = set()  # 声明了 #FUNCTION(S) 的函数

        # 合法"全局/数据表名"白名单：已注册变量名 + 各 name_map 键（CSV 数据表列名），
        # 这些名字是合法的数据表访问标识符，不属于"未声明局部变量"。
        registered_names = self._ensure_registered_names()

        # ── 第一遍：收集函数名与 #FUNCTION 声明 ──
        for prog in programs:
            for f in prog.functions:
                func_names.add(f.name.upper())
                if f.is_function or f.is_functions:
                    is_function_names.add(f.name.upper())

        # ── 第二遍：逐函数检查 ──
        for prog in programs:
            for f in prog.functions:
                fname = f.name.upper()
                file = f.source_file or ""
                line = f.line
                # 该函数内已 #DIM 声明的局部变量（私有变量）
                declared_locals: set[str] = set()
                for stmt in f.body:
                    if isinstance(stmt, VarDeclNode):
                        declared_locals.add(stmt.name.upper())

                is_func_decl = f.is_function or f.is_functions

                # #DIM CONST 常量（C# 内联展开的常量字面量，如 等待/逃离）
                declared_consts: set[str] = set()
                for stmt in f.body:
                    if isinstance(stmt, VarDeclNode) and "CONST" in stmt.modifiers:
                        for val in stmt.initial_values:
                            if isinstance(val, str):
                                declared_consts.add(val.upper())

                # SEMA-01 参数名合法性
                # 对齐 C# ErbLoader.cs:571-599：参数可赋值的条件 =
                #   (1) VariableCode.ARG/ARGS（内置参数变量），或
                #   (2) Identifier.IsPrivate（函数内 #DIM 声明的私有变量）
                # 自定义全局名（TYPE/WHO/ENEMY/LOCAL1 未 #DIM 者等）→ 报 "无法解释标识符"
                for p in f.parameters:
                    pname = p.name.upper()
                    base = pname.split(":")[0].split("(")[0]
                    if base in self._LEGIT_PARAM_NAMES:
                        continue
                    if base in declared_locals:
                        continue  # 私有变量（函数内已 #DIM）——C# IsPrivate 分支
                    diagnostics.append(
                        f"SEMA-01 @{f.name} 参数 '{p.name}' 必须是 ARG/ARGS 或 #DIM 私有变量"
                        f" [SEMA-01] {file}:{line}"
                    )

                # SEMA-05 #DIM 重复
                seen_dims: set[str] = set()
                for stmt in f.body:
                    if isinstance(stmt, VarDeclNode):
                        key = stmt.name.upper()
                        if key in seen_dims:
                            diagnostics.append(
                                f"SEMA-05 @{f.name} 局部变量 '{stmt.name}' 已 #DIM 过，重复声明"
                                f" [SEMA-05] {file}:{line}"
                            )
                        seen_dims.add(key)

                # 遍历函数体（收集 SEMA-03/04/06）
                used_locals: set[str] = set()

                def _check_assign_lhs(
                    target,
                    declared_locals: set[str],
                    registered_names: set[str],
                    fname: str,
                    file: str,
                    line: int,
                    is_func_decl: bool,
                    used_locals: set[str],
                ) -> None:
                    """SEMA-06：赋值 LHS 位置的裸自定义名 = 局部变量使用点。

                    仅当 LHS 是"纯标识符、无下标、未 #DIM、非内置/注册全局"
                    的自定义名时才报——即真正的"使用但未声明"局部变量。
                    """
                    if target is None or not isinstance(target, VariableAccessNode):
                        return
                    if len(target.indices) > 0:
                        return
                    base = target.var_name.upper()
                    if not base.isidentifier():
                        return
                    if any(base.startswith(prefix) for prefix in self._LOCAL_PREFIXES):
                        return
                    if base in declared_locals:
                        return
                    if base in declared_consts:
                        return
                    if base in self._BUILTIN_GLOBAL_NAMES:
                        return
                    if base in registered_names:
                        return
                    if base in func_names or base in is_function_names:
                        return
                    used_locals.add(base)

                def _walk_stmt(node: StatementNode) -> None:
                    if isinstance(node, CallNode):
                        # SEMA-03 #FUNCTION 函数体内出现普通 CALL（针对用户函数）。
                        # 仅当目标是"已定义的用户函数"时报；内置指令（SETCOLOR 等）
                        # 不转移控制流，C# 允许在 #FUNCTION 内使用，故不报。
                        target = node.function_name.upper() if isinstance(node.function_name, str) else ""
                        if is_func_decl:
                            if target in func_names:
                                diagnostics.append(
                                    f"SEMA-03 @{f.name}（#FUNCTION）内禁止普通 CALL 用户函数 '{node.function_name}'"
                                    f" [SEMA-03] {file}:{line}"
                                )
                            # SEMA-07 输入等待类指令（WAIT/TWAIT/WAITANYKEY）非 METHOD_SAFE
                            if target in self._METHOD_UNSAFE_IN_FUNCTION:
                                diagnostics.append(
                                    f"SEMA-07 @{f.name}（#FUNCTION）内禁止 {target}（非 METHOD_SAFE：输入等待类指令）"
                                    f" [SEMA-07] {file}:{line}"
                                )
                        for a in node.arguments:
                            _walk_expr(a, in_func=is_func_decl)
                        return
                    if isinstance(node, InputNode):
                        # SEMA-07 INPUT 族（含 TINPUT/ONEINPUT 等）非 METHOD_SAFE
                        if is_func_decl:
                            diagnostics.append(
                                f"SEMA-07 @{f.name}（#FUNCTION）内禁止 {node.input_type}（非 METHOD_SAFE：输入等待类指令）"
                                f" [SEMA-07] {file}:{line}"
                            )
                        return
                    if isinstance(node, BeginNode):
                        # SEMA-07 BEGIN 跨函数跳转非 METHOD_SAFE
                        if is_func_decl:
                            diagnostics.append(
                                f"SEMA-07 @{f.name}（#FUNCTION）内禁止 BEGIN（非 METHOD_SAFE：跨函数跳转）"
                                f" [SEMA-07] {file}:{line}"
                            )
                        return
                    if isinstance(node, TrycCallformNode):
                        for a in node.arguments:
                            _walk_expr(a, in_func=is_func_decl)
                        return  # 表达式形态，合法
                    if isinstance(node, VarDeclNode):
                        return
                    # 赋值语句：遍历 LHS（SEMA-06）+ RHS 表达式（SEMA-04 / SEMA-06）
                    if isinstance(node, AssignNode):
                        _check_assign_lhs(node.target, declared_locals, registered_names,
                                          f.name, file, line, is_func_decl, used_locals)
                        _walk_expr(node.value, in_func=is_func_decl)
                        return
                    if isinstance(node, StringAssignNode):
                        _check_assign_lhs(node.target, declared_locals, registered_names,
                                          f.name, file, line, is_func_decl, used_locals)
                        _walk_expr(node.value, in_func=is_func_decl)
                        return
                    if isinstance(node, CaseNode):
                        for v in node.values:
                            _walk_expr(v, in_func=is_func_decl)
                        for lo, hi in node.ranges:
                            _walk_expr(lo, in_func=is_func_decl)
                            _walk_expr(hi, in_func=is_func_decl)
                        for s in node.body:
                            _walk_stmt(s)
                        return
                    # 递归子语句
                    for attr in ("body", "then_body", "else_body", "try_body", "catch_body"):
                        val = getattr(node, attr, None)
                        if isinstance(val, list):
                            for s in val:
                                if isinstance(s, StatementNode):
                                    _walk_stmt(s)
                        elif isinstance(val, StatementNode):
                            _walk_stmt(val)
                    # 条件/表达式子树
                    for attr in ("condition", "count", "start", "end", "step", "scrutinee"):
                        val = getattr(node, attr, None)
                        if val is not None:
                            _walk_expr(val, in_func=is_func_decl)

                def _walk_expr(expr: ExpressionNode, in_func: bool) -> None:
                    if expr is None:
                        return
                    if isinstance(expr, FunctionCallNode):
                        # SEMA-04 无 #FUNCTION 函数作表达式项
                        target = expr.function_name.upper()
                        if target in func_names and target not in is_function_names:
                            diagnostics.append(
                                f"SEMA-04 函数 '{expr.function_name}' 未声明 #FUNCTION，不能作为表达式项"
                                f" [SEMA-04] {file}:{line}"
                            )
                        for a in expr.arguments:
                            _walk_expr(a, in_func)
                        return
                    if isinstance(expr, BinaryOpNode):
                        _walk_expr(expr.left, in_func)
                        _walk_expr(expr.right, in_func)
                        return
                    if isinstance(expr, UnaryOpNode):
                        _walk_expr(expr.operand, in_func)
                        return
                    if isinstance(expr, TernaryOpNode):
                        _walk_expr(expr.condition, in_func)
                        _walk_expr(expr.true_expr, in_func)
                        _walk_expr(expr.false_expr, in_func)
                        return
                    if isinstance(expr, InlineCondNode):
                        _walk_expr(expr.condition, in_func)
                        _walk_expr(expr.true_expr, in_func)
                        _walk_expr(expr.false_expr, in_func)
                        return
                    if isinstance(expr, VariableAccessNode):
                        # SEMA-06 在"赋值 LHS 位置"由 _check_assign_lhs 处理；
                        # 表达式位置（RHS / 条件 / 下标）的 bare 名视为合法
                        # 常量/名表键/字面量，不做 SEMA-06 检查（保守口径，
                        # 避免 #DIM CONST 内联展开与 CSV 名表列名误报）。
                        return
                    # FormatStringNode 等其余表达式类型：递归其内嵌表达式段
                    segs = getattr(expr, "segments", None)
                    if isinstance(segs, list):
                        for seg in segs:
                            seg_val = getattr(seg, "value", None)
                            if seg_val is not None:
                                _walk_expr(seg_val, in_func)

                # 遍历 body 与 If/SelectCase 等容器内的表达式
                for stmt in f.body:
                    _walk_stmt(stmt)
                    # IfNode / SifNode / DoLoop / While / Repeat 的条件在 _walk_stmt 内递归
                    if isinstance(stmt, IfNode):
                        for cond, _b in stmt.branches:
                            _walk_expr(cond, in_func=is_func_decl)
                    elif isinstance(stmt, SifNode):
                        _walk_expr(stmt.condition, in_func=is_func_decl)

                # SEMA-06 汇总：used_locals 此时已只含"纯标识符、未 #DIM、非内置、
                # 未注册全局"的变量名——即真正的"使用但未声明"局部变量。
                for v in sorted(used_locals):
                    diagnostics.append(
                        f"SEMA-06 @{f.name} 使用局部变量 '{v}' 但未 #DIM 声明"
                        f" [SEMA-06] {file}:{line}"
                    )

        # ── 第三遍：SEMA-02 普通 CALL 调 #FUNCTION 函数（全局）──
        if is_function_names:
            for prog in programs:
                for f in prog.functions:
                    if f.name.upper() in is_function_names:
                        continue  # #FUNCTION 自身调用 #FUNCTION 合法（表达式）
                    def _find_calls(node: StatementNode) -> None:
                        if isinstance(node, CallNode) and isinstance(node.function_name, str):
                            target = node.function_name.upper()
                            if target in is_function_names and target in func_names:
                                diagnostics.append(
                                    f"SEMA-02 @{f.name} 对 #FUNCTION 函数 '{node.function_name}' 使用普通 CALL，"
                                    f"应在表达式中调用（CALLFORM） [SEMA-02] {f.source_file}:{f.line}"
                                )
                        for attr in ("body", "then_body", "else_body", "try_body", "catch_body"):
                            val = getattr(node, attr, None)
                            if isinstance(val, list):
                                for s in val:
                                    if isinstance(s, StatementNode):
                                        _find_calls(s)
                            elif isinstance(val, StatementNode):
                                _find_calls(val)
                    for stmt in f.body:
                        _find_calls(stmt)

        return diagnostics

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
        return InlineCondNode(condition=new_condition, true_expr=new_true, false_expr=new_false)
