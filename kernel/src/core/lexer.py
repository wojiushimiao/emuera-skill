from __future__ import annotations

import re
from typing import Any

from .tokens import LexerError, Token, TokenType

_KEYWORD_MAP: dict[str, TokenType] = {
    'IF': TokenType.IF,
    'ELSEIF': TokenType.ELSEIF,
    'ELSE': TokenType.ELSE,
    'ENDIF': TokenType.ENDIF,
    'SIF': TokenType.SIF,
    'SELECTCASE': TokenType.SELECTCASE,
    'CASE': TokenType.CASE,
    'CASEELSE': TokenType.CASEELSE,
    'TO': TokenType.TO,
    'STEP': TokenType.STEP,
    'ENDSELECT': TokenType.ENDSELECT,
    'FOR': TokenType.FOR,
    'NEXT': TokenType.NEXT,
    'WHILE': TokenType.WHILE,
    'WEND': TokenType.WEND,
    'DO': TokenType.DO,
    'LOOP': TokenType.LOOP,
    'UNTIL': TokenType.UNTIL,
    'REPEAT': TokenType.REPEAT,
    'REND': TokenType.REND,
    'BREAK': TokenType.BREAK,
    'CONTINUE': TokenType.CONTINUE,
    'GOTO': TokenType.GOTO,
    'RETURN': TokenType.RETURN,
    'RETURNF': TokenType.RETURNF,
    'CALL': TokenType.CALL,
    'TRYCALL': TokenType.TRYCALL,
    'CALLFORM': TokenType.CALLFORM,
    'TRYCALLFORM': TokenType.TRYCALLFORM,
    'TRYCCALLFORM': TokenType.TRYCCALLFORM,
    'CATCH': TokenType.CATCH,
    'ENDCATCH': TokenType.ENDCATCH,
    'TRYCALLLIST': TokenType.TRYCALLLIST,
    'ENDIFUNC': TokenType.ENDIFUNC,
    'JUMP': TokenType.JUMP,
    'DOTRAIN': TokenType.DOTRAIN,
    'PRINT': TokenType.PRINT,
    'PRINTL': TokenType.PRINTL,
    'PRINTW': TokenType.PRINTW,
    'PRINTC': TokenType.PRINTC,
    'PRINTLC': TokenType.PRINTLC,
    'PRINTDL': TokenType.PRINTDL,
    'PRINTV': TokenType.PRINTV,
    'PRINTVL': TokenType.PRINTVL,
    'PRINTS': TokenType.PRINTS,
    'PRINTSL': TokenType.PRINTSL,
    'PRINTFORM': TokenType.PRINTFORM,
    'PRINTFORML': TokenType.PRINTFORML,
    'PRINTFORMW': TokenType.PRINTFORMW,
    'PRINTFORMC': TokenType.PRINTFORMC,
    'PRINTFORMLC': TokenType.PRINTFORMLC,
    'PRINTFORMDC': TokenType.PRINTFORMDC,
    'PRINTFORMD': TokenType.PRINTFORMD,
    'PRINTFORMDL': TokenType.PRINTFORMDL,
    'PRINTFORMDW': TokenType.PRINTFORMDW,
    'PRINTFORMS': TokenType.PRINTFORMS,
    'SPRITEDISPOSE': TokenType.SPRITEDISPOSE,
    'PRINTDATA': TokenType.PRINTDATA,
    'PRINTDATAL': TokenType.PRINTDATAL,
    'DATALIST': TokenType.DATALIST,
    'ENDLIST': TokenType.ENDLIST,
    'DATA': TokenType.DATA,
    'DATAFORM': TokenType.DATAFORM,
    'ENDDATA': TokenType.ENDDATA,
    'INPUT': TokenType.INPUT,
    'INPUTS': TokenType.INPUTS,
    'ONEINPUT': TokenType.ONEINPUT,
    'ONEINPUTS': TokenType.ONEINPUTS,
    'TINPUT': TokenType.TINPUT,
    'TINPUTS': TokenType.TINPUTS,
    'TONEINPUT': TokenType.TONEINPUT,
    'TONEINPUTS': TokenType.TONEINPUTS,
    'WAIT': TokenType.WAIT,
    'DRAWLINE': TokenType.DRAWLINE,
    'DRAWLINEFORM': TokenType.DRAWLINEFORM,
    'CLEARLINE': TokenType.CLEARLINE,
    'REDRAW': TokenType.REDRAW,
    'CUSTOMDRAWLINE': TokenType.CUSTOMDRAWLINE,
    'SETCOLOR': TokenType.SETCOLOR,
    'RESETCOLOR': TokenType.RESETCOLOR,
    'PRINTBUTTON': TokenType.PRINTBUTTON,
    'PRINTBUTTONC': TokenType.PRINTBUTTONC,
    'BAR': TokenType.BAR,
    'TIMES': TokenType.TIMES,
    'THROW': TokenType.THROW,
    'BEGIN': TokenType.BEGIN,
    'RESTART': TokenType.RESTART,
    'VARSET': TokenType.VARSET,
    'INVERTBIT': TokenType.INVERTBIT,
    'GETBIT': TokenType.GETBIT,
    'SETBIT': TokenType.SETBIT,
    'CLEARBIT': TokenType.CLEARBIT,
    'ADDCHARA': TokenType.ADDCHARA,
    'DELCHARA': TokenType.DELCHARA,
    'SAVEDATA': TokenType.SAVEDATA,
    'LOADDATA': TokenType.LOADDATA,
    'LOADGLOBAL': TokenType.LOADGLOBAL,
    'SAVEGLOBAL': TokenType.SAVEGLOBAL,
    'FUNCTION': TokenType.FUNCTION,
    'FUNCTIONS': TokenType.FUNCTIONS,
    'DIM': TokenType.DIM,
    'DIMS': TokenType.DIMS,
    'DEFINE': TokenType.DEFINE,
    'CONST': TokenType.CONST,
    'DYNAMIC': TokenType.DYNAMIC,
    'REF': TokenType.REF,
    'SAVEDATA_MOD': TokenType.SAVEDATA_MOD,
    'GLOBAL_MOD': TokenType.GLOBAL_MOD,
    'CHARA_MOD': TokenType.CHARA_MOD,
    'CHARADATA_MOD': TokenType.CHARADATA_MOD,
    'DEBUGPRINT': TokenType.DEBUGPRINT,
    'DEBUGPRINTL': TokenType.DEBUGPRINTL,
    'DEBUGPRINTW': TokenType.DEBUGPRINTW,
    'DEBUGPRINTFORM': TokenType.DEBUGPRINTFORM,
    'DEBUGPRINTFORML': TokenType.DEBUGPRINTFORML,
    'DEBUGPRINTFORMW': TokenType.DEBUGPRINTFORMW,
    'PRINTSINGLEFORM': TokenType.PRINTSINGLEFORM,
    'PRINTSINGLEFORMS': TokenType.PRINTSINGLEFORMS,
    'PRINTPLAINFORM': TokenType.PRINTPLAINFORM,
    'PRINTPLAIN': TokenType.PRINTPLAIN,
    'HTML_PRINT': TokenType.HTML_PRINT,
    'ALIGNMENT': TokenType.ALIGNMENT,
    'RESETCOLOR': TokenType.RESETCOLOR,
    'GETTIME': TokenType.GETTIME,
    'STRLENS': TokenType.STRLENS,
    'STRLENSU': TokenType.STRLENSU,
    'SUBSTRING': TokenType.SUBSTRING,
    'SUBSTRINGU': TokenType.SUBSTRINGU,
    'CHARATU': TokenType.CHARATU,
    'REPLACE': TokenType.REPLACE,
    'SPLIT': TokenType.SPLIT,
    'STRCOUNT': TokenType.STRCOUNT,
    'STRFIND': TokenType.STRFIND,
    'STRFINDU': TokenType.STRFINDU,
    'TOSTR': TokenType.TOSTR,
    'TOINT': TokenType.TOINT,
    'LIMIT': TokenType.LIMIT,
    'RAND': TokenType.RAND,
    'ABS': TokenType.ABS,
    'SIGN': TokenType.SIGN,
    'MAX': TokenType.MAX,
    'MIN': TokenType.MIN,
    'POWER': TokenType.POWER_FUNC,
    'POWER_FUNC': TokenType.POWER_FUNC,
    'SQRT': TokenType.SQRT,
    'FINDELEMENT': TokenType.FINDELEMENT,
    'FINDCHARA': TokenType.FINDCHARA,
    'CHARANUM': TokenType.CHARANUM,
    'CURRENTREDRAW': TokenType.CURRENTREDRAW,
    'LINECOUNT': TokenType.LINECOUNT,
    'RESETDATA': TokenType.RESETDATA,
    'LOADGAME': TokenType.LOADGAME,
    'SAVEGAME': TokenType.SAVEGAME,
    'PUTFORM': TokenType.PUTFORM,
    'FONTSTYLE': TokenType.FONTSTYLE,
    'SETFONT': TokenType.SETFONT,
    'TWAIT': TokenType.TWAIT,
    'TONEINPUT': TokenType.TONEINPUT,
    'TONEINPUTS': TokenType.TONEINPUTS,
    'SAVECHARA': TokenType.SAVECHARA,
    'LOADCHARA': TokenType.LOADCHARA,
    'STRLENFORMU': TokenType.STRLENFORMU,
    'STRLENFORM': TokenType.STRLENFORM,
    'CALLFORMF': TokenType.CALLFORMF,
    'TRYCALLFORMF': TokenType.TRYCALLFORMF,
    'REUSELASTLINE': TokenType.REUSELASTLINE,
    'PRINTSW': TokenType.PRINTSW,
    'SKIPDISP': TokenType.SKIPDISP,
    'SETBGCOLOR': TokenType.SETBGCOLOR,
    'RESETBGCOLOR': TokenType.RESETBGCOLOR,
    'ARRAYCOPY': TokenType.ARRAYCOPY,
    'SWAP': TokenType.SWAP,
    'SWAPCHARA': TokenType.SWAPCHARA,
    'COPYCHARA': TokenType.COPYCHARA,
    'PICKUPCHARA': TokenType.PICKUPCHARA,
    'SORTCHARA': TokenType.SORTCHARA,
    'CHKDATA': TokenType.CHKDATA,
    'CHKFONT': TokenType.CHKFONT,
    'DELDATA': TokenType.DELDATA,
    'ADDCOPYCHARA': TokenType.ADDCOPYCHARA,
    'SETLINECOUNT': TokenType.SETLINECOUNT,
    'GETLINECOUNT': TokenType.GETLINECOUNT,
    'CHKSPEED': TokenType.CHKSPEED,
}

