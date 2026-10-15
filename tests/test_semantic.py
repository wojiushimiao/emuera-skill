"""SEMA 语义校验 fixture 测试：用注入错误的小型游戏目录验证 6 类规则命中。

设计要点：
- 每个 fixture 游戏目录只放一个 ERB 文件 + 空 CSV 目录（CSV 为空即可装配）；
- SEMA-01/05 直接命中（确定性）；
- SEMA-02/03/04/06 通过真实游戏回归（era红魔馆NTRplusplus）验证：
  真阳性可捕获注入错误、无误报（total 诊断 = 已知真阳性数）。
"""
import sys, os, shutil, tempfile
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from emuera_skill.kernel_bridge.engine import assemble_engine

GAME_DIR = r"D:\ERA红魔馆改\games\era红魔馆NTRplusplus"


def _make_game(tmp: str, erb_content: str) -> str:
    os.makedirs(os.path.join(tmp, "ERB"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "CSV"), exist_ok=True)
    with open(os.path.join(tmp, "ERB", "FIX.ERB"), "w", encoding="utf-8") as f:
        f.write(erb_content)
    return tmp


def test_sema01_bad_param_name():
    """SEMA-01：参数用了自定义名 TYPE/WHO → 报 2 条"""
    tmp = tempfile.mkdtemp(prefix="sema01_")
    try:
        src = "@F1(TYPE, WHO)\nTYPE = 1\nRETURN\n"
        _make_game(tmp, src)
        diags = assemble_engine(tmp).engine.run_semantic_checks()
        hits = [d for d in diags if d.startswith("SEMA-01")]
        assert len(hits) == 2, f"expected 2 SEMA-01, got {len(hits)}: {hits}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sema05_duplicate_dim():
    """SEMA-05：同函数内 #DIM MEMO_C 写两遍 → 报 1 条"""
    tmp = tempfile.mkdtemp(prefix="sema05_")
    try:
        src = "@Q1\n#DIM MEMO_C\n#DIM MEMO_C\nMEMO_C = 1\nRETURN\n"
        _make_game(tmp, src)
        diags = assemble_engine(tmp).engine.run_semantic_checks()
        hits = [d for d in diags if d.startswith("SEMA-05")]
        assert len(hits) == 1, f"expected 1 SEMA-05, got {len(hits)}: {hits}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_clean_fixtures_no_false_positive():
    """干净 fixture（全部合法写法）→ 0 诊断"""
    tmp = tempfile.mkdtemp(prefix="sema_clean_")
    try:
        src = (
            "@GOOD_PROC\n#DIM MEMO_A\nMEMO_A = 1\nRETURN\n"
            "@GOOD_FUNC\n#FUNCTION\n#DIM MEMO_B\nMEMO_B = 2\nRETURNF MEMO_B\n"
            "@CALLER\n#DIM MEMO_C\nCALL GOOD_PROC\nLOCAL1 = GOOD_FUNC()\nMEMO_C = LOCAL1\nRETURN\n"
        )
        _make_game(tmp, src)
        diags = assemble_engine(tmp).engine.run_semantic_checks()
        assert diags == [], f"clean fixture should have 0 diagnostics, got: {diags}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sema07_input_in_function():
    """SEMA-07：#FUNCTION 内使用非 METHOD_SAFE 输入等待类指令 → 命中；
    PROC 内的 INPUT 与干净 #FUNCTION 不误报。"""
    tmp = tempfile.mkdtemp(prefix="sema07_")
    try:
        src = (
            "@BAD_INPUT\n#FUNCTION\n#DIM X\nINPUT\nRETURNF X\n"
            "@BAD_WAIT\n#FUNCTION\nWAIT\nRETURNF 0\n"
            "@OK_PROC\nINPUT\nRETURN\n"
            "@OK_FUNC\n#FUNCTION\n#DIM Y\nY = 1\nRETURNF Y\n"
        )
        _make_game(tmp, src)
        diags = assemble_engine(tmp).engine.run_semantic_checks()
        hits = [d for d in diags if d.startswith("SEMA-07")]
        assert len(hits) == 2, f"expected 2 SEMA-07, got {len(hits)}: {hits}"
        assert all("#FUNCTION" in h for h in hits), hits
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_real_game_semantic_clean():
    """真实游戏（era红魔馆NTRplusplus）语义门禁：7 类规则全部零诊断。

    历史：2026-10-15 首次运行时 SEMA-04 命中 2 条真阳性（`@访问者NTR行为选择` /
    `@料理菜单选择` 为 PROC 却被当表达式调用，C# IdentifierDictionary.cs:592 → CodeEE）。
    已修复：前者加 `#FUNCTION` + `RETURNF`；后者含 INPUT（非 METHOD_SAFE，不可为
    #FUNCTION），改调用点为 `CALL` + `RESULT`。本测试冻结"零诊断"口径防回归。
    """
    diags = assemble_engine(GAME_DIR).engine.run_semantic_checks()
    assert diags == [], f"语义门禁未清零（含误报或新真阳性）: {diags}"


def test_engine_semantic_api_shape():
    """引擎 SEMA API 形态：返回 list[str]，每行含规则码与定位"""
    eng = assemble_engine(GAME_DIR).engine
    diags = eng.run_semantic_checks()
    assert isinstance(diags, list)
    for d in diags:
        assert isinstance(d, str)
        assert d.startswith("SEMA-"), f"诊断行必须含规则码: {d!r}"
    # get_semantic_warnings 与 run_semantic_checks 一致
    assert eng.get_semantic_warnings() == diags


def test_monitor_report_exposes_semantic_warnings():
    """监控报告带 semantic_warnings 字段（装配后自动一轮校验）"""
    eng = assemble_engine(GAME_DIR).engine
    report = eng.get_monitor_report()
    assert "semantic_warnings" in report
    assert isinstance(report["semantic_warnings"], list)
