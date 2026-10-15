# SEMA 语义校验能力改造说明（内核 + 工具包暴露）

> 依据：`docs/11_ERAsqc0.52温泉旅行NTR/执行计划/调试报告_emuera日志.md` §5 教训——
> 内核报 `parse_errors: 0` 但 Emuera 实机加载中止。把 C# 引擎 7 条硬语义规则移植为内核
> 跨函数校验，**实机测试前完整暴露**"编译 0 错、加载即中止"类问题。

## 1. 规则（对齐 C# 官方引擎取证）

| 规则码 | 校验内容 | C# 取证 | C# 级别 |
|---|---|---|---|
| SEMA-01 | 参数必须是 `ARG`/`ARGS` 或函数内 `#DIM` 私有变量 | `ErbLoader.cs:556-599`（`VariableCode.ARG/ARGS` + `IsPrivate`） | hard（中止） |
| SEMA-02 | 普通 `CALL` 调 `#FUNCTION` 函数 | `Process.CalledFunction.cs:119` | hard（中止） |
| SEMA-03 | `#FUNCTION` 函数体内 `CALL` 用户函数 | `ErbLoader.cs:873`（"X指令不能在#FUNCTION函数中使用"） | warn Lv2（isError） |
| SEMA-04 | 无 `#FUNCTION` 函数作表达式项（PROC 写进表达式） | `IdentifierDictionary.cs:590-592`（CodeEE） | hard（中止） |
| SEMA-05 | 同函数内 `#DIM` 重复声明 | `LogicalLineParser.cs:254-264`（"変数名Xは既に使用されています"） | warn Lv2 + 丢弃后声明 |
| SEMA-06 | 函数体赋值 LHS 使用未 `#DIM` 声明的局部变量 | `IdentifierDictionary.cs:617`（"变量\"X\"未在函数中定义"） | hard（中止） |
| SEMA-07 | `#FUNCTION` 内使用**非 METHOD_SAFE** 指令（输入等待类 `INPUT`/`WAIT` 族、跨函数跳转 `BEGIN`） | `ErbLoader.cs:869-875`（`IsMethodSafe` 检查 → `Warn(..., 2, isError:true)`）；`FunctionIdentifier.cs:16` METHOD_SAFE 定义 | warn Lv2（isError） |

**SEMA-07 取证细节**（决定"能否把某个 PROC 改成 `#FUNCTION`"）：
`METHOD_SAFE` 注释原文「#Function中で呼び出してよい命令。**WAITなど入力を伴うもの**、CALLなど関数呼び出しを伴うものは不可」。
逐指令 flag 核验结果——

| 指令 | flag | 可用于 #FUNCTION |
|---|---|---|
| `INPUT`/`INPUTS`/`ONEINPUT(S)`/`TINPUT(S)` | `IS_PRINT \| IS_INPUT`（`Instraction.Child.cs:621/647/674/709/742/778`） | ❌ |
| `WAIT` | `IS_PRINT`（`:562`） | ❌ |
| `WAITANYKEY` | `IS_PRINT`（`:580`） | ❌ |
| `TWAIT` | `IS_PRINT \| EXTENDED`（`:593`） | ❌ |
| `BEGIN` | `FLOW_CONTROL`（`:1674`） | ❌ |
| `SETCOLOR`/`RESETCOLOR`/`PRINT*`/`DRAWLINE` | 含 `METHOD_SAFE`（`FunctionIdentifier.cs:264` 等） | ✅ |
| 控制流 `IF`/`FOR`/`RETURN`/`RETURNF` | 经指令对象注册为 `METHOD_SAFE` | ✅ |

> ⚠️ 注意：不能把 `FunctionIdentifier.cs` 中「源码行未出现 METHOD_SAFE 字面量」的 `addFunction` 条目
> 直接当作非 METHOD_SAFE——控制流等条目经**指令对象**（如 `ENDIF_Instruction`）携带 flag，
> 需逐类核验（上表已核验）。

