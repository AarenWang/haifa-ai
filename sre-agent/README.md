# SRE Agent - 生产只读诊断智能体

基于 Claude Agent SDK 的 Linux/Java 服务只读诊断工具，自动收集证据并给出根因假设。

## 功能特性

- **只读诊断**：通过白名单命令执行，不会 kill/restart、不会修改配置
- **MCP 工具集成**：使用 Model Context Protocol 封装诊断命令
- **结构化输出**：生成符合 JSON Schema 的证据包和诊断报告
- **审计日志**：记录所有命令执行时间、耗时、输出哈希
- **敏感信息脱敏**：自动脱敏并记录替换规则

## 快速开始

### 1. 前置要求

- Python 3.10+
- Claude Code（需要登录）
- 目标主机 SSH 访问权限

### 2. 安装依赖

```bash
cd sre-agent
pip install -r requirements.txt
```

### 3. 配置环境变量（可选）

```bash
# 审计日志路径
export OPS_AGENT_AUDIT_LOG="./audit.log"

# Anthropic API（仅用于生成最终报告 Phase B）
export ANTHROPIC_AUTH_TOKEN="your-auth-token"
export ANTHROPIC_BASE_URL="https://your-anthropic-endpoint"
```

说明：

- Phase A（采证）通过 Claude Code CLI 通信，不使用 `ANTHROPIC_AUTH_TOKEN` 与 `ANTHROPIC_BASE_URL`
- Phase B（生成最终报告）才会使用上述 Anthropic 环境变量

### 4. 运行诊断

```bash
# 基本诊断（输出 evidence_pack）
python diag_load_agent.py --host 192.168.1.100 --service myapp

# 指定时间窗口
python diag_load_agent.py --host 192.168.1.100 --service myapp --window-minutes 60

# 生成最终诊断报告
python diag_load_agent.py --host 192.168.1.100 --service myapp --final-report
```

### 5. 测试示例

项目包含两个 Java 测试应用，可用于模拟故障场景：

#### CPU 高负载模拟

```bash
cd example/java-netty-cpu-hotspot
mvn -q -DskipTests package
java -Xms256m -Xmx256m -jar target/java-netty-cpu-hotspot-0.1.0.jar --port 8080

# 触发 CPU 高负载
curl -s -XPOST "http://127.0.0.1:8080/burn/start?threads=8&intensity=100"

# 停止负载
curl -s -XPOST http://127.0.0.1:8080/burn/stop
```

#### IO Wait 高负载模拟

```bash
cd example/java-netty-io-wait-load
mvn -q -DskipTests package
java -Xms256m -Xmx256m -jar target/java-netty-io-wait-load-0.1.0.jar --port 8081
```

## 可用诊断命令

| cmd_id | 命令 | 说明 |
|--------|------|------|
| `uptime` | `uptime` | 系统运行时间和负载 |
| `loadavg` | `cat /proc/loadavg` | 负载平均值 |
| `top` | `top -b -n 1 \| head -n 40` | 进程快照 |
| `ps_cpu` | `ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%cpu` | 按 CPU 排序进程 |
| `ps_mem` | `ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%mem` | 按内存排序进程 |
| `vmstat` | `vmstat 1 5` | 虚拟内存统计 |
| `iostat` | `iostat -x 1 3` | IO 统计 |
| `free` | `free -m` | 内存使用情况 |
| `df` | `df -h` | 磁盘使用情况 |
| `jps` | `jps -l` | Java 进程列表 |
| `jstat` | `jstat -gcutil {pid} 1 5` | GC 统计 |
| `jstack` | `jstack -l {pid}` | Java 线程栈 |
| `jcmd_threads` | `jcmd {pid} Thread.print` | 线程信息 |
| `journalctl` | `journalctl -u {service}` | 服务日志 |

## 项目结构

```
sre-agent/
├── diag_load_agent.py      # Agent 主入口
├── mcp_server_sre.py        # MCP 服务器（诊断工具）
├── report_generator.py      # 报告生成器
├── redaction.py             # 敏感信息脱敏
├── audit.py                 # 审计日志
├── evidence_schema.json     # 证据包 Schema
├── report_schema.json       # 报告 Schema
├── requirements.txt         # Python 依赖
├── PRD.md                   # 产品需求文档
├── TECH-DESIGN.md           # 技术设计文档
└── example/                 # 测试应用
    ├── java-netty-cpu-hotspot/     # CPU 高负载模拟
    └── java-netty-io-wait-load/    # IO Wait 高负载模拟
```

## 输出格式

### evidence_pack（默认输出）

```json
{
  "meta": {
    "host": "192.168.1.100",
    "service": "myapp",
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "snapshots": [
    {
      "cmd_id": "uptime",
      "signal": "load average: 8.52, 7.89, 7.12",
      "summary": "高负载",
      "audit_ref": "uptime-1705319400"
    }
  ],
  "hypothesis": [
    {
      "category": "cpu_saturation",
      "confidence": "high",
      "why": "Load average 远超 CPU 核心数",
      "evidence_refs": ["uptime-1705319400"]
    }
  ],
  "next_checks": [
    {
      "cmd_id": "jstack",
      "purpose": "确认线程状态"
    }
  ]
}
```

### diagnosis_report（--final-report）

使用 Anthropic API 生成更详细的可读报告。

## 安全说明

- 所有命令必须来自白名单，默认拒绝其他命令
- 不支持任何写操作、重启、kill 等破坏性操作
- 所有输出自动脱敏（IP、密码等敏感信息）
- 完整审计日志可追溯

## 相关文档

- [PRD.md](PRD.md) - 产品需求文档
- [TECH-DESIGN.md](TECH-DESIGN.md) - 技术设计文档
