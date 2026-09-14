from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CHARACTER_VARIABLES: set[str] = {
    "BASE", "MAXBASE", "ABL", "TALENT", "EXP", "MARK", "PALAM", "SOURCE",
    "CUP", "CDOWN", "STAIN", "TEQUIP", "EQUIP", "DOWNBASE", "CFLAG", "CSTR",
    "TCVAR", "JUEL", "NOWEX", "EX", "RELATION", "CDFLAG",
}


@dataclass
class VariableDescriptor:
    name: str
    var_type: str = "int"
    dimensions: int = 0
    is_character_var: bool = False
    is_readonly: bool = False
    is_savedata: bool = False
    is_global: bool = False
    is_temporary: bool = False
    default_size: list[int] = field(default_factory=list)
    name_map: dict[str, int] = field(default_factory=dict)
    reset_timing: str | None = None


class VariableManager:

    def __init__(self) -> None:
        self._descriptors: dict[str, VariableDescriptor] = {}
        self._scalar_storage: dict[str, Any] = {}
        self._array_storage: dict[str, Any] = {}
        self._scope_stack: list[dict[str, Any]] = []
        self._character_count: int = 0
        self._register_builtin_scalars()
        self._register_builtin_arrays()

    def _register_builtin_scalars(self) -> None:
        scalar_defs: list[tuple[str, str, Any, bool]] = [
            ("MONEY", "int", 0, False),
            ("DAY", "int", 0, False),
            ("TIME", "int", 0, False),
            ("CHARANUM", "int", 0, True),
            ("MASTER", "int", 0, False),
            ("TARGET", "int", -1, False),
            ("ASSI", "int", -1, False),
            ("SELECTCOM", "int", 0, False),
            ("PREVCOM", "int", -1, False),
            ("PLAYER", "int", 0, False),
        ]
        for name, var_type, default, readonly in scalar_defs:
            desc = VariableDescriptor(
                name=name,
                var_type=var_type,
                dimensions=0,
                is_readonly=readonly,
            )
            self.register_variable(desc)
            self._scalar_storage[name] = default

    def _register_builtin_arrays(self) -> None:
        array_defs: list[tuple[str, int, list[int], str, bool, bool, bool, str | None]] = [
            ("FLAG", 1, [1000], "int", False, False, False, None),
            ("ITEM", 1, [1000], "int", False, False, False, None),
            ("ITEMSALES", 1, [1000], "int", False, False, False, None),
            ("RESULT", 1, [100], "int", False, False, False, None),
            ("RESULTS", 1, [100], "str", False, False, False, None),
            ("TFLAG", 1, [1000], "int", True, False, False, "command_end"),
            ("TSTR", 1, [100], "str", True, False, False, "command_end"),
            ("LOCAL", 1, [100], "int", False, False, False, "function_exit"),
            ("LOCALS", 1, [100], "str", False, False, False, "function_exit"),
            ("ARG", 1, [100], "int", False, False, False, "function_exit"),
            ("ARGS", 1, [100], "str", False, False, False, "function_exit"),
            ("GLOBAL", 1, [1000], "int", False, True, False, None),
            ("GLOBALS", 1, [100], "str", False, True, False, None),
            ("SAVESTR", 1, [100], "str", False, False, False, None),
            ("BASE", 2, [100], "int", False, False, True, None),
            ("ABL", 2, [100], "int", False, False, True, None),
            ("TALENT", 2, [1000], "int", False, False, True, None),
            ("EXP", 2, [100], "int", False, False, True, None),
            ("MARK", 2, [100], "int", False, False, True, None),
            ("PALAM", 2, [100], "int", False, False, True, None),
            ("SOURCE", 2, [100], "int", True, False, True, "command_end"),
            ("CFLAG", 2, [1000], "int", False, False, True, None),
            ("CSTR", 2, [100], "str", False, False, True, None),
            ("CUP", 2, [100], "int", True, False, True, "command_end"),
            ("CDOWN", 2, [100], "int", True, False, True, "command_end"),
            ("STAIN", 2, [100], "int", False, False, True, None),
            ("TEQUIP", 2, [100], "int", False, False, True, None),
            ("EQUIP", 2, [100], "int", False, False, True, None),
            ("DOWNBASE", 2, [2], "int", True, False, True, "command_end"),
            ("TCVAR", 2, [100], "int", True, False, True, "command_end"),
            ("JUEL", 2, [100], "int", False, False, True, None),
            ("NOWEX", 2, [100], "int", False, False, True, None),
            ("EX", 2, [100], "int", False, False, True, None),
            ("RELATION", 2, [100], "int", False, False, True, None),
            ("CDFLAG", 3, [10], "int", False, False, True, None),
        ]
        for name, dims, size, vtype, temp, glob, char, timing in array_defs:
            desc = VariableDescriptor(
                name=name,
                var_type=vtype,
                dimensions=dims,
                is_character_var=char,
                is_temporary=temp,
                is_global=glob,
                default_size=size,
                reset_timing=timing,
            )
            self.register_variable(desc)
            self._init_array_storage(desc)

    def _init_array_storage(self, desc: VariableDescriptor) -> None:
        name = desc.name
        if desc.dimensions == 1:
            if desc.var_type == "str":
                self._array_storage[name] = [""] * desc.default_size[0]
            else:
                # DEV-15: 使用Python列表而非numpy数组，支持混合类型
                self._array_storage[name] = [0] * desc.default_size[0]
        elif desc.dimensions == 2:
            if desc.is_character_var:
                if desc.var_type == "str":
                    self._array_storage[name] = {}
                else:
                    self._array_storage[name] = {}
            else:
                if desc.var_type == "str":
                    self._array_storage[name] = [[""] * desc.default_size[1] for _ in range(desc.default_size[0])]
                else:
                    self._array_storage[name] = [[0] * desc.default_size[1] for _ in range(desc.default_size[0])]
        elif desc.dimensions == 3:
            if desc.is_character_var:
                self._array_storage[name] = {}
            else:
                self._array_storage[name] = [[[0] * desc.default_size[2] for _ in range(desc.default_size[1])] for _ in range(desc.default_size[0])]

    def register_variable(self, descriptor: VariableDescriptor) -> None:
        # Emuera 默认忽略大小写（Config.IgnoreCase 默认 true，
        # ICVariable/ICFunction 默认均为真），故统一以大写名为规范键。
        descriptor.name = descriptor.name.upper()
        self._descriptors[descriptor.name] = descriptor

    def get_descriptor(self, var_name: str) -> VariableDescriptor | None:
        return self._descriptors.get(var_name.upper())

    def is_character_variable(self, var_name: str) -> bool:
        upper_name = var_name.upper()
        desc = self._descriptors.get(upper_name)
        if desc is not None:
            return desc.is_character_var
        return upper_name in CHARACTER_VARIABLES

    _NAME_MAP_ALIASES: dict[str, str] = {
        "MAXBASE": "BASE",
        "DOWNBASE": "BASE",
        "CUP": "PALAM",
        "CDOWN": "PALAM",
        "NOWEX": "EX",
        "ITEMSALES": "ITEM",
    }

    def resolve_name(self, var_name: str, index_name: str) -> int:
        if not index_name:
            return 0
        upper_name = var_name.upper()
        desc = self._descriptors.get(upper_name)
        if desc is not None and index_name in desc.name_map:
            return desc.name_map[index_name]
        alias = self._NAME_MAP_ALIASES.get(upper_name)
        if alias is not None:
            alias_desc = self._descriptors.get(alias)
            if alias_desc is not None and index_name in alias_desc.name_map:
                return alias_desc.name_map[index_name]
        try:
            return int(index_name)
        except ValueError:
            raise KeyError(f"Cannot resolve name '{index_name}' for variable '{var_name}'")

    def _get_local(self, var_name: str, indices: list[int]) -> Any:
        for scope in reversed(self._scope_stack):
            if var_name in scope:
                val = scope[var_name]
                if isinstance(val, dict):
                    key = tuple(indices) if len(indices) > 1 else (indices[0] if indices else 0)
                    return val.get(key, 0 if self._descriptors.get(var_name, VariableDescriptor(name=var_name)).var_type == "int" else "")
                return val
        raise KeyError(f"Local variable '{var_name}' not found in any scope")

    def _set_local(self, var_name: str, indices: list[int], value: Any) -> None:
        for scope in reversed(self._scope_stack):
            if var_name in scope:
                val = scope[var_name]
                if isinstance(val, dict):
                    key = tuple(indices) if len(indices) > 1 else (indices[0] if indices else 0)
                    val[key] = value
                else:
                    scope[var_name] = value
                return
        raise KeyError(f"Local variable '{var_name}' not found in any scope")

    def _ensure_character_slot(self, var_name: str, char_id: int) -> None:
        storage = self._array_storage.get(var_name)
        if storage is None:
            return
        desc = self._descriptors[var_name]
        if char_id not in storage:
            if desc.dimensions == 2:
                if desc.var_type == "str":
                    storage[char_id] = [""] * (desc.default_size[0] if desc.default_size else 100)
                else:
                    storage[char_id] = [0] * (desc.default_size[0] if desc.default_size else 100)
            elif desc.dimensions == 3:
                dim0 = desc.default_size[0] if len(desc.default_size) > 0 else 10
                dim1 = desc.default_size[1] if len(desc.default_size) > 1 else dim0
                if desc.var_type == "str":
                    storage[char_id] = [[""] * dim1 for _ in range(dim0)]
                else:
                    storage[char_id] = [[0] * dim1 for _ in range(dim0)]

    def get_value(self, var_name: str, indices: list[int] | None = None) -> Any:
        var_name = var_name.upper()
        if indices is None:
            indices = []
        desc = self._descriptors.get(var_name)
        if desc is None:
            if self._scope_stack:
                return self._get_local(var_name, indices)
            raise KeyError(f"Variable '{var_name}' is not registered")
        if desc.is_temporary and desc.reset_timing == "function_exit" and self._scope_stack:
            for scope in reversed(self._scope_stack):
                if var_name in scope:
                    val = scope[var_name]
                    if isinstance(val, dict):
                        key = tuple(indices) if len(indices) > 1 else (indices[0] if indices else 0)
                        return val.get(key, 0 if desc.var_type == "int" else "")
                    return val
        if desc.dimensions == 0:
            return self._scalar_storage.get(var_name, 0 if desc.var_type == "int" else "")
        storage = self._array_storage.get(var_name)
        if storage is None:
            return 0 if desc.var_type == "int" else ""
        if desc.dimensions == 1:
            if not indices:
                return storage
            idx = indices[0]
            if desc.var_type == "str":
                return storage[idx] if idx < len(storage) else ""
            return storage[idx]
        elif desc.dimensions == 2:
            if desc.is_character_var:
                if not indices:
                    return storage
                char_id = indices[0]
                if char_id not in storage:
                    return 0 if desc.var_type == "int" else ""
                if len(indices) == 1:
                    return storage[char_id]
                idx = indices[1]
                arr = storage[char_id]
                if desc.var_type == "str":
                    return arr[idx] if idx < len(arr) else ""
                return arr[idx]
            else:
                if not indices:
                    return storage
                if len(indices) == 1:
                    return storage[indices[0]]
                return storage[indices[0]][indices[1]]
        elif desc.dimensions == 3:
            if desc.is_character_var:
                if not indices:
                    return storage
                char_id = indices[0]
                if char_id not in storage:
                    return 0 if desc.var_type == "int" else ""
                if len(indices) == 1:
                    return storage[char_id]
                arr = storage[char_id]
                if len(indices) == 2:
                    return arr[indices[1]]
                return arr[indices[1]][indices[2]]
            else:
                if not indices:
                    return storage
                if len(indices) == 1:
                    return storage[indices[0]]
                elif len(indices) == 2:
                    return storage[indices[0]][indices[1]]
                return storage[indices[0]][indices[1]][indices[2]]
        return 0 if desc.var_type == "int" else ""

    def set_value(self, var_name: str, indices: list[int] | None = None, value: Any = None) -> None:
        var_name = var_name.upper()
        if indices is None:
            indices = []
        desc = self._descriptors.get(var_name)
        if desc is None:
            if self._scope_stack:
                self._set_local(var_name, indices, value)
                return
            raise KeyError(f"Variable '{var_name}' is not registered")
        if desc.is_readonly:
            raise ValueError(f"Variable '{var_name}' is read-only")
        if desc.is_temporary and desc.reset_timing == "function_exit" and self._scope_stack:
            for scope in reversed(self._scope_stack):
                if var_name in scope:
                    val = scope[var_name]
                    if isinstance(val, dict):
                        key = tuple(indices) if len(indices) > 1 else (indices[0] if indices else 0)
                        val[key] = value
                    else:
                        scope[var_name] = value
                    return
        if desc.dimensions == 0:
            self._scalar_storage[var_name] = value
            return
        storage = self._array_storage.get(var_name)
        if storage is None:
            # DEV-16: Auto-create storage for registered variables that lack it
            if desc.dimensions == 1:
                size = desc.default_size[0] if desc.default_size else 100
                if desc.var_type == "str":
                    storage = [""] * size
                else:
                    storage = [0] * size
                self._array_storage[var_name] = storage
            else:
                return
        if desc.dimensions == 1:
            idx = indices[0] if indices else 0
            if desc.var_type == "str":
                storage[idx] = str(value)
            else:
                # DEV-15: 只在值是数字类型时才转换为int
                if isinstance(value, str):
                    storage[idx] = value  # 保持字符串原样
                else:
                    try:
                        storage[idx] = int(value)
                    except (ValueError, TypeError):
                        storage[idx] = value
        elif desc.dimensions == 2:
            if desc.is_character_var:
                char_id = indices[0] if indices else 0
                self._ensure_character_slot(var_name, char_id)
                idx = indices[1] if len(indices) > 1 else 0
                arr = storage[char_id]
                if desc.var_type == "str":
                    arr[idx] = str(value)
                else:
                    # DEV-15: 只在值是数字类型时才转换为int
                    if isinstance(value, str):
                        arr[idx] = value
                    else:
                        try:
                            arr[idx] = int(value)
                        except (ValueError, TypeError):
                            arr[idx] = value
            else:
                i0 = indices[0] if indices else 0
                i1 = indices[1] if len(indices) > 1 else 0
                storage[i0][i1] = int(value) if desc.var_type == "int" else str(value)
        elif desc.dimensions == 3:
            if desc.is_character_var:
                char_id = indices[0] if indices else 0
                self._ensure_character_slot(var_name, char_id)
                arr = storage[char_id]
                i1 = indices[1] if len(indices) > 1 else 0
                i2 = indices[2] if len(indices) > 2 else 0
                arr[i1][i2] = int(value) if desc.var_type == "int" else str(value)
            else:
                i0 = indices[0] if indices else 0
                i1 = indices[1] if len(indices) > 1 else 0
                i2 = indices[2] if len(indices) > 2 else 0
                storage[i0][i1][i2] = int(value) if desc.var_type == "int" else str(value)

    def push_scope(self) -> None:
        local_vars: dict[str, Any] = {}
        for name, desc in self._descriptors.items():
            if desc.is_temporary and desc.reset_timing == "function_exit":
                if desc.dimensions == 0:
                    local_vars[name] = 0 if desc.var_type == "int" else ""
                elif desc.dimensions == 1:
                    if desc.var_type == "str":
                        local_vars[name] = {i: "" for i in range(desc.default_size[0])}
                    else:
                        local_vars[name] = {i: 0 for i in range(desc.default_size[0])}
        self._scope_stack.append(local_vars)

    def pop_scope(self) -> None:
        if self._scope_stack:
            self._scope_stack.pop()

    def reset_temporary(self, timing: str) -> None:
        for name, desc in self._descriptors.items():
            if desc.is_temporary and desc.reset_timing == timing:
                if desc.dimensions == 0:
                    default = 0 if desc.var_type == "int" else ""
                    self._scalar_storage[name] = default
                elif desc.dimensions == 1:
                    if desc.var_type == "str":
                        self._array_storage[name] = [""] * desc.default_size[0]
                    else:
                        self._array_storage[name] = [0] * desc.default_size[0]
                elif desc.dimensions == 2:
                    if desc.is_character_var:
                        self._array_storage[name] = {}
                    else:
                        if desc.var_type == "str":
                            self._array_storage[name] = [[""] * desc.default_size[1] for _ in range(desc.default_size[0])]
                        else:
                            self._array_storage[name] = [[0] * desc.default_size[1] for _ in range(desc.default_size[0])]
                elif desc.dimensions == 3:
                    if desc.is_character_var:
                        self._array_storage[name] = {}
                    else:
                        self._array_storage[name] = [[[0] * desc.default_size[2] for _ in range(desc.default_size[1])] for _ in range(desc.default_size[0])]

    def ensure_character(self, char_id: int) -> None:
        for name, desc in self._descriptors.items():
            if desc.is_character_var and desc.dimensions >= 2:
                self._ensure_character_slot(name, char_id)
        self._character_count = max(self._character_count, char_id + 1)
        self._scalar_storage["CHARANUM"] = self._character_count

    def remove_character(self, char_id: int) -> None:
        for name, desc in self._descriptors.items():
            if desc.is_character_var and name in self._array_storage:
                storage = self._array_storage[name]
                if isinstance(storage, dict) and char_id in storage:
                    del storage[char_id]

    def serialize(self) -> dict:
        data: dict[str, Any] = {
            "scalars": dict(self._scalar_storage),
            "arrays": {},
            "character_count": self._character_count,
        }
        for name, desc in self._descriptors.items():
            if desc.is_global:
                continue
            if desc.is_temporary and desc.reset_timing in ("command_end", "function_exit"):
                continue
            if desc.dimensions == 0:
                continue
            storage = self._array_storage.get(name)
            if storage is None:
                continue
            if desc.is_character_var and isinstance(storage, dict):
                serialized: dict[int, Any] = {}
                for cid, arr in storage.items():
                    if isinstance(arr, list):
                        serialized[cid] = arr
                    else:
                        serialized[cid] = arr
                data["arrays"][name] = serialized
            elif isinstance(storage, list):
                data["arrays"][name] = storage
            else:
                data["arrays"][name] = storage
        return data

    def deserialize(self, data: dict) -> None:
        scalars = data.get("scalars", {})
        for name, value in scalars.items():
            if name in self._scalar_storage:
                desc = self._descriptors.get(name)
                if desc and desc.is_readonly and name != "CHARANUM":
                    continue
                self._scalar_storage[name] = value
        arrays = data.get("arrays", {})
        for name, value in arrays.items():
            desc = self._descriptors.get(name)
            if desc is None:
                continue
            if desc.is_global:
                continue
            if desc.is_character_var and isinstance(value, dict):
                restored: dict[int, Any] = {}
                for cid_str, arr in value.items():
                    cid = int(cid_str) if isinstance(cid_str, str) else cid_str
                    if desc.var_type == "str":
                        restored[cid] = arr if isinstance(arr, list) else list(arr)
                    else:
                        restored[cid] = arr if isinstance(arr, list) else list(arr)
                self._array_storage[name] = restored
            elif desc.var_type == "str" and isinstance(value, list):
                self._array_storage[name] = value
            elif isinstance(value, list):
                self._array_storage[name] = value
        self._character_count = data.get("character_count", 0)
        self._scalar_storage["CHARANUM"] = self._character_count
