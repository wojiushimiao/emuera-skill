# Emuera-SKILL 操作指引

## 命令速查表

### 工程体检
```bash
python run_cli.py scan --game-dir <游戏目录>
```

### 图谱分析
```bash
python run_cli.py graph --game-dir <游戏目录>
```

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
emuera-skill --game-dir ./my_game project-checkup
# 输出：函数数、变量数、缺口数、实现度
```

### Playbook 2: 函数诊断
```bash
emuera-skill --game-dir ./my_game diagnose-function --func-name SYSTEM_TITLE
# 输出：函数位置、文件、行号
```

### Playbook 3: 开发流程
```bash
emuera-skill --game-dir ./my_game author-flow --query EVENT_TRAIN
# 输出：锚点、骨架、影响面
```

### Playbook 4: 开局游玩
```bash
emuera-skill --game-dir ./my_game play-start
# 输出：会话 ID、首屏动作
```

### Playbook 5: 知识库查询
```bash
emuera-skill --game-dir ./my_game kb --mnemonic PRINT
# 输出：指令详情、实现状态
```

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
