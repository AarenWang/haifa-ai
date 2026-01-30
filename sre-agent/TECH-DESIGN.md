# 生产只读运维智能体 技术设计

## 1. 总体架构

### 1.1 两阶段流程

**Phase A：Agent 采证**
- Claude Agent SDK (v1) / 直接调用千问 API (v2, v3)
- 调用 MCP 工具 `sre_diag`
- 输出 evidence_pack.json

**Phase B：结构化报告**
- Claude API `output_format` + JSON Schema (v1)
- 千问 API + JSON Schema (v2, v3)
- 输入 evidence_pack
- 输出 diagnosis_report.json

### 1.2 版本对比

| 版本 | AI 模型 | MCP 工具 | 诊断策略 | 文件 |
|------|---------|----------|----------|------|
| v1 | Claude Sonnet | ✓ | 固定轮数 | `diag_load_agent.py` |
| v2 | 千问 (qwen-plus) | ✗ | 固定5轮 | `diag_load_agent_v2.py` |
| v3 | 千问 + LangGraph | ✗ | 智能路由决策 | `diag_load_agent_v3.py` |

## 2. 模块与职责

### 2.1 主程序

**v1: `diag_load_agent.py`**
- 使用 Claude Agent SDK
- 通过 MCP 协议调用工具
- 证据收集与 evidence_schema 校验
- 可选生成最终报告

**v2: `diag_load_agent_v2.py`**
- 直接调用千问 API（OpenAI 兼容接口）
- 内置诊断工具，无需 MCP
- 固定5轮迭代诊断
- 支持更多细粒度命令

**v3: `diag_load_agent_v3.py`**
- 使用 LangGraph 编排诊断流程
- 根据问题类型动态选择诊断路径
- 减少不必要的命令执行

### 2.2 MCP 服务器

**`mcp_server_sre.py`**
- 只读命令白名单（40+ 命令）
- SSH 直连执行（支持密钥/密码认证）
- 输出脱敏与审计
- 通过 FastMCP 暴露工具

### 2.3 辅助模块

| 模块 | 职责 |
|------|------|
| `report_generator.py` | Phase B 结构化报告生成 |
| `redaction.py` | 脱敏规则与替换计数 |
| `audit.py` | 审计日志写入 |

## 3. MCP 调用流程

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  diag_load_agent.py (主程序 - v1)                           │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ ClaudeSDKClient                                        │ │
│  │   - 连接到 Claude API                                   │ │
│  │   - 发送 prompt，告诉 AI 使用 MCP 工具                  │ │
│  └───────────────┬───────────────────────────────────────┘ │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐ │
│  │ MCP Server 配置                                         │ │
│  │   mcp_servers: {                                        │ │
│  │     "sre": {                                            │ │
│  │       "command": ["python", "mcp_server_sre.py"]        │ │
│  │     }                                                   │ │
│  │   }                                                     │ │
│  └───────────────┬───────────────────────────────────────┘ │
│                  │ 启动子进程                                │
└──────────────────┼───────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  mcp_server_sre.py (独立子进程)                             │
│                                                             │
│  - 启动 FastMCP 服务器                                       │
│  - 暴露工具: sre_diag(), sre_list_commands(), sre_get_status()│
│  - 通过 stdio 与 ClaudeSDKClient 通信                       │
│  - 收到工具调用后执行 SSH 命令                               │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ sre_diag(host, cmd_id, service, pid)                  │ │
│  │   └─> SSH 执行 ──> 脱敏 ──> 返回结果                   │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 调用时序

```
1. diag_load_agent.py 启动
   │
2. 创建 ClaudeSDKClient，配置 MCP 服务器
   │
3. ClaudeSDKClient 启动子进程:
   │   python mcp_server_sre.py
   │
4. mcp_server_sre.py 启动 FastMCP 服务器
   │   - 通过 stdio 进行通信
   │   - 注册工具: sre_diag, sre_list_commands, sre_get_status
   │
5. ClaudeSDKClient 发送 prompt 给 Claude
   │   prompt 中说明: "Use the MCP tool `sre_diag(...)`"
   │
6. Claude 分析后决定调用工具:
   │   Claude -> ClaudeSDKClient -> MCP协议 -> mcp_server_sre.py
   │
7. mcp_server_sre.py 执行 SSH 命令，返回结果
   │
8. 结果通过 MCP 协议返回给 Claude
   │
9. Claude 基于工具返回继续分析，可能调用更多工具
   │
10. 最终结果返回给 diag_load_agent.py
```