误报抑制口径（已实现并验证零误报）：
- SEMA-01 只认 `ARG/ARGS` 与函数内 `#DIM` 私有变量（C# `IsPrivate` 分支）；
- SEMA-03 仅报 `#FUNCTION` 体内 `CALL` 到**用户函数**（内置指令 `SETCOLOR` 等合法）；
- SEMA-05 仅查 `#DIM` 重复（`#LOCALSIZE` 已有单独行为）；
- SEMA-06 仅查**赋值 LHS 裸自定义名**：免报全局/角色变量、CSV 名表键、`LOCAL/MEMO/VAR`
  本地命名空间、`#DIM CONST` 常量（C# 内联展开为字面量）、函数名；
  表达式位置的 bare 名一律视为合法常量/名表键/字面量（保守口径，避免 `CSTR:ARG:行为心情 = 等待`
  这类合法写法误报）；
- SEMA-07 仅查已逐类核验为非 METHOD_SAFE 的指令白名单（上表），不整表照搬。

## 2. 内核改动（`kernel/src/`，零侵入基线已同步重建）

| 文件 | 改动 |
|---|---|
| `core/semantic_analyzer.py` | 新增 `check_programs(programs)`（三遍扫描：函数名/#FUNCTION 收集 → 逐函数 SEMA-01/03/04/05/06/07 → 全局 SEMA-02）；`_ensure_registered_names()` 惰性收集已注册全局变量名 + CSV name_map 键（装配阶段 CSV 才加载，不能 `__init__` 时收集）；`_LOCAL_PREFIXES`/`_BUILTIN_GLOBAL_NAMES`/`_LEGIT_PARAM_NAMES`/`_METHOD_UNSAFE_IN_FUNCTION` 白名单 |
| `engine.py` | `initialize()` 装配后自动跑一轮 `run_semantic_checks()`；新增 `run_semantic_checks()` / `get_semantic_warnings()` 公开 API；`get_monitor_report()` 增加 `semantic_warnings` 字段；诊断按 `WARNING` 类别落 `_monitor_events`（不阻塞装配，`parse_errors` 保持 0） |

设计原则（与内核既有风格一致）：
- 只读、不改 AST、不抛异常（对齐 C# `ParserMediator.Warn` 语义）；
- 命中即记录，实机中止类（hard）在报告中可见，供人工确认后再进实机。

## 3. 工具包暴露

| 位置 | 内容 |
|---|---|
| `emuera_skill/kernel_bridge/engine.py` `capture_snapshot` | `Snapshot.semantic_warnings` 优先取引擎 `get_semantic_warnings()`，缺失时回退监控事件 WARNING |
| `emuera_skill/pipeline_a.py` | `snapshot.json` 落盘 + 返回 `semantic_warnings` 清单；`summary.semantic_warnings` 计数（缓存命中路径同） |
| `emuera_skill/preset/aggregator.py` `project_checkup` | summary 增加 `parse_errors` / `semantic_warnings` / `semantic_warnings_sample`（前 10 条）；`force_refresh=True` 确保拿到最新诊断 |
| `emuera_skill/interface/cli.py` `_handle_capability` | 新增 `semantic_check_capability`（7 条规则 + 暴露路径声明） |
| `SKILL.md` | 新增「语义校验（SEMA 系列）——实机测试前置门禁」章节（规则表 + 暴露路径 + 门禁口径） |

## 4. 验收

```bash
cd "D:/ERA红魔馆改/emuera-skill"
PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# 全量（含 7 个新增 SEMA 测试）
"$PY" -m pytest tests -q
# 实测：80 passed, 0 failed（基线 73 + 新增 7）

# 引擎 API 直验
"$PY" -c "
import sys; sys.path.insert(0, '.')
from emuera_skill.kernel_bridge.engine import assemble_engine
eng = assemble_engine(r'D:\ERA红魔馆改\games\era红魔馆NTRplusplus').engine
print(eng.run_semantic_checks())"
# 当前：0 条（2026-10-15 修复 2 条 SEMA-04 真阳性后清零）

# 工具包入口
"$PY" run_cli.py scan --game-dir "D:/ERA红魔馆改/games/era红魔馆NTRplusplus"
# summary.semantic_warnings = 0（与引擎一致）
```

## 5. 已修复真阳性（era红魔馆NTRplusplus，2026-10-15）

