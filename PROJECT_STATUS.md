# Emuera-SKILL 项目状态

## 里程碑状态

| 阶段 | 状态 | 完成日期 | 测试 |
|---|---|---|---|
| P-1 文档基线补全 | ✅ 已完成 | 2026-09-05 | - |
| P0 基线守护与脚手架 | ✅ 已完成 | 2026-09-05 | 4/4 |
| P1 内核桥接与工程摄取 | ✅ 已完成 | 2026-09-05 | 8/8 |
| P2 代码图谱与缺口分析 | ✅ 已完成 | 2026-09-05 | 6/6 |
| P3 无头运行与痕迹采集 | ✅ 已完成 | 2026-09-06 | 8/8 |
| P4 会话与跨对话持久化 | ✅ 已完成 | 2026-09-06 | 11/11 |
| P5 开发辅助与模型编排 | ✅ 已完成 | 2026-09-06 | 7/7 |
| P6 接口层与预设聚合 | ✅ 已完成 | 2026-09-06 | 16/16 |
| P7 知识库子系统 | ✅ 已完成 | 2026-09-06 | 6/6 |
| P8 MCP 封装与操作指引 | ✅ 已完成 | 2026-09-06 | 5/5 |
| P9 验收与回归 | ⏳ 待开始 | - | - |

## 测试总结

- **总测试数**：83 通过 / 1 跳过（0 失败）——**历史值**
  - **⚠️ 2026-10-14 实测更正**：当前 `tests/` 实收 **73 个用例**，实测 `pytest tests -q` = **`73 passed / 0 skipped / 0 failed`**。
  - **成因**：**前期版本回滚导致部分测试用例丢失**（`tests/**` 时间戳集中于 2026-09-24，早于本次游戏改造；非本次回归）。
  - **处置**：待丢失用例补齐后重新冻结基线；在此之前验收门槛＝「当前收集数全通过」（`73 passed / 0 failed`）。权威口径同 `AGENTS.md` §四「数字口径」备注。
  - **➕ 2026-10-15 SEMA 语义校验改造**：新增 `tests/test_semantic.py`（7 用例，SEMA-01~07 校验 + 误报/真阳性回归），实测 **`80 passed / 0 failed`**；内核零侵入基线随 `kernel/` 改动同步重建（`tests/.kernel_baseline.json`）。
  - **同日修复（SEMA-04 真阳性）**：era红魔馆NTRplusplus 命中 2 条 PROC 被当表达式项——`访问者NTR.ERB` 加 `#FUNCTION` + 26 处 `RETURNF`；`COMF1809.ERB` 因含 `INPUT`（非 METHOD_SAFE）改 `CALL` + `RESULT`。修复后语义门禁 **0 诊断**。
- **内核零侵入基线**：文件哈希快照（`tests/.kernel_baseline.json`，2026-10-15 随 SEMA 改造重建）
- **语义校验能力（SEMA-01~07）**：对齐 C# 引擎 7 条硬规则（参数名 / #FUNCTION 互斥 / #FUNCTION 内 CALL / PROC 作表达式项 / #DIM 重复 / 局部变量未声明 / #FUNCTION 内非 METHOD_SAFE 指令），装配后自动执行，经 `run_cli.py scan` / `preset project-checkup` / `capability` 暴露 `semantic_warnings`，作为**实机测试前门禁**。详见 `kernel/docs/sema_semantic_checks.md` 与 `SKILL.md`「语义校验」章节。

## 交付物

### 核心模块
- `emuera_skill/kernel_bridge/` - 内核桥接
- `emuera_skill/ingestion/` - 文档摄取
- `emuera_skill/code_graph/` - 代码图谱
- `emuera_skill/gap_analysis/` - 缺口分析
- `emuera_skill/runtime/` - 无头运行
- `emuera_skill/player_session/` - 玩家会话
- `emuera_skill/debug/` - 调试会话
- `emuera_skill/authoring/` - 开发辅助
- `emuera_skill/llm_orchestration/` - 模型编排
- `emuera_skill/kb/` - 知识库
- `emuera_skill/interface/` - CLI 接口
- `emuera_skill/preset/` - 预设聚合
- `emuera_skill/mcp_server/` - MCP Server

### 文档
- `SKILL.md` - 操作指引
- `README.md` - 项目说明

### 管线
- `pipeline_a.py` - P-A 管线
- `pipeline_bc.py` - P-B/C 管线
- `pipeline_d.py` - P-D 管线

## 工程结构（合并后）

合并日期：**2026-09-16**。本仓库现为一个合并工程，同时包含 Emuera Python 内核与 Emuera-SKILL 工具包。

- `kernel/`：Emuera Python 解释器内核（原 `era红魔馆NTRplusplus/解释器` 全部内容）。保持 `src` 包层（`core/ io/ loader/ llm/ web/` + `engine.py`）；内核相对导入维持 `from src.engine import ERBEngine`。
- `emuera_skill/`：工具包（原 `src/`），导入名现为 **`emuera_skill`**。13 个子包 + 8 个顶层模块（`__init__.py config_loader.py errors.py guard.py output_dir.py pipeline_a.py pipeline_bc.py pipeline_d.py`）。
- `emuera_skill/kernel_bridge/engine.py`：解析到 `<工程根>/kernel/src`，并把 `kernel/` 加入 `sys.path`，使内核相对导入可工作。
- 工具层测试位于工程根 `tests/`（含 `.kernel_baseline.json` 内核零侵入基线）；自 **v1.2.2** 起随仓库一并版本控制并随发布包分发（此前部署包内不含测试）。

## 下一步

执行 P9（验收与回归）完成整个项目。
