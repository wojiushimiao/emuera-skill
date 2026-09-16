"""
接口层子系统 - CLI 入口与输出格式化。
九命令族路由、异常归一化、格式化输出。
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..pipeline_a import run_pipeline_a
    from ..pipeline_bc import run_pipeline_bc
    from ..pipeline_d import run_pipeline_d
    from ..player_session.session import SessionManager
    from ..debug.debugger import DebugManager
    from ..authoring.generator import locate_anchor, generate_skeleton, validate_draft, assess_impact, deliver_draft
    from ..kb.knowledge import kb_search, kb_lookup, KnowledgeBase
    from ..code_graph.graph import build_graph
    from ..llm_orchestration.orchestrator import orchestrate
    from ..guard import guard_write
    from ..output_dir import ensure_output_dir
    from ..errors import EmueraError
except ImportError:
    from pipeline_a import run_pipeline_a
    from pipeline_bc import run_pipeline_bc
    from pipeline_d import run_pipeline_d
    from player_session.session import SessionManager
    from debug.debugger import DebugManager
    from authoring.generator import locate_anchor, generate_skeleton, validate_draft, assess_impact, deliver_draft
    from kb.knowledge import kb_search, kb_lookup, KnowledgeBase
    from code_graph.graph import build_graph
    from llm_orchestration.orchestrator import orchestrate
    from guard import guard_write
    from output_dir import ensure_output_dir
    from errors import EmueraError


# ── 输出格式化 ──

def format_output(data: Any, fmt: str = "json") -> str:
    """格式化输出，默认 JSON"""
    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    elif fmt == "text":
        return _to_text(data)
    elif fmt == "summary":
        return _to_summary(data)
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _to_text(data: Any, indent: int = 0) -> str:
    """转换为文本格式"""
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{'  ' * indent}{key}:")
                lines.append(_to_text(value, indent + 1))
            else:
                lines.append(f"{'  ' * indent}{key}: {value}")
        return "\n".join(lines)
    elif isinstance(data, list):
        return "\n".join(f"{'  ' * indent}- {item}" for item in data)
    return str(data)


def _to_summary(data: Any) -> str:
    """转换为摘要格式"""
    if isinstance(data, dict):
        items = []
        for key in ['status', 'node_count', 'edge_count', 'total', 'implementation_ratio']:
            if key in data:
                items.append(f"{key}: {data[key]}")
        if 'output' in data:
            items.append(f"output: {data['output']}")
        return " | ".join(items) if items else str(data)
    return str(data)[:200]


# ── 命令族路由 ──

COMMANDS = {
    "scan": "P-A",
    "snapshot": "P-A",
    "graph": "P-B",
    "gap": "P-C",
    "run": "P-D",
    "debug": "P-E",
    "author": "P-F",
    "validate": "P-F",
    "impact": "P-F",
    "play": "P-G",
    "polish": "P-H",
    "capability": "capability",
    "kb": "kb",
}


def route_command(cmd: str, game_dir: str, output_root: str, **kwargs) -> Dict[str, Any]:
    """路由命令到对应管线"""
    pipeline = COMMANDS.get(cmd)
    if not pipeline:
        return {"error": f"未知命令: {cmd}"}

    fingerprint = _compute_fingerprint(game_dir)

    try:
        if pipeline == "P-A":
            return run_pipeline_a(game_dir)
        elif pipeline == "P-B":
            return run_pipeline_bc(
                _get_snapshot(game_dir),
                output_root,
                fingerprint,
            )
        elif pipeline == "P-C":
            return run_pipeline_bc(
                _get_snapshot(game_dir),
                output_root,
                fingerprint,
            )
        elif pipeline == "P-D":
            # run 报告导出守卫：落盘目录不得落入游戏目录
            output_dir = ensure_output_dir(output_root, fingerprint)
            guard_write(output_dir, game_dir)
            return run_pipeline_d(
                game_dir,
                output_root,
                fingerprint,
                entry=kwargs.get("entry", ""),
                timeout_s=kwargs.get("timeout", 60.0),
            )
        elif pipeline == "P-G":
            manager = SessionManager(output_root)
            session = manager.start_session(game_dir, fingerprint)
            actions = manager.list_actions(session)
            return {"session_id": session.session_id, "actions": actions}
        elif pipeline == "P-F":
            return _handle_author(cmd, game_dir, output_root, fingerprint, **kwargs)
        elif pipeline == "P-E":
            return _handle_debug(game_dir, output_root, fingerprint, **kwargs)
        elif pipeline == "P-H":
            context = kwargs.get("context") or {
                "task": "polish",
                "text": kwargs.get("text", kwargs.get("query", "")),
            }
            result = orchestrate("polish", context, model_invoke=None)
            return {
                "status": "polish",
                "result": result,
                "degraded": result.get("degraded", False),
            }
        elif pipeline == "capability":
            return _handle_capability()
        elif pipeline == "kb":
            query = kwargs.get("query", "")
            mnemonic = kwargs.get("mnemonic")
            kb = _get_kb(kwargs.get("kb"))
            if mnemonic:
                entry = kb_lookup(kb, mnemonic)
                return {
                    "mnemonic": mnemonic,
                    "found": entry is not None,
                    "entry": {
                        "mnemonic": entry.mnemonic,
                        "category": entry.category,
                        "impl_status": entry.impl_status,
                    } if entry else None,
                }
            results = kb_search(kb, query)
            return {
                "results": len(results),
                "query": query,
                "entries": [r.mnemonic for r in results[:20]],
            }
    except EmueraError as e:
        return {"error": True, "code": e.code, "message": str(e)}
    except Exception as e:
        return {"error": True, "message": str(e)}


def _handle_author(cmd: str, game_dir: str, output_root: str, fingerprint: str, **kwargs) -> Dict[str, Any]:
    """处理 author 命令族（author/validate/impact）"""
    query = kwargs.get("query", "")
    graph = _build_graph(game_dir)

    if cmd == "author":
        if not query:
            return {"status": "author", "error": "需要 query 参数以检索锚点"}
        anchors = locate_anchor(graph, query)
        draft = generate_skeleton(anchors, event_name=query)
        validation = validate_draft(draft, graph, ledger=None)
        impact = assess_impact(graph, anchors)

        # 交付守卫：草案落盘目录不得落入游戏目录
        drafts_dir = str(Path(output_root) / fingerprint[:8] / "drafts")
        guard_write(drafts_dir, game_dir)
        draft_path = deliver_draft(
            draft, validation, impact, output_root, fingerprint,
            protected_roots=[game_dir],
        )
        return {
            "status": "author",
            "query": query,
            "anchors": [a.name for a in anchors],
            "anchor_count": len(anchors),
            "draft": draft.content,
            "validation": {
                "valid": validation.valid,
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
            "impact": {
                "affected_functions": impact.affected_functions,
                "affected_events": impact.affected_events,
                "traversal_complete": impact.traversal_complete,
            },
            "draft_path": draft_path,
        }

    elif cmd == "validate":
        anchors = locate_anchor(graph, query or "EVENT")
        draft = generate_skeleton(anchors, event_name=query)
        validation = validate_draft(draft, graph, ledger=None)
        return {
            "status": "validate",
            "valid": validation.valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
        }

    elif cmd == "impact":
        anchors = locate_anchor(graph, query or "EVENT")
        impact = assess_impact(graph, anchors)
        return {
            "status": "impact",
            "affected_functions": impact.affected_functions,
            "affected_events": impact.affected_events,
            "traversal_complete": impact.traversal_complete,
        }

    return {"status": cmd}


def _handle_debug(game_dir: str, output_root: str, fingerprint: str, **kwargs) -> Dict[str, Any]:
    """处理 debug 命令：真调 DebugManager 并采集运行时痕迹"""
    manager = DebugManager(output_root)
    session = manager.create_session(game_dir, fingerprint)

    steps = int(kwargs.get("steps", 1))
    step_result = manager.step(session, steps=steps)
    snapshot = manager.snapshot_state(session)

    # 报告导出守卫：调试会话保存目录不得落入游戏目录
    save_dir = str(Path(output_root) / fingerprint[:8] / "debug_saves")
    guard_write(save_dir, game_dir)
    conclusion = manager.conclude(session)

    return {
        "status": "debug",
        "session_id": session.session_id,
        "state": session.state,
        "step_result": step_result,
        "trace": snapshot,
        "conclusion": conclusion,
    }


def _handle_capability() -> Dict[str, Any]:
    """动态汇总子系统能力：debug 声明能力 + 子系统可用性探测"""
    caps: Dict[str, Any] = {}

    # debug 模块声明的（不）可能力
    try:
        dm = DebugManager(".")
        caps["debug_capability"] = dm.declare_capability()
    except Exception:
        caps["debug_capability"] = None

    # 检测到的子系统可用性
    subsystems = {}
    for name in [
        "pipeline_a", "pipeline_bc", "pipeline_d", "debug", "authoring",
        "gap_analysis", "kb", "llm_orchestration", "mcp_server", "player_session",
        "kernel_bridge", "runtime", "code_graph", "guard",
    ]:
        try:
            __import__("emuera_skill." + name)
            subsystems[name] = True
        except Exception:
            subsystems[name] = False
    caps["subsystems"] = subsystems
    caps["available_count"] = sum(1 for v in subsystems.values() if v)

    return caps


def _build_graph(game_dir: str):
    """从真实游戏目录构建代码图谱"""
    snapshot = _get_snapshot(game_dir)
    return build_graph(snapshot)


_KB_DATA_DIR = Path(__file__).parent.parent.parent / "test_kb_data"


def _get_kb(kb):
    """kb 为 None 时自动实例化 KnowledgeBase（数据来自项目内 test_kb_data）"""
    if kb is None:
        return KnowledgeBase(data_dir=str(_KB_DATA_DIR))
    return kb


def _compute_fingerprint(game_dir: str) -> str:
    """计算指纹（全量内容哈希，与 kernel_bridge.compute_fingerprint 同源语义）"""
    import hashlib
    game_path = Path(game_dir)
    if not game_path.exists():
        return "unknown"
    files = []
    for ext in ["*.ERB", "*.erb", "*.csv"]:
        for f in game_path.rglob(ext):
            if f.is_file():
                try:
                    digest = hashlib.md5()
                    with open(f, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            digest.update(chunk)
                    files.append(f"{f.name}:{digest.hexdigest()[:8]}")
                except Exception:
                    pass
    files.sort()
    return hashlib.sha256("|".join(files).encode()).hexdigest()[:16]


def _get_snapshot(game_dir: str) -> Any:
    """获取快照"""
    try:
        from ..kernel_bridge.engine import assemble_engine, capture_snapshot
    except ImportError:
        from kernel_bridge.engine import assemble_engine, capture_snapshot
    handle = assemble_engine(game_dir)
    snapshot = capture_snapshot(handle)
    snapshot.fingerprint = _compute_fingerprint(game_dir)
    return snapshot


# ── CLI 入口 ──

def cli_main(argv: List[str] = None) -> int:
    """CLI 主入口"""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("用法: emuera-skill <command> [options]")
        print("命令: scan, snapshot, graph, gap, run, debug, author, validate, impact, play, polish, capability, kb")
        return 1

    # 程序名（脚本路径）不参与命令解析
    if argv and argv[0].endswith(".py"):
        argv = argv[1:]

    # 统一解析：旗标（--xxx value）优先，首个非旗标 token 作为命令，
    # 同时兼容 [程序名, --game-dir, X, scan] 与 [--game-dir, X, scan] 两种 argv 惯例
    cmd = ""
    args = {}
    game_dir = None
    output_root = "./emuera-skill-out"
    fmt = "json"

    flags = {
        "--game-dir": "game_dir",
        "--output-root": "output_root",
        "--format": "fmt",
        "--query": "query",
        "--entry": "entry",
        "--mnemonic": "mnemonic",
    }
    skip_value = False
    numeric_flags = {"--timeout"}
    i = 0
    while i < len(argv):
        token = argv[i]
        if skip_value:
            args[last_flag] = float(token) if last_flag in numeric_flags else token
            skip_value = False
        elif token.startswith("--"):
            last_flag = token
            skip_value = True
        elif not cmd:
            cmd = token
        i += 1
    if skip_value and last_flag in flags:
        # 旗标缺值时用空串兜底
        if last_flag == "--game-dir":
            game_dir = ""
    if game_dir is None:
        game_dir = args.get("game_dir")
    if not game_dir:
        game_dir = args.get("--game-dir")
    if args.get("--output-root"):
        output_root = args["--output-root"]
    if args.get("--format"):
        fmt = args["--format"]
    if args.get("--query"):
        args["query"] = args.pop("--query")
    if args.get("--timeout"):
        args["timeout"] = args.pop("--timeout")
    if args.get("--entry"):
        args["entry"] = args.pop("--entry")
    if args.get("--mnemonic"):
        args["mnemonic"] = args.pop("--mnemonic")
    args.pop("--game-dir", None)
    args.pop("--output-root", None)
    args.pop("--format", None)

    if not game_dir:
        print("错误: 需要 --game-dir 参数")
        return 1

    result = route_command(cmd, game_dir, output_root, **args)
    print(format_output(result, fmt))
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