首次运行 SEMA 校验命中 2 条 **SEMA-04 真阳性**（PROC 被当表达式项，C# `IdentifierDictionary.cs:592` → CodeEE 中止）。
两处**修法不同**，依据是 SEMA-07 的 METHOD_SAFE 取证：

| 位置 | 问题 | 修复 | 为何用此法 |
|---|---|---|---|
| `访问者NTR.ERB:18` `@访问者NTR行为选择`（L73）| `行为类型 = 访问者NTR行为选择(目标角色)` 表达式调用 PROC | 函数加 `#FUNCTION` 指令；**26 处** `RETURN n` → `RETURNF n` | 纯计算选择器（无 INPUT/PRINT/CALL），可安全转为 method |
| `COMF1809.ERB:12` `@料理菜单选择`（L54）| `料理类型 = 料理菜单选择(菜单页)` 表达式调用 PROC | 调用点改为 `CALL 料理菜单选择(菜单页)` + `料理类型 = RESULT`（+1 行）| 函数体含 **`INPUT`**（非 METHOD_SAFE，不可用于 `#FUNCTION`）；`RETURN n` 会写入 `RESULT`（`Instraction.Child.cs:2004-2024`），故 `CALL + RESULT` 等价且合法 |

验证：修复后 `parse_errors = 0`、`semantic_warnings = 0`；游戏内 `#FUNCTION` 体内非 METHOD_SAFE 指令
普查为 **0 命中**（SEMA-07 无新真阳性）。

> 校验器本身不自动改游戏代码（`games/` 边界）；本次修复由用户明确指令授权执行。
> **还原备份**：`_backup_sema04_fix_2026-10-15/`（两文件修复前原文，工作区无 git，为唯一还原路径；
> 目录内 `README.md` 载明还原方式）。

## 6. 温泉旅行NTR（ERAsqc0.52）回归结论

| 调试报告根因 | 对应 SEMA 规则 | 覆盖状态 |
|---|---|---|
| R-A 自定义参数名（5） | SEMA-01 | ✅ fixture 验证命中（TYPE/WHO → 2 条） |
| R-B CALL 调 #FUNCTION（11） | SEMA-02 | ✅ 逻辑实现（era红魔馆当前无此形态，真阳性为 0） |
| R-C #FUNCTION 内 CALL（1） | SEMA-03 | ✅ 逻辑实现（内置 CALL 已排除误报） |
| R-D PROC 进表达式（1） | SEMA-04 | ✅ era红魔馆命中 2 条真阳性 → 已修复清零 |
| R-E #DIM 重复（1） | SEMA-05 | ✅ fixture 验证命中 |
| R-F 局部变量未声明（2） | SEMA-06 | ✅ 逻辑实现（LHS 口径 + 白名单，零误报） |
| （新增）输入等待类指令误入 #FUNCTION | SEMA-07 | ✅ fixture 验证命中；游戏内 0 命中 |

注：`docs/11_ERAsqc0.52温泉旅行NTR` 目录仅有执行计划与调试报告，游戏本体目录
`games/ERAsqc0.52全汉化_LuckyAAA汉化` 未应用本次 NTR 改造（R-A~F 为改造后问题），
故 29 条诊断无法在该目录直接复现；以 era红魔馆NTRplusplus（同族游戏）+ fixture 注入
完成全规则命中验证。

## 7. 附：era红魔馆NTRplusplus 编码约定说明（IN-102 非致命）

`project-checkup` 报 **312 项 IN-102**（非 ASCII 脚本缺 UTF-8 BOM，293 个 ERB）。经核验
**在本游戏非致命**：`emuera.config` 中 `全ファイルをUTF-8として読み込む: YES`（全部文件按
UTF-8 读取），故 Emuera 不依赖 BOM 判定编码。该状态为游戏基线（含 `SOURCE.ERB`/`SYSTEM.ERB`
等长期核心文件），非本分支回归，**本次不改**（改 293 个文件违反最小变更）。

> 但注意：**未开启该配置的游戏**（如调试报告中的 `ERAsqc0.52` 项目）缺 BOM 会导致
> Emuera 按 Shift-JIS 解析而报错——跨项目复用时需先确认 `emuera.config`。
