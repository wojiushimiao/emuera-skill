"""
统一错误结构与错误码定义。
所有子系统异常归一化为 EmueraError，禁止抛裸堆栈出包边界。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Subsystem(Enum):
    """子系统前缀（对齐 L2 04 §15 错误码命名规范）"""
    KERNEL_BRIDGE = "KB"
    INGESTION = "IN"
    CODE_GRAPH = "CG"
    GAP_ANALYSIS = "GA"
    RUNTIME = "RT"
    DEBUG = "DB"
    AUTHORING = "AU"
    PLAYER_SESSION = "PS"
    LLM_ORCHESTRATION = "LL"
    INTERFACE = "IF"
    PRESET = "PR"
    KNOWLEDGE_BASE = "KN"


@dataclass
class EmueraError(Exception):
    """
    统一错误结构。
    对齐 L2 04 错误结构：{code, subsystem, message, context?, recoverable}
    """
    code: str
    subsystem: Subsystem
    message: str
    context: Optional[Any] = None
    recoverable: bool = False

    def to_dict(self) -> dict:
        """序列化为字典（JSON 可序列化）"""
        result = {
            "code": self.code,
            "subsystem": self.subsystem.value,
            "message": self.message,
            "recoverable": self.recoverable,
        }
        if self.context is not None:
            result["context"] = self.context
        return result

    def __str__(self) -> str:
        prefix = f"[{self.subsystem.value}-{self.code}]"
        return f"{prefix} {self.message}"


# ── 错误码常量表（L2 04 §15 + P-1 新增 PR-） ──

# kernel-bridge
KB_001 = ("001", Subsystem.KERNEL_BRIDGE, "目录不存在")
KB_002 = ("002", Subsystem.KERNEL_BRIDGE, "编码探测失败且不在回退列表")
KB_003 = ("003", Subsystem.KERNEL_BRIDGE, "内核装配抛异常")
KB_010 = ("010", Subsystem.KERNEL_BRIDGE, "配置文件无法解析")

# ingestion
IN_101 = ("101", Subsystem.INGESTION, "工程布局无法识别")
IN_102 = ("102", Subsystem.INGESTION, "编码约定违规：非 ASCII 脚本/数据文件缺 UTF-8 BOM")

# code-graph
CG_201 = ("201", Subsystem.CODE_GRAPH, "图谱构建异常")

# gap-analysis
GA_301 = ("301", Subsystem.GAP_ANALYSIS, "分析异常")

# runtime
RT_401 = ("401", Subsystem.RUNTIME, "装配失败")

# debug
DB_501 = ("501", Subsystem.DEBUG, "调试会话异常")

# authoring
AU_601 = ("601", Subsystem.AUTHORING, "引用未声明变量")
AU_602 = ("602", Subsystem.AUTHORING, "调用不存在函数")

# player-session
PS_701 = ("701", Subsystem.PLAYER_SESSION, "会话异常")
PS_702 = ("702", Subsystem.PLAYER_SESSION, "持久化会话装载失败（缺失/指纹不符/损坏）")

# llm-orchestration
LL_801 = ("801", Subsystem.LLM_ORCHESTRATION, "模型输出不符契约")

# interface
IF_901 = ("901", Subsystem.INTERFACE, "检测到对游戏目录的写操作，拒绝并终止")

# knowledge-base (P7)
KN_001 = ("001", Subsystem.KNOWLEDGE_BASE, "知识库数据文件加载失败")
KN_002 = ("002", Subsystem.KNOWLEDGE_BASE, "指令字典同步失败（账本为空或结构异常）")
KN_003 = ("003", Subsystem.KNOWLEDGE_BASE, "指令字典骨架生成失败")


def make_error(error_tuple: tuple, context: Any = None, recoverable: bool = False) -> EmueraError:
    """从错误码常量元组创建 EmueraError 实例"""
    code, subsystem, message = error_tuple
    return EmueraError(code=code, subsystem=subsystem, message=message,
                       context=context, recoverable=recoverable)
