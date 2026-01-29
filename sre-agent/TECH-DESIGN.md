# 生产只读运维智能体 技术设计

## 1. 总体架构

### 1.1 两阶段流程

1. Phase A：Agent 采证
   - Claude Agent SDK
   - 调用 MCP 工具 `sre_diag`
   - 输出 evidence_pack.json
2. Phase B：结构化报告
   - Claude API `output_format` + JSON Schema
   - 输入 evidence_pack
   - 输出 diagnosis_report.json

## 2. 模块与职责

- [ops-agent/diag_load_agent.py](ops-agent/diag_load_agent.py)
  - Agent 主入口
  - 证据收集与 evidence_schema 校验
  - 可选生成最终报告

- [ops-agent/mcp_server_sre.py](ops-agent/mcp_server_sre.py)
  - 只读命令白名单
  - SSH 直连执行
  - 输出脱敏与审计

- [ops-agent/report_generator.py](ops-agent/report_generator.py)
  - Phase B 结构化报告生成

- [ops-agent/redaction.py](ops-agent/redaction.py)
  - 脱敏规则与替换计数

- [ops-agent/audit.py](ops-agent/audit.py)
  - 审计日志写入

## 3. 数据结构

### 3.1 evidence_pack.json

Schema 见 [ops-agent/evidence_schema.json](ops-agent/evidence_schema.json)。核心字段：

- meta: host、service、timestamp
- snapshots: cmd_id、signal、summary、audit_ref
- hypothesis: category、confidence、why、evidence_refs
- next_checks: cmd_id、purpose

### 3.2 diagnosis_report.json

Schema 见 [ops-agent/report_schema.json](ops-agent/report_schema.json)。核心字段：

- meta
- root_cause
- evidence_table
- next_actions
- audit
- redaction

## 4. 只读命令白名单

在 MCP Server 内通过 cmd_id 控制：

- 系统负载：uptime、loadavg
- CPU/内存：top、ps_cpu、ps_mem、free、vmstat
- IO：iostat、df
- Java：jps、jstat、jstack、jcmd_threads
- 日志：journalctl

## 5. 安全与审计

### 5.1 安全策略

- cmd_id 白名单
- 参数必填校验（service/pid）
- 输出截断与超时限制

### 5.2 审计

- 记录 id、cmd_id、start_time、elapsed_ms
- 记录 redacted output hash
- 审计日志可通过 OPS_AGENT_AUDIT_LOG 配置

## 6. 脱敏策略

默认规则见 [ops-agent/redaction.py](ops-agent/redaction.py)：

- IP、邮箱、Token、路径、用户名
- 输出仅保存脱敏后内容

## 7. 运行方式

### 7.1 Phase A 采证

python diag_load_agent.py --host 10.0.0.12 --service myapp

### 7.2 Phase B 最终报告

ANTHROPIC_API_KEY=xxx python diag_load_agent.py --host 10.0.0.12 --service myapp --final-report

## 8. 配置

- ANTHROPIC_API_KEY：Phase B 生成报告
- OPS_AGENT_AUDIT_LOG：审计日志路径

## 9. 风险与后续

- 模型输出偏差：通过 Schema 校验 + retry 降低
- 命令覆盖不全：扩展 cmd_id 白名单
- 复杂场景（多 JVM）：增加 pid 选择逻辑
