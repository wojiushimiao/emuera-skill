"""
路径守卫工具函数。
guard_write(path, game_dir)：供各阶段复用，
命中游戏目录抛 IF-901。
"""

import os
from pathlib import Path

try:
    from .errors import make_error, IF_901
except ImportError:
    from errors import make_error, IF_901


def guard_write(path: str, game_dir: str) -> None:
    """
    检查路径是否指向游戏目录下的写操作。
    如果是，抛出 IF-901 错误。

    参数:
        path: 待写入的目标路径
        game_dir: 游戏工程根目录

    异常:
        EmueraError(IF-901): 当 path 位于 game_dir 内部时抛出
    """
    target = Path(path).resolve()
    game = Path(game_dir).resolve()

    try:
        target.relative_to(game)
        raise make_error(IF_901, context=f"目标路径: {path}，游戏目录: {game_dir}")
    except ValueError:
        # target 不在 game 下，放行
        pass
