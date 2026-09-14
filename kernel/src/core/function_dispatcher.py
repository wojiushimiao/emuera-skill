from __future__ import annotations

import math
import os
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .ast_nodes import FunctionDefNode


@dataclass
class FunctionDescriptor:
    name: str
    node: FunctionDefNode
    is_function: bool
    is_functions: bool
    parameter_count: int
    is_event: bool
    is_system: bool
    source_file: str
    compiled_bytecode: Any = None
    call_count: int = 0


class FunctionDispatcher:

    def __init__(self, vm) -> None:
        self._vm = vm
        self._functions: dict[str, FunctionDescriptor] = {}
        self._builtins: dict[str, Callable] = {}
        self._event_handlers: dict[str, list[str]] = {}
        self._register_builtins()

    def register_function(self, descriptor: FunctionDescriptor) -> None:
        self._functions[descriptor.name] = descriptor
        if descriptor.is_event:
            event_name = descriptor.name
            if event_name not in self._event_handlers:
                self._event_handlers[event_name] = []
            self._event_handlers[event_name].append(descriptor.name)

    def register_builtin(self, name: str, func: Callable) -> None:
        self._builtins[name.upper()] = func

    def get_function(self, name: str) -> FunctionDefNode | None:
        upper_name = name.upper()
        descriptor = self._functions.get(upper_name)
        if descriptor is not None:
            return descriptor.node
        return None

    def call_builtin(self, name: str, args: list[Any]) -> Any:
        upper_name = name.upper()
        if upper_name in self._builtins:
            return self._builtins[upper_name](*args)
        return 0

    def call(self, name: str, args: list[Any]) -> tuple[int, str]:
        upper_name = name.upper()
        if upper_name in self._builtins:
            result = self._builtins[upper_name](*args)
            return (0, str(result))
        descriptor = self._functions.get(upper_name)
        if descriptor is not None:
            descriptor.call_count += 1
            result = self._vm.execute_function(descriptor, args)
            return (0, str(result))
        return (1, f"Function '{name}' not found")

    def call_function_type(self, name: str, args: list[Any]) -> Any:
        upper_name = name.upper()
        if upper_name in self._builtins:
            return self._builtins[upper_name](*args)
        descriptor = self._functions.get(upper_name)
        if descriptor is not None:
            descriptor.call_count += 1
            return self._vm.execute_function(descriptor, args)
        return 0

    def call_functions_type(self, name: str, args: list[Any]) -> str:
        upper_name = name.upper()
        if upper_name in self._builtins:
            result = self._builtins[upper_name](*args)
            return str(result)
        descriptor = self._functions.get(upper_name)
        if descriptor is not None:
            descriptor.call_count += 1
            result = self._vm.execute_function(descriptor, args)
            return str(result) if result is not None else ""
        return ""

    def try_call(self, name: str, args: list[Any]) -> bool:
        upper_name = name.upper()
        if upper_name in self._builtins:
            self._builtins[upper_name](*args)
            return True
        descriptor = self._functions.get(upper_name)
        if descriptor is not None:
            descriptor.call_count += 1
            self._vm.execute_function(descriptor, args)
            return True
        return False

    def call_form(self, format_str: str, args: list[Any]) -> tuple[int, str]:
        resolved_name = self._resolve_format_name(format_str, args)
        return self.call(resolved_name, args)

    def tryc_callform(self, format_str: str, args: list[Any], catch_handler: Callable) -> tuple[int, str]:
        try:
            resolved_name = self._resolve_format_name(format_str, args)
            return self.call(resolved_name, args)
        except Exception:
            catch_handler()
            return (1, "")

    def trycall_list(self, entries: list[tuple[str, list[Any]]]) -> bool:
        for func_name, func_args in entries:
            if self.try_call(func_name, func_args):
                return True
        return False

    def dispatch_event(self, event_name: str) -> None:
        upper_event = event_name.upper()
        handlers = self._event_handlers.get(upper_event, [])
        for handler_name in handlers:
            descriptor = self._functions.get(handler_name)
            if descriptor is not None:
                descriptor.call_count += 1
                self._vm.execute_function(descriptor, [])
        descriptor = self._functions.get(upper_event)
        if descriptor is not None:
            descriptor.call_count += 1
            self._vm.execute_function(descriptor, [])

    def has_function(self, name: str) -> bool:
        upper_name = name.upper()
        return upper_name in self._functions or upper_name in self._builtins

    def _resolve_format_name(self, format_str: str, args: list[Any]) -> str:
        result = format_str
        for i, arg in enumerate(args):
            result = result.replace(f"{{{i}}}", str(arg))
        result = re.sub(r"\{(\w+)\}", lambda m: str(self._vm.get_variable(m.group(1))), result)
        return result

    def _register_builtins(self) -> None:
        self._builtins["ABS"] = lambda x: abs(int(x))
        self._builtins["SIGN"] = lambda x: (1 if int(x) > 0 else (-1 if int(x) < 0 else 0))
        self._builtins["SQRT"] = lambda x: int(math.sqrt(max(0, int(x))))
        self._builtins["POWER"] = self._builtin_power  # DEV-005: 支持2/3参数
        self._builtins["LIMIT"] = self._builtin_limit
        self._builtins["MIN"] = lambda *args: min(int(a) for a in args)
        self._builtins["MAX"] = lambda *args: max(int(a) for a in args)
        self._builtins["RAND"] = lambda x: random.randint(0, max(0, int(x) - 1))
        self._builtins["RANDF"] = lambda: random.random()

        self._builtins["GETBIT"] = lambda x, p: 1 if (int(x) & (1 << int(p))) else 0
        self._builtins["SETBIT"] = lambda x, p: int(x) | (1 << int(p))
        self._builtins["CLEARBIT"] = lambda x, p: int(x) & ~(1 << int(p))
        self._builtins["INVERTBIT"] = lambda x, p: int(x) ^ (1 << int(p))

        self._builtins["STRLENS"] = lambda s: len(str(s).encode("utf-16-le")) // 2
        self._builtins["STRLENSU"] = lambda s: len(str(s))
        self._builtins["STRCOUNT"] = self._builtin_strcount
        self._builtins["SUBSTRING"] = self._builtin_substring
        self._builtins["SUBSTRINGU"] = self._builtin_substringu
        self._builtins["STRFIND"] = self._builtin_strfind
        self._builtins["STRFINDU"] = self._builtin_strfindu
        self._builtins["STR_REPLACE"] = self._builtin_str_replace
        self._builtins["SPLIT"] = self._builtin_split
        self._builtins["ESCAPE"] = lambda s: str(s).replace("'", "''")
        self._builtins["STRCMP"] = lambda a, b: (1 if str(a) > str(b) else (-1 if str(a) < str(b) else 0))

        self._builtins["VARSET"] = self._builtin_varset
        self._builtins["VARSIZE"] = self._builtin_varsize
        self._builtins["SORT"] = self._builtin_sort

        self._builtins["ADDCHARA"] = self._builtin_addchara
        self._builtins["DELCHARA"] = self._builtin_delchara
        self._builtins["ADDCHARA_DATA"] = self._builtin_addchara_data
        self._builtins["EXISTCSV"] = self._builtin_existcsv
        self._builtins["HAS_PENIS"] = self._builtin_has_penis
        self._builtins["HAS_VAGINA"] = self._builtin_has_vagina
        self._builtins["IS_MALE"] = self._builtin_is_male
        self._builtins["IS_FEMALE"] = self._builtin_is_female
        self._builtins["IS_FUTA"] = self._builtin_is_futa

        self._builtins["TIME_PROGRESS"] = self._builtin_time_progress
        self._builtins["DATETIME"] = self._builtin_datetime
        self._builtins["GETTIME"] = self._builtin_gettime
        self._builtins["GETTIMES"] = self._builtin_gettimes

        self._builtins["SAVEGAME"] = self._builtin_savegame
        self._builtins["LOADGAME"] = self._builtin_loadgame
        self._builtins["SAVEDATA"] = self._builtin_savedata
        self._builtins["LOADDATA"] = self._builtin_loaddata
        self._builtins["PUTFORM"] = self._builtin_putform

        self._builtins["CAN_MOVE"] = self._builtin_can_move
        self._builtins["MAXROOM"] = self._builtin_maxroom
        self._builtins["GET_PRIVATE_ROOM"] = self._builtin_get_private_room
        self._builtins["FIND_CHARA_BY_NAME"] = self._builtin_find_chara_by_name

        # DEV-001: CHKDATA
        self._builtins["CHKDATA"] = self._builtin_chkdata
        # DEV-002: SWAPCHARA, COPYCHARA
        self._builtins["SWAPCHARA"] = self._builtin_swapchara
        self._builtins["COPYCHARA"] = self._builtin_copychara
        # DEV-003: SORTCHARA
        self._builtins["SORTCHARA"] = self._builtin_sortchara
        # DEV-004: CHKFONT
        self._builtins["CHKFONT"] = self._builtin_chkfont
        # DRAWLINE / CUSTOMDRAWLINE
        self._builtins["DRAWLINE"] = self._builtin_drawline
        self._builtins["CUSTOMDRAWLINE"] = self._builtin_customdrawline
        # DELDATA
        self._builtins["DELDATA"] = self._builtin_deldata
        # DEV-018: Safe divide for status bar calculations
        self._builtins["SAFE_DIVIDE"] = self._builtin_safe_divide

    @staticmethod
    def _builtin_limit(value: Any, min_val: Any, max_val: Any) -> int:
        v = int(value)
        lo = int(min_val)
        hi = int(max_val)
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v

    @staticmethod
    def _builtin_strcount(s: Any, pattern: Any) -> int:
        return str(s).count(str(pattern))

    @staticmethod
    def _builtin_substring(s: Any, start: Any, length: Any) -> str:
        text = str(s)
        st = int(start)
        ln = int(length)
        encoded = text.encode("utf-16-le")
        char_start = st * 2
        char_end = (st + ln) * 2
        if char_start >= len(encoded):
            return ""
        if char_end > len(encoded):
            char_end = len(encoded)
        try:
            return encoded[char_start:char_end].decode("utf-16-le")
        except Exception:
            return ""

    @staticmethod
    def _builtin_substringu(s: Any, start: Any, length: Any) -> str:
        text = str(s)
        st = int(start)
        ln = int(length)
        return text[st:st + ln]

    @staticmethod
    def _builtin_strfind(s: Any, pattern: Any) -> int:
        text = str(s)
        pat = str(pattern)
        idx = text.find(pat)
        if idx == -1:
            return -1
        return len(text[:idx].encode("utf-16-le")) // 2

    @staticmethod
    def _builtin_strfindu(s: Any, pattern: Any) -> int:
        idx = str(s).find(str(pattern))
        return idx

    @staticmethod
    def _builtin_str_replace(s: Any, pattern: Any, replacement: Any) -> str:
        return str(s).replace(str(pattern), str(replacement))

    def _builtin_split(self, s: Any, delimiter: Any) -> int:
        parts = str(s).split(str(delimiter))
        vm = self._vm
        for i, part in enumerate(parts):
            vm.variable_mgr.set_value("RESULTS", [i], part)
        vm.variable_mgr.set_value("RESULT", [], len(parts))
        return len(parts)

    def _builtin_varset(self, *args: Any) -> int:
        vm = self._vm
        if len(args) < 1:
            return 0
        var_name = str(args[0]).upper()
        value = args[1] if len(args) > 1 else 0
        start_idx = int(args[2]) if len(args) > 2 else None
        end_idx = int(args[3]) if len(args) > 3 else None
        desc = vm.variable_mgr.get_descriptor(var_name)
        if desc is None:
            return 0
        if desc.dimensions == 0:
            vm.variable_mgr.set_value(var_name, [], value)
        elif desc.dimensions == 1:
            storage = vm.variable_mgr.get_value(var_name)
            if start_idx is not None and end_idx is not None:
                for i in range(start_idx, end_idx):
                    vm.variable_mgr.set_value(var_name, [i], value)
            else:
                for i in range(len(storage) if hasattr(storage, '__len__') else 0):
                    vm.variable_mgr.set_value(var_name, [i], value)
        return 0

    def _builtin_varsize(self, *args: Any) -> int:
        vm = self._vm
        if len(args) < 1:
            return 0
        var_name = str(args[0]).upper()
        dimension = int(args[1]) if len(args) > 1 else 0
        desc = vm.variable_mgr.get_descriptor(var_name)
        if desc is None:
            return 0
        if dimension < len(desc.default_size):
            return desc.default_size[dimension]
        if desc.dimensions == 0:
            return 1
        return 0

    def _builtin_sort(self, *args: Any) -> int:
        vm = self._vm
        if len(args) < 1:
            return 0
        var_name = str(args[0]).upper()
        desc = vm.variable_mgr.get_descriptor(var_name)
        if desc is None:
            return 0
        if desc.dimensions == 1:
            storage = vm.variable_mgr.get_value(var_name)
            if desc.var_type == "str":
                sorted_vals = sorted(storage)
            else:
                sorted_vals = sorted(storage)
            for i, val in enumerate(sorted_vals):
                vm.variable_mgr.set_value(var_name, [i], val)
        return 0

    def _builtin_addchara(self, *args: Any) -> int:
        vm = self._vm
        if len(args) >= 1:
            char_id = int(args[0])
        else:
            char_id = vm.variable_mgr.get_value("CHARANUM", [])
        vm.variable_mgr.ensure_character(char_id)
        return 0

    def _builtin_delchara(self, *args: Any) -> int:
        vm = self._vm
        if len(args) < 1:
            return 0
        char_id = int(args[0])
        vm.variable_mgr.remove_character(char_id)
        return 0

    def _builtin_addchara_data(self, *args: Any) -> int:
        vm = self._vm
        if len(args) < 1:
            return 0
        csv_no = int(args[0])
        chara_data = getattr(vm, 'csv_loader', None)
        if chara_data is None:
            return 0
        data = chara_data.chara_data.get(csv_no)
        if data is None:
            return 0
        char_id = vm.variable_mgr.get_value("CHARANUM", [])
        vm.variable_mgr.ensure_character(char_id)
        for var_name in ("BASE", "ABL", "TALENT", "EXP", "CFLAG", "CSTR", "RELATION"):
            src = getattr(data, var_name.lower(), None)
            if src is None:
                continue
            if isinstance(src, dict):
                for idx, val in src.items():
                    vm.variable_mgr.set_value(var_name, [char_id, idx], val)
        return 0

    def _builtin_existcsv(self, *args: Any) -> int:
        if len(args) < 1:
            return 0
        csv_no = int(args[0])
        chara_data = getattr(self._vm, 'csv_loader', None)
        if chara_data is None:
            return 0
        return 1 if csv_no in chara_data.chara_data else 0

    def _builtin_has_penis(self, *args: Any) -> int:
        vm = self._vm
        if len(args) >= 1:
            char_id = int(args[0])
        else:
            char_id = vm.variable_mgr.get_value("TARGET", [])
        try:
            talent_val = vm.variable_mgr.get_value("TALENT", [char_id, 2])
            return 1 if talent_val else 0
        except (KeyError, IndexError):
            return 0

    def _builtin_has_vagina(self, *args: Any) -> int:
        vm = self._vm
        if len(args) >= 1:
            char_id = int(args[0])
        else:
            char_id = vm.variable_mgr.get_value("TARGET", [])
        try:
            talent_val = vm.variable_mgr.get_value("TALENT", [char_id, 1])
            return 1 if talent_val else 0
        except (KeyError, IndexError):
            return 0

    def _builtin_is_male(self, *args: Any) -> int:
        vm = self._vm
        if len(args) >= 1:
            char_id = int(args[0])
        else:
            char_id = vm.variable_mgr.get_value("TARGET", [])
        try:
            has_penis = vm.variable_mgr.get_value("TALENT", [char_id, 2])
            has_vagina = vm.variable_mgr.get_value("TALENT", [char_id, 1])
            return 1 if has_penis and not has_vagina else 0
        except (KeyError, IndexError):
            return 0

    def _builtin_is_female(self, *args: Any) -> int:
        vm = self._vm
        if len(args) >= 1:
            char_id = int(args[0])
        else:
            char_id = vm.variable_mgr.get_value("TARGET", [])
        try:
            has_penis = vm.variable_mgr.get_value("TALENT", [char_id, 2])
            has_vagina = vm.variable_mgr.get_value("TALENT", [char_id, 1])
            return 1 if has_vagina and not has_penis else 0
        except (KeyError, IndexError):
            return 0

    def _builtin_is_futa(self, *args: Any) -> int:
        vm = self._vm
        if len(args) >= 1:
            char_id = int(args[0])
        else:
            char_id = vm.variable_mgr.get_value("TARGET", [])
        try:
            has_penis = vm.variable_mgr.get_value("TALENT", [char_id, 2])
            has_vagina = vm.variable_mgr.get_value("TALENT", [char_id, 1])
            return 1 if has_penis and has_vagina else 0
        except (KeyError, IndexError):
            return 0

    @staticmethod
    def _builtin_time_progress(*args: Any) -> int:
        now = datetime.now()
        return now.hour * 3600 + now.minute * 60 + now.second

    @staticmethod
    def _builtin_datetime(*args: Any) -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S")

    @staticmethod
    def _builtin_gettime(*args: Any) -> str:
        return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    @staticmethod
    def _builtin_gettimes(*args: Any) -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S")

    def _builtin_savegame(self, *args: Any) -> int:
        vm = self._vm
        if hasattr(vm, 'save_game'):
            vm.save_game()
        return 0

    def _builtin_loadgame(self, *args: Any) -> int:
        vm = self._vm
        if hasattr(vm, 'load_game'):
            vm.load_game()
        return 0

    def _builtin_savedata(self, *args: Any) -> int:
        vm = self._vm
        if len(args) < 1:
            return 0
        slot = int(args[0])
        if hasattr(vm, 'save_data'):
            vm.save_data(slot)
        return 0

    def _builtin_loaddata(self, *args: Any) -> int:
        vm = self._vm
        if len(args) < 1:
            return 0
        slot = int(args[0])
        if hasattr(vm, 'load_data'):
            vm.load_data(slot)
        return 0

    def _builtin_putform(self, *args: Any) -> int:
        vm = self._vm
        if len(args) < 1:
            return 0
        text = str(args[0])
        results = vm.variable_mgr.get_value("RESULTS", [])
        if isinstance(results, list):
            idx = vm.variable_mgr.get_value("RESULT", [])
            if isinstance(idx, int) and idx < len(results):
                results[idx] = text
                vm.variable_mgr.set_value("RESULTS", [idx], text)
        return 0

    def _builtin_can_move(self, *args: Any) -> int:
        if len(args) < 1:
            return 0
        _from = int(args[0])
        _to = int(args[1]) if len(args) > 1 else -1
        move_rules = getattr(self._vm, 'move_rules', None)
        if move_rules is not None:
            return 1 if move_rules.can_move(_from, _to) else 0
        return 1

    def _builtin_maxroom(self, *args: Any) -> int:
        map_data = getattr(self._vm, 'map_data', None)
        if map_data is not None:
            return getattr(map_data, 'room_count', 0)
        return 0

    def _builtin_get_private_room(self, *args: Any) -> int:
        if len(args) < 1:
            return -1
        char_id = int(args[0])
        map_data = getattr(self._vm, 'map_data', None)
        if map_data is not None:
            return getattr(map_data, 'private_rooms', {}).get(char_id, -1)
        return -1

    def _builtin_find_chara_by_name(self, *args: Any) -> int:
        if len(args) < 1:
            return -1
        name = str(args[0])
        vm = self._vm
        name_map = None
        desc = vm.variable_mgr.get_descriptor("NAME")
        if desc is not None and hasattr(desc, 'name_map'):
            name_map = desc.name_map
        if name_map is not None:
            for idx, n in name_map.items():
                if n == name:
                    return idx
        callname_desc = vm.variable_mgr.get_descriptor("CALLNAME")
        if callname_desc is not None and hasattr(callname_desc, 'name_map'):
            callname_map = callname_desc.name_map
            for idx, n in callname_map.items():
                if n == name:
                    return idx
        try:
            return int(name)
        except ValueError:
            return -1

    # DEV-005: POWER 支持2/3参数
    def _builtin_power(self, *args: Any) -> int:
        if len(args) < 2:
            return 0
        base = int(args[0])
        exp = int(args[1])
        result = int(math.pow(base, exp))
        if len(args) >= 3:
            # 3参数形式: 将结果存入目标变量
            dest_node = args[2]
            if hasattr(dest_node, 'var_name'):
                self._vm.variable_mgr.set_value(dest_node.var_name, dest_node.indices, result)
            elif hasattr(dest_node, 'name'):
                self._vm.variable_mgr.set_value(dest_node.name, [], result)
            else:
                self._vm.variable_mgr.set_value("RESULT", [], result)
        else:
            self._vm.variable_mgr.set_value("RESULT", [], result)
        return result

    # DEV-001: CHKDATA
    def _builtin_chkdata(self, *args: Any) -> int:
        """CHKDATA slot - 检查存档是否存在"""
        slot = int(args[0]) if args else -1
        game_dir = self._vm.game_dir if hasattr(self._vm, 'game_dir') else "."
        save_dir = os.path.join(game_dir, "Sav")
        if not os.path.exists(save_dir):
            return -1
        # 尝试多种存档文件名格式
        for pattern in [f"ERAsqc{slot:02d}.sav", f"{slot:02d}.sav", f"save{slot:02d}.sav"]:
            save_file = os.path.join(save_dir, pattern)
            if os.path.exists(save_file) and os.path.getsize(save_file) > 0:
                return 0
        return -1

    # DEV-002: SWAPCHARA
    def _builtin_swapchara(self, *args: Any) -> None:
        """SWAPCHARA id1, id2 - 交换两个角色数据"""
        if len(args) < 2:
            return
        id1 = int(args[0])
        id2 = int(args[1])
        if hasattr(self._vm.variable_mgr, 'swap_character'):
            self._vm.variable_mgr.swap_character(id1, id2)
        else:
            # 简化实现: 交换角色相关变量
            for var_name in ["NAME", "CALLNAME", "BASE", "ABL", "TALENT", "CFLAG", "EX", "JUEL", "PALAM"]:
                desc = self._vm.variable_mgr.get_descriptor(var_name)
                if desc is not None:
                    try:
                        val1 = self._vm.variable_mgr.get_value(var_name, [id1])
                        val2 = self._vm.variable_mgr.get_value(var_name, [id2])
                        self._vm.variable_mgr.set_value(var_name, [id1], val2)
                        self._vm.variable_mgr.set_value(var_name, [id2], val1)
                    except Exception:
                        pass

    # DEV-002: COPYCHARA
    def _builtin_copychara(self, *args: Any) -> None:
        """COPYCHARA src, dest - 复制角色数据"""
        if len(args) < 2:
            return
        src = int(args[0])
        dest = int(args[1])
        for var_name in ["NAME", "CALLNAME", "BASE", "ABL", "TALENT", "CFLAG", "EX", "JUEL", "PALAM"]:
            desc = self._vm.variable_mgr.get_descriptor(var_name)
            if desc is not None:
                try:
                    val = self._vm.variable_mgr.get_value(var_name, [src])
                    self._vm.variable_mgr.set_value(var_name, [dest], val)
                except Exception:
                    pass

    # DEV-003: SORTCHARA
    def _builtin_sortchara(self, *args: Any) -> None:
        """SORTCHARA key[, BACK] - 按指定键排序角色"""
        reverse = False
        sort_key = None
        if len(args) >= 1:
            # 检查最后一个参数是否为BACK
            last_arg = args[-1]
            last_str = str(last_arg).upper() if not hasattr(last_arg, 'value') else str(last_arg.value).upper()
            if last_str == 'BACK':
                reverse = True
                args = args[:-1]
            if args:
                sort_key = args[0]
        # 简化实现: 实际排序需要更复杂的逻辑
        # 这里只是设置排序标志
        if hasattr(self._vm, 'sort_key'):
            self._vm.sort_key = sort_key
            self._vm.sort_reverse = reverse

    # DEV-004: CHKFONT
    def _builtin_chkfont(self, *args: Any) -> int:
        """CHKFONT "fontname" - 检查字体是否存在"""
        # 简化实现: 始终返回1（字体存在）
        # 完整实现需要调用系统API检查字体
        return 1

    # DRAWLINE
    def _builtin_drawline(self, *args: Any) -> None:
        """DRAWLINE - 绘制分割线"""
        renderer = self._vm.io_renderer
        if renderer and hasattr(renderer, 'print_text'):
            renderer.print_text("----------------------------------------------------------------")

    # CUSTOMDRAWLINE
    def _builtin_customdrawline(self, *args: Any) -> None:
        """CUSTOMDRAWLINE [char] - 使用指定字符绘制分割线"""
        char = str(args[0]) if args else "-"
        if len(char) == 0:
            char = "-"
        renderer = self._vm.io_renderer
        if renderer and hasattr(renderer, 'print_text'):
            renderer.print_text(char * 60)

    # DELDATA
    def _builtin_deldata(self, *args: Any) -> None:
        """DELDATA slot - 删除存档数据"""
        slot = int(args[0]) if args else -1
        game_dir = self._vm.game_dir if hasattr(self._vm, 'game_dir') else "."
        save_dir = os.path.join(game_dir, "Sav")
        if not os.path.exists(save_dir):
            return
        for pattern in [f"ERAsqc{slot:02d}.sav", f"{slot:02d}.sav", f"save{slot:02d}.sav"]:
            save_file = os.path.join(save_dir, pattern)
            if os.path.exists(save_file):
                try:
                    os.remove(save_file)
                except Exception:
                    pass

    # DEV-018: Safe divide - returns 0 on division by zero
    @staticmethod
    def _builtin_safe_divide(*args: Any) -> int:
        """SAFE_DIVIDE(a, b) - returns a/b or 0 if b is 0."""
        if len(args) < 2:
            return 0
        a = int(args[0])
        b = int(args[1])
        if b == 0:
            return 0
        return a // b if a % b == 0 else int(a / b)
