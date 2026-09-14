from __future__ import annotations

import json


class LLMContextManager:
    def __init__(self):
        self._state_keys_priority = [
            "day",
            "time",
            "master",
            "assistant",
            "target",
            "player",
            "location",
        ]
        self._relationship_keys = [
            "favor",
            "rely",
            "intimate",
            "dominant",
        ]
        self._max_state_items = 20
        self._max_history_items = 10

    def build_context(self, game_state: dict, max_tokens: int = 2000) -> str:
        compressed = self.compress_state(game_state)
        sections = []

        if "core" in compressed and compressed["core"]:
            core_lines = [f"{k}: {v}" for k, v in compressed["core"].items()]
            sections.append("[Core State]\n" + "\n".join(core_lines))

        if "characters" in compressed and compressed["characters"]:
            char_parts = []
            for char_id, char_data in compressed["characters"].items():
                char_lines = [f"  {k}: {v}" for k, v in char_data.items()]
                char_parts.append(f"Character {char_id}:\n" + "\n".join(char_lines))
            sections.append("[Characters]\n" + "\n".join(char_parts))

        if "relationships" in compressed and compressed["relationships"]:
            rel_parts = []
            for rel_key, rel_data in compressed["relationships"].items():
                if isinstance(rel_data, dict):
                    rel_lines = [f"  {k}: {v}" for k, v in rel_data.items()]
                    rel_parts.append(f"{rel_key}:\n" + "\n".join(rel_lines))
                else:
                    rel_parts.append(f"{rel_key}: {rel_data}")
            sections.append("[Relationships]\n" + "\n".join(rel_parts))

        if "history" in compressed and compressed["history"]:
            hist_lines = [f"  - {h}" for h in compressed["history"]]
            sections.append("[Recent Events]\n" + "\n".join(hist_lines))

        if "location" in compressed and compressed["location"]:
            loc_lines = [f"  {k}: {v}" for k, v in compressed["location"].items()]
            sections.append("[Location]\n" + "\n".join(loc_lines))

        result = "\n\n".join(sections)

        estimated_tokens = len(result) // 4
        if estimated_tokens > max_tokens:
            result = result[: max_tokens * 4]

        return result

    def compress_state(self, full_state: dict) -> dict:
        compressed: dict = {}

        core: dict = {}
        for key in self._state_keys_priority:
            if key in full_state:
                val = full_state[key]
                if isinstance(val, (str, int, float, bool)):
                    core[key] = val
                elif isinstance(val, dict):
                    core[key] = json.dumps(val, ensure_ascii=False)
        if core:
            compressed["core"] = core

        if "characters" in full_state and isinstance(full_state["characters"], dict):
            chars: dict = {}
            count = 0
            for char_id, char_data in full_state["characters"].items():
                if count >= self._max_state_items:
                    break
                if isinstance(char_data, dict):
                    filtered: dict = {}
                    for k, v in char_data.items():
                        if isinstance(v, (str, int, float, bool)):
                            filtered[k] = v
                    if filtered:
                        chars[str(char_id)] = filtered
                        count += 1
            if chars:
                compressed["characters"] = chars

        if "relationships" in full_state and isinstance(full_state["relationships"], dict):
            rels: dict = {}
            for rel_key, rel_data in full_state["relationships"].items():
                if isinstance(rel_data, dict):
                    filtered_rel: dict = {}
                    for rk in self._relationship_keys:
                        if rk in rel_data:
                            filtered_rel[rk] = rel_data[rk]
                    if filtered_rel:
                        rels[str(rel_key)] = filtered_rel
            if rels:
                compressed["relationships"] = rels

        if "event_history" in full_state and isinstance(full_state["event_history"], list):
            history = full_state["event_history"][-self._max_history_items:]
            compressed["history"] = [str(h) for h in history]

        if "location" in full_state and isinstance(full_state["location"], dict):
            loc: dict = {}
            for k, v in full_state["location"].items():
                if isinstance(v, (str, int, float, bool)):
                    loc[k] = v
            if loc:
                compressed["location"] = loc

        return compressed
