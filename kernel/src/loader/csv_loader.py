from __future__ import annotations

import csv
import os
import codecs
from dataclasses import dataclass, field
from typing import Any


_NAME_MAP_FILES: list[str] = [
    "Abl", "Talent", "Base", "Palam", "Exp", "Ex", "Mark", "Source",
    "Stain", "Equip", "Tequip", "Juel", "Train", "Item",
    "Flag", "CFlag", "TFlag", "Tcvar",
]

_ENCODINGS: list[str] = ["utf-8-sig", "utf-8", "shift_jis", "gb18030"]


@dataclass
class CharaData:
    no: int
    name: str
    callname: str
    base: dict[int, int] = field(default_factory=dict)
    maxbase: dict[int, int] = field(default_factory=dict)
    abl: dict[int, int] = field(default_factory=dict)
    talent: dict[int, int] = field(default_factory=dict)
    exp: dict[int, int] = field(default_factory=dict)
    cflag: dict[int, int] = field(default_factory=dict)
    cstr: dict[int, str] = field(default_factory=dict)
    relation: dict[int, int] = field(default_factory=dict)


class CSVLoader:

    def __init__(self, csv_dir: str) -> None:
        self.csv_dir: str = csv_dir
        self.name_maps: dict[str, dict[str, int]] = {}
        self.reverse_maps: dict[str, dict[int, str]] = {}
        self.chara_data: dict[int, CharaData] = {}
        self.variable_sizes: dict[str, list[int]] = {}
        self.game_base: dict[str, str] = {}

    def load_all(self) -> None:
        self._load_name_maps()
        self._load_chara_data()
        self._load_variable_sizes()
        self._load_game_base()
        self._load_replace_config()
        self._load_rename_config()

    def _read_csv(self, filepath: str) -> list[list[str]]:
        for enc in _ENCODINGS:
            try:
                rows: list[list[str]] = []
                with codecs.open(filepath, "r", encoding=enc) as f:
                    reader = csv.reader(f)
                    for row in reader:
                        rows.append(row)
                return rows
            except (UnicodeDecodeError, UnicodeError):
                continue
        return []

    def _csv_path(self, name: str) -> str:
        return os.path.join(self.csv_dir, f"{name}.csv")

    def _load_name_maps(self) -> None:
        for basename in _NAME_MAP_FILES:
            var_name = basename.upper()
            filepath = self._csv_path(basename)
            if not os.path.isfile(filepath):
                continue
            rows = self._read_csv(filepath)
            name_map: dict[str, int] = {}
            reverse_map: dict[int, str] = {}
            for row in rows:
                if len(row) < 2:
                    continue
                idx_str = row[0].strip()
                name = row[1].strip()
                if not idx_str or not name:
                    continue
                try:
                    idx = int(idx_str)
                except ValueError:
                    continue
                name_map[name] = idx
                if idx not in reverse_map:
                    reverse_map[idx] = name
                if len(row) >= 3:
                    alias = row[2].strip()
                    if alias:
                        name_map[alias] = idx
            self.name_maps[var_name] = name_map
            self.reverse_maps[var_name] = reverse_map

    def _load_chara_data(self) -> None:
        chara_dir = os.path.join(self.csv_dir, "chara")
        if not os.path.isdir(chara_dir):
            return
        for filename in os.listdir(chara_dir):
            if not filename.lower().startswith("chara") or not filename.lower().endswith(".csv"):
                continue
            filepath = os.path.join(chara_dir, filename)
            chara = self._parse_chara_csv(filepath)
            if chara is not None:
                self.chara_data[chara.no] = chara

    # eraTW uses Japanese field names in chara CSVs
    _CHARA_FIELD_MAP: dict[str, str] = {
        "番号": "NO", "名前": "NAME", "呼び名": "CALLNAME",
        "基礎": "BASE", "最大基础": "MAXBASE", "素質": "TALENT",
        "能力": "ABL", "経験": "EXP", "フラグ": "CFLAG",
        "相性": "RELATION", "CSTR": "CSTR",
        # Also handle the original English keys
        "NO": "NO", "NAME": "NAME", "CALLNAME": "CALLNAME",
        "BASE": "BASE", "MAXBASE": "MAXBASE", "TALENT": "TALENT",
        "ABL": "ABL", "EXP": "EXP", "CFLAG": "CFLAG",
        "RELATION": "RELATION",
    }

    def _parse_chara_csv(self, filepath: str) -> CharaData | None:
        rows = self._read_csv(filepath)
        no: int = -1
        name: str = ""
        callname: str = ""
        base: dict[int, int] = {}
        maxbase: dict[int, int] = {}
        abl: dict[int, int] = {}
        talent: dict[int, int] = {}
        exp: dict[int, int] = {}
        cflag: dict[int, int] = {}
        cstr: dict[int, str] = {}
        relation: dict[int, int] = {}
        # Temporary storage using string keys (resolved later)
        base_tmp: dict[str, int] = {}
        maxbase_tmp: dict[str, int] = {}
        abl_tmp: dict[str, int] = {}
        talent_tmp: dict[str, int] = {}
        exp_tmp: dict[str, int] = {}
        cflag_tmp: dict[str, int] = {}
        cstr_tmp: dict[str, str] = {}
        relation_tmp: dict[str, int] = {}
        for row in rows:
            if len(row) < 2:
                continue
            raw_key = row[0].strip()
            # Strip semicolons (inline comments)
            if raw_key.startswith(";"):
                continue
            key = raw_key.upper()
            val = row[1].strip()
            # Strip inline comment from val
            if ";" in val:
                val = val.split(";")[0].strip()
            # Map Japanese field names to English
            mapped = self._CHARA_FIELD_MAP.get(raw_key, self._CHARA_FIELD_MAP.get(key, key))
            if mapped == "NO":
                try:
                    no = int(val)
                except ValueError:
                    pass
            elif mapped == "NAME":
                name = val
            elif mapped == "CALLNAME":
                callname = val
            elif mapped in ("BASE", "MAXBASE", "ABL", "TALENT", "EXP", "CFLAG", "RELATION"):
                if len(row) < 3:
                    continue
                idx_str = row[1].strip()
                value_str = row[2].strip()
                # Strip inline comment from value
                if ";" in value_str:
                    value_str = value_str.split(";")[0].strip()
                # idx may be a name (eraTW style) or a number (Emuera style)
                try:
                    idx = int(idx_str)
                    value = int(value_str)
                except ValueError:
                    # eraTW uses names like "体力", "性別", etc. Use hash as key
                    idx = hash(idx_str) % 10000
                    try:
                        value = int(value_str)
                    except ValueError:
                        continue
                target_tmp: dict[str | int, int] | None = None
                if mapped == "BASE":
                    target_tmp = base_tmp
                elif mapped == "MAXBASE":
                    target_tmp = maxbase_tmp
                elif mapped == "ABL":
                    target_tmp = abl_tmp
                elif mapped == "TALENT":
                    target_tmp = talent_tmp
                elif mapped == "EXP":
                    target_tmp = exp_tmp
                elif mapped == "CFLAG":
                    target_tmp = cflag_tmp
                elif mapped == "RELATION":
                    target_tmp = relation_tmp
                if target_tmp is not None:
                    target_tmp[idx_str if not isinstance(idx, int) or idx_str.isdigit() else idx_str] = value
                    # Also store with numeric key for direct access
                    if isinstance(idx, int):
                        target_tmp[idx] = value
            elif mapped == "CSTR":
                if len(row) < 3:
                    continue
                idx_str = row[1].strip()
                value = row[2].strip()
                if ";" in value:
                    value = value.split(";")[0].strip()
                try:
                    idx = int(idx_str)
                except ValueError:
                    idx = hash(idx_str) % 10000
                cstr_tmp[idx] = value
        if no < 0:
            return None

        # Resolve name-based indices using forward name_maps
        # name_maps["BASE"] = {"体力": 0, "気力": 1, ...}
        def _resolve(tmp: dict, target: dict, var_name: str) -> None:
            """Convert name-based keys to proper index via name_maps."""
            nm = self.name_maps.get(var_name, {})
            for k, v in tmp.items():
                if isinstance(k, int):
                    target[k] = v
                elif isinstance(k, str):
                    if k.isdigit():
                        target[int(k)] = v
                    elif k in nm:
                        target[nm[k]] = v

        _resolve(base_tmp, base, "BASE")
        _resolve(maxbase_tmp, maxbase, "BASE")
        _resolve(abl_tmp, abl, "ABL")
        _resolve(talent_tmp, talent, "TALENT")
        _resolve(exp_tmp, exp, "EXP")
        _resolve(cflag_tmp, cflag, "CFLAG")
        _resolve(relation_tmp, relation, "RELATION")

        return CharaData(
            no=no, name=name, callname=callname,
            base=base, maxbase=maxbase, abl=abl,
            talent=talent, exp=exp, cflag=cflag,
            cstr=cstr, relation=relation,
        )

    def _load_variable_sizes(self) -> None:
        filepath = self._csv_path("VariableSize")
        if not os.path.isfile(filepath):
            return
        rows = self._read_csv(filepath)
        for row in rows:
            if len(row) < 2:
                continue
            var_name = row[0].strip().upper()
            sizes: list[int] = []
            for i in range(1, len(row)):
                s = row[i].strip()
                if not s:
                    continue
                try:
                    sizes.append(int(s))
                except ValueError:
                    break
            if sizes:
                self.variable_sizes[var_name] = sizes

    def _load_game_base(self) -> None:
        filepath = self._csv_path("GameBase")
        if not os.path.isfile(filepath):
            return
        rows = self._read_csv(filepath)
        for row in rows:
            if len(row) < 2:
                continue
            key = row[0].strip()
            value = row[1].strip()
            if key:
                self.game_base[key] = value

    def _load_replace_config(self) -> None:
        filepath = self._csv_path("_Replace")
        if not os.path.isfile(filepath):
            return
        self._read_csv(filepath)

    def _load_rename_config(self) -> None:
        filepath = self._csv_path("_Rename")
        if not os.path.isfile(filepath):
            return
        self._read_csv(filepath)