### 3.3 MCP 通信细节

**配置方式 (v1 代码):**

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "sre": {
            "command": [current_python, "mcp_server_sre.py"],
        }
    },
    env=api_env,  # 传递环境变量给子进程
)
```

**FastMCP 工具注册:**

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("sre-tools")

@mcp.tool()
def sre_diag(host: str, cmd_id: str, service: str = None, pid: str = None):
    """工具定义，AI 可以调用"""
    # 执行 SSH 命令
    return {"ok": True, "output": "..."}

if __name__ == "__main__":
    mcp.run()  # 启动 stdio 通信
```

**关键组件:**

| 组件 | 作用 |
|------|------|
| `ClaudeSDKClient` | Claude Agent SDK 的客户端，管理 MCP 服务器 |
| `FastMCP` | MCP 服务器框架，通过 stdio 通信 |
| `@mcp.tool()` | 装饰器，将 Python 函数注册为 MCP 工具 |
| `mcp_servers` 配置 | 告诉 SDK 启动哪些 MCP 服务器子进程 |
| stdio | 子进程与父进程之间的通信通道 |

### 3.4 为什么这样设计？

1. **隔离性** - MCP 服务器运行在独立子进程，崩溃不影响主程序
2. **可扩展** - 可以同时启动多个 MCP 服务器（如不同的诊断工具）
3. **安全** - 工具在沙箱中运行，AI 只能调用白名单工具
4. **标准化** - MCP 是通用协议，任何支持 MCP 的 AI 都能使用这些工具

## 4. 诊断策略

### 4.1 v2 固定轮数策略

```
第1轮: 基础系统状态 (uptime, top, vmstat, iostat...)
   │
第2轮: 进程级细节 (/proc/pid/*)
   │
第3轮: Java深度分析 (jstat, jstack...)
   │
第4轮: IO瓶颈分析 (iotop, pidstat -d)
   │
第5轮: 最终综合诊断
```

### 4.2 v3 智能路由策略

```
基础信息收集 → AI分类决策
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
    CPU高           IO等待          内存压力
    │               │               │
    ▼               ▼               ▼
 mpstat          pidstat_io      jstat_gc
 /proc/pid/status /proc/pid/io   jcmd_heap
 jstack          iotop
        │               │               │
        └───────────────┼───────────────┘
                        ▼
                   生成最终报告
```

## 5. 数据结构

### 5.1 evidence_pack.json

Schema 见 [evidence_schema.json](evidence_schema.json)。核心字段：

- meta: host、service、timestamp
- snapshots: cmd_id、signal、summary、audit_ref
- hypothesis: category、confidence、why、evidence_refs
- next_checks: cmd_id、purpose

### 5.2 diagnosis_report.json

Schema 见 [report_schema.json](report_schema.json)。核心字段：

- meta
- root_cause
- evidence_table
- next_actions
- audit
- redaction

## 6. 只读命令白名单

### 6.1 基础系统信息

| cmd_id | 命令 |
|--------|------|
| uptime | uptime |
| loadavg | cat /proc/loadavg |
| top | top -b -n 1 |
| ps_cpu | ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%cpu |
| vmstat | vmstat 1 5 |
| iostat | iostat -x 1 3 |
| free | free -m |

### 6.2 CPU 深度诊断

| cmd_id | 命令 |
|--------|------|
| mpstat | mpstat -P ALL 1 1 |
| pidstat | pidstat -h 1 1 |
| proc_pid_status | cat /proc/{pid}/status |
| proc_pid_stack | cat /proc/{pid}/stack |
| proc_pid_wchan | cat /proc/{pid}/wchan |

### 6.3 IO 深度诊断

| cmd_id | 命令 |
|--------|------|
| proc_pid_io | cat /proc/{pid}/io |
| iotop | iotop -b -n 1 -o |
| pidstat_io | pidstat -d 1 2 |

### 6.4 Java 诊断

