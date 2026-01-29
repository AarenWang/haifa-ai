# 生产只读运维智能体 PRD

## 1. 背景与目标

运维排障需要在生产环境中快速定位 Java 服务 load 高的根因，同时严格避免破坏性操作。项目目标是在仅 SSH 直连场景下，构建一个只读诊断 Agent，实现证据驱动的诊断输出与结构化报告。

## 2. 范围

### 2.1 In Scope

- 生产主机 SSH 直连的只读诊断能力
- 诊断路径覆盖：CPU、IO wait、内存、GC、线程竞争、外部依赖
- 证据收集 → 假设 → 验证建议 的闭环
- 结构化 JSON 输出（evidence_pack 与最终 diagnosis_report）
- 审计日志与敏感信息脱敏

### 2.2 Out of Scope

- 任何写操作、重启、kill、改配置、改文件
- 对接监控平台/工单系统/告警系统
- 跳板机与多级链路

## 3. 用户画像与使用场景

- 生产 SRE/运维工程师
- 场景：Java 服务 load 高或性能异常，需要只读快速定位

## 4. 需求与约束

### 4.1 功能需求

1. 只读命令白名单执行（通过 MCP 工具封装）
2. 证据驱动诊断：所有结论必须可追溯到命令输出
3. 两阶段产物：
   - Phase A：evidence_pack.json
   - Phase B：diagnosis_report.json
4. 审计日志：记录命令、执行时间、耗时、输出哈希
5. 脱敏：对敏感字段进行替换并记录规则

### 4.2 非功能需求

- 安全性：默认拒绝非白名单命令
- 可审计：完整可追溯（时间戳、哈希）
- 可靠性：Schema 校验与错误回退
- 可扩展：命令白名单与工具可增量扩展

## 5. 约束与策略

- 仅 SSH 直连
- 只读诊断
- JSON Schema 严格输出

## 6. 交付物

- PRD 与技术设计文档
- 代码与配置
- Schema 文件

## 7. 验收标准

- 所有诊断命令均来自白名单
- 所有输出通过 JSON Schema 校验
- 审计日志包含 cmd_id、开始时间、耗时、输出哈希
- 脱敏规则生效且记录替换数量

## 8. 相关文档

- 生产只读方案与技术设计见 [ops-agent/TECH-DESIGN.md](ops-agent/TECH-DESIGN.md)
- 结构化 Schema 见 [ops-agent/report_schema.json](ops-agent/report_schema.json) 与 [ops-agent/evidence_schema.json](ops-agent/evidence_schema.json)