_TWO_CHAR_OPS: dict[str, TokenType] = {
    '**': TokenType.POWER,
    "'=": TokenType.STR_ASSIGN,
    '++': TokenType.INCREMENT,
    '--': TokenType.DECREMENT,
    '==': TokenType.EQ,
    '!=': TokenType.NEQ,
    '<=': TokenType.LTE,
    '>=': TokenType.GTE,
    '<<': TokenType.LSHIFT,
    '>>': TokenType.RSHIFT,
    '&&': TokenType.AND,
    '||': TokenType.OR,
    '+=': TokenType.PLUS_ASSIGN,
    '-=': TokenType.MINUS_ASSIGN,
    '*=': TokenType.STAR_ASSIGN,
    '/=': TokenType.SLASH_ASSIGN,
    '%=': TokenType.PERCENT_ASSIGN,
    '|=': TokenType.PIPE_ASSIGN,
    '&=': TokenType.AMP_ASSIGN,
    '^=': TokenType.CARET_ASSIGN,
    '[[': TokenType.DOUBLE_LBRACKET,
    ']]': TokenType.DOUBLE_RBRACKET,
}

_ONE_CHAR_OPS: dict[str, TokenType] = {
    '+': TokenType.PLUS,
    '-': TokenType.MINUS,
    '*': TokenType.STAR,
    '/': TokenType.SLASH,
    '%': TokenType.PERCENT,
    '&': TokenType.AMP,
    '|': TokenType.PIPE,
    '^': TokenType.CARET,
    '~': TokenType.TILDE,
    '!': TokenType.NOT,
    '<': TokenType.LT,
    '>': TokenType.GT,
    '=': TokenType.ASSIGN,
    '?': TokenType.QUESTION,
    ',': TokenType.COMMA,
    '(': TokenType.LPAREN,
    ')': TokenType.RPAREN,
    '{': TokenType.LBRACE,
    '}': TokenType.RBRACE,
}