| cmd_id | 命令 |
|--------|------|
| jps | jps -l |
| jstat | jstat -gcutil {pid} 1 5 |
| jstat_gc | jstat -gc {pid} 1 1 |
| jstack | jstack -l {pid} |
| jcmd_threads | jcmd {pid} Thread.print |
| jcmd_heap | jcmd {pid} GC.heap_info |

## 7. 安全与审计

### 7.1 安全策略

- cmd_id 白名单
- 参数必填校验（service/pid）
- 输出截断与超时限制
- 只读诊断，无写操作

### 7.2 审计

- 记录 id、cmd_id、start_time、elapsed_ms
- 记录 redacted output hash
- 审计日志可通过 `OPS_AGENT_AUDIT_LOG` 配置

### 7.3 脱敏策略

默认规则见 [redaction.py](redaction.py)：

- IP、邮箱、Token、路径、用户名
- 输出仅保存脱敏后内容

## 8. 运行方式

### 8.1 v1 (Claude + MCP)

```bash
# 基础诊断
export ANTHROPIC_API_KEY="sk-xxx"
python diag_load_agent.py --host 10.0.0.12 --service myapp

# 生成最终报告
python diag_load_agent.py --host 10.0.0.12 --service myapp --final-report
```

### 8.2 v2 (千问 + 固定轮数)

```bash
# 设置千问 API Key
export DASHSCOPE_API_KEY="sk-xxx"

# 基础诊断
python diag_load_agent_v2.py --host 10.0.0.12 --service myapp

# 指定轮数
python diag_load_agent_v2.py --host 10.0.0.12 --service myapp --max-rounds 3

# 保存报告
python diag_load_agent_v2.py --host 10.0.0.12 --service myapp -o
```

### 8.3 v3 (千问 + LangGraph)

```bash
# 智能路由诊断
pip install langgraph langchain-core
python diag_load_agent_v3.py --host 10.0.0.12 --service myapp -o
```

### 8.4 SSH 认证

```bash
# 密钥认证 (默认)
python diag_load_agent_v2.py --host 10.0.0.12 --service myapp

# 密码认证
python diag_load_agent_v2.py --host 10.0.0.12 --service myapp \
  --ssh-user admin --ssh-password "password"
```

## 9. 配置

### 9.1 环境变量

| 变量 | 用途 | 版本 |
|------|------|------|
| `ANTHROPIC_API_KEY` | Claude API Key | v1 |
| `ANTHROPIC_BASE_URL` | Claude API endpoint | v1 |
| `DASHSCOPE_API_KEY` | 千问 API Key | v2, v3 |
| `SRE_SSH_USER` | SSH 用户名 | all |
| `SRE_SSH_PASSWORD` | SSH 密码 | all |
| `SRE_SSH_PORT` | SSH 端口 | all |
| `OPS_AGENT_AUDIT_LOG` | 审计日志路径 | all |
| `OPS_AGENT_LOG_LEVEL` | 日志级别 | all |

### 9.2 报告路径

- v2/v3 默认保存到 `sre-agent/report/YYMMDD_HHMM.json`

## 10. 日志

### 10.1 MCP 服务器日志

```
[INFO] [MCP-SRE] SRE MCP Server 启动
[INFO] [MCP-SRE] 配置:
[INFO] [MCP-SRE]   - SSH 用户: root
[INFO] [MCP-SRE]   - SSH 端口: 22
[INFO] [MCP-SRE]   - 可用命令: 30
[INFO] [MCP-SRE] [DIAG] 开始诊断: host=10.0.0.12, cmd_id=uptime
[INFO] [MCP-SRE] [SSH] 开始执行: host=root@10.0.0.12 cmd_id=uptime
[INFO] [MCP-SRE] [SSH] 完成: host=root@10.0.0.12, elapsed=0.45s
[INFO] [MCP-SRE] [DIAG] 完成: cmd_id=uptime, elapsed_ms=452
```

### 10.2 日志级别控制

```bash
export OPS_AGENT_LOG_LEVEL=DEBUG  # 详细日志
export OPS_AGENT_LOG_LEVEL=INFO   # 默认
```

## 11. 风险与后续

- 模型输出偏差：通过 Schema 校验 + retry 降低
- 命令覆盖不全：扩展 cmd_id 白名单
- 复杂场景（多 JVM）：增加 pid 选择逻辑
- LangGraph 依赖：提供降级模式
