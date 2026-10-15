# Emuera-SKILL 操作指引

## DSH PM 技能触发意图基线（v1.1.0 起）

为避免与通用"扫描/图谱/缺口/headless/调试/author/kb/引擎"等词误触其它技能，本技能注册到 DSH Project Manager 时仅绑定 5 个与 "emuera" 字面强相关的触发意图：

- `emuera`
- `Emuera`
- `emuera-skill`
- `Emuera-SKILL`
- `EMUERA`

所有其它宽泛词（扫描、图谱、缺口、headless、调试会话、开发辅助、author、kb、kernel、引擎、emera、脚本游戏、RPG Maker、ERA、红魔馆、游戏开发/调试/游玩）不再作为匹配意图，仅作为功能说明保留在描述里。

维护基线（2026-09-15 实测结论，已按 D:\project\project_manager 源码核实）：

1. PM 技能注册表是内存字典，以 skill_id 为键，`pm__skill__register` 对同名技能拒绝更新（assembly.py:1813 SKILL_ALREADY_EXISTS）；状态机单向 DRAFT→ACTIVE→DEPRECATED→ARCHIVED，archived 为终态，无注销工具。
2. 因此旧 v1.0.0 宽触发词条目已被 `pm__skill__transition` 推进到 archived（终态），当前处于"已停用"状态：`pm__skill__match` 对它不再命中任何意图（含 emuera 与 扫描），8 个关联命令（scan/graph/gap/run/debug/author/play/kb）也已在转为非 ACTIVE 时联动注销，不再出现在 `pm__command__list` 中。
3. v1.1.0 收窄版注册因同名占用无法在当前 PM 进程中完成，需在 PM 进程重启后、且旧条目未再被重新注册的前提下，按上述 5 个触发意图 + v1.1.0 重新执行 `pm__skill__register` 并 transition 到 active。若重启后 `pm__skill__list` 显示 v1.0.0 条目已消失，直接注册即可；若仍显示为 archived，同样可直接注册（archived 条目不占用名称的唯一性判定——该判定只查注册表内已存在条目，须以重启后实际 list 结果为准）。
4. 后续如需再调整触发意图，同样须遵循"重启后重新 register"流程，并同步更新本文件。

决策记录：`docs/adr/ADR-emuera-skill-trigger-narrowing.md`（PM knowledge base `df30e6ddaea9fe74`）。

---

## 命令速查表

### 工程体检
```bash
python run_cli.py scan --game-dir <游戏目录>
```

### 图谱分析
```bash
python run_cli.py graph --game-dir <游戏目录>
```

> ⚠️ **不可使用 DSH Project Manager 的 `pm__graph__code__build` 构建 ERB 图谱。**
> 该工具基于 tree-sitter，仅支持 Python/JS/TS/Go/Rust 等通用语言，**静默忽略 `.ERB` 文件**（传入 `languages=["python","erb"]` 时仍只检出 Python 文件）。
> ERB 图谱必须通过本技能自有管线构建（内核词法/语法分析器 + `code_graph/graph.py`），调用方式见下方「图谱调用规范」章节。

### 缺口分析
```bash
python run_cli.py gap --game-dir <游戏目录>
```

### 无头运行
```bash
python run_cli.py run --entry SYSTEM_TITLE --timeout 60 --game-dir <游戏目录>
```

### 调试会话
```bash
python run_cli.py debug --game-dir <游戏目录>
```

### 开发辅助
```bash
python run_cli.py author --query EVENT_TRAIN --game-dir <游戏目录>
```

### 游玩
```bash
python run_cli.py play --game-dir <游戏目录>
```

### 知识库查询
```bash
python run_cli.py kb --mnemonic PRINT --game-dir <游戏目录>
```

## Playbook

### Playbook 1: 工程体检
```bash
python run_cli.py scan --game-dir ./my_game
# 输出：函数数、变量数、缺口数、实现度
```

### Playbook 2: 函数诊断
```bash
python run_cli.py author --query SYSTEM_TITLE --game-dir ./my_game
# 输出：函数位置、文件、行号
```

### Playbook 3: 开发流程
```bash
python run_cli.py author --query EVENT_TRAIN --game-dir ./my_game
# 输出：锚点、骨架、影响面
```

### Playbook 4: 开局游玩
```bash
python run_cli.py play --game-dir ./my_game
# 输出：会话 ID、首屏动作
```

### Playbook 5: 知识库查询
```bash
python run_cli.py kb --mnemonic PRINT --game-dir ./my_game
# 输出：指令详情、实现状态
```

### Playbook 6: ERB 图谱构建（推荐路径）
```bash
# CLI（首选）
python run_cli.py graph --game-dir "D:/ERA红魔馆改/games/eraMegaten0.309"

# 或 Python API
import sys; sys.path.insert(0, "D:/ERA红魔馆改/emuera-skill")
from emuera_skill.interface.cli import route_command
result = route_command("graph",
    game_dir=r"D:\ERA红魔馆改\games\eraMegaten0.309",
    output_root=r"D:\ERA红魔馆改\emuera-skill\test_output\graph_test")
print(result["graph"]["node_count"])
```
> 输出：`code_graph.json`（节点/边/函数/变量/事件）+ `gap_ledger.json`（缺口账本）

## 图谱调用规范（ERB 专用）

> **核心原则**：`.ERB` 脚本的图谱构建**必须且只能**使用 emuera-skill 自有管线。
> DSH Project Manager 的 `pm__graph__code__build` 仅支持 Python 通用代码，**不支持 ERB**，传入后会被静默跳过（`languages` 检测不含 erb）。