_THREE_CHAR_OPS: dict[str, TokenType] = {
    '<<=': TokenType.LSHIFT_ASSIGN,
    '>>=': TokenType.RSHIFT_ASSIGN,
}

_RE_IDENTIFIER = re.compile(r'[\w／￥％：（）～「」？・＿＝＆！＋]+', re.UNICODE)
_RE_INTEGER = re.compile(r'[0-9]+')
_RE_FLOAT = re.compile(r'[0-9]+\.[0-9]+')
_RE_HEX = re.compile(r'0[xX][0-9a-fA-F]+')
_RE_IF_DEBUG_START = re.compile(r'\[IF[_ ]DEBUG\]', re.IGNORECASE)
_RE_SKIP_DIRECTIVE = re.compile(r'\[(SKIPSTART|SKIPEND)\]', re.IGNORECASE)
_RE_SKIPEND = re.compile(r'\[SKIPEND\]', re.IGNORECASE)
_RE_IF_DEBUG_END = re.compile(r'\[ENDIF\]', re.IGNORECASE)
_RE_BIT_POSITION = re.compile(r'^(\d+)p(\d+)$')

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
    TokenType.DATAFORM,
    TokenType.DEBUGPRINTFORM,
    TokenType.DEBUGPRINTFORML,
    TokenType.DEBUGPRINTFORMW,
    TokenType.PRINTSINGLEFORM,
    TokenType.PRINTSINGLEFORMS,
    TokenType.PRINTPLAINFORM,
    TokenType.SPRITEDISPOSE,
})

_PRINT_TEXT_TYPES = frozenset({
    TokenType.PRINT,
    TokenType.PRINTL,
    TokenType.PRINTW,
    TokenType.PRINTC,
    TokenType.PRINTLC,
    TokenType.PRINTDL,
    TokenType.PRINTV,
    TokenType.PRINTVL,
    TokenType.PRINTSL,
    TokenType.PRINTPLAIN,
    TokenType.DRAWLINEFORM,
})


