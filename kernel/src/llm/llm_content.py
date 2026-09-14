from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm_bridge import LLMBridge


@dataclass
class EventContext:
    target_id: int = 0
    player_id: int = 0
    current_location: str = ""
    character_states: dict = field(default_factory=dict)
    relationship_data: dict = field(default_factory=dict)
    event_history: list = field(default_factory=list)
    scene_description: str = ""
    custom_prompt: str = ""


@dataclass
class DialogueContext:
    character_id: int = 0
    dialogue_type: str = ""
    character_states: dict = field(default_factory=dict)
    relationship_data: dict = field(default_factory=dict)
    scene_description: str = ""


@dataclass
class SceneContext:
    scene_type: str = ""
    location: str = ""
    time_of_day: str = ""
    weather: str = ""
    characters_present: list = field(default_factory=list)


class LLMContentGenerator:
    def __init__(self, bridge: LLMBridge):
        self._bridge = bridge

    async def generate_event_text(self, event_type: str, context: EventContext) -> str:
        system_prompt = (
            "你是一个ERA游戏的事件文本生成器。根据提供的事件类型和上下文，"
            "生成符合游戏世界观和角色性格的事件描述文本。"
            "只输出事件文本，不要添加任何解释或元数据。"
        )
        user_parts = [
            f"事件类型: {event_type}",
            f"目标角色ID: {context.target_id}",
            f"玩家ID: {context.player_id}",
            f"当前位置: {context.current_location}",
        ]
        if context.character_states:
            user_parts.append(f"角色状态: {context.character_states}")
        if context.relationship_data:
            user_parts.append(f"关系数据: {context.relationship_data}")
        if context.event_history:
            user_parts.append(f"事件历史: {context.event_history}")
        if context.scene_description:
            user_parts.append(f"场景描述: {context.scene_description}")
        if context.custom_prompt:
            user_parts.append(f"额外要求: {context.custom_prompt}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return await self._bridge._call_api(messages)

    async def generate_dialogue(self, character_id: int, dialogue_type: str, context: DialogueContext) -> str:
        system_prompt = (
            "你是一个ERA游戏的对话生成器。根据提供的角色ID、对话类型和上下文，"
            "生成符合角色性格和当前情境的对话文本。"
            "只输出对话文本，不要添加任何解释或元数据。"
        )
        user_parts = [
            f"角色ID: {character_id}",
            f"对话类型: {dialogue_type}",
        ]
        if context.character_states:
            user_parts.append(f"角色状态: {context.character_states}")
        if context.relationship_data:
            user_parts.append(f"关系数据: {context.relationship_data}")
        if context.scene_description:
            user_parts.append(f"场景描述: {context.scene_description}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return await self._bridge._call_api(messages)

    async def generate_scene_description(self, scene_type: str, context: SceneContext) -> str:
        system_prompt = (
            "你是一个ERA游戏的场景描述生成器。根据提供的场景类型和上下文，"
            "生成富有氛围感的场景描述文本。"
            "只输出场景描述，不要添加任何解释或元数据。"
        )
        user_parts = [
            f"场景类型: {scene_type}",
            f"位置: {context.location}",
            f"时间段: {context.time_of_day}",
        ]
        if context.weather:
            user_parts.append(f"天气: {context.weather}")
        if context.characters_present:
            user_parts.append(f"在场角色: {context.characters_present}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        return await self._bridge._call_api(messages)
