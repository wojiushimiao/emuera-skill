from __future__ import annotations

import json
import os
import codecs
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from .core.lexer import Lexer
from .core.parser import Parser
from .core.semantic_analyzer import SemanticAnalyzer
from .core.variable_manager import VariableManager
from .core.function_dispatcher import FunctionDispatcher, FunctionDescriptor
from .core.vm import VirtualMachine, BeginSignal, ThrowSignal
from .io.renderer import TerminalRenderer
from .loader.csv_loader import CSVLoader
from .loader.erh_processor import ERHProcessor


@dataclass
class LLMConfig:
    api_key: str = ""
    model: str = ""
    endpoint: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048


@dataclass
class MonitorEvent:
    timestamp: float
    category: str
    message: str
    detail: str = ""


class ERBEngine:

    def __init__(self, game_dir: str, llm_config: LLMConfig | None = None, monitor_log: str | None = None,
                 abort_event: Any = None, progress_callback: Any = None):
        self.game_dir = game_dir
        self.llm_config = llm_config
        # 协作式装配控制（可选，向后兼容）：
        #   abort_event       —— 任何带 .is_set() 的对象（如 threading.Event）；置位后在文件边界优雅中止
        #   progress_callback —— callable(phase, done, total)；用于外部按“进度”而非“墙钟”判别健康度
        self._abort_event = abort_event
        self._progress_callback = progress_callback
        self.variable_mgr: VariableManager | None = None
        self.lexer: Lexer | None = None
        self.parser: Parser | None = None
        self.semantic_analyzer: SemanticAnalyzer | None = None
        self.function_dispatch: FunctionDispatcher | None = None
        self.io_renderer: TerminalRenderer | None = None
        self.llm_bridge: Any = None
        self.vm: VirtualMachine | None = None
        self.csv_loader: CSVLoader | None = None
        self.erh_processor: ERHProcessor | None = None
        self._programs: list[Any] = []
        self._begin_mode: str = "TITLE"
        self._running: bool = False
        self._monitor_log_path: str | None = monitor_log
        self._monitor_events: list[MonitorEvent] = []
        self._init_time: float = 0.0
        self._run_start_time: float = 0.0
        self._begin_transitions: list[tuple[str, str, float]] = []
        self._parse_errors: list[str] = []
        self._runtime_errors: list[str] = []
        self._func_call_count: int = 0

    def _log_event(self, category: str, message: str, detail: str = "") -> None:
        event = MonitorEvent(time.time(), category, message, detail)
        self._monitor_events.append(event)
        if self._monitor_log_path:
            with open(self._monitor_log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S', time.localtime(event.timestamp))}] [{category}] {message}\n")

    def run_semantic_checks(self) -> list[str]:
        """对外暴露的语义校验入口（装配后、实机运行前调用）。

        重跑一次跨函数 SEMA 校验并返回诊断清单（纯文本行，每行含规则码与 文件:行号）。
        引擎 initialize() 已自动执行过一轮；本方法供工具包（scan / project-checkup /
        capability）在展示"0 解析错误"之外再补充 SEMA 语义层结论。
        """
        if self.semantic_analyzer is None or not self._programs:
            return []
        diagnostics = self.semantic_analyzer.check_programs(self._programs)
        self._sema_warnings = list(diagnostics)
        for diag in diagnostics:
            self._log_event("WARNING", f"[SEMA] {diag}")
        return diagnostics

    def get_semantic_warnings(self) -> list[str]:
        """返回最近一次 SEMA 校验的原始诊断清单（若 initialize 已执行）。"""
        return list(getattr(self, "_sema_warnings", []))

    def _emit_progress(self, phase: str, done: int, total: int) -> None:
        """协作式进度上报：向可选的 progress_callback 发出 (phase, done, total)。
        回调内部异常一律吞掉，绝不影响装配主流程。"""
        cb = self._progress_callback
        if cb is None:
            return
        try:
            cb(phase, done, total)
        except Exception:
            pass

    def _abort_requested(self) -> bool:
        """协作式中止检查：外部通过 abort_event 请求中止装配。"""
        ev = self._abort_event
        return ev is not None and ev.is_set()

    def get_monitor_report(self) -> dict[str, Any]:
        errors = [e for e in self._monitor_events if e.category in ("ERROR", "PARSE_ERROR", "RUNTIME_ERROR")]
        warnings = [e for e in self._monitor_events if e.category == "WARNING"]
        return {
            "game_dir": self.game_dir,
            "init_time_sec": self._init_time,
            "total_events": len(self._monitor_events),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "begin_transitions": self._begin_transitions,
            "func_call_count": self._func_call_count,
            "parse_errors": self._parse_errors,
            "runtime_errors": self._runtime_errors,
            "errors": [{"time": e.timestamp, "msg": e.message, "detail": e.detail} for e in errors],
            "warnings": [{"time": e.timestamp, "msg": e.message, "detail": e.detail} for e in warnings],
            "semantic_warnings": list(getattr(self, "_sema_warnings", [])),
        }

    def run_semantic_checks(self) -> list[str]:
        """跨函数语义校验（SEMA 系列），实机测试前完整暴露问题。

        覆盖 7 类硬规则（参数名/#FUNCTION 互斥/#FUNCTION 内 CALL/PROC 表达式项/
        #DIM 重复/局部变量未声明/#FUNCTION 内非 METHOD_SAFE 指令）。返回诊断清单；
        命中即按 WARNING 落 _monitor_events，使"编译 0 错但实机中止"类问题在装配后立刻可见。
        """
        if not hasattr(self, "semantic_analyzer") or self.semantic_analyzer is None:
            return []
        diagnostics = self.semantic_analyzer.check_programs(self._programs)
        for diag in diagnostics:
            self._log_event("WARNING", diag)
        return diagnostics

    def get_semantic_warnings(self) -> list[str]:
        """返回最近一次语义校验的诊断清单（initialize 内已自动执行一轮）。"""
        return list(getattr(self, "_sema_warnings", []))

    def initialize(self) -> None:
        t0 = time.time()
        self._log_event("INFO", "Engine initialization started")

        self.variable_mgr = VariableManager()

        csv_dir = os.path.join(self.game_dir, "CSV")
        self.csv_loader = CSVLoader(csv_dir)
        if os.path.isdir(csv_dir):
            try:
                self.csv_loader.load_all()
                self._log_event("INFO", f"CSV loaded: {len(self.csv_loader.name_maps)} name maps")
            except Exception as e:
                self._log_event("ERROR", "CSV loading failed", traceback.format_exc())
        self._emit_progress("csv", 1, 1)

        for var_name, name_map in self.csv_loader.name_maps.items():
            desc = self.variable_mgr.get_descriptor(var_name)
            if desc is not None:
                desc.name_map = name_map
        # 将源变量的 name_map 同步到 alias 变量（如 MAXBASE <- BASE, CUP <- PALAM）
        for alias_name, source_name in VariableManager._NAME_MAP_ALIASES.items():
            alias_desc = self.variable_mgr.get_descriptor(alias_name)
            source_desc = self.variable_mgr.get_descriptor(source_name)
            if alias_desc is not None and source_desc is not None and source_desc.name_map:
                alias_desc.name_map = source_desc.name_map
        for var_name, sizes in self.csv_loader.variable_sizes.items():
            desc = self.variable_mgr.get_descriptor(var_name)
            if desc is not None:
                desc.default_size = sizes
                # 重新初始化数组存储以应用 VariableSize.csv 中定义的大小
                self.variable_mgr._init_array_storage(desc)

        erb_dir = os.path.join(self.game_dir, "ERB")
        self.erh_processor = ERHProcessor(self.variable_mgr)
        if os.path.isdir(erb_dir):
            try:
                self.erh_processor.process_all(erb_dir)
                self._log_event("INFO", "ERH processing completed")
            except Exception as e:
                self._log_event("ERROR", "ERH processing failed", traceback.format_exc())
        self._emit_progress("erh", 1, 1)

        erb_sources: dict[str, str] = {}
        if os.path.isdir(erb_dir):
            for root, _dirs, files in os.walk(erb_dir):
                for f in files:
                    if f.lower().endswith(".erb"):
                        filepath = os.path.join(root, f)
                        source = self._read_source(filepath)
                        if source is not None:
                            erb_sources[filepath] = source
                        else:
                            self._log_event("WARNING", f"Cannot read file: {filepath}")

        self._log_event("INFO", f"Found {len(erb_sources)} ERB files")

        known_variables: set[str] = set(self.variable_mgr._descriptors.keys())
        known_functions: set[str] = set()
        self.lexer = Lexer(known_variables, known_functions)

        self.semantic_analyzer = SemanticAnalyzer(self.variable_mgr)
        self._programs = []
        total_funcs = 0
        file_count = len(erb_sources)
        progress_interval = max(1, file_count // 20)
        for idx, (filepath, source) in enumerate(erb_sources.items()):
            if self._abort_requested():
                self._log_event("WARNING", f"Assembly aborted by request at {idx}/{file_count}")
                break
            if idx % progress_interval == 0:
                self._log_event("PROGRESS", f"Parsing ERB files: {idx}/{file_count} ({idx*100//file_count}%)")
            self._emit_progress("parse", idx + 1, file_count)
            try:
                tokens = self.lexer.tokenize(source, filepath)
                parser = Parser(self.variable_mgr)
                program = parser.parse(tokens)
                program = self.semantic_analyzer.analyze(program)
                self._programs.append(program)
                for func_def in program.functions:
                    known_functions.add(func_def.name.upper())
                    total_funcs += 1
            except Exception as e:
                err_msg = f"{os.path.basename(filepath)}: {type(e).__name__}: {e}"
                self._parse_errors.append(err_msg)
                self._log_event("PARSE_ERROR", err_msg)

        self._log_event("INFO", f"Parsed {total_funcs} functions from {len(self._programs)} programs")
        if self._parse_errors:
            self._log_event("WARNING", f"{len(self._parse_errors)} parse errors encountered")

        # 跨函数语义校验（SEMA 系列）：对齐 C# ErbLoader/LogicalLineParser 的 5 类规则
        # （参数名/＃FUNCTION 互斥/PROC 表达式项/#DIM 重复/局部变量未声明）。
        # 诊断以 WARNING 落 _monitor_events——不阻塞装配，但保证实机测试前问题可见。
        self._sema_warnings = self.run_semantic_checks()

        self.function_dispatch = FunctionDispatcher(None)

        self.io_renderer = TerminalRenderer()

        if self.llm_config is not None:
            self.llm_bridge = None

        self.vm = VirtualMachine(
            variable_mgr=self.variable_mgr,
            function_dispatch=self.function_dispatch,
            io_renderer=self.io_renderer,
            llm_bridge=self.llm_bridge,
            game_dir=self.game_dir,
        )
        self.function_dispatch._vm = self.vm
        # Connect csv_loader to VM so EXISTCSV/ADDCHARA_DATA builtins work
        self.vm.csv_loader = self.csv_loader

        for program in self._programs:
            for func_def in program.functions:
                desc = FunctionDescriptor(
                    name=func_def.name.upper(),
                    node=func_def,
                    is_function=func_def.is_function,
                    is_functions=func_def.is_functions,
                    parameter_count=len(func_def.parameters),
                    is_event=func_def.name.upper().startswith("EVENT"),
                    is_system=func_def.name.upper().startswith("SYSTEM"),
                    source_file=func_def.source_file,
                )
                self.function_dispatch.register_function(desc)

        self._init_time = time.time() - t0
        self._log_event("INFO", f"Engine initialization completed in {self._init_time:.2f}s")

    def run(self) -> None:
        if self.vm is None:
            raise RuntimeError("Engine not initialized. Call initialize() first.")
        self._running = True
        self._begin_mode = "TITLE"
        self._run_start_time = time.time()
        self._log_event("INFO", "Game run started")
        loop_count = 0
        while self._running:
            loop_count += 1
            old_mode = self._begin_mode
            try:
                if self._begin_mode == "TITLE":
                    self.vm.call_function("SYSTEM_TITLE", [])
                elif self._begin_mode == "FIRST":
                    self.vm.call_function("EVENTFIRST", [])
                elif self._begin_mode == "SHOP":
                    self.vm.call_function("SHOW_SHOP", [])
                    result = self.io_renderer.input_number()
                    self.variable_mgr.set_value("RESULT", [], result)
                    self.vm.call_function("USERSHOP", [])
                elif self._begin_mode == "TRAIN":
                    self.vm.call_function("SHOW_STATUS", [])
                    result = self.io_renderer.input_number()
                    self.variable_mgr.set_value("RESULT", [], result)
                    self.vm.call_function("USERCOM", [])
                elif self._begin_mode == "TURNEND":
                    self.vm.call_function("TURNEND", [])
                elif self._begin_mode == "ABLUP":
                    self.vm.call_function("SHOW_ABLUP", [])
                    result = self.io_renderer.input_number()
                    self.variable_mgr.set_value("RESULT", [], result)
                    self.vm.call_function("USERABLUP", [])
                else:
                    self._running = False
            except BeginSignal as sig:
                new_mode = sig.mode.upper()
                self._begin_transitions.append((old_mode, new_mode, time.time()))
                self._begin_mode = new_mode
                self._log_event("TRANSITION", f"BEGIN {old_mode} -> {new_mode}")
            except ThrowSignal as sig:
                self._runtime_errors.append(str(sig.message))
                self._log_event("RUNTIME_ERROR", f"ThrowSignal: {sig.message}", traceback.format_exc())
                self._running = False
            except EOFError as sig:
                self._log_event("INFO", f"Input exhausted: {sig}")
                self._running = False
            except KeyboardInterrupt:
                self._log_event("INFO", "Interrupted by user")
                self._running = False
            except MemoryError:
                self._log_event("ERROR", "MemoryError: output buffer overflow", traceback.format_exc())
                self._running = False
            except Exception as e:
                self._runtime_errors.append(f"{type(e).__name__}: {e}")
                self._log_event("RUNTIME_ERROR", f"{type(e).__name__}: {e}", traceback.format_exc())
                self._running = False

        elapsed = time.time() - self._run_start_time
        self._log_event("INFO", f"Game run ended after {elapsed:.2f}s, {loop_count} main loops, {len(self._begin_transitions)} mode transitions")

    def load_game(self, save_path: str) -> None:
        if self.variable_mgr is None:
            raise RuntimeError("Engine not initialized.")
        with open(save_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.variable_mgr.deserialize(data)

    def save_game(self, save_path: str) -> None:
        if self.variable_mgr is None:
            raise RuntimeError("Engine not initialized.")
        data = self.variable_mgr.serialize()
        dir_path = os.path.dirname(save_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_source(self, filepath: str) -> str | None:
        encodings = ["utf-8-sig", "utf-8", "shift_jis", "gb18030"]
        for enc in encodings:
            try:
                with codecs.open(filepath, "r", encoding=enc) as fh:
                    return fh.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
        return None
