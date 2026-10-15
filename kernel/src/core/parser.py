from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tokens import Token, TokenType
from .lexer import Lexer
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
    FormatStringNode,
    ExpressionNode,
    StatementNode,
    StringExpressionNode,
)


class ParserError(Exception):

    def __init__(
        self,
        message: str,
        filename: str = "",
        line: int = 0,
        expected: TokenType | None = None,
        actual: Token | None = None,
    ):
        self.filename = filename
        self.line = line
        self.expected = expected
        self.actual = actual
        detail = message
        if filename:
            detail = f"{filename}:{line}: {message}"
        if expected is not None and actual is not None:
            detail += f" (expected {expected.value}, got {actual.type.value} '{actual.value}')"
        super().__init__(detail)


class Parser:

    _CALL_TYPES = frozenset({
        TokenType.CALL,
        TokenType.TRYCALL,
        TokenType.CALLFORM,
        TokenType.TRYCALLFORM,
        TokenType.CALLFORMF,
        TokenType.TRYCALLFORMF,
        TokenType.JUMP,
        TokenType.DOTRAIN,
    })

    _PRINT_TYPES = frozenset({
        TokenType.PRINT,
        TokenType.PRINTL,
        TokenType.PRINTW,
        TokenType.PRINTC,
        TokenType.PRINTLC,
        TokenType.PRINTDL,
        TokenType.PRINTV,
        TokenType.PRINTVL,
        TokenType.PRINTS,
        TokenType.PRINTSL,
        TokenType.PRINTFORM,
        TokenType.PRINTFORML,
        TokenType.PRINTFORMW,
        TokenType.PRINTFORMC,
        TokenType.PRINTFORMLC,
        TokenType.PRINTFORMDC,
        TokenType.PRINTFORMD,
        TokenType.PRINTFORMDL,
        TokenType.PRINTFORMDW,
        TokenType.PRINTFORMS,
        TokenType.DEBUGPRINT,
        TokenType.DEBUGPRINTL,
        TokenType.DEBUGPRINTW,
        TokenType.DEBUGPRINTFORM,
        TokenType.DEBUGPRINTFORML,
        TokenType.DEBUGPRINTFORMW,
        TokenType.PRINTSINGLEFORM,
        TokenType.PRINTSINGLEFORMS,
        TokenType.PRINTPLAINFORM,
        TokenType.PRINTPLAIN,
        TokenType.HTML_PRINT,
        TokenType.PRINTSW,
        TokenType.SPRITEDISPOSE,
    })

    _PRINTFORM_TYPES = frozenset({
        TokenType.PRINTFORM,
        TokenType.PRINTFORML,
        TokenType.PRINTFORMW,
        TokenType.PRINTFORMC,
        TokenType.PRINTFORMLC,
        TokenType.PRINTFORMDC,
        TokenType.PRINTFORMD,
        TokenType.PRINTFORMDL,
        TokenType.PRINTFORMDW,
        TokenType.PRINTFORMS,
        TokenType.DEBUGPRINTFORM,
        TokenType.DEBUGPRINTFORML,
        TokenType.DEBUGPRINTFORMW,
        TokenType.PRINTSINGLEFORM,
        TokenType.PRINTSINGLEFORMS,
        TokenType.PRINTPLAINFORM,
        TokenType.SPRITEDISPOSE,
    })

    _STATEMENT_STARTERS = frozenset({
        TokenType.IF,
        TokenType.SIF,
        TokenType.SELECTCASE,
        TokenType.FOR,
        TokenType.WHILE,
        TokenType.DO,
        TokenType.REPEAT,
        TokenType.CALL,
        TokenType.TRYCALL,
        TokenType.CALLFORM,
        TokenType.TRYCALLFORM,
        TokenType.TRYCCALLFORM,
        TokenType.TRYCALLLIST,
        TokenType.CALLFORMF,
        TokenType.TRYCALLFORMF,
        TokenType.RETURN,
        TokenType.RETURNF,
        TokenType.PRINT,
        TokenType.PRINTL,
        TokenType.PRINTW,
        TokenType.PRINTDL,
        TokenType.PRINTV,
        TokenType.PRINTVL,
        TokenType.PRINTSL,
        TokenType.PRINTFORM,
        TokenType.PRINTFORML,
        TokenType.PRINTFORMW,
        TokenType.PRINTFORMC,
        TokenType.PRINTFORMLC,
        TokenType.PRINTFORMDC,
        TokenType.PRINTFORMD,
        TokenType.PRINTFORMDL,
        TokenType.PRINTFORMDW,
        TokenType.PRINTFORMS,
        TokenType.PRINTDATA,
        TokenType.PRINTDATAL,
        TokenType.DATALIST,
        TokenType.DATAFORM,
        TokenType.INPUT,
        TokenType.INPUTS,
        TokenType.ONEINPUT,
        TokenType.ONEINPUTS,
        TokenType.TINPUT,
        TokenType.TINPUTS,
        TokenType.TONEINPUT,
        TokenType.TONEINPUTS,
        TokenType.GOTO,
        TokenType.LABEL,
        TokenType.TIMES,
        TokenType.THROW,
        TokenType.BEGIN,
        TokenType.VARSET,
        TokenType.INVERTBIT,
        TokenType.GETBIT,
        TokenType.SETBIT,
        TokenType.CLEARBIT,
        TokenType.ADDCHARA,
        TokenType.DELCHARA,
        TokenType.SAVEDATA,
        TokenType.LOADDATA,
        TokenType.LOADGLOBAL,
        TokenType.SAVEGLOBAL,
        TokenType.BREAK,
        TokenType.CONTINUE,
        TokenType.JUMP,
        TokenType.DOTRAIN,
        TokenType.WAIT,
        TokenType.TWAIT,
        TokenType.DRAWLINE,
        TokenType.DRAWLINEFORM,
        TokenType.CLEARLINE,
        TokenType.REDRAW,
        TokenType.CUSTOMDRAWLINE,
        TokenType.SETCOLOR,
        TokenType.RESETCOLOR,
        TokenType.PRINTBUTTON,
        TokenType.PRINTBUTTONC,
        TokenType.BAR,
        TokenType.RESTART,
        TokenType.COMMENT,
        TokenType.IF_DEBUG,
        TokenType.DEBUGPRINT,
        TokenType.DEBUGPRINTL,
        TokenType.DEBUGPRINTW,
        TokenType.DEBUGPRINTFORM,
        TokenType.DEBUGPRINTFORML,
        TokenType.DEBUGPRINTFORMW,
        TokenType.PRINTSINGLEFORM,
        TokenType.PRINTSINGLEFORMS,
        TokenType.PRINTPLAINFORM,
        TokenType.PRINTPLAIN,
        TokenType.HTML_PRINT,
        TokenType.ALIGNMENT,
        TokenType.GETTIME,
        TokenType.RESETDATA,
        TokenType.LOADGAME,
        TokenType.SAVEGAME,
        TokenType.SPLIT,
        TokenType.FONTSTYLE,
        TokenType.SETFONT,
        TokenType.SAVECHARA,
        TokenType.LOADCHARA,
        TokenType.STRLENFORMU,
        TokenType.STRLENFORM,
        TokenType.PUTFORM,
        TokenType.REUSELASTLINE,
        TokenType.PRINTSW,
        TokenType.SPRITEDISPOSE,
        TokenType.SKIPDISP,
        TokenType.SETBGCOLOR,
        TokenType.RESETBGCOLOR,
        TokenType.ARRAYCOPY,
        TokenType.SWAP,
        TokenType.ADDCOPYCHARA,
        TokenType.SETLINECOUNT,
        TokenType.GETLINECOUNT,
        TokenType.CHKSPEED,
    })

    def __init__(self, variable_metadata: Any):
        self._variable_metadata = variable_metadata
        self._tokens: list[Token] = []
        self._pos: int = 0
        self._current_filename: str = ""
        self._local_var_types: dict[str, str] = {}
        self._in_printform: bool = False
        self._paren_depth: int = 0

    def parse(self, tokens: list[Token]) -> ProgramNode:
        self._tokens = tokens
        self._pos = 0
        self._current_filename = tokens[0].filename if tokens else ""
        self._local_var_types = {}
        self._in_printform = False
        self._paren_depth = 0
        return self._parse_program()

    def parse_function(self, tokens: list[Token]) -> FunctionDefNode:
        self._tokens = tokens
        self._pos = 0
        self._current_filename = tokens[0].filename if tokens else ""
        self._local_var_types = {}
        self._in_printform = False
        return self._parse_function_def()

    def parse_expression(self, tokens: list[Token]) -> ExpressionNode:
        self._tokens = tokens
        self._pos = 0
        self._current_filename = tokens[0].filename if tokens else ""
        return self._parse_expression()

    def _peek(self) -> Token | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _peek_next(self) -> Token | None:
        if self._pos + 1 < len(self._tokens):
            return self._tokens[self._pos + 1]
        return None

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _check(self, token_type: TokenType) -> bool:
        tok = self._peek()
        return tok is not None and tok.type == token_type

    def _match(self, *types: TokenType) -> bool:
        for t in types:
            if self._check(t):
                self._advance()
                return True
        return False

    def _expect(self, token_type: TokenType) -> Token:
        tok = self._peek()
        if tok is None or tok.type != token_type:
            raise ParserError(
                f"Expected {token_type.value}",
                filename=self._current_filename,
                line=tok.line if tok else 0,
                expected=token_type,
                actual=tok,
            )
        return self._advance()

    def _is_at_end(self) -> bool:
        return self._pos >= len(self._tokens) or (self._peek() is not None and self._peek().type == TokenType.EOF)

    def _consume_newline_or_eof(self) -> None:
        while self._check(TokenType.COMMENT):
            self._advance()
        if self._check(TokenType.NEWLINE):
            self._advance()
        elif not self._is_at_end():
            pass

    def _skip_newlines(self) -> None:
        while self._check(TokenType.NEWLINE):
            self._advance()

    def _parse_program(self) -> ProgramNode:
        functions: list[FunctionDefNode] = []
        self._skip_newlines()
        while not self._is_at_end():
            if self._check(TokenType.AT):
                functions.append(self._parse_function_def())
            else:
                self._advance()
            self._skip_newlines()
        return ProgramNode(functions=functions, source_file=self._current_filename)

    def _parse_function_def(self) -> FunctionDefNode:
        at_tok = self._expect(TokenType.AT)
        self._current_filename = at_tok.filename
        name = at_tok.value
        if not name:
            if self._check(TokenType.IDENTIFIER):
                name = self._advance().value
            elif self._check(TokenType.VARIABLE):
                name = self._advance().value
        parameters: list[ParameterNode] = []
        if self._check(TokenType.LPAREN):
            self._advance()
            if not self._check(TokenType.RPAREN):
                parameters = self._parse_param_list()
            self._expect(TokenType.RPAREN)
        elif self._check(TokenType.COMMA):
            self._advance()
            parameters = self._parse_param_list_no_parens()
        self._consume_newline_or_eof()
        body = self._parse_function_body()
        is_function = False
        is_functions = False
        for stmt in body:
            if isinstance(stmt, VarDeclNode):
                if stmt.var_type.upper() == "FUNCTION":
                    is_function = True
                elif stmt.var_type.upper() == "FUNCTIONS":
                    is_functions = True
        return FunctionDefNode(
            name=name,
            parameters=parameters,
            body=body,
            is_function=is_function,
            is_functions=is_functions,
            line=at_tok.line,
            source_file=self._current_filename,
        )

    def _parse_single_param(self) -> ParameterNode | None:
        is_ref = False
        if self._check(TokenType.REF):
            self._advance()
            is_ref = True
        name_tok = self._peek()
        if name_tok is None or name_tok.type not in (TokenType.IDENTIFIER, TokenType.VARIABLE):
            return None
        name = self._advance().value
        while self._check(TokenType.COLON):
            self._advance()
            idx_tok = self._peek()
            if idx_tok is not None and idx_tok.type in (TokenType.INTEGER, TokenType.IDENTIFIER, TokenType.VARIABLE):
                idx = self._advance().value
                name = f"{name}:{idx}"
            else:
                break
        default_value = None
        if self._check(TokenType.ASSIGN):
            self._advance()
            tok = self._peek()
            if tok is None or tok.type in (TokenType.NEWLINE, TokenType.RPAREN, TokenType.COMMA):
                default_value = None
            elif tok is not None and tok.type == TokenType.STRING:
                default_value = self._advance().value
            elif tok is not None and tok.type == TokenType.INTEGER:
                default_value = self._advance().value
            elif tok is not None and tok.type == TokenType.MINUS:
                self._advance()
                num_tok = self._peek()
                if num_tok is not None and num_tok.type == TokenType.INTEGER:
                    default_value = -self._advance().value
                else:
                    default_value = 0
            else:
                # Support expression default values like OBJ_ID_FIRST
                try:
                    default_value = self._parse_expression()
                except ParserError:
                    default_value = None
        return ParameterNode(name=name, is_ref=is_ref, default_value=default_value)

    def _parse_param_list(self) -> list[ParameterNode]:
        params: list[ParameterNode] = []
        param = self._parse_single_param()
        if param is not None:
            params.append(param)
        while self._check(TokenType.COMMA):
            self._advance()
            param = self._parse_single_param()
            if param is not None:
                params.append(param)
            else:
                break
        return params

    def _parse_param_list_no_parens(self) -> list[ParameterNode]:
        params: list[ParameterNode] = []
        while not self._check(TokenType.NEWLINE) and not self._is_at_end():
            param = self._parse_single_param()
            if param is None:
                break
            params.append(param)
            if not self._check(TokenType.COMMA):
                break
            self._advance()
        return params

    def _parse_function_body(self) -> list[StatementNode]:
        body: list[StatementNode] = []
        self._skip_newlines()
        while not self._is_at_end() and not self._check(TokenType.AT):
            self._skip_newlines()
            if self._is_at_end() or self._check(TokenType.AT):
                break
            stmt = self._parse_statement_or_decl()
            if stmt is not None:
                body.append(stmt)
            self._skip_newlines()
        return body

    def _parse_statement_or_decl(self) -> StatementNode | None:
        tok = self._peek()
        if tok is None:
            return None
        if tok.type == TokenType.HASH:
            return self._parse_var_decl()
        if tok.type == TokenType.COMMENT:
            self._advance()
            self._consume_newline_or_eof()
            return None
        if tok.type == TokenType.IF_DEBUG:
            self._advance()
            self._consume_newline_or_eof()
            while not self._is_at_end():
                if self._peek().type == TokenType.ENDIF_DEBUG:
                    self._advance()
                    self._consume_newline_or_eof()
                    break
                self._advance()
            return None
        if tok.type == TokenType.ENDIF_DEBUG:
            self._advance()
            self._consume_newline_or_eof()
            return None
        if tok.type == TokenType.LABEL:
            return self._parse_label()
        return self._parse_statement()

    def _parse_var_decl(self) -> VarDeclNode:
        self._expect(TokenType.HASH)
        var_type_tok = self._advance()
        var_type = var_type_tok.value.upper()
        if var_type == "DIM":
            var_type = "int"
        elif var_type == "DIMS":
            var_type = "str"
        name_tok = self._advance()
        name = name_tok.value
        if isinstance(name, int):
            name = str(name)
        modifiers: list[str] = []
        # Handle CONST and DYNAMIC modifiers between type and variable name
        # e.g. #DIM CONST SLOT_LEFT, 20 = 7,2,4,5,3
        while name.upper() in ("CONST", "DYNAMIC", "REF") or name_tok.type in (TokenType.CONST, TokenType.DYNAMIC, TokenType.REF):
            mod_name = name.upper()
            if name_tok.type == TokenType.CONST:
                mod_name = "CONST"
            elif name_tok.type == TokenType.DYNAMIC:
                mod_name = "DYNAMIC"
            elif name_tok.type == TokenType.REF:
                mod_name = "REF"
            modifiers.append(mod_name)
            name_tok = self._advance()
            name = name_tok.value
            if isinstance(name, int):
                name = str(name)
        dimensions: list[int] = []
        while self._check(TokenType.LPAREN):
            self._advance()
            if not self._check(TokenType.RPAREN):
                dim_expr = self._parse_expression()
                # 归一化：纯整数字面量转 int，与逗号分支行为一致
                if isinstance(dim_expr, LiteralNode) and isinstance(dim_expr.value, int):
                    dim_expr = dim_expr.value
                dimensions.append(dim_expr)
            while self._check(TokenType.COMMA):
                self._advance()
                if not self._check(TokenType.RPAREN):
                    dim_expr = self._parse_expression()
                    if isinstance(dim_expr, LiteralNode) and isinstance(dim_expr.value, int):
                        dim_expr = dim_expr.value
                    dimensions.append(dim_expr)
            if self._check(TokenType.RPAREN):
                self._advance()
        is_chara_data = False
        while self._check(TokenType.COMMA):
            self._advance()
            # Handle trailing comma: stop if at newline, comment, or end
            if self._check(TokenType.NEWLINE) or self._check(TokenType.COMMENT) or self._is_at_end():
                break
            # Handle consecutive commas (empty dimension slot): skip them
            if self._check(TokenType.COMMA):
                dimensions.append(LiteralNode(value=None))
                continue
            if self._check(TokenType.INTEGER):
                saved_pos = self._pos
                dim_val = self._advance().value
                next_tok = self._peek()
                if next_tok is not None and next_tok.type in (TokenType.STAR, TokenType.PLUS, TokenType.MINUS, TokenType.SLASH, TokenType.PERCENT):
                    self._pos = saved_pos
                    dim_expr = self._parse_expression()
                    dimensions.append(dim_expr)
                else:
                    dimensions.append(int(dim_val))
                continue
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                dim_expr = self._parse_expression()
                dimensions.append(dim_expr)
        initial_values: list[Any] = []
        if self._match(TokenType.ASSIGN):
            initial_values = self._parse_initial_values()
        self._consume_newline_or_eof()
        self._local_var_types[name.upper()] = var_type
        return VarDeclNode(
            var_type=var_type,
            name=name,
            dimensions=dimensions,
            initial_values=initial_values,
            modifiers=modifiers,
            is_chara_data=is_chara_data,
        )

    def _parse_initial_values(self) -> list[Any]:
        values: list[Any] = []
        if self._check(TokenType.NEWLINE) or self._check(TokenType.COMMENT) or self._is_at_end():
            return values
        values.append(self._parse_expression())
        while self._check(TokenType.COMMA):
            self._advance()
            if self._check(TokenType.NEWLINE) or self._check(TokenType.COMMENT) or self._is_at_end():
                break
            values.append(self._parse_expression())
        return values

    def _parse_statement(self) -> StatementNode:
        tok = self._peek()
        if tok is None:
            raise ParserError("Unexpected end of input", filename=self._current_filename)
        tt = tok.type
        # Standalone '{' line indicates Emuera code block start
        if tt == TokenType.LBRACE:
            return self._parse_brace_block()
        if tt == TokenType.IF:
            return self._parse_if()
        if tt == TokenType.SIF:
            return self._parse_sif()
        if tt == TokenType.SELECTCASE:
            return self._parse_selectcase()
        if tt == TokenType.FOR:
            return self._parse_for()
        if tt == TokenType.WHILE:
            return self._parse_while()
        if tt == TokenType.DO:
            return self._parse_do_loop()
        if tt == TokenType.REPEAT:
            return self._parse_repeat()
        if tt in self._CALL_TYPES:
            return self._parse_call()
        if tt == TokenType.TRYCCALLFORM:
            return self._parse_tryc_callform()
        if tt == TokenType.TRYCALLLIST:
            return self._parse_trycall_list()
        if tt == TokenType.RETURN:
            return self._parse_return()
        if tt == TokenType.RETURNF:
            return self._parse_returnf()
        if tt in self._PRINT_TYPES:
            return self._parse_print()
        if tt == TokenType.PRINTDATA or tt == TokenType.PRINTDATAL:
            return self._parse_printdata()
        if tt in (TokenType.INPUT, TokenType.INPUTS, TokenType.ONEINPUT, TokenType.ONEINPUTS,
                  TokenType.TINPUT, TokenType.TINPUTS, TokenType.TONEINPUT, TokenType.TONEINPUTS):
            return self._parse_input()
        if tt == TokenType.GOTO:
            return self._parse_goto()
        if tt == TokenType.TIMES:
            return self._parse_times()
        if tt == TokenType.THROW:
            return self._parse_throw()
        if tt == TokenType.BEGIN:
            return self._parse_begin()
        if tt == TokenType.VARSET:
            return self._parse_varset()
        if tt in (TokenType.INVERTBIT, TokenType.SETBIT, TokenType.CLEARBIT, TokenType.GETBIT):
            return self._parse_bit_op()
        if tt == TokenType.ADDCHARA:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="ADDCHARA", arguments=args, call_type="ADDCHARA")
        if tt == TokenType.DELCHARA:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="DELCHARA", arguments=args, call_type="DELCHARA")
        if tt == TokenType.SAVEDATA:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="SAVEDATA", arguments=args, call_type="SAVEDATA")
        if tt == TokenType.LOADDATA:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="LOADDATA", arguments=args, call_type="LOADDATA")
        if tt == TokenType.LOADGLOBAL:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="LOADGLOBAL", arguments=[], call_type="LOADGLOBAL")
        if tt == TokenType.SAVEGLOBAL:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="SAVEGLOBAL", arguments=[], call_type="SAVEGLOBAL")
        if tt == TokenType.GETTIME:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="GETTIME", arguments=[], call_type="GETTIME")
        if tt == TokenType.CURRENTREDRAW:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="CURRENTREDRAW", arguments=[], call_type="CURRENTREDRAW")
        if tt == TokenType.ALIGNMENT:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                arg = self._parse_expression()
                self._consume_newline_or_eof()
                return CallNode(function_name="ALIGNMENT", arguments=[arg], call_type="ALIGNMENT")
            self._consume_newline_or_eof()
            return CallNode(function_name="ALIGNMENT", arguments=[], call_type="ALIGNMENT")
        if tt == TokenType.RESETDATA:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="RESETDATA", arguments=[], call_type="RESETDATA")
        if tt == TokenType.LOADGAME:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="LOADGAME", arguments=[], call_type="LOADGAME")
        if tt == TokenType.SAVEGAME:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="SAVEGAME", arguments=[], call_type="SAVEGAME")
        if tt == TokenType.SPLIT:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="SPLIT", arguments=args, call_type="SPLIT")
        if tt == TokenType.ENDDATA:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="ENDDATA", arguments=[], call_type="NOOP")
        if tt == TokenType.ENDLIST:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="ENDLIST", arguments=[], call_type="NOOP")
        # DEV-001/002/003/004: CHKDATA, SWAPCHARA, COPYCHARA, SORTCHARA, CHKFONT, DELDATA
        if tt in (TokenType.CHKDATA, TokenType.CHKFONT, TokenType.SORTCHARA,
                  TokenType.SWAPCHARA, TokenType.COPYCHARA, TokenType.PICKUPCHARA,
                  TokenType.DELDATA):
            return self._parse_builtin_function()
        # K-01: 前缀 ++VAR / --VAR 作为语句（等价 VAR = VAR ± 1）
        if tt in (TokenType.INCREMENT, TokenType.DECREMENT):
            self._advance()
            operand = self._parse_unary()
            if not isinstance(operand, VariableAccessNode):
                raise ParserError(
                    f"++/-- requires a variable operand, got {type(operand).__name__}",
                    filename=self._current_filename,
                    line=self._peek().line if self._peek() else None,
                )
            inc_op = "+" if tt == TokenType.INCREMENT else "-"
            self._consume_newline_or_eof()
            return AssignNode(target=operand, value=BinaryOpNode(op=inc_op, left=operand, right=LiteralNode(value=1)))
        if tt in (TokenType.VARIABLE, TokenType.IDENTIFIER):
            return self._parse_assignment_or_expr()
        if tt in (TokenType.RAND, TokenType.ABS, TokenType.SIGN, TokenType.MAX, TokenType.MIN, TokenType.GETBIT,
                  TokenType.POWER_FUNC, TokenType.SQRT, TokenType.FINDELEMENT, TokenType.FINDCHARA,
                  TokenType.STRLENS, TokenType.STRLENSU, TokenType.SUBSTRING, TokenType.SUBSTRINGU,
                  TokenType.CHARATU, TokenType.REPLACE, TokenType.SPLIT, TokenType.STRCOUNT,
                  TokenType.STRFIND, TokenType.STRFINDU,
                  TokenType.TOSTR, TokenType.TOINT, TokenType.LIMIT):
            return self._parse_builtin_function()
        if tt == TokenType.BREAK:
            self._advance()
            self._consume_newline_or_eof()
            return BreakNode()
        if tt == TokenType.CONTINUE:
            self._advance()
            self._consume_newline_or_eof()
            return ContinueNode()
        if tt == TokenType.JUMP:
            return self._parse_call()
        if tt == TokenType.DOTRAIN:
            return self._parse_call()
        if tt == TokenType.WAIT:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="WAIT", arguments=[], call_type="WAIT")
        if tt == TokenType.DRAWLINE:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="DRAWLINE", arguments=[], call_type="DRAWLINE")
        if tt == TokenType.DRAWLINEFORM:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                arg = self._parse_expression()
                self._consume_newline_or_eof()
                return CallNode(function_name="DRAWLINEFORM", arguments=[arg], call_type="DRAWLINEFORM")
            self._consume_newline_or_eof()
            return CallNode(function_name="DRAWLINEFORM", arguments=[], call_type="DRAWLINEFORM")
        if tt == TokenType.CLEARLINE:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                arg = self._parse_expression()
                self._consume_newline_or_eof()
                return CallNode(function_name="CLEARLINE", arguments=[arg], call_type="CLEARLINE")
            self._consume_newline_or_eof()
            return CallNode(function_name="CLEARLINE", arguments=[], call_type="CLEARLINE")
        if tt == TokenType.REDRAW:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                arg = self._parse_expression()
                self._consume_newline_or_eof()
                return CallNode(function_name="REDRAW", arguments=[arg], call_type="REDRAW")
            self._consume_newline_or_eof()
            return CallNode(function_name="REDRAW", arguments=[], call_type="REDRAW")
        if tt == TokenType.CUSTOMDRAWLINE:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                # DEV-006: 处理 CUSTOMDRAWLINE == 形式
                # == 作为字符参数（使用=字符绘制线条）
                if self._check(TokenType.EQ):
                    self._advance()
                    self._consume_newline_or_eof()
                    return CallNode(function_name="CUSTOMDRAWLINE",
                                  arguments=[LiteralNode(value="==")],
                                  call_type="CUSTOMDRAWLINE")
                if self._check(TokenType.ASSIGN):
                    # FIX-R1-1: CUSTOMDRAWLINE = 形式（单 = 作为绘制字符参数）
                    self._advance()
                    self._consume_newline_or_eof()
                    return CallNode(function_name="CUSTOMDRAWLINE",
                                  arguments=[LiteralNode(value="=")],
                                  call_type="CUSTOMDRAWLINE")
                arg = self._parse_expression()
                self._consume_newline_or_eof()
                return CallNode(function_name="CUSTOMDRAWLINE", arguments=[arg], call_type="CUSTOMDRAWLINE")
            self._consume_newline_or_eof()
            return CallNode(function_name="CUSTOMDRAWLINE", arguments=[], call_type="CUSTOMDRAWLINE")
        if tt == TokenType.SETCOLOR:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="SETCOLOR", arguments=args, call_type="SETCOLOR")
        if tt == TokenType.RESETCOLOR:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="RESETCOLOR", arguments=[], call_type="RESETCOLOR")
        if tt == TokenType.PRINTBUTTON:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="PRINTBUTTON", arguments=args, call_type="PRINTBUTTON")
        if tt == TokenType.PRINTBUTTONC:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="PRINTBUTTONC", arguments=args, call_type="PRINTBUTTONC")
        if tt == TokenType.BAR:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="BAR", arguments=args, call_type="BAR")
        if tt == TokenType.RESTART:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="RESTART", arguments=[], call_type="RESTART")
        if tt == TokenType.DATA:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                value = self._parse_expression()
                self._consume_newline_or_eof()
                return CallNode(function_name="DATA", arguments=[value], call_type="NOOP")
            self._consume_newline_or_eof()
            return CallNode(function_name="DATA", arguments=[], call_type="NOOP")
        if tt == TokenType.DATAFORM:
            self._advance()
            content = self._parse_printform_content()
            self._consume_newline_or_eof()
            return PrintNode(content=content, print_type="DATAFORM")
        if tt == TokenType.DATALIST:
            return self._parse_printdata()
        if tt == TokenType.FONTSTYLE:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="FONTSTYLE", arguments=args, call_type="FONTSTYLE")
        if tt == TokenType.SETFONT:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="SETFONT", arguments=args, call_type="SETFONT")
        if tt == TokenType.TWAIT:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="TWAIT", arguments=args, call_type="TWAIT")
        if tt == TokenType.SAVECHARA:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="SAVECHARA", arguments=args, call_type="SAVECHARA")
        if tt == TokenType.LOADCHARA:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="LOADCHARA", arguments=args, call_type="LOADCHARA")
        if tt == TokenType.STRLENFORMU:
            self._advance()
            content = self._parse_printform_content()
            self._consume_newline_or_eof()
            return CallNode(function_name="STRLENFORMU", arguments=[], call_type="STRLENFORMU", format_expression=content)
        if tt == TokenType.STRLENFORM:
            self._advance()
            content = self._parse_printform_content()
            self._consume_newline_or_eof()
            return CallNode(function_name="STRLENFORM", arguments=[], call_type="STRLENFORM", format_expression=content)
        if tt == TokenType.PUTFORM:
            self._advance()
            content = self._parse_printform_content()
            self._consume_newline_or_eof()
            return CallNode(function_name="PUTFORM", arguments=[], call_type="PUTFORM", format_expression=content)
        if tt == TokenType.CALLFORMF:
            return self._parse_call()
        if tt == TokenType.TRYCALLFORMF:
            return self._parse_call()
        if tt == TokenType.REUSELASTLINE:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                content = self._parse_printform_content()
                self._consume_newline_or_eof()
                return CallNode(function_name="REUSELASTLINE", arguments=[], call_type="REUSELASTLINE", format_expression=content)
            self._consume_newline_or_eof()
            return CallNode(function_name="REUSELASTLINE", arguments=[], call_type="REUSELASTLINE")
        if tt == TokenType.PRINTSW:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                args = self._parse_argument_list_inline()
                self._consume_newline_or_eof()
                return CallNode(function_name="PRINTSW", arguments=args, call_type="PRINTSW")
            self._consume_newline_or_eof()
            return CallNode(function_name="PRINTSW", arguments=[], call_type="PRINTSW")
        if tt == TokenType.SKIPDISP:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                arg = self._parse_expression()
                self._consume_newline_or_eof()
                return CallNode(function_name="SKIPDISP", arguments=[arg], call_type="SKIPDISP")
            self._consume_newline_or_eof()
            return CallNode(function_name="SKIPDISP", arguments=[], call_type="SKIPDISP")
        if tt == TokenType.SETBGCOLOR:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="SETBGCOLOR", arguments=args, call_type="SETBGCOLOR")
        if tt == TokenType.RESETBGCOLOR:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="RESETBGCOLOR", arguments=[], call_type="RESETBGCOLOR")
        if tt == TokenType.ARRAYCOPY:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="ARRAYCOPY", arguments=args, call_type="ARRAYCOPY")
        if tt == TokenType.SWAP:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="SWAP", arguments=args, call_type="SWAP")
        if tt == TokenType.ADDCOPYCHARA:
            self._advance()
            args = self._parse_argument_list_inline()
            self._consume_newline_or_eof()
            return CallNode(function_name="ADDCOPYCHARA", arguments=args, call_type="ADDCOPYCHARA")
        if tt == TokenType.SETLINECOUNT:
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                arg = self._parse_expression()
                self._consume_newline_or_eof()
                return CallNode(function_name="SETLINECOUNT", arguments=[arg], call_type="SETLINECOUNT")
            self._consume_newline_or_eof()
            return CallNode(function_name="SETLINECOUNT", arguments=[], call_type="SETLINECOUNT")
        if tt == TokenType.GETLINECOUNT:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="GETLINECOUNT", arguments=[], call_type="GETLINECOUNT")
        if tt == TokenType.CHKSPEED:
            self._advance()
            self._consume_newline_or_eof()
            return CallNode(function_name="CHKSPEED", arguments=[], call_type="CHKSPEED")
        raise ParserError(
            f"Unexpected token '{tok.value}'",
            filename=self._current_filename,
            line=tok.line,
            actual=tok,
        )

    def _parse_builtin_function(self) -> CallNode:
        tok = self._advance()
        func_name = tok.value
        # GETBIT is a special case - it's a keyword but used as a function
        if tok.type == TokenType.GETBIT:
            func_name = "GETBIT"
        args: list[ExpressionNode] = []
        if self._check(TokenType.COLON):
            self._advance()
            args.append(self._parse_expression())
            while self._check(TokenType.COMMA):
                self._advance()
                args.append(self._parse_expression())
        elif not self._check(TokenType.NEWLINE) and not self._is_at_end():
            # Use _parse_argument_list_inline for statement-level builtin calls.
            # Do NOT treat '(' as function-call syntax here, because the '(' may
            # be a parenthesized sub-expression within the first argument, e.g.
            #   LIMIT (TALENT:ARG:(ARG:1))+ARG:2,-1,1
            # The parenthesized function-call form is handled in _parse_primary().
            args = self._parse_argument_list_inline()
        self._consume_newline_or_eof()
        return CallNode(function_name=func_name, arguments=args, call_type="BUILTIN")

    def _parse_argument_list_inline(self) -> list[ExpressionNode]:
        args: list[ExpressionNode] = []
        if self._check(TokenType.NEWLINE) or self._is_at_end():
            return args
        args.append(self._parse_expression())
        while self._check(TokenType.COMMA):
            self._advance()
            # Handle trailing comma: stop if at newline or end
            if self._check(TokenType.NEWLINE) or self._is_at_end():
                break
            # FIX-2: Handle empty argument (e.g. WALK_DUNGEON ,,,0)
            if self._check(TokenType.COMMA) or self._check(TokenType.NEWLINE):
                args.append(LiteralNode(value=None))
            else:
                args.append(self._parse_expression())
        return args

    def _parse_argument_list(self) -> list[ExpressionNode]:
        args: list[ExpressionNode] = []
        if self._check(TokenType.RPAREN):
            return args
        # Allow empty first argument (e.g. SLIT(, 1))
        if self._check(TokenType.COMMA):
            args.append(LiteralNode(value=None))
        else:
            args.append(self._parse_expression())
        while self._check(TokenType.COMMA):
            self._advance()
            # Allow empty argument after comma (e.g. FUNC(1, ,3))
            if self._check(TokenType.COMMA) or self._check(TokenType.RPAREN):
                args.append(LiteralNode(value=None))
            else:
                args.append(self._parse_expression())
        return args

    def _parse_if(self) -> IfNode:
        self._expect(TokenType.IF)
        condition = self._parse_expression()
        self._consume_newline_or_eof()
        body = self._parse_block(TokenType.ELSEIF, TokenType.ELSE, TokenType.ENDIF)
        elseifs: list[tuple[ExpressionNode, list[StatementNode]]] = []
        else_body: list[StatementNode] = []
        while self._check(TokenType.ELSEIF):
            self._advance()
            elif_cond = self._parse_expression()
            self._consume_newline_or_eof()
            elif_body = self._parse_block(TokenType.ELSEIF, TokenType.ELSE, TokenType.ENDIF)
            elseifs.append((elif_cond, elif_body))
        if self._check(TokenType.ELSE):
            self._advance()
            self._consume_newline_or_eof()
            else_body = self._parse_block(TokenType.ENDIF)
        if self._check(TokenType.ENDIF):
            self._advance()
            self._consume_newline_or_eof()
        branches = [(condition, body)]
        branches.extend(elseifs)
        return IfNode(branches=branches, else_body=else_body if else_body else None)

    def _parse_sif(self) -> SifNode:
        self._expect(TokenType.SIF)
        condition = self._parse_expression()
        if self._check(TokenType.COMMA):
            self._advance()
        self._consume_newline_or_eof()
        body: list[StatementNode] = []
        if not self._is_at_end() and not self._check(TokenType.NEWLINE):
            stmt = self._parse_statement_or_decl()
            if stmt is not None:
                body.append(stmt)
        return SifNode(condition=condition, then_body=body[0] if body else None)

    def _parse_selectcase(self) -> SelectCaseNode:
        self._expect(TokenType.SELECTCASE)
        expr = self._parse_expression()
        self._consume_newline_or_eof()
        cases: list[CaseNode] = []
        case_else_body: list[StatementNode] | None = None
        while not self._check(TokenType.ENDSELECT) and not self._is_at_end():
            if self._check(TokenType.CASE):
                case_node = self._parse_case()
                cases.append(case_node)
            elif self._check(TokenType.CASEELSE):
                self._advance()
                self._consume_newline_or_eof()
                case_else_body = self._parse_block(TokenType.ENDSELECT)
            else:
                self._advance()
        if self._check(TokenType.ENDSELECT):
            self._advance()
            self._consume_newline_or_eof()
        return SelectCaseNode(scrutinee=expr, cases=cases, case_else=case_else_body)

    def _parse_case(self) -> CaseNode:
        self._expect(TokenType.CASE)
        values: list[ExpressionNode] = []
        ranges: list[tuple[ExpressionNode, ExpressionNode]] = []
        # Skip comment after CASE values (e.g. CASE 80;comment)
        if self._check(TokenType.COMMENT):
            self._advance()
            self._consume_newline_or_eof()
            body = self._parse_block(TokenType.CASE, TokenType.CASEELSE, TokenType.ENDSELECT)
            return CaseNode(values=values, ranges=ranges, body=body)
        first_val = self._parse_expression()
        if self._check(TokenType.TO):
            self._advance()
            range_end = self._parse_expression()
            ranges.append((first_val, range_end))
        else:
            values.append(first_val)
        # Handle comment after first value (e.g. CASE 80;comment)
        if self._check(TokenType.COMMENT):
            self._advance()
            self._consume_newline_or_eof()
            body = self._parse_block(TokenType.CASE, TokenType.CASEELSE, TokenType.ENDSELECT)
            return CaseNode(values=values, ranges=ranges, body=body)
        while True:
            has_comma = False
            if self._check(TokenType.COMMA):
                self._advance()
                has_comma = True
            if self._check(TokenType.NEWLINE) or self._is_at_end():
                if has_comma:
                    self._advance()
                    self._skip_newlines()
                    next_tok = self._peek()
                    if next_tok is not None and next_tok.type in (
                        TokenType.INTEGER, TokenType.FLOAT, TokenType.STRING,
                        TokenType.MINUS, TokenType.NOT, TokenType.TILDE,
                        TokenType.LPAREN, TokenType.DOUBLE_LBRACKET,
                        TokenType.CHARANUM, TokenType.RAND, TokenType.ABS,
                        TokenType.TOSTR, TokenType.TOINT, TokenType.LIMIT,
                        TokenType.MAX, TokenType.MIN, TokenType.SIGN,
                        TokenType.POWER_FUNC, TokenType.SQRT,
                        TokenType.STRLENS, TokenType.STRLENSU,
                        TokenType.FINDELEMENT, TokenType.FINDCHARA,
                        TokenType.GETTIME, TokenType.LINECOUNT,
                        TokenType.CURRENTREDRAW,
                        TokenType.FORMAT_STRING,
                        TokenType.INLINE_COND, TokenType.GETBIT,
                        TokenType.STRCOUNT, TokenType.SUBSTRING, TokenType.SUBSTRINGU,
                        TokenType.CHARATU, TokenType.REPLACE, TokenType.SPLIT,
                        TokenType.GLOBAL_MOD, TokenType.SAVEDATA_MOD, TokenType.CHARA_MOD, TokenType.CHARADATA_MOD,
                    ):
                        continue
                    elif next_tok is not None and next_tok.type in (TokenType.IDENTIFIER, TokenType.VARIABLE):
                        peek_next = self._peek_next()
                        if peek_next is not None and peek_next.type in (TokenType.ASSIGN, TokenType.STR_ASSIGN):
                            break
                        continue
                    else:
                        break
                else:
                    break
            # Handle comment in CASE value list
            if self._check(TokenType.COMMENT):
                self._advance()
                self._consume_newline_or_eof()
                break
            val = self._parse_expression()
            if self._check(TokenType.TO):
                self._advance()
                range_end = self._parse_expression()
                ranges.append((val, range_end))
            else:
                values.append(val)
        self._consume_newline_or_eof()
        body = self._parse_block(TokenType.CASE, TokenType.CASEELSE, TokenType.ENDSELECT)
        return CaseNode(values=values, ranges=ranges, body=body)

    def _parse_block(self, *terminators: TokenType) -> list[StatementNode]:
        body: list[StatementNode] = []
        self._skip_newlines()
        while not self._is_at_end():
            tok = self._peek()
            if tok is not None and tok.type in terminators:
                break
            stmt = self._parse_statement_or_decl()
            if stmt is not None:
                body.append(stmt)
            self._skip_newlines()
        return body

    def _parse_brace_block(self) -> CallNode:
        """Parse a standalone '{' ... '}' code block (Emuera extension)."""
        self._expect(TokenType.LBRACE)
        self._skip_newlines()
        # Inside brace blocks, also stop at CASE/CASEELSE/ENDSELECT to avoid
        # consuming tokens that belong to the enclosing SELECTCASE
        body = self._parse_block(TokenType.RBRACE, TokenType.CASE, TokenType.CASEELSE, TokenType.ENDSELECT)
        if self._check(TokenType.RBRACE):
            self._advance()
        self._skip_newlines()
        if self._check(TokenType.NEWLINE):
            self._advance()
        return CallNode(function_name="BRACE_BLOCK", arguments=[], call_type="NOOP")

    def _parse_for(self) -> ForNode:
        self._expect(TokenType.FOR)
        var_tok = self._advance()
        var_name = str(var_tok.value)
        while self._check(TokenType.COLON):
            self._advance()
            idx_tok = self._peek()
            if idx_tok is not None and idx_tok.type in (TokenType.INTEGER, TokenType.IDENTIFIER, TokenType.VARIABLE):
                idx = self._advance().value
                var_name = f"{var_name}:{idx}"
            else:
                break
        start: ExpressionNode
        end: ExpressionNode
        step: ExpressionNode | None = None
        if self._check(TokenType.ASSIGN):
            self._advance()
            start = self._parse_expression()
            self._expect(TokenType.TO)
            end = self._parse_expression()
            if self._check(TokenType.COMMA):
                self._advance()
                step = self._parse_expression()
        else:
            self._expect(TokenType.COMMA)
            start = self._parse_expression()
            self._expect(TokenType.COMMA)
            end = self._parse_expression()
            if self._check(TokenType.COMMA):
                self._advance()
                step = self._parse_expression()
        self._consume_newline_or_eof()
        body = self._parse_block(TokenType.NEXT)
        if self._check(TokenType.NEXT):
            self._advance()
            self._consume_newline_or_eof()
        return ForNode(var_name=var_name, start=start, end=end, step=step, body=body)

    def _parse_while(self) -> WhileNode:
        self._expect(TokenType.WHILE)
        condition = self._parse_expression()
        self._consume_newline_or_eof()
        body = self._parse_block(TokenType.WEND)
        if self._check(TokenType.WEND):
            self._advance()
            self._consume_newline_or_eof()
        return WhileNode(condition=condition, body=body)

    def _parse_do_loop(self) -> DoLoopNode:
        self._expect(TokenType.DO)
        condition: ExpressionNode | None = None
        condition_position: str = "none"
        if self._check(TokenType.WHILE):
            self._advance()
            condition = self._parse_expression()
            condition_position = "pre"
        self._consume_newline_or_eof()
        body = self._parse_block(TokenType.LOOP)
        if self._check(TokenType.LOOP):
            self._advance()
        if condition_position != "pre":
            if self._check(TokenType.WHILE):
                self._advance()
                condition = self._parse_expression()
                condition_position = "post"
            elif self._check(TokenType.UNTIL):
                self._advance()
                inner = self._parse_expression()
                condition = UnaryOpNode(op="!", operand=inner)
                condition_position = "post"
            elif not self._check(TokenType.NEWLINE) and not self._is_at_end():
                condition = self._parse_expression()
                condition_position = "post"
        self._consume_newline_or_eof()
        return DoLoopNode(condition=condition, condition_position=condition_position, body=body)

    def _parse_repeat(self) -> RepeatNode:
        self._expect(TokenType.REPEAT)
        count = self._parse_expression()
        self._consume_newline_or_eof()
        body = self._parse_block(TokenType.REND)
        if self._check(TokenType.REND):
            self._advance()
            self._consume_newline_or_eof()
        return RepeatNode(count=count, body=body)

    def _parse_call(self) -> CallNode:
        tok = self._advance()
        call_type = tok.type.value
        is_form = call_type in ("CALLFORM", "TRYCALLFORM", "JUMPFORM", "TRYJUMPFORM", "CALLFORMF")
        func_name: str = ""
        format_expr: list[PrintSegmentNode] | None = None
        if is_form:
            format_expr = self._parse_callform_name()
        elif self._check(TokenType.STRING):
            func_name = self._advance().value
        elif self._check(TokenType.IDENTIFIER):
            func_name = self._advance().value
        elif self._check(TokenType.VARIABLE):
            func_name = self._advance().value
        elif not self._check(TokenType.LPAREN) and not self._check(TokenType.COMMA) and not self._check(TokenType.NEWLINE) and not self._is_at_end():
            func_name = self._advance().value
        args: list[ExpressionNode] = []
        if self._check(TokenType.LPAREN):
            self._advance()
            if not self._check(TokenType.RPAREN):
                args = self._parse_argument_list()
            self._expect(TokenType.RPAREN)
        elif self._check(TokenType.COMMA):
            self._advance()
            args = self._parse_argument_list_inline()
        self._consume_newline_or_eof()
        if is_form:
            return CallNode(function_name=func_name, arguments=args, call_type=call_type, format_expression=format_expr)
        return CallNode(function_name=func_name, arguments=args, call_type=call_type)

    def _parse_callform_name(self) -> list[PrintSegmentNode]:
        old_in_printform = self._in_printform
        self._in_printform = True
        saved_paren_depth = self._paren_depth
        self._paren_depth = 0
        segments: list[PrintSegmentNode] = []
        text_buf: list[str] = []
        while not self._check(TokenType.LPAREN) and not self._check(TokenType.COMMA) and not self._check(TokenType.NEWLINE) and not self._is_at_end():
            tok = self._peek()
            if tok is None:
                break
            if tok.type == TokenType.LBRACE:
                if text_buf:
                    segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
                    text_buf = []
                self._advance()
                expr = self._parse_printform_expr(allow_modulo=True)
                self._skip_printform_whitespace()
                if self._check(TokenType.RBRACE):
                    self._advance()
                segments.append(PrintSegmentNode(segment_type="expression", value=expr))
            elif tok.type == TokenType.PERCENT:
                if text_buf:
                    segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
                    text_buf = []
                self._advance()
                var = self._parse_printform_expr()
                width_expr = None
                align_expr = None
                if self._check(TokenType.COMMA):
                    self._advance()
                    if not self._check(TokenType.PERCENT) and not self._check(TokenType.NEWLINE) and not self._is_at_end():
                        width_expr = self._parse_printform_expr()
                    if self._check(TokenType.COMMA):
                        self._advance()
                        if not self._check(TokenType.PERCENT) and not self._check(TokenType.NEWLINE) and not self._is_at_end():
                            align_expr = self._parse_printform_expr()
                if self._check(TokenType.PERCENT):
                    self._advance()
                segments.append(PrintSegmentNode(segment_type="expression", value=var, width=width_expr, alignment=align_expr))
            elif tok.type == TokenType.FORMAT_STRING:
                # @"..." format string inside printform content
                if text_buf:
                    segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
                    text_buf = []
                self._advance()
                # Parse the @"..." content as printform segments
                format_segments = self._parse_printform_content()
                segments.extend(format_segments)
            else:
                text_buf.append(str(tok.value))
                self._advance()
        if text_buf:
            segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
        if self._check(TokenType.FORMAT_STRING_END):
            self._advance()
        self._in_printform = old_in_printform
        self._paren_depth = saved_paren_depth
        return segments

    def _parse_tryc_callform(self) -> TrycCallformNode:
        self._expect(TokenType.TRYCCALLFORM)
        format_segments = self._parse_callform_name()
        args: list[ExpressionNode] = []
        if self._check(TokenType.LPAREN):
            self._advance()
            if not self._check(TokenType.RPAREN):
                args = self._parse_argument_list()
            self._expect(TokenType.RPAREN)
        elif self._check(TokenType.COMMA):
            self._advance()
            args = self._parse_argument_list_inline()
        self._consume_newline_or_eof()
        try_body = self._parse_block(TokenType.CATCH)
        if self._check(TokenType.CATCH):
            self._advance()
            self._consume_newline_or_eof()
        catch_body = self._parse_block(TokenType.ENDCATCH)
        if self._check(TokenType.ENDCATCH):
            self._advance()
            self._consume_newline_or_eof()
        return TrycCallformNode(format_expression=format_segments, arguments=args, try_body=try_body, catch_body=catch_body)

    def _parse_trycall_list(self) -> TrycallListNode:
        self._expect(TokenType.TRYCALLLIST)
        entries: list[CallEntryNode] = []
        func_name = self._parse_expression()
        args: list[ExpressionNode] = []
        if self._check(TokenType.COMMA):
            self._advance()
            args = self._parse_argument_list_inline()
        entries.append(CallEntryNode(function_name=func_name, arguments=args))
        self._consume_newline_or_eof()
        return TrycallListNode(entries=entries)

    def _parse_return(self) -> ReturnNode:
        self._expect(TokenType.RETURN)
        values: list[ExpressionNode] = []
        if not self._check(TokenType.NEWLINE) and not self._is_at_end():
            values.append(self._parse_expression())
            while self._check(TokenType.COMMA):
                self._advance()
                values.append(self._parse_expression())
        self._consume_newline_or_eof()
        return ReturnNode(value=values[0] if values else None)

    def _parse_returnf(self) -> ReturnNode:
        self._expect(TokenType.RETURNF)
        value: ExpressionNode | None = None
        if not self._check(TokenType.NEWLINE) and not self._is_at_end():
            value = self._parse_expression()
        self._consume_newline_or_eof()
        return ReturnNode(value=value, is_returnf=True)

    def _parse_print(self) -> PrintNode:
        tok = self._advance()
        print_type = tok.type.value
        alignment: str | None = None
        if print_type in ("PRINTFORMC", "PRINTC", "PRINTLC", "PRINTFORMLC"):
            alignment = "center"
        content: list[PrintSegmentNode] = []
        if print_type in ("PRINT", "PRINTL", "PRINTW", "PRINTC", "PRINTLC",
                          "PRINTDL",
                          "DEBUGPRINT", "DEBUGPRINTL", "DEBUGPRINTW",
                          "PRINTPLAIN"):
            if self._check(TokenType.STRING):
                text_tok = self._advance()
                content.append(PrintSegmentNode(segment_type="text", value=text_tok.value))
            elif not self._check(TokenType.NEWLINE) and not self._is_at_end():
                expr = self._parse_expression()
                content.append(PrintSegmentNode(segment_type="expression", value=expr))
        elif print_type in ("PRINTFORM", "PRINTFORML", "PRINTFORMW", "PRINTFORMC",
                            "PRINTFORMLC", "PRINTFORMDC",
                            "PRINTFORMD", "PRINTFORMDL", "PRINTFORMDW",
                            "DEBUGPRINTFORM", "DEBUGPRINTFORML", "DEBUGPRINTFORMW",
                            "PRINTSINGLEFORM", "PRINTSINGLEFORMS", "PRINTPLAINFORM"):
            content = self._parse_printform_content()
        elif print_type == "PRINTFORMS":
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                content = self._parse_printform_content()
        elif print_type in ("PRINTV", "PRINTVL"):
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                expr = self._parse_expression()
                content.append(PrintSegmentNode(segment_type="expression", value=expr))
        elif print_type in ("PRINTS", "PRINTSL"):
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                expr = self._parse_expression()
                content.append(PrintSegmentNode(segment_type="expression", value=expr))
        elif print_type == "HTML_PRINT":
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                expr = self._parse_expression()
                content.append(PrintSegmentNode(segment_type="expression", value=expr))
        elif print_type == "PRINTSW":
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                content = self._parse_printform_content()
        elif print_type == "SPRITEDISPOSE":
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                content = self._parse_printform_content()
        self._consume_newline_or_eof()
        return PrintNode(content=content, print_type=print_type, alignment=alignment)

    def _parse_printform_content(self) -> list[PrintSegmentNode]:
        old_in_printform = self._in_printform
        self._in_printform = True
        # Save and reset paren_depth so that % inside @"..." is treated as
        # format string delimiter, not modulo operator, even when the @"..."
        # appears inside a function call (which sets paren_depth > 0).
        saved_paren_depth = self._paren_depth
        self._paren_depth = 0
        segments: list[PrintSegmentNode] = []
        text_buf: list[str] = []
        while not self._check(TokenType.NEWLINE) and not self._is_at_end() and not self._check(TokenType.FORMAT_STRING_END):
            tok = self._peek()
            if tok is None:
                break
            if tok.type == TokenType.LBRACE:
                if text_buf:
                    segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
                    text_buf = []
                self._advance()
                expr = self._parse_printform_expr(allow_modulo=True)
                width_expr = None
                align_expr = None
                if self._check(TokenType.COMMA):
                    self._advance()
                    if not self._check(TokenType.RBRACE) and not self._check(TokenType.NEWLINE) and not self._is_at_end():
                        width_expr = self._parse_printform_expr()
                    if self._check(TokenType.COMMA):
                        self._advance()
                        if not self._check(TokenType.RBRACE) and not self._check(TokenType.NEWLINE) and not self._is_at_end():
                            align_expr = self._parse_printform_expr()
                if self._check(TokenType.RBRACE):
                    self._advance()
                segments.append(PrintSegmentNode(segment_type="expression", value=expr, width=width_expr, alignment=align_expr))
            elif tok.type == TokenType.PERCENT:
                if text_buf:
                    segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
                    text_buf = []
                self._advance()
                var = self._parse_printform_expr(allow_modulo=True)
                width_expr = None
                align_expr = None
                if self._check(TokenType.COMMA):
                    self._advance()
                    if not self._check(TokenType.PERCENT) and not self._check(TokenType.NEWLINE) and not self._is_at_end():
                        width_expr = self._parse_printform_expr()
                    if self._check(TokenType.COMMA):
                        self._advance()
                        if not self._check(TokenType.PERCENT) and not self._check(TokenType.NEWLINE) and not self._is_at_end():
                            align_expr = self._parse_printform_expr()
                if self._check(TokenType.PERCENT):
                    self._advance()
                segments.append(PrintSegmentNode(segment_type="expression", value=var, width=width_expr, alignment=align_expr))
            elif tok.type == TokenType.FORMAT_STRING:
                # @"..." format string inside printform content
                if text_buf:
                    segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
                    text_buf = []
                self._advance()
                # Parse the @"..." content as printform segments
                format_segments = self._parse_printform_content()
                segments.extend(format_segments)
            else:
                text_buf.append(str(tok.value))
                self._advance()
        if text_buf:
            segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
        if self._check(TokenType.FORMAT_STRING_END):
            self._advance()
        self._in_printform = old_in_printform
        self._paren_depth = saved_paren_depth
        return segments

    def _parse_printform_expr(self, allow_modulo: bool = False) -> ExpressionNode:
        old_in_printform = self._in_printform
        self._in_printform = True
        result = self._parse_expression()
        self._in_printform = old_in_printform
        return result

    def _skip_printform_whitespace(self) -> None:
        while self._check(TokenType.IDENTIFIER) and self._peek() is not None and self._peek().value == ' ':
            self._advance()

    def _parse_printdata(self) -> PrintDataNode:
        tok = self._advance()
        print_type = tok.type.value
        entries: list[PrintDataEntryNode] = []
        while not self._check(TokenType.ENDDATA) and not self._is_at_end():
            if self._check(TokenType.DATA):
                self._advance()
                value = self._parse_expression()
                self._consume_newline_or_eof()
                entries.append(PrintDataEntryNode(entry_type="DATA", value=value))
            elif self._check(TokenType.DATAFORM):
                self._advance()
                content = self._parse_printform_content()
                self._consume_newline_or_eof()
                entries.append(PrintDataEntryNode(entry_type="DATAFORM", value=content))
            elif self._check(TokenType.DATALIST):
                self._advance()
                self._consume_newline_or_eof()
            elif self._check(TokenType.ENDLIST):
                self._advance()
                self._consume_newline_or_eof()
            else:
                self._advance()
        if self._check(TokenType.ENDDATA):
            self._advance()
        self._consume_newline_or_eof()
        return PrintDataNode(entries=entries, is_random=True)

    def _parse_input(self) -> InputNode:
        tok = self._advance()
        input_type = tok.type.value
        prompt: ExpressionNode | None = None
        timeout_var: str | None = None
        mouse_support: bool = False
        if not self._check(TokenType.NEWLINE) and not self._is_at_end():
            prompt = self._parse_expression()
        # TINPUT/TINPUTS/TONEINPUT/TONEINPUTS support multiple arguments:
        # arg1=timeout, arg2=timeout_var_name, arg3=mouse_support_flag
        if self._check(TokenType.COMMA) and input_type in ("TINPUT", "TINPUTS", "TONEINPUT", "TONEINPUTS"):
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                var_tok = self._peek()
                if var_tok is not None and var_tok.type == TokenType.STRING:
                    timeout_var = self._advance().value
                elif var_tok is not None and var_tok.type in (TokenType.IDENTIFIER, TokenType.VARIABLE):
                    timeout_var = self._advance().value
                else:
                    # second arg could be an expression, skip it
                    self._parse_expression()
            if self._check(TokenType.COMMA):
                self._advance()
                if not self._check(TokenType.NEWLINE) and not self._is_at_end():
                    flag_tok = self._peek()
                    if flag_tok is not None and flag_tok.type == TokenType.INTEGER:
                        mouse_support = self._advance().value != 0
                    else:
                        self._parse_expression()
        self._consume_newline_or_eof()
        return InputNode(input_type=input_type, timeout=prompt, timeout_var=timeout_var, mouse_support=mouse_support)

    def _parse_goto(self) -> GotoNode:
        self._expect(TokenType.GOTO)
        label = self._advance().value
        self._consume_newline_or_eof()
        return GotoNode(label=label)

    def _parse_label(self) -> LabelNode:
        label_tok = self._expect(TokenType.LABEL)
        name = label_tok.value
        self._consume_newline_or_eof()
        return LabelNode(name=name)

    def _parse_times(self) -> TimesNode:
        self._expect(TokenType.TIMES)
        var = self._parse_variable_access()
        self._expect(TokenType.COMMA)
        expr = self._parse_expression()
        if isinstance(expr, LiteralNode):
            multiplier = float(expr.value)
        else:
            multiplier = 0.0
        self._consume_newline_or_eof()
        return TimesNode(target=var, multiplier=multiplier)

    def _parse_throw(self) -> ThrowNode:
        self._expect(TokenType.THROW)
        message: ExpressionNode | None = None
        if not self._check(TokenType.NEWLINE) and not self._is_at_end():
            old_in_printform = self._in_printform
            self._in_printform = True
            segments = self._parse_printform_content()
            self._in_printform = old_in_printform
            self._consume_newline_or_eof()
            return ThrowNode(message=LiteralNode(value=""), format_segments=segments)
        self._consume_newline_or_eof()
        return ThrowNode(message=message)

    def _parse_begin(self) -> BeginNode:
        self._expect(TokenType.BEGIN)
        mode = self._advance().value
        self._consume_newline_or_eof()
        return BeginNode(mode=mode)

    def _parse_varset(self) -> VarsetNode:
        self._expect(TokenType.VARSET)
        var = self._parse_variable_access()
        value: ExpressionNode | None = None
        start: ExpressionNode | None = None
        end: ExpressionNode | None = None
        if self._check(TokenType.COMMA):
            self._advance()
            if not self._check(TokenType.NEWLINE) and not self._check(TokenType.COMMENT) and not self._is_at_end():
                # Check if next token could start an expression (not an assignment)
                next_tok = self._peek()
                if next_tok is not None and next_tok.type not in (TokenType.ASSIGN, TokenType.STR_ASSIGN):
                    try:
                        value = self._parse_expression()
                    except ParserError:
                        value = None
            if self._check(TokenType.COMMA):
                self._advance()
                if not self._check(TokenType.NEWLINE) and not self._check(TokenType.COMMENT) and not self._is_at_end():
                    try:
                        start = self._parse_expression()
                    except ParserError:
                        start = None
                if self._check(TokenType.COMMA):
                    self._advance()
                    if not self._check(TokenType.NEWLINE) and not self._check(TokenType.COMMENT) and not self._is_at_end():
                        try:
                            end = self._parse_expression()
                        except ParserError:
                            end = None
        self._consume_newline_or_eof()
        return VarsetNode(target=var, value=value, start_index=start, end_index=end)

    def _parse_bit_op(self) -> CallNode:
        tok = self._advance()
        op_name = tok.type.value
        args = self._parse_argument_list_inline()
        self._consume_newline_or_eof()
        return CallNode(function_name=op_name, arguments=args, call_type=op_name)

    def _is_string_variable(self, var: VariableAccessNode) -> bool:
        name = var.var_name
        name_upper = name.upper()
        if name_upper in self._local_var_types:
            return self._local_var_types[name_upper] == "str"
        if name.endswith("S") and len(name) > 1:
            return True
        if name in ("RESULTS", "LOCALS", "ARGS", "SAVESTR", "GLOBALS", "CSTR", "TSTR", "NICKNAME", "MASTERNAME", "NAME", "CALLNAME", "MAPDATA"):
            return True
        if self._variable_metadata is not None:
            desc = None
            if hasattr(self._variable_metadata, 'get_descriptor'):
                desc = self._variable_metadata.get_descriptor(name)
            if desc is not None and hasattr(desc, 'var_type') and desc.var_type == "str":
                return True
        return False

    def _parse_assignment_or_expr(self) -> StatementNode:
        var = self._parse_variable_access()
        if self._check(TokenType.STR_ASSIGN):
            self._advance()
            next_tok = self._peek()
            # '= followed by %...% format expression (e.g. var '= %EXPR%)
            if next_tok is not None and next_tok.type == TokenType.PERCENT:
                segments = self._parse_printform_content()
                self._consume_newline_or_eof()
                return StringAssignNode(target=var, value=LiteralNode(value=""), format_segments=segments)
            value = self._parse_string_expression()
            # Handle comma-separated string values after '=
            # e.g. var '= "str1", "str2", "str3"
            while self._check(TokenType.COMMA):
                self._advance()
                if not self._check(TokenType.NEWLINE) and not self._check(TokenType.COMMENT) and not self._is_at_end():
                    _extra = self._parse_string_expression()
            self._consume_newline_or_eof()
            # Check if string expression returned format segments (from @"..." or {expr} concatenation)
            if isinstance(value, list):
                return StringAssignNode(target=var, value=LiteralNode(value=""), format_segments=value)
            return StringAssignNode(target=var, value=value)
        if self._check(TokenType.ASSIGN):
            self._advance()
            if self._check(TokenType.NEWLINE) or self._is_at_end():
                if isinstance(var, VariableAccessNode) and self._is_string_variable(var):
                    self._consume_newline_or_eof()
                    return StringAssignNode(target=var, value=LiteralNode(value=""))
                self._consume_newline_or_eof()
                return AssignNode(target=var, value=LiteralNode(value=0))
            next_tok = self._peek()
            if next_tok is not None and next_tok.type == TokenType.PERCENT:
                segments = self._parse_printform_content()
                self._consume_newline_or_eof()
                return StringAssignNode(target=var, value=LiteralNode(value=""), format_segments=segments)
            if next_tok is not None and next_tok.type == TokenType.STRING:
                value = self._parse_string_expression()
                self._consume_newline_or_eof()
                if isinstance(value, list):
                    return StringAssignNode(target=var, value=LiteralNode(value=""), format_segments=value)
                return StringAssignNode(target=var, value=value)
            if isinstance(var, VariableAccessNode) and self._is_string_variable(var):
                if next_tok is not None and next_tok.type == TokenType.STRING:
                    value = self._parse_string_expression()
                    self._consume_newline_or_eof()
                    # Check if string expression returned format segments
                    if isinstance(value, list):
                        return StringAssignNode(target=var, value=LiteralNode(value=""), format_segments=value)
                    return StringAssignNode(target=var, value=value)
                saved_pos = self._pos
                try:
                    value = self._parse_expression()
                    if self._check(TokenType.NEWLINE) or self._check(TokenType.COMMENT) or self._is_at_end():
                        self._consume_newline_or_eof()
                        return AssignNode(target=var, value=value)
                    self._pos = saved_pos
                except ParserError:
                    self._pos = saved_pos
                parts: list[str] = []
                while not self._check(TokenType.NEWLINE) and not self._check(TokenType.COMMENT) and not self._is_at_end():
                    t = self._advance()
                    parts.append(str(t.value))
                self._consume_newline_or_eof()
                return StringAssignNode(target=var, value=LiteralNode(value="".join(parts)))
            saved_pos2 = self._pos
            try:
                value = self._parse_expression()
                if self._check(TokenType.NEWLINE) or self._check(TokenType.COMMENT) or self._is_at_end():
                    self._consume_newline_or_eof()
                    return AssignNode(target=var, value=value)
                self._pos = saved_pos2
            except ParserError:
                self._pos = saved_pos2
            parts2: list[str] = []
            while not self._check(TokenType.NEWLINE) and not self._check(TokenType.COMMENT) and not self._is_at_end():
                t = self._advance()
                parts2.append(str(t.value))
            self._consume_newline_or_eof()
            return StringAssignNode(target=var, value=LiteralNode(value="".join(parts2)))
        if self._check(TokenType.PLUS_ASSIGN):
            self._advance()
            # Check if this is a string variable with @"..." format string
            next_tok = self._peek()
            if isinstance(var, VariableAccessNode) and self._is_string_variable(var):
                value = self._parse_string_expression()
                self._consume_newline_or_eof()
                if isinstance(value, list):
                    return StringAssignNode(target=var, value=var, format_segments=value, op="+=")
                return AssignNode(target=var, value=value, op="+=")
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="+=")
        if self._check(TokenType.MINUS_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="-=")
        if self._check(TokenType.STAR_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="*=")
        if self._check(TokenType.SLASH_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="/=")
        if self._check(TokenType.PERCENT_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="%=")
        if self._check(TokenType.PIPE_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="|=")
        if self._check(TokenType.AMP_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="&=")
        if self._check(TokenType.CARET_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="^=")
        if self._check(TokenType.LSHIFT_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op="<<=")
        if self._check(TokenType.RSHIFT_ASSIGN):
            self._advance()
            value = self._parse_expression()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=value, op=">>=")
        if self._check(TokenType.INCREMENT):
            self._advance()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=BinaryOpNode(op="+", left=var, right=LiteralNode(value=1)))
        if self._check(TokenType.DECREMENT):
            self._advance()
            self._consume_newline_or_eof()
            return AssignNode(target=var, value=BinaryOpNode(op="-", left=var, right=LiteralNode(value=1)))
        if isinstance(var, VariableAccessNode) and not var.indices:
            if self._check(TokenType.LPAREN):
                func_name = var.var_name
                self._advance()
                args: list[ExpressionNode] = []
                if not self._check(TokenType.RPAREN):
                    args = self._parse_argument_list()
                self._expect(TokenType.RPAREN)
                self._consume_newline_or_eof()
                return CallNode(function_name=func_name, arguments=args, call_type="CALL")
            if self._check(TokenType.COMMA):
                self._advance()
                args = self._parse_argument_list_inline()
                self._consume_newline_or_eof()
                return CallNode(function_name=var.var_name, arguments=args, call_type="CALL")
        self._consume_newline_or_eof()
        return CallNode(function_name=var.var_name if isinstance(var, VariableAccessNode) else str(var), arguments=[], call_type="EXPR")

    def _parse_string_expression(self) -> StringExpressionNode:
        tok = self._peek()
        if tok is None or tok.type in (TokenType.NEWLINE, TokenType.EOF):
            return ""
        if tok is not None and tok.type == TokenType.STRING:
            self._advance()
            parts = [tok.value]
            while not self._check(TokenType.NEWLINE) and not self._is_at_end():
                next_tok = self._peek()
                if next_tok is None:
                    break
                if next_tok.type == TokenType.STRING:
                    parts.append(self._advance().value)
                elif next_tok.type in (TokenType.IDENTIFIER, TokenType.VARIABLE,
                                       TokenType.INTEGER, TokenType.COLON,
                                       TokenType.DOUBLE_LBRACKET, TokenType.RBRACKET):
                    parts.append(str(self._advance().value))
                elif next_tok.type == TokenType.PLUS:
                    combined = "".join(parts)
                    self._advance()
                    right = self._parse_expression()
                    return BinaryOpNode(op="+", left=LiteralNode(value=combined), right=right)
                elif next_tok.type == TokenType.LBRACE:
                    combined = "".join(parts)
                    segments = self._parse_string_concat_after_text(combined)
                    return segments
                # DEV-15: STAR(*)作为乘法运算符，不作为文本
                # 当右操作数不是有效表达式起始时，退化为文本拼接（如 MAP_08.ERB 的 ""*::...）
                elif next_tok.type == TokenType.STAR:
                    _after_star = self._peek_next()
                    _star_valid_start = _after_star is not None and _after_star.type in (
                        TokenType.INTEGER, TokenType.FLOAT, TokenType.STRING, TokenType.LPAREN,
                        TokenType.IDENTIFIER, TokenType.VARIABLE, TokenType.MINUS, TokenType.NOT,
                        TokenType.TILDE, TokenType.INCREMENT, TokenType.DECREMENT,
                        TokenType.FORMAT_STRING, TokenType.INLINE_COND, TokenType.DOUBLE_LBRACKET,
                        TokenType.PERCENT, TokenType.CHKFONT, TokenType.CHKDATA,
                        TokenType.RAND, TokenType.ABS, TokenType.SIGN, TokenType.MAX, TokenType.MIN,
                        TokenType.LIMIT, TokenType.TOSTR, TokenType.TOINT, TokenType.SQRT,
                        TokenType.POWER_FUNC, TokenType.STRLENS, TokenType.STRLENSU,
                        TokenType.SUBSTRING, TokenType.SUBSTRINGU, TokenType.CHARATU,
                        TokenType.REPLACE, TokenType.SPLIT, TokenType.STRCOUNT,
                        TokenType.STRFIND, TokenType.STRFINDU, TokenType.FINDELEMENT,
                        TokenType.FINDCHARA, TokenType.GETBIT, TokenType.GETTIME,
                        TokenType.LINECOUNT, TokenType.CURRENTREDRAW, TokenType.CHARANUM,
                    )
                    if _star_valid_start:
                        combined = "".join(parts)
                        self._advance()
                        right = self._parse_expression()
                        return BinaryOpNode(op="*", left=LiteralNode(value=combined), right=right)
                    else:
                        parts.append(str(self._advance().value))
                elif next_tok.type in (TokenType.SLASH, TokenType.PIPE,
                                       TokenType.CARET, TokenType.TILDE, TokenType.LT,
                                       TokenType.GT, TokenType.EQ, TokenType.NEQ,
                                       TokenType.LTE, TokenType.GTE, TokenType.AMP,
                                       TokenType.NOT, TokenType.MINUS, TokenType.HASH):
                    parts.append(str(self._advance().value))
                else:
                    break
            combined = "".join(parts)
            return combined
        if tok is not None and tok.type == TokenType.INTEGER:
            parts: list[str] = [str(tok.value)]
            self._advance()
            while not self._check(TokenType.NEWLINE) and not self._is_at_end():
                t = self._advance()
                parts.append(str(t.value))
            return "".join(parts)
        if tok is not None and tok.type in (TokenType.ASSIGN, TokenType.MINUS, TokenType.PLUS,
                                             TokenType.STAR, TokenType.SLASH, TokenType.PERCENT,
                                             TokenType.LT, TokenType.GT, TokenType.EQ, TokenType.NEQ,
                                             TokenType.LTE, TokenType.GTE, TokenType.AMP, TokenType.PIPE,
                                             TokenType.CARET, TokenType.TILDE, TokenType.NOT,
                                             TokenType.QUESTION, TokenType.HASH, TokenType.COMMA):
            parts: list[str] = [str(tok.value)]
            self._advance()
            while not self._check(TokenType.NEWLINE) and not self._is_at_end():
                t = self._advance()
                parts.append(str(t.value))
            return "".join(parts)
        if tok is not None and tok.type == TokenType.PERCENT:
            self._advance()
            expr = self._parse_expression()
            if self._check(TokenType.PERCENT):
                self._advance()
            return expr
        expr = self._parse_expression()
        return expr

    def _parse_string_concat_after_text(self, initial_text: str) -> list[PrintSegmentNode]:
        """Parse string concatenation after a string literal, e.g. "text"{expr}."""
        segments: list[PrintSegmentNode] = [PrintSegmentNode(segment_type="text", value=initial_text)]
        while not self._check(TokenType.NEWLINE) and not self._check(TokenType.COMMENT) and not self._is_at_end():
            tok = self._peek()
            if tok is None:
                break
            if tok.type == TokenType.LBRACE:
                self._advance()
                expr = self._parse_printform_expr(allow_modulo=True)
                self._skip_printform_whitespace()
                if self._check(TokenType.RBRACE):
                    self._advance()
                segments.append(PrintSegmentNode(segment_type="expression", value=expr))
            elif tok.type == TokenType.PERCENT:
                self._advance()
                var = self._parse_printform_expr(allow_modulo=False)
                if self._check(TokenType.PERCENT):
                    self._advance()
                segments.append(PrintSegmentNode(segment_type="expression", value=var))
            elif tok.type == TokenType.STRING:
                text_tok = self._advance()
                segments.append(PrintSegmentNode(segment_type="text", value=text_tok.value))
            else:
                # Collect remaining text tokens
                text_buf: list[str] = []
                while not self._check(TokenType.NEWLINE) and not self._check(TokenType.COMMENT) and not self._is_at_end():
                    t = self._peek()
                    if t is not None and t.type in (TokenType.LBRACE, TokenType.PERCENT, TokenType.STRING):
                        break
                    t = self._advance()
                    text_buf.append(str(t.value))
                if text_buf:
                    segments.append(PrintSegmentNode(segment_type="text", value="".join(text_buf)))
                else:
                    break
        return segments

    def _parse_variable_access(self) -> VariableAccessNode:
        tok = self._advance()
        name = tok.value
        indices: list[ExpressionNode] = []
        while self._check(TokenType.COLON):
            self._advance()
            if self._check(TokenType.LPAREN):
                self._advance()
                old_in_printform = self._in_printform
                self._in_printform = False
                idx = self._parse_expression()
                self._in_printform = old_in_printform
                self._expect(TokenType.RPAREN)
                indices.append(idx)
            elif self._check(TokenType.DOUBLE_LBRACKET):
                self._advance()
                char_name_tok = self._expect(TokenType.STRING)
                self._expect(TokenType.DOUBLE_RBRACKET)
                indices.append(FunctionCallNode(
                    function_name="FIND_CHARA_BY_NAME",
                    arguments=[LiteralNode(value=char_name_tok.value)],
                ))
            else:
                idx_tok = self._peek()
                if idx_tok is not None and idx_tok.type == TokenType.INTEGER:
                    indices.append(LiteralNode(value=self._advance().value))
                elif idx_tok is not None and idx_tok.type in (TokenType.IDENTIFIER, TokenType.VARIABLE):
                    var_name = self._advance().value
                    if self._check(TokenType.LPAREN):
                        self._advance()
                        args: list[ExpressionNode] = []
                        if not self._check(TokenType.RPAREN):
                            args = self._parse_argument_list()
                        self._expect(TokenType.RPAREN)
                        indices.append(FunctionCallNode(function_name=var_name, arguments=args))
                    else:
                        indices.append(VariableAccessNode(var_name=var_name, indices=[]))
                elif idx_tok is not None and idx_tok.type == TokenType.STRING:
                    indices.append(LiteralNode(value=self._advance().value))
                elif idx_tok is not None and idx_tok.type == TokenType.MINUS:
                    self._advance()
                    num_tok = self._peek()
                    if num_tok is not None and num_tok.type == TokenType.INTEGER:
                        indices.append(LiteralNode(value=-self._advance().value))
                    else:
                        indices.append(UnaryOpNode(op="-", operand=LiteralNode(value=0)))
                elif idx_tok is not None and idx_tok.type in (TokenType.TOINT, TokenType.TOSTR, TokenType.ABS,
                                                               TokenType.SIGN, TokenType.MAX, TokenType.MIN,
                                                               TokenType.LIMIT, TokenType.RAND, TokenType.SQRT,
                                                               TokenType.POWER_FUNC, TokenType.STRLENS, TokenType.STRLENSU,
                                                               TokenType.SUBSTRING, TokenType.SUBSTRINGU, TokenType.CHARATU,
                                                               TokenType.REPLACE, TokenType.STRCOUNT, TokenType.FINDELEMENT,
                                                               TokenType.FINDCHARA):
                    func_name = self._advance().value
                    if self._check(TokenType.LPAREN):
                        self._advance()
                        func_args: list[ExpressionNode] = []
                        if not self._check(TokenType.RPAREN):
                            func_args = self._parse_argument_list()
                        self._expect(TokenType.RPAREN)
                        indices.append(FunctionCallNode(function_name=func_name, arguments=func_args))
                    elif self._check(TokenType.COLON):
                        self._advance()
                        arg = self._parse_expression()
                        indices.append(FunctionCallNode(function_name=func_name, arguments=[arg]))
                    else:
                        indices.append(VariableAccessNode(var_name=func_name, indices=[]))
                elif idx_tok is not None and idx_tok.type == TokenType.FORMAT_STRING:
                    # FIX-6: @"..." dynamic variable name (e.g. ABL:LOCAL:@"潜質{LOCAL:1}")
                    self._advance()
                    content = self._parse_printform_content()
                    if len(content) == 1:
                        seg = content[0]
                        if seg.segment_type == "text":
                            indices.append(LiteralNode(value=seg.value))
                        elif seg.segment_type == "expression":
                            indices.append(seg.value)
                    else:
                        indices.append(FormatStringNode(segments=content))
                else:
                    break
        return VariableAccessNode(var_name=name, indices=indices)

    def _parse_expression(self) -> ExpressionNode:
        return self._parse_ternary()

    def _parse_ternary(self) -> ExpressionNode:
        expr = self._parse_or()
        if self._check(TokenType.QUESTION):
            self._advance()
            true_expr = self._parse_expression()
            if self._check(TokenType.HASH):
                self._advance()
                false_expr = self._parse_expression()
            elif self._check(TokenType.COLON):
                self._advance()
                false_expr = self._parse_expression()
            else:
                false_expr = LiteralNode(value=0)
            return TernaryOpNode(condition=expr, true_expr=true_expr, false_expr=false_expr)
        return expr

    def _parse_or(self) -> ExpressionNode:
        left = self._parse_and()
        while self._check(TokenType.OR):
            self._advance()
            right = self._parse_and()
            left = BinaryOpNode(op="||", left=left, right=right)
        return left

    def _parse_and(self) -> ExpressionNode:
        left = self._parse_bitwise_or()
        while self._check(TokenType.AND):
            self._advance()
            right = self._parse_bitwise_or()
            left = BinaryOpNode(op="&&", left=left, right=right)
        return left

    def _parse_bitwise_or(self) -> ExpressionNode:
        left = self._parse_bitwise_xor()
        while self._check(TokenType.PIPE) and not self._check(TokenType.OR):
            self._advance()
            right = self._parse_bitwise_xor()
            left = BinaryOpNode(op="|", left=left, right=right)
        # FIX-7: Handle !| (NOR) — logical NOR: !(A || B)
        while self._check(TokenType.NOR):
            self._advance()
            right = self._parse_bitwise_xor()
            left = BinaryOpNode(op="!|", left=left, right=right)
        return left

    def _parse_bitwise_xor(self) -> ExpressionNode:
        left = self._parse_bitwise_and()
        while self._check(TokenType.CARET):
            self._advance()
            right = self._parse_bitwise_and()
            left = BinaryOpNode(op="^", left=left, right=right)
        return left

    def _parse_bitwise_and(self) -> ExpressionNode:
        left = self._parse_equality()
        while self._check(TokenType.AMP) and not self._check(TokenType.AND):
            self._advance()
            right = self._parse_equality()
            left = BinaryOpNode(op="&", left=left, right=right)
        # FIX-7: Handle !& (NAND) — logical NAND: !(A && B)
        while self._check(TokenType.NAND):
            self._advance()
            right = self._parse_equality()
            left = BinaryOpNode(op="!&", left=left, right=right)
        return left

    def _parse_equality(self) -> ExpressionNode:
        left = self._parse_relational()
        while self._check(TokenType.EQ) or self._check(TokenType.NEQ):
            op = self._advance().value
            right = self._parse_relational()
            left = BinaryOpNode(op=op, left=left, right=right)
        return left

    def _parse_relational(self) -> ExpressionNode:
        left = self._parse_shift()
        while self._check(TokenType.LT) or self._check(TokenType.GT) or self._check(TokenType.LTE) or self._check(TokenType.GTE):
            op = self._advance().value
            right = self._parse_shift()
            left = BinaryOpNode(op=op, left=left, right=right)
        return left

    def _parse_shift(self) -> ExpressionNode:
        left = self._parse_additive()
        while self._check(TokenType.LSHIFT) or self._check(TokenType.RSHIFT):
            op = self._advance().value
            right = self._parse_additive()
            left = BinaryOpNode(op=op, left=left, right=right)
        return left

    def _parse_additive(self) -> ExpressionNode:
        left = self._parse_multiplicative()
        while self._check(TokenType.PLUS) or self._check(TokenType.MINUS):
            op = self._advance().value
            right = self._parse_multiplicative()
            left = BinaryOpNode(op=op, left=left, right=right)
        return left

    def _parse_multiplicative(self) -> ExpressionNode:
        left = self._parse_power()
        while self._check(TokenType.STAR) or self._check(TokenType.SLASH) or self._check_percent_as_operator():
            op = self._advance().value
            right = self._parse_power()
            left = BinaryOpNode(op=op, left=left, right=right)
        return left

    def _check_percent_as_operator(self) -> bool:
        if not self._check(TokenType.PERCENT):
            return False
        if self._in_printform and self._paren_depth > 0:
            return True
        if self._in_printform:
            return False
        return True

    def _parse_power(self) -> ExpressionNode:
        base = self._parse_unary()
        if self._check(TokenType.POWER):
            self._advance()
            exp = self._parse_power()
            return BinaryOpNode(op="**", left=base, right=exp)
        return base

    def _parse_unary(self) -> ExpressionNode:
        if self._check(TokenType.PLUS):
            # 一元正号：+expr → expr（原版Emuera支持，如 += +MIN(...) 中的冗余+）
            self._advance()
            return self._parse_unary()
        if self._check(TokenType.MINUS):
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode(op="-", operand=operand)
        if self._check(TokenType.NOT):
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode(op="!", operand=operand)
        if self._check(TokenType.TILDE):
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode(op="~", operand=operand)
        if self._check(TokenType.INCREMENT):
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode(op="++", operand=operand)
        if self._check(TokenType.DECREMENT):
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode(op="--", operand=operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> ExpressionNode:
        expr = self._parse_primary()
        while True:
            if self._check(TokenType.LPAREN):
                if isinstance(expr, VariableAccessNode):
                    func_name = expr.var_name
                    self._advance()
                    args: list[ExpressionNode] = []
                    if not self._check(TokenType.RPAREN):
                        args = self._parse_argument_list()
                    self._expect(TokenType.RPAREN)
                    expr = FunctionCallNode(function_name=func_name, arguments=args)
                else:
                    break
            elif self._check(TokenType.LBRACE):
                if isinstance(expr, VariableAccessNode) or isinstance(expr, LiteralNode) or isinstance(expr, BinaryOpNode):
                    if isinstance(expr, VariableAccessNode):
                        base_str = expr.var_name
                    elif isinstance(expr, LiteralNode):
                        base_str = str(expr.value)
                    else:
                        base_str = None
                    if base_str is not None:
                        self._advance()
                        inner_expr = self._parse_expression()
                        self._expect(TokenType.RBRACE)
                        expr = BinaryOpNode(
                            op="+",
                            left=LiteralNode(value=base_str),
                            right=FunctionCallNode(function_name="TOSTR", arguments=[inner_expr]),
                        )
                    else:
                        self._advance()
                        inner_expr = self._parse_expression()
                        self._expect(TokenType.RBRACE)
                        expr = BinaryOpNode(
                            op="+",
                            left=expr,
                            right=FunctionCallNode(function_name="TOSTR", arguments=[inner_expr]),
                        )
                    while True:
                        if self._check(TokenType.IDENTIFIER) or self._check(TokenType.VARIABLE):
                            text_tok = self._advance()
                            text_val = text_tok.value
                            expr = BinaryOpNode(op="+", left=expr, right=LiteralNode(value=text_val))
                        elif self._check(TokenType.LBRACE):
                            self._advance()
                            inner_expr = self._parse_expression()
                            self._expect(TokenType.RBRACE)
                            expr = BinaryOpNode(
                                op="+",
                                left=expr,
                                right=FunctionCallNode(function_name="TOSTR", arguments=[inner_expr]),
                            )
                        else:
                            break
                else:
                    break
            elif self._check(TokenType.INCREMENT):
                self._advance()
                expr = UnaryOpNode(op="++", operand=expr, is_postfix=True)
            elif self._check(TokenType.DECREMENT):
                self._advance()
                expr = UnaryOpNode(op="--", operand=expr, is_postfix=True)
            else:
                break
        return expr

    def _parse_primary(self) -> ExpressionNode:
        tok = self._peek()
        if tok is None:
            raise ParserError("Unexpected end of expression", filename=self._current_filename)
        if tok.type == TokenType.INTEGER:
            self._advance()
            next_tok = self._peek()
            if next_tok is not None and next_tok.type == TokenType.IDENTIFIER and next_tok.value == 'p':
                self._advance()
                bit_tok = self._peek()
                if bit_tok is not None and bit_tok.type == TokenType.INTEGER:
                    self._advance()
                    return BitPositionNode(position=tok.value * 32 + bit_tok.value)
            return LiteralNode(value=tok.value)
        if tok.type == TokenType.FLOAT:
            self._advance()
            return LiteralNode(value=tok.value)
        if tok.type == TokenType.STRING:
            self._advance()
            return LiteralNode(value=tok.value)
        if tok.type == TokenType.LPAREN:
            self._advance()
            self._paren_depth += 1
            expr = self._parse_expression()
            self._paren_depth -= 1
            self._expect(TokenType.RPAREN)
            return expr
        if tok.type == TokenType.LBRACKET:
            parts: list[str] = []
            while not self._check(TokenType.NEWLINE) and not self._is_at_end():
                t = self._advance()
                parts.append(str(t.value))
            return LiteralNode(value="".join(parts))
        if tok.type == TokenType.DOUBLE_LBRACKET:
            self._advance()
            char_name_tok = self._expect(TokenType.STRING)
            self._expect(TokenType.DOUBLE_RBRACKET)
            return FunctionCallNode(
                function_name="FIND_CHARA_BY_NAME",
                arguments=[LiteralNode(value=char_name_tok.value)],
            )
        if tok.type == TokenType.FORMAT_STRING:
            self._advance()
            # @"..." format string - parse the content as printform segments
            content = self._parse_printform_content()
            if len(content) == 1:
                seg = content[0]
                if seg.segment_type == "text":
                    return LiteralNode(value=seg.value)
                elif seg.segment_type == "expression":
                    return seg.value
            # Multiple segments - return as a StringExpressionNode or format segments
            return FormatStringNode(segments=content)
        if tok.type == TokenType.PERCENT:
            # %...% string interpolation in expression context (e.g. inside \@...\@)
            self._advance()
            # Save and set _in_printform so that % is treated as a delimiter
            # (not as modulo) inside the interpolated expression
            saved_in_printform = self._in_printform
            self._in_printform = True
            expr = self._parse_expression()
            self._in_printform = saved_in_printform
            if self._check(TokenType.PERCENT):
                self._advance()
            return expr
        if tok.type == TokenType.INLINE_COND:
            self._advance()
            # Parse condition up to ? (don't use _parse_expression which would consume ? as ternary)
            condition = self._parse_or()
            if self._check(TokenType.QUESTION):
                self._advance()
                if self._check(TokenType.HASH):
                    true_expr = LiteralNode(value="")
                else:
                    true_expr = self._parse_or()
            else:
                true_expr = self._parse_or()
            if self._check(TokenType.HASH):
                self._advance()
                if self._check(TokenType.INLINE_COND):
                    false_expr = LiteralNode(value="")
                else:
                    false_expr = self._parse_or()
            else:
                false_expr = LiteralNode(value=0)
            if self._check(TokenType.INLINE_COND):
                self._advance()
            return InlineCondNode(condition=condition, true_expr=true_expr, false_expr=false_expr)
        if tok.type in (TokenType.VARIABLE, TokenType.IDENTIFIER):
            next_tok = self._peek_next()
            if next_tok is not None and next_tok.type == TokenType.LPAREN and tok.type == TokenType.IDENTIFIER:
                name = self._advance().value
                self._advance()
                self._paren_depth += 1
                args: list[ExpressionNode] = []
                if not self._check(TokenType.RPAREN):
                    args = self._parse_argument_list()
                self._paren_depth -= 1
                self._expect(TokenType.RPAREN)
                return FunctionCallNode(function_name=name, arguments=args)
            return self._parse_variable_access()
        if tok.type in (TokenType.GLOBAL_MOD, TokenType.SAVEDATA_MOD, TokenType.CHARA_MOD, TokenType.CHARADATA_MOD):
            var_name = self._advance().value
            return VariableAccessNode(var_name=var_name, indices=[])
        if tok.type in (TokenType.CHARANUM, TokenType.LINECOUNT, TokenType.CURRENTREDRAW,
                        TokenType.RAND, TokenType.ABS, TokenType.SIGN, TokenType.MAX, TokenType.MIN, TokenType.GETBIT,
                        TokenType.POWER_FUNC, TokenType.SQRT, TokenType.FINDELEMENT, TokenType.FINDCHARA,
                        TokenType.STRLENS, TokenType.STRLENSU, TokenType.SUBSTRING, TokenType.SUBSTRINGU,
                        TokenType.CHARATU, TokenType.REPLACE, TokenType.SPLIT, TokenType.STRCOUNT,
                        TokenType.STRFIND, TokenType.STRFINDU,
                        TokenType.TOSTR, TokenType.TOINT, TokenType.LIMIT, TokenType.GETTIME,
                        TokenType.CHKFONT, TokenType.CHKDATA):
            var_name = self._advance().value
            # Support parenthesized argument form: LIMIT(expr, min, max)
            if self._check(TokenType.LPAREN):
                self._advance()
                self._paren_depth += 1
                args: list[ExpressionNode] = []
                if not self._check(TokenType.RPAREN):
                    args = self._parse_argument_list()
                self._paren_depth -= 1
                self._expect(TokenType.RPAREN)
                return FunctionCallNode(function_name=var_name, arguments=args)
            indices: list[ExpressionNode] = []
            while self._check(TokenType.COLON):
                self._advance()
                indices.append(self._parse_expression())
            if indices:
                return FunctionCallNode(function_name=var_name, arguments=indices)
            return VariableAccessNode(var_name=var_name, indices=[])
        raise ParserError(
            f"Unexpected token in expression: '{tok.value}'",
            filename=self._current_filename,
            line=tok.line,
            actual=tok,
        )
