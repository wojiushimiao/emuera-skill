# Emuera-SKILL

Emuera 脚本游戏开发、调试、游玩工具包 —— **内置完整 Python 版 ERB 解释器内核**，开箱即用。

**版本**：v1.2.0 ｜ **Python**：≥ 3.11 ｜ **核心依赖**：零（纯标准库）

## 功能特性

- **内置完整内核**：`kernel/src/` 收录完整 Python 解释器内核（词法/语法/语义分析、虚拟机、CSV/ERH 加载、渲染器、LLM 桥接、Web 服务）
- **代码图谱分析**：构建四类节点（函数/变量/角色/事件）、三类边（调用/跳转/变量读写）的结构化图谱
- **缺口检测**：从静态可达性、语句实现度、动态覆盖率三路分析缺口
- **无头运行**：引擎在无人值守模式下可观测地运行，带超时看门狗
- **会话管理**：玩家会话状态机，支持跨对话持久化（终态装载，逐字节一致）
- **开发辅助**：锚点检索、骨架生成、规范校验、影响面评估
- **模型编排**：上下文压缩、提示模板、契约校验、降级兜底
- **知识库**：指令字典、语法手册、模式库，按需检索
- **MCP Server**：stdio 本地进程，9 个工具 + 1 个资源端点供 LLM 直接调用

## 快速开始

### 免安装运行（推荐）

```bash
# CLI
python run_cli.py --game-dir <游戏目录> <命令>

# 查看全部命令
python run_cli.py
```

命令：`scan, graph, gap, run, debug, author, play, polish, capability, kb`

### 安装为命令行工具

```bash
pip install .
emuera-skill --game-dir ./my_game scan
```

### 基本使用

```bash
# 工程体检
python run_cli.py --game-dir ./my_game scan

# 函数诊断
python run_cli.py --game-dir ./my_game graph build

# 无头运行（引擎真实跑起来）
python run_cli.py --game-dir ./my_game run --entry SYSTEM_TITLE --timeout 60

# 知识库查询
python run_cli.py --game-dir ./my_game kb --lookup PRINT
```

### MCP Server

```bash
python run_mcp_server.py
```

配置到 MCP 客户端：

```json
{
  "mcpServers": {
    "emuera-skill": {
      "command": "python",
      "args": ["<部署包路径>/run_mcp_server.py"]
    }
  }
}
```

## 目录结构

```
Emuera-SKILL/
├── emuera_skill/        # 工具层（可导入包，pip install 后为 emuera_skill）
│   ├── kernel_bridge/   # 内核桥接（自动探测 kernel/src）
│   ├── ingestion/       # 文档摄取
│   ├── code_graph/      # 代码图谱
│   ├── gap_analysis/    # 缺口分析
│   ├── runtime/         # 无头运行
│   ├── debug/           # 调试会话
│   ├── authoring/       # 开发辅助
│   ├── llm_orchestration/ # 模型编排
│   ├── player_session/  # 玩家会话
│   ├── interface/       # CLI 接口（9 命令族）
│   ├── preset/          # 预设聚合（6 个一键预设）
│   ├── kb/              # 知识库
│   ├── mcp_server/      # MCP Server（9 工具）
│   └── pipeline_a/bc/d.py # 管线
├── kernel/              # 内置完整 Python 内核
│   └── src/             # 内核包（保留 src 包名，零修改）
│       ├── engine.py    # ERBEngine 入口
│       ├── core/        # 词法/语法/语义/VM/变量/函数分发
│       ├── io/          # 渲染器
│       ├── loader/      # CSV / ERH 加载
│       ├── llm/         # LLM 桥接（需 aiohttp）
│       └── web/         # Web 服务（需 aiohttp）
├── templates/           # 提示模板（4 个 YAML）
├── test_kb_data/        # 知识库数据（3 个 JSON）
├── config/              # 默认配置
├── contracts/           # 契约定义
├── run_cli.py           # CLI 入口
├── run_mcp_server.py    # MCP 入口
├── pyproject.toml
└── requirements.txt
```

## 依赖

**核心功能零第三方依赖** —— 工程扫描、图谱、缺口分析、无头运行、会话、调试、知识库、CLI、MCP 全部基于标准库 + 内置内核。

仅以下两项可选功能需要 `aiohttp`：

- 内核 LLM 桥接：`kernel/src/llm/llm_bridge.py`
- 内核 Web 服务：`kernel/src/web/server.py`

```bash
pip install "aiohttp>=3.9.0"   # 或 pip install -e ".[full]"
```

## 文档

- [SKILL.md](SKILL.md)：LLM 操作指引（命令速查、Playbook、错误码处置映射）
- [真实验收与能力评估.md](真实验收与能力评估.md)：真实完成状态与能力边界
- [系统完善与修复计划_R1.md](系统完善与修复计划_R1.md)：修复计划与执行记录
- [PROJECT_STATUS.md](PROJECT_STATUS.md)：项目状态

## 内核路径解析

`emuera_skill/kernel_bridge/engine.py` 自动定位内核，优先使用部署包内置的 `kernel/src/`，未找到时回退到开发工程路径（`../era红魔馆NTRplusplus/解释器/src`）。

内核内部使用 `from src.engine import ...` 与包内相对导入，因此部署包保留 `kernel/src/` 的 `src` 包名层级，**内核源码零修改**即可运行。

## 版本

- **v1.2.0 (2026-09-15)**：内置完整 Python 内核（含 llm/、web/）；同步最新源码（8 个模块更新）；修正内核包层级与导入路径
- v1.1.0 (2026-09-09)：首个发布版，内核仅含核心子集（core/io/loader）
- v1.0.0 (2026-09-06)：初始版本

## 许可

内部项目，仅供开发团队使用。