| 调用场景 | 正确方式 | 错误方式（避免） |
|---|---|---|
| 构建 ERB 图谱 | `run_cli.py graph --game-dir <dir>` | `pm__graph__code__build` |
| Python API | `route_command("graph", game_dir, out)` | `pm__graph__build` |
| 引擎解析验证 | `run_cli.py scan --game-dir <dir>` | — |
| 缺口分析 | `run_cli.py gap --game-dir <dir>` | — |

### 误调用自检

若出现以下任一特征，说明正在误用 PM 图谱工具解析 ERB：
1. 输出中 `languages` 数组仅含 `python` 而项目目录以 `.ERB` 为主
2. 文件统计量（`files_count`）远小于实际 ERB 文件数（如 223 vs 6519）
3. 调用参数中出现 `db_path`/`repo_path`（PM 工具专属参数名，非 emuera-skill CLI 参数）
4. 结果中无 `code_graph.json` / `gap_ledger.json` 输出路径

## 语义校验（SEMA 系列）——实机测试前置门禁

> **教训（温泉旅行NTR 实机事故）**：内核"编译 0 错"不等于实机能启动。
> C# 引擎在**加载期**会中止的 7 类语义错误，Python 内核原本只做语法解析、不校验语义，
> 导致 `parse_errors: 0` 而 Emuera 实体运行直接中止。现已把 7 条 C# 硬规则移植为
> 跨函数语义校验，装配后自动执行，诊断以 WARNING 落监控事件与快照，**不阻塞装配**。

| 规则码 | 校验内容 | C# 取证 |
|---|---|---|
| SEMA-01 | 函数参数必须是 `ARG`/`ARGS` 或私有变量（LOCAL/MEMO/VAR） | `ErbLoader.cs:556-599` |
| SEMA-02 | 普通 `CALL` 不能调 `#FUNCTION` 函数（应在表达式中调用） | `Process.CalledFunction.cs:119` |
| SEMA-03 | `#FUNCTION` 函数体内禁止普通 `CALL` 指令 | `ErbLoader.cs:873` |
| SEMA-04 | 无 `#FUNCTION` 的函数不可作为表达式项 | `IdentifierDictionary.cs:590-592` |
| SEMA-05 | 同函数内 `#DIM` 重复声明 | `LogicalLineParser.cs:254-264` |
| SEMA-06 | 使用未 `#DIM` 声明的局部变量 | Emuera 局部作用域语义 |
| SEMA-07 | `#FUNCTION` 内禁用非 METHOD_SAFE 指令（`INPUT`/`WAIT` 族、`BEGIN`） | `ErbLoader.cs:869-875`、`FunctionIdentifier.cs:16` |

> **SEMA-07 实用推论**：想把一个 PROC 改成 `#FUNCTION` 前，先确认函数体内**没有** `INPUT`/`WAIT`/
> `BEGIN`（这些指令非 METHOD_SAFE，放进 `#FUNCTION` 会让 Emuera 加载中止）。若含 `INPUT`，
> 改为 `CALL 函数(参数)` + `变量 = RESULT`（`RETURN n` 会写入 `RESULT`）。

暴露路径：`engine.run_semantic_checks()` / `get_monitor_report()["semantic_warnings"]` /
`Snapshot.semantic_warnings` / `run_cli.py scan → summary.semantic_warnings` /
`preset project-checkup → summary.semantic_warnings`。

**实机测试前门禁**：`semantic_warnings` 计数必须为 0（或逐条人工确认），方可进实机。

## 错误码处置映射

| 错误码 | 子系统 | 含义 | 下一步动作 |
|---|---|---|---|
| KB-001 | kernel-bridge | 游戏目录不存在 | 检查 --game-dir 参数 |
| KB-003 | kernel-bridge | 引擎装配失败 | 先跑 project-checkup 看解析错误 |
| IN-101 | ingestion | 目录结构异常 | 检查游戏目录是否完整 |
| RT-401 | runtime | 无头装配失败 | 先跑 project-checkup 看解析错误 |
| PS-702 | player-session | 会话文件损坏 | 检查工程是否变更后重开新局 |
| AU-601 | authoring | 变量未声明 | 检查草案中的变量引用 |
| AU-602 | authoring | 函数不存在 | 检查草案中的函数引用 |
| IF-901 | interface | 游戏目录写入被拒绝 | 不要尝试写入游戏目录 |
| PM-001 | interface | 用 `pm__graph__code__build` 解析 ERB 时静默返回 `languages=["python"]`、文件数远小于实际 | **换用 `run_cli.py graph --game-dir <dir>`**；PM 图谱工具仅支持 Python 通用代码，不支持 ERB 语法 |

## Token 预算指引

- 预设工具默认返回摘要（≤2KB）
- 使用 `--format text` 获取人类可读格式
- 使用 `--format summary` 获取极简摘要
- 完整数据请直接调用子系统管线

## MCP Server

```bash
# 启动 stdio MCP Server
python -m emuera_skill.mcp_server.server
```

工具列表：
- `project_checkup` - 工程体检
- `diagnose_function` - 函数诊断
- `author_flow` - 开发流程
- `play_start` - 开局游玩
- `play_turn` - 回合推进
- `polish` - 润色文本
- `kb_search` - 知识库搜索
- `kb_lookup` - 知识库单条检索
- `capability` - 能力声明