class Lexer:
    def __init__(self, known_variables: set[str], known_functions: set[str]):
        self.known_variables = known_variables
        self.known_functions = known_functions
        self._filename: str = '<unknown>'
        self._in_debug_block: bool = False

    def tokenize(self, source: str, filename: str = '<unknown>') -> list[Token]:
        self._filename = filename
        self._in_debug_block = False
        tokens: list[Token] = []
        lines = source.split('\n')
        skip_mode = False
        joined_lines = self._join_brace_continuation(lines)
        for line_no, line in enumerate(joined_lines, start=1):
            stripped = line.strip()
            if skip_mode:
                if not stripped.startswith(';') and '[SKIPEND]' in line.upper():
                    skip_mode = False
                continue
            if not stripped.startswith(';') and '[SKIPSTART]' in line.upper():
                skip_mode = True
                continue
            line_tokens = self.tokenize_line(line, line_no)
            tokens.extend(line_tokens)
        tokens.append(Token(TokenType.EOF, None, len(lines), 0, self._filename))
        return tokens

    def _join_brace_continuation(self, lines: list[str]) -> list[str]:
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.rstrip()
            if stripped.strip() == '{':
                indent = line[:len(line) - len(line.lstrip())]
                brace_depth = 1
                content_parts = []
                i += 1
                while i < len(lines) and brace_depth > 0:
                    next_line = lines[i]
                    next_stripped = next_line.strip()
                    for ch in next_stripped:
                        if ch == '{':
                            brace_depth += 1
                        elif ch == '}':
                            brace_depth -= 1
                    if brace_depth <= 0:
                        # Remove the closing } and any content after it
                        last_brace = next_stripped.rfind('}')
                        part = next_stripped[:last_brace].strip()
                        if part:
                            content_parts.append(part)
                    else:
                        content_parts.append(next_stripped)
                    i += 1
                    if brace_depth <= 0:
                        break
                joined = indent + ' '.join(content_parts)
                result.append(joined)
            elif stripped.endswith('{') and not stripped.endswith("'{") and not self._is_in_string(stripped, len(stripped) - 1):
                indent = line[:len(line) - len(line.lstrip())]
                content_before_brace = stripped[:-1].strip()
                brace_depth = 1
                content_parts = [content_before_brace] if content_before_brace else []
                i += 1
                while i < len(lines) and brace_depth > 0:
                    next_line = lines[i]
                    next_stripped = next_line.strip()
                    for ch in next_stripped:
                        if ch == '{':
                            brace_depth += 1
                        elif ch == '}':
                            brace_depth -= 1
                    if brace_depth <= 0:
                        # Remove the closing } and any content after it
                        last_brace = next_stripped.rfind('}')
                        part = next_stripped[:last_brace].strip()
                        if part:
                            content_parts.append(part)
                    else:
                        content_parts.append(next_stripped)
                    i += 1
                    if brace_depth <= 0:
                        break
                joined = indent + ' '.join(content_parts)
                result.append(joined)
            elif i + 1 < len(lines):
                next_stripped = lines[i + 1].lstrip()
                if next_stripped.startswith('||') or next_stripped.startswith('&&'):
                    joined = line.rstrip()
                    i += 1
                    while i < len(lines):
                        next_stripped = lines[i].lstrip()
                        if next_stripped.startswith('||') or next_stripped.startswith('&&'):
                            joined += ' ' + next_stripped
                            i += 1
                        else:
                            break
                    result.append(joined)
                elif (stripped.endswith(',') or stripped.endswith('(')) and self._is_continuation_line(stripped):
                    joined = line.rstrip()
                    i += 1
                    while i < len(lines):
                        next_stripped = lines[i].strip()
                        # Don't join if next line starts a new statement
                        if self._starts_new_statement(next_stripped):
                            break
                        joined += ' ' + next_stripped
                        i += 1
                        if not next_stripped.endswith(',') and not next_stripped.endswith('('):
                            break
                    result.append(joined)
                else:
                    result.append(line)
                    i += 1
            else:
                result.append(line)
                i += 1
        return result


    def _is_continuation_line(self, stripped: str) -> bool:
        upper = stripped.strip().upper()
        continuation_prefixes = (
            'CALL ', 'CALLFORM ', 'TRYCALL ', 'TRYCALLFORM ',
            'TRYCCALLFORM ', 'SETBIT ', 'CLEARBIT ', 'INVERTBIT ', 'GETBIT ',
            'VARSET ', 'ARRAYCOPY ', 'SWAP ', 'BAR ',
            'PRINT_DATA ', 'PRINTDATA',
        )
        for prefix in continuation_prefixes:
            if upper.startswith(prefix):
                return True
        if stripped.rstrip().endswith('('):
            func_callers = ('CALL ', 'ASK_M', 'HPH_PRINT', 'K2_HPH_PRINT',
                            'PRINT_COLORBAR', 'K65_AEGI', 'K17_SPLIT_SHUFFLE',
                            'TEXTR', 'M_KOJO_K83_AUTO')
            for fc in func_callers:
                if fc.upper() in upper:
                    return True
        return False

    def _starts_new_statement(self, line: str) -> bool:
        """Check if a line starts with a statement keyword (not a continuation)."""
        upper = line.lstrip().upper()
        # Keywords that always start a new statement
        statement_keywords = (
            'PRINT', 'PRINTL', 'PRINTS', 'PRINTV', 'PRINTFORM', 'PRINTFORML',
            'PRINTFORMS', 'PRINTFORMV', 'PRINTDATA', 'DATALIST', 'DATA', 'DATAFORM',
            'ENDLIST', 'ENDDATA',
            'IF', 'ELSEIF', 'ELSE', 'ENDIF', 'SIF',
            'FOR', 'NEXT', 'WHILE', 'WEND', 'DO', 'LOOP', 'REPEAT', 'REND',
            'SELECTCASE', 'CASE', 'CASEELSE', 'ENDSELECT',
            'GOTO', 'GOSUB', 'RETURN', 'RETURNF',
            'CALL', 'CALLFORM', 'TRYCALL', 'TRYCALLFORM',
            'JUMP', 'JUMPFORM', 'TRYJUMP', 'TRYJUMPFORM',
            'BEGIN',
            'WAIT', 'WAITANYKEY',
            'DRAWLINE', 'CUSTOMDRAWLINE',
            'TIMES', 'INPUT', 'TINPUT', 'ONEINPUT', 'TONEINPUT',
            'STRLEN', 'STRLENS', 'STRLENSU',
            'VARSET', 'CUPCHECK',
            'SETBIT', 'CLEARBIT', 'INVERTBIT',
            'PUTFORM', 'SAVEDATA', 'LOADDATA',
            'THROW', 'DEBUGPRINT', 'DEBUGPRINTL',
            'ADDDEFCHARA', 'DELCHARA', 'SWAP', 'SWAPCHARA', 'COPYCHARA', 'ADDCHARA',
            'PICKUPCHARA', 'SORTCHARA',
            'SPRITEDISPOSE',
            'REDRAW', 'FONTSTYLE', 'FONTCOLOR', 'BGCOLOR',
            'CLEARLINE', 'CLEARLOG',
            'BAR', 'STRFIND', 'STRFINDU',
            'SPLIT', 'REPLACE', 'SUBSTRING', 'SUBSTRINGU',
            'GETBIT', 'GETNUM',
            'ADDDATA', 'DELALLDATA',
            'CHOOSE', 'CHKFONT', 'CHKDATA', 'DELDATA',
            'MONEYSTR', 'GETTIME', 'GETMILLISECOND', 'GETSECOND', 'GETMINUTE', 'GETHOUR', 'GETDAY', 'GETMONTH', 'GETYEAR',
            'GETCONFIG', 'GETCONFIGS',
            'NOLOCALS', 'NOREF', 'PRI', 'LATER', 'SINGLE',
            'FUNCTION', 'ENDFUNCTION', 'EVENT', 'ENDEVENT',
            '#DIM', '#DIMS', '#DEFINE', '#CONST', '#DYNAMIC', '#REF',
        )
        for kw in statement_keywords:
            if upper.startswith(kw):
                rest_idx = len(kw)
                if rest_idx < len(upper) and upper[rest_idx].isalpha():
                    continue
                return True
        stripped_line = line.strip()
        if "'=" in stripped_line or " = " in stripped_line or stripped_line.endswith("="):
            if not stripped_line.startswith(';'):
                return True
        return False
    def _is_in_string(self, line: str, pos: int) -> bool:
        in_str = False
        quote_char = None
        for i in range(pos):
            ch = line[i]
            if not in_str and ch in ('"', "'"):
                in_str = True
                quote_char = ch
            elif in_str and ch == quote_char:
                in_str = False
                quote_char = None
        return in_str

    def tokenize_line(self, line: str, line_no: int) -> list[Token]:
        self._filename = getattr(self, '_filename', '<unknown>')
        tokens: list[Token] = []
        pos = 0
        length = len(line)

        if self._in_debug_block:
            end_match = _RE_IF_DEBUG_END.search(line)
            if end_match:
                self._in_debug_block = False
                tokens.append(Token(
                    TokenType.ENDIF_DEBUG, '[ENDIF]',
                    line_no, end_match.start() + 1, self._filename,
                ))
            return tokens

        stripped = line.lstrip()
        if stripped.startswith(';'):
            tokens.append(Token(
                TokenType.COMMENT, line.strip(),
                line_no, 1, self._filename,
            ))
            tokens.append(Token(TokenType.NEWLINE, '\n', line_no, length + 1, self._filename))
            return tokens

        if not stripped:
            tokens.append(Token(TokenType.NEWLINE, '\n', line_no, 1, self._filename))
            return tokens

        debug_match = _RE_IF_DEBUG_START.search(line)
        if debug_match:
            self._in_debug_block = True
            tokens.append(Token(
                TokenType.IF_DEBUG, '[IF_DEBUG]',
                line_no, debug_match.start() + 1, self._filename,
            ))
            end_match = _RE_IF_DEBUG_END.search(line, debug_match.end())
            if end_match:
                self._in_debug_block = False
                tokens.append(Token(
                    TokenType.ENDIF_DEBUG, '[ENDIF]',
                    line_no, end_match.start() + 1, self._filename,
                ))
            tokens.append(Token(TokenType.NEWLINE, '\n', line_no, length + 1, self._filename))
            return tokens

        in_printform_content = False
        in_printform_expr = False
        in_brace_expr = False
        after_assign = False
        paren_depth_in_expr = 0
        in_string_literal = False  # DEV-007/008: 跟踪字符串字面量状态

        if line.startswith('\ufeff'):
            line = line[1:]
            length = len(line)

        while pos < length:
            ch = line[pos]

            if ch in (' ', '\t', '\r', '\u3000'):
                if in_printform_content and not in_printform_expr:
                    tokens.append(Token(TokenType.IDENTIFIER, ch, line_no, pos + 1, self._filename))
                pos += 1
                continue

            if ch == ';':
                tokens.append(Token(
                    TokenType.COMMENT, line[pos:],
                    line_no, pos + 1, self._filename,
                ))
                break

            if ch == '$':
                pos += 1
                label_match = _RE_IDENTIFIER.match(line, pos)
                if label_match:
                    label_name = label_match.group()
                    tokens.append(Token(
                        TokenType.LABEL, label_name,
                        line_no, pos + 1, self._filename,
                    ))
                    pos = label_match.end()
                else:
                    tokens.append(Token(
                        TokenType.LABEL, '',
                        line_no, pos + 1, self._filename,
                    ))
                    pos += 1
                continue

            if ch == '@':
                next_pos = pos + 1
                if next_pos < length and line[next_pos] == '"':
                    tokens.append(Token(TokenType.FORMAT_STRING, '@', line_no, pos + 1, self._filename))
                    pos += 1
                    # Scan the @"..." content but tokenize it like PRINTFORM content
                    # so that %...% and \@...\@ are properly parsed
                    string_token, end_pos = self._scan_string(line, pos, line_no, format_string=True)
                    inner_content = string_token.value
                    pos = end_pos
                    # Re-tokenize the inner content as PRINTFORM content
                    inner_tokens = self._tokenize_format_string_content(inner_content, line_no)
                    tokens.extend(inner_tokens)
                    tokens.append(Token(TokenType.FORMAT_STRING_END, '', line_no, pos, self._filename))
                    continue
                pos += 1
                func_match = _RE_IDENTIFIER.match(line, pos)
                if func_match:
                    func_name = func_match.group()
                    tokens.append(Token(
                        TokenType.AT, func_name,
                        line_no, pos + 1, self._filename,
                    ))
                    pos = func_match.end()
                else:
                    tokens.append(Token(
                        TokenType.AT, '',
                        line_no, pos + 1, self._filename,
                    ))
                continue

            if ch == '#':
                pos += 1
                directive_match = _RE_IDENTIFIER.match(line, pos)
                if directive_match:
                    directive_name = directive_match.group().upper()
                    if directive_name == 'DIM':
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.DIM, 'DIM', line_no, pos + 1, self._filename))
                    elif directive_name == 'DIMS':
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.DIMS, 'DIMS', line_no, pos + 1, self._filename))
                    elif directive_name == 'DEFINE':
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.DEFINE, 'DEFINE', line_no, pos + 1, self._filename))
                    elif directive_name == 'FUNCTION':
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.FUNCTION, 'FUNCTION', line_no, pos + 1, self._filename))
                    elif directive_name == 'FUNCTIONS':
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.FUNCTIONS, 'FUNCTIONS', line_no, pos + 1, self._filename))
                    elif directive_name == 'CONST':
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.CONST, 'CONST', line_no, pos + 1, self._filename))
                    elif directive_name == 'DYNAMIC':
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.DYNAMIC, 'DYNAMIC', line_no, pos + 1, self._filename))
                    elif directive_name == 'REF':
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.REF, 'REF', line_no, pos + 1, self._filename))
                    else:
                        tokens.append(Token(TokenType.HASH, '#', line_no, pos, self._filename))
                        tokens.append(Token(TokenType.IDENTIFIER, directive_name, line_no, pos + 1, self._filename))
                    pos = directive_match.end()
                else:
                    tokens.append(Token(TokenType.HASH, '#', line_no, pos + 1, self._filename))
                continue

            if ch == '@' and pos + 1 < length and line[pos + 1] in ('"', "'"):
                quote_char = line[pos + 1]
                if quote_char == '"':
                    # @"..." format string - tokenize content as PRINTFORM
                    tokens.append(Token(TokenType.FORMAT_STRING, '@', line_no, pos + 1, self._filename))
                    pos += 1
                    string_token, end_pos = self._scan_string(line, pos, line_no, format_string=True)
                    inner_content = string_token.value
                    pos = end_pos
                    inner_tokens = self._tokenize_format_string_content(inner_content, line_no)
                    tokens.extend(inner_tokens)
                    tokens.append(Token(TokenType.FORMAT_STRING_END, '', line_no, pos, self._filename))
                else:
                    # @'...' - treat as AT + string
                    tokens.append(Token(TokenType.AT, '@', line_no, pos + 1, self._filename))
                    pos += 1
                    ch = line[pos]
                    string_token, end_pos = self._scan_string(line, pos, line_no)
                    tokens.append(string_token)
                    pos = end_pos
                continue

            if ch == "'" and pos + 1 < length and line[pos + 1] == '=':
                _str_assign_ok = False
                if tokens:
                    _last_tok = tokens[-1]
                    if _last_tok.type in (TokenType.VARIABLE, TokenType.IDENTIFIER,
                                           TokenType.RPAREN, TokenType.RBRACKET,
                                           TokenType.INTEGER, TokenType.DOUBLE_RBRACKET):
                        _str_assign_ok = True
                if _str_assign_ok:
                    tokens.append(Token(TokenType.STR_ASSIGN, "'=", line_no, pos + 1, self._filename))
                    pos += 2
                    continue

            if ch in ('"', "'"):
                string_token, end_pos = self._scan_string(line, pos, line_no)
                tokens.append(string_token)
                pos = end_pos
                continue

            if ch == ':':
                next_pos = pos + 1
                if next_pos < length:
                    next_ch = line[next_pos]
                    if ('0' <= next_ch <= '9') or _RE_IDENTIFIER.match(line, next_pos):
                        tokens.append(Token(TokenType.COLON, ':', line_no, pos + 1, self._filename))
                        pos += 1
                        continue
                tokens.append(Token(TokenType.COLON, ':', line_no, pos + 1, self._filename))
                pos += 1
                continue

            if ch == '[':
                if pos + 1 < length and line[pos + 1] == '[':
                    bracket_end = line.find(']]', pos + 2)
                    if bracket_end != -1:
                        char_name = line[pos + 2:bracket_end]
                        tokens.append(Token(TokenType.DOUBLE_LBRACKET, '[[', line_no, pos + 1, self._filename))
                        tokens.append(Token(TokenType.STRING, char_name, line_no, pos + 3, self._filename))
                        tokens.append(Token(TokenType.DOUBLE_RBRACKET, ']]', line_no, bracket_end + 1, self._filename))
                        pos = bracket_end + 2
                        continue
                bracket_end = line.find(']', pos)
                if bracket_end != -1:
                    bracket_content = line[pos + 1:bracket_end].strip().upper()
                    if bracket_content in ('IF_DEBUG', 'IF DEBUG'):
                        self._in_debug_block = True
                        tokens.append(Token(TokenType.IF_DEBUG, '[IF_DEBUG]', line_no, pos + 1, self._filename))
                        tokens.append(Token(TokenType.NEWLINE, '\n', line_no, length + 1, self._filename))
                        return tokens
                    elif bracket_content in ('ENDIF', 'END IF'):
                        self._in_debug_block = False
                        tokens.append(Token(TokenType.ENDIF_DEBUG, '[ENDIF]', line_no, pos + 1, self._filename))
                        tokens.append(Token(TokenType.NEWLINE, '\n', line_no, length + 1, self._filename))
                        return tokens
                tokens.append(Token(TokenType.LBRACKET, '[', line_no, pos + 1, self._filename))
                pos += 1
                continue

            if ch == ']':
                tokens.append(Token(TokenType.RBRACKET, ']', line_no, pos + 1, self._filename))
                pos += 1
                continue

            if ch == '0' and pos + 1 < length and line[pos + 1] in ('x', 'X'):
                hex_match = _RE_HEX.match(line, pos)
                if hex_match:
                    tokens.append(Token(
                        TokenType.INTEGER, int(hex_match.group(), 16),
                        line_no, pos + 1, self._filename,
                    ))
                    pos = hex_match.end()
                    continue

            if '0' <= ch <= '9':
                num_match = _RE_FLOAT.match(line, pos)
                if num_match:
                    tokens.append(Token(
                        TokenType.FLOAT, float(num_match.group()),
                        line_no, pos + 1, self._filename,
                    ))
                    pos = num_match.end()
                    continue
                num_match = _RE_INTEGER.match(line, pos)
                if num_match:
                    num_str = num_match.group()
                    after_pos = num_match.end()
                    if after_pos < length and line[after_pos] == 'p':
                        p_after_pos = after_pos + 1
                        second_num = _RE_INTEGER.match(line, p_after_pos)
                        if second_num:
                            bit_val = f"{num_str}p{second_num.group()}"
                            tokens.append(Token(
                                TokenType.INTEGER, bit_val,
                                line_no, pos + 1, self._filename,
                            ))
                            pos = second_num.end()
                            continue
                    tokens.append(Token(
                        TokenType.INTEGER, int(num_str),
                        line_no, pos + 1, self._filename,
                    ))
                    pos = after_pos
                continue

            if ch.isalpha() or ch == '_' or (ord(ch) > 127 and re.match(r'\w', ch, re.UNICODE)):
                id_match = _RE_IDENTIFIER.match(line, pos)
                if id_match:
                    name = id_match.group()
                    name_upper = name.upper()
                    col = pos + 1

                    if name_upper in _KEYWORD_MAP:
                        token_type = _KEYWORD_MAP[name_upper]
                        tokens.append(Token(token_type, name, line_no, col, self._filename))
                        if token_type in _PRINTFORM_TYPES:
                            in_printform_content = True
                            if pos < length and line[pos] in (' ', '\t'):
                                pos += 1
                        elif token_type in _PRINT_TEXT_TYPES:
                            pos = id_match.end()
                            while pos < length and line[pos] in (' ', '\t'):
                                pos += 1
                            if pos < length:
                                text_content = line[pos:]
                                if text_content:
                                    tokens.append(Token(TokenType.STRING, text_content, line_no, pos + 1, self._filename))
                                pos = length
                            continue
                    elif name.upper() in self.known_variables:
                        # Emuera 默认忽略大小写，变量令牌统一输出大写规范名
                        tokens.append(Token(TokenType.VARIABLE, name.upper(), line_no, col, self._filename))
                    elif name.upper() in self.known_functions:
                        tokens.append(Token(TokenType.IDENTIFIER, name.upper(), line_no, col, self._filename))
                    else:
                        tokens.append(Token(TokenType.IDENTIFIER, name, line_no, col, self._filename))

                    pos = id_match.end()
                    continue

            if pos + 2 < length:
                three_char = line[pos:pos + 3]
                if three_char in _THREE_CHAR_OPS:
                    tokens.append(Token(_THREE_CHAR_OPS[three_char], three_char, line_no, pos + 1, self._filename))
                    pos += 3
                    continue

            if pos + 1 < length:
                two_char = line[pos:pos + 2]
                if two_char in _TWO_CHAR_OPS:
                    tokens.append(Token(_TWO_CHAR_OPS[two_char], two_char, line_no, pos + 1, self._filename))
                    pos += 2
                    continue

            # DEV-010/011/012: 在PRINTFORM内容中跟踪字符串字面量状态
            if in_printform_content and ch == '"' and not in_printform_expr:
                in_string_literal = not in_string_literal
            if in_printform_content and ch == '"' and in_printform_expr:
                in_string_literal = not in_string_literal

            if ch in _ONE_CHAR_OPS:
                tok_type = _ONE_CHAR_OPS[ch]
                if tok_type == TokenType.ASSIGN:
                    after_assign = True
                if in_printform_content and ch == '{' and not in_string_literal:
                    in_printform_expr = True
                    in_brace_expr = True
                elif in_printform_content and ch == '%' and not in_printform_expr and not in_string_literal:
                    in_printform_expr = True
                    in_brace_expr = False
                    paren_depth_in_expr = 0
                elif in_printform_content and in_printform_expr and ch == '%' and not in_brace_expr and paren_depth_in_expr <= 0 and not in_string_literal:
                    in_printform_expr = False
                elif in_printform_content and in_printform_expr and ch == '(':
                    paren_depth_in_expr += 1
                elif in_printform_content and in_printform_expr and ch == ')' and paren_depth_in_expr > 0:
                    paren_depth_in_expr -= 1
                elif in_printform_content and in_printform_expr and ch == '}' and paren_depth_in_expr <= 0:
                    in_printform_expr = False
                    in_brace_expr = False
                elif after_assign and ch == '%' and not in_printform_content:
                    in_printform_content = True
                    in_printform_expr = True
                    in_brace_expr = False
                    after_assign = False
                if in_printform_content and ch == '/' and pos + 1 < length and line[pos + 1] == '\\':
                    tokens.append(Token(TokenType.IDENTIFIER, '/', line_no, pos + 1, self._filename))
                    pos += 1
                    continue
                tokens.append(Token(tok_type, ch, line_no, pos + 1, self._filename))
                pos += 1
                continue

            if ch == '\\':
                if pos + 1 < length and line[pos + 1] == '@':
                    tokens.append(Token(TokenType.INLINE_COND, '\\@', line_no, pos + 1, self._filename))
                    pos += 2
                    continue
                if in_printform_content:
                    if pos + 1 < length:
                        next_ch = line[pos + 1]
                        if next_ch == '/':
                            tokens.append(Token(TokenType.IDENTIFIER, '/', line_no, pos + 1, self._filename))
                            pos += 2
                            continue
                        elif next_ch == '\\':
                            tokens.append(Token(TokenType.IDENTIFIER, '\\', line_no, pos + 1, self._filename))
                            pos += 2
                            continue
                        elif next_ch == '@':
                            tokens.append(Token(TokenType.INLINE_COND, '\\@', line_no, pos + 1, self._filename))
                            pos += 2
                            continue
                        elif next_ch == '%':
                            tokens.append(Token(TokenType.IDENTIFIER, '%', line_no, pos + 1, self._filename))
                            pos += 2
                            continue
                    tokens.append(Token(TokenType.IDENTIFIER, ch, line_no, pos + 1, self._filename))
                    pos += 1
                    continue
                tokens.append(Token(TokenType.IDENTIFIER, ch, line_no, pos + 1, self._filename))
                pos += 1
                continue

            if _RE_IDENTIFIER.match(ch) or ord(ch) > 127:
                ident_match = _RE_IDENTIFIER.match(line, pos)
                if ident_match:
                    ident = ident_match.group()
                    tokens.append(Token(TokenType.IDENTIFIER, ident, line_no, pos + 1, self._filename))
                    pos = ident_match.end()
                else:
                    tokens.append(Token(TokenType.IDENTIFIER, ch, line_no, pos + 1, self._filename))
                    pos += 1
                continue

            if ch == '.':
                tokens.append(Token(TokenType.IDENTIFIER, ch, line_no, pos + 1, self._filename))
                pos += 1
                continue

            # Backtick (`) is treated as a regular text character in ERB
            if ch == '`':
                tokens.append(Token(TokenType.IDENTIFIER, ch, line_no, pos + 1, self._filename))
                pos += 1
                continue

            raise LexerError(
                f"unexpected character: {ch!r}",
                self._filename, line_no, pos + 1,
            )

        tokens.append(Token(TokenType.NEWLINE, '\n', line_no, length + 1, self._filename))
        return tokens

    def _scan_string(self, line: str, pos: int, line_no: int, format_string: bool = False):
        quote = line[pos]
        start = pos
        pos += 1
        length = len(line)
        in_expr = False
        in_inline_cond = False
        in_string_literal = False  # DEV-010/011: 跟踪字符串字面量状态
        paren_depth = 0

        while pos < length:
            ch = line[pos]
            if in_expr:
                # DEV-010/011: 跟踪字符串字面量状态
                if ch == '"':
                    in_string_literal = not in_string_literal
                if in_string_literal:
                    pos += 1
                    continue
                if ch == '(':
                    paren_depth += 1
                elif ch == ')':
                    paren_depth -= 1
                elif ch == '%' and paren_depth <= 0:
                    in_expr = False
                pos += 1
                continue
            if in_inline_cond:
                # Inside \@...\@, look for closing \@
                if ch == '\\' and pos + 1 < length and line[pos + 1] == '@':
                    in_inline_cond = False
                    pos += 2
                    continue
                pos += 1
                continue
            # DEV-010/011: 只在format_string模式下才将%视为表达式定界符
            if ch == '%' and format_string:
                in_expr = True
                paren_depth = 0
                pos += 1
                continue
            # Detect \@ to start inline condition inside format strings
            if format_string and ch == '\\' and pos + 1 < length and line[pos + 1] == '@':
                in_inline_cond = True
                pos += 2
                continue
            if ch == quote:
                if format_string and pos + 1 < length and line[pos + 1] == quote:
                    pos += 2
                    continue
                if not format_string and quote == '"':
                    backslash_count = 0
                    p = pos - 1
                    while p > start and line[p] == '\\':
                        backslash_count += 1
                        p -= 1
                    if backslash_count % 2 == 1:
                        pos += 1
                        continue
                inner = line[start + 1:pos]
                if format_string:
                    inner = inner.replace('""', '"')
                elif quote == '"':
                    inner = inner.replace('\\\\', '\x00BACKSLASH\x00')
                    inner = inner.replace('\\"', '"')
                    inner = inner.replace('\x00BACKSLASH\x00', '\\')
                return Token(TokenType.STRING, inner, line_no, start + 1, self._filename), pos + 1
            pos += 1

        inner = line[start + 1:]
        if format_string:
            inner = inner.replace('""', '"')
        return Token(TokenType.STRING, inner, line_no, start + 1, self._filename), len(line)

    def _tokenize_format_string_content(self, content: str, line_no: int) -> list:
        """Tokenize the content of @"..." like PRINTFORM content.
        This handles %...% expressions and \\@...\\@ inline conditions."""
        tokens = []
        pos = 0
        length = len(content)
        in_expr = False
        in_inline_cond = False
        in_string_literal = False  # DEV-010/011/012: 跟踪字符串字面量状态
        paren_depth = 0
        text_start = 0

        while pos < length:
            ch = content[pos]

            if not in_expr and not in_inline_cond:
                # Look for { to start brace expression
                if ch == '{':
                    # Flush text before {
                    if pos > text_start:
                        text = content[text_start:pos]
                        tokens.append(Token(TokenType.IDENTIFIER, text, line_no, pos + 1, self._filename))
                    tokens.append(Token(TokenType.LBRACE, '{', line_no, pos + 1, self._filename))
                    pos += 1
                    text_start = pos
                    continue
                if ch == '}':
                    # Flush text before }
                    if pos > text_start:
                        text = content[text_start:pos]
                        expr_tokens = self._tokenize_expression_text(text, line_no)
                        tokens.extend(expr_tokens)
                    tokens.append(Token(TokenType.RBRACE, '}', line_no, pos + 1, self._filename))
                    pos += 1
                    text_start = pos
                    continue
                # Look for % to start expression
                if ch == '%':
                    # Flush text before %
                    if pos > text_start:
                        text = content[text_start:pos]
                        tokens.append(Token(TokenType.IDENTIFIER, text, line_no, pos + 1, self._filename))
                    tokens.append(Token(TokenType.PERCENT, '%', line_no, pos + 1, self._filename))
                    in_expr = True
                    paren_depth = 0
                    pos += 1
                    text_start = pos
                    continue
                # Look for \@ to start inline condition
                if ch == '\\' and pos + 1 < length and content[pos + 1] == '@':
                    # Flush text before \@
                    if pos > text_start:
                        text = content[text_start:pos]
                        tokens.append(Token(TokenType.IDENTIFIER, text, line_no, pos + 1, self._filename))
                    tokens.append(Token(TokenType.INLINE_COND, '\\@', line_no, pos + 1, self._filename))
                    in_inline_cond = True
                    paren_depth = 0
                    pos += 2
                    text_start = pos
                    continue
                pos += 1
                continue

            if in_inline_cond:
                # DEV-012: 跟踪字符串字面量状态，字符串内的字符不作特殊处理
                if ch == '"' and not in_string_literal:
                    in_string_literal = True
                    pos += 1
                    continue
                elif ch == '"' and in_string_literal:
                    in_string_literal = False
                    pos += 1
                    continue
                elif in_string_literal:
                    pos += 1
                    continue
                # Inside \@...\@, look for closing \@
                if ch == '\\' and pos + 1 < length and content[pos + 1] == '@':
                    # Flush expression text before \@
                    if pos > text_start:
                        expr_text = content[text_start:pos]
                        expr_tokens = self._tokenize_expression_text(expr_text, line_no)
                        tokens.extend(expr_tokens)
                    tokens.append(Token(TokenType.INLINE_COND, '\\@', line_no, pos + 1, self._filename))
                    in_inline_cond = False
                    in_string_literal = False  # 重置字符串状态
                    pos += 2
                    text_start = pos
                    continue
                pos += 1
                continue

            if in_expr:
                # DEV-010/011: 跟踪字符串字面量状态，字符串内的%不作定界符
                if ch == '"' and not in_string_literal:
                    in_string_literal = True
                    pos += 1
                    continue
                elif ch == '"' and in_string_literal:
                    in_string_literal = False
                    pos += 1
                    continue
                elif in_string_literal:
                    pos += 1
                    continue
                # Inside %...%, track parentheses and look for closing %
                if ch == '(':
                    paren_depth += 1
                    pos += 1
                    continue
                elif ch == ')':
                    paren_depth -= 1
                    pos += 1
                    continue
                elif ch == '%' and paren_depth <= 0:
                    # Closing % found
                    if pos > text_start:
                        expr_text = content[text_start:pos]
                        expr_tokens = self._tokenize_expression_text(expr_text, line_no)
                        tokens.extend(expr_tokens)
                    tokens.append(Token(TokenType.PERCENT, '%', line_no, pos + 1, self._filename))
                    in_expr = False
                    in_string_literal = False  # 重置字符串状态
                    pos += 1
                    text_start = pos
                    continue
                pos += 1
                continue

        # Flush remaining text
        if text_start < length:
            remaining = content[text_start:]
            if in_expr or in_inline_cond:
                expr_tokens = self._tokenize_expression_text(remaining, line_no)
                tokens.extend(expr_tokens)
            else:
                tokens.append(Token(TokenType.IDENTIFIER, remaining, line_no, length, self._filename))

        return tokens

    def _tokenize_expression_text(self, text: str, line_no: int) -> list:
        """Tokenize expression text from inside %...% or \\@...\\@ in format strings."""
        tokens = []
        saved_filename = self._filename
        try:
            line_tokens = self.tokenize_line(text, line_no)
            for tok in line_tokens:
                if tok.type != TokenType.NEWLINE:
                    tokens.append(tok)
        except LexerError:
            tokens.append(Token(TokenType.IDENTIFIER, text, line_no, 1, saved_filename))
        return tokens

    def _is_printform_context(self, line: str, string_pos: int) -> bool:
        before = line[:string_pos].strip().upper()
        for kw in ('PRINTFORM', 'PRINTFORML', 'PRINTFORMW', 'PRINTFORMC', 'DATAFORM'):
            if before.endswith(kw):
                return True
        return False
