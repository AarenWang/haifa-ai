# 通用运维 SRE Agent 规划设计

> 目标：从“单场景高负载诊断脚本”升级为“通用、可治理、可审计、可扩展”的生产运维诊断 Agent。

## 一、核心目标与原则

- **只读安全**：所有执行动作必须为 READ_ONLY，任何非只读动作必须被硬性拒绝。
- **证据驱动**：结论必须绑定证据；证据必须包含审计记录与脱敏信息。
- **可扩展**：命令、探针、解析器可按场景/平台增量扩展。
- **一致输出**：统一 Schema，强制校验，缺失字段显式标注。
- **可回放**：支持离线回放与回归测试，便于评估诊断效果。

## 二、总体架构

### 2.1 分层架构

- **控制面 (Orchestrator)**
  - 任务编排：state machine / graph
  - 诊断阶段：环境探测 → 基线采证 → 假设生成 → 目标采证 → 结论汇总

- **执行面 (Execution Engine)**
  - 命令/探针注册中心 (Registry)
  - 依赖与风险标注（READ_ONLY/LOW）
  - 运行前安全校验（参数白名单、格式校验）

- **证据面 (Evidence Store)**
  - raw / redacted / parsed 三层证据
  - 每条证据包含 audit_ref 与 redaction 统计

- **推理面 (Reasoning Layer)**
  - 规则引擎负责分类与异常门控
  - LLM 负责解释与归因、生成可读结论

- **输出面 (Reporting Layer)**
  - 统一 schema 输出
  - 结构化报告 + 证据索引 + 审计摘要

- **适配面 (Adapters)**
  - LLM Vendor / Agent SDK 可插拔
  - 统一接口与配置驱动的切换机制

### 2.2 统一数据模型

**EvidenceEvent**
- `cmd_id`: 命令 ID
- `raw_ref`: 原始输出存储引用
- `redacted_ref`: 脱敏后输出引用
- `signals`: 结构化指标
- `timing`: 执行时延、超时标记
- `audit_ref`: 审计记录引用

**Signal**
- 标准化指标：loadavg, %iowait, %cpu, runqueue, gc_pause 等

**Hypothesis**
- `category`: CPU/IO/MEM/GC/NET/EXTERNAL_DEP/UNKNOWN
- `confidence`: 0~1
- `evidence_refs`: 证据引用
- `counter_evidence`: 反证

**Report**
- `root_cause`, `evidence_table`, `next_actions`, `audit`, `redaction`
- `next_actions` 仅允许 READ_ONLY/LOW 风险动作

## 三、诊断流程 (Deterministic First)

1. **环境探测**
   - OS、CPU 核数、容器/裸机、JVM 是否存在

2. **基线采证**
   - uptime/loadavg/top/ps/vmstat/iostat/free/dmesg/journalctl

3. **规则分类**
   - CPU / IO / MEM / GC / NET / EXTERNAL_DEP

4. **目标采证**
   - 根据分类路由精细命令集
   - 仅执行必需命令，避免盲目全量采集

5. **LLM 解释与结论**
   - 只负责解释和生成结论
   - 输出前走 policy filter

6. **Schema 校验与输出**
   - 校验失败立即 fallback 或标注 `unknown`

## 四、安全与治理设计

- **参数校验**
  - `pid` 必须为数字
  - `service` 必须符合 `^[A-Za-z0-9_.@-]+$`

- **动作过滤器**
  - 非 READ_ONLY 动作硬拒绝
  - LLM 输出的 action 必须通过 policy filter

- **审计闭环**
  - 命令、时间、耗时、输出哈希、脱敏规则、替换数量

- **最小权限**
  - 强制只读 allowlist
  - 禁止用户自定义命令

## 五、扩展性设计

- **场景扩展**
  - JVM、高 IO、内存泄漏、线程死锁、外部依赖超时

- **平台扩展**
  - Linux 裸机、K8s、容器

- **插件化**
  - 命令/探针注册中心
  - 解析器与信号生成器

## 六、评估与验证

- **用例库**
  - CPU 忙循环、IO wait、内存泄漏、GC 频繁、线程死锁、外部依赖异常

- **指标**
  - 根因定位准确率
  - 平均采证条数
  - 误报率
  - 只读合规率

- **回放机制**
  - evidence pack 可离线回放
  - 支持回归测试

---

# 七、代码目录结构（建议）

> 目标：实现“策略/采证/推理/执行/输出/适配器”解耦，便于替换底层 Agent SDK 与 LLM Vendor。

```
sre-agent/
├── archived/                 # 现有 Python 代码归档
├── docs/                     # 设计文档与规范
│   ├── PRD.md
│   ├── TECH-DESIGN.md
│   └── optimize-sre-agent.md
├── schemas/                  # 统一 Schema
│   ├── evidence_schema.json
│   └── report_schema.json
├── configs/                  # 策略与注册配置
│   ├── policy.yaml
│   ├── commands.yaml
│   └── routing.yaml
├── src/
│   ├── cli/                  # CLI 入口
│   │   └── sre_agent_cli.py
│   ├── orchestrator/         # 状态机/图编排
│   │   ├── graph.py
│   │   └── stages.py
│   ├── adapters/             # 适配层（可插拔）
│   │   ├── llm/
│   │   │   ├── base.py        # LLM 接口
│   │   │   ├── anthropic.py
│   │   │   ├── openai.py
│   │   │   └── qwen.py
│   │   ├── agent_sdk/
│   │   │   ├── base.py        # Agent SDK 接口
│   │   │   ├── claude_sdk.py
│   │   │   └── langgraph.py
│   │   └── exec/
│   │       ├── ssh.py
│   │       ├── mcp.py
│   │       └── local.py
│   ├── registry/             # 命令/解析器/信号注册
│   │   ├── commands.py
│   │   ├── parsers.py
│   │   └── signals.py
│   ├── storage/              # 证据/审计/脱敏
│   │   ├── evidence_store.py
│   │   ├── audit_store.py
│   │   └── redaction.py
│   ├── policy/               # 只读策略与过滤
│   │   ├── action_filter.py
│   │   └── validators.py
│   └── reporting/            # 输出与校验
│       ├── schema_validate.py
│       └── report_builder.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── scripts/
└── report/
```

## SDK / LLM Vendor 灵活切换要求

- **统一接口**：定义 `LLMClient` 与 `AgentSDKClient` 抽象接口，屏蔽厂商差异。
- **配置驱动**：通过配置文件或环境变量指定 provider（如 `LLM_VENDOR=qwen|anthropic|openai`）。
- **运行时可切换**：允许按任务或场景在运行时选择 vendor（如故障回退）。
- **能力协商**：适配层暴露能力集（tool calling、json schema、streaming）。
- **统一错误模型**：对外统一错误码与重试策略。

---

# 迭代计划 (Plan)

## Phase 0 — 现状修复 (1-2 周)
- 修复命令注入风险（`pid/service` 参数校验）
- 强制只读策略（报告/输出过滤非只读建议）
- 统一 Schema 与 prompt 的一致性
- 采集层补齐脱敏与审计链路

## Phase 1 — 通用架构落地 (2-4 周)
- 引入统一 Orchestrator（state machine / graph）
- 建立 Evidence Store（raw/redacted/parsed）
- 命令注册中心 + 风险元数据
- 适配层落地（LLM Vendor / Agent SDK 可切换）

## Phase 2 — 规则引擎与分类 (2-3 周)
- 规则引擎实现基础分类
- 支持 CPU / IO / MEM / GC / NET 等主路径
- 诊断路径按分类动态路由

## Phase 3 — 扩展与评估 (4-6 周)
- 新场景扩展（外部依赖、k8s、容器）
- 建立回放与评估框架
- 输出稳定性与准确性指标建设

## Phase 4 — 产品化 (持续迭代)
- 输出与监控/告警平台对接
- 支持多环境、多平台适配
- 安全审计、权限治理标准化

---

# 里程碑验收标准 (Milestones)

## M0 — 现状修复完成
- 命令注入防护通过：`pid/service` 参数格式校验 + 单元测试覆盖关键边界
- 只读策略生效：任何非 READ_ONLY 建议被过滤并记录原因
- Schema 对齐：prompt/模型输出/校验一致，通过率 >= 95%
- 采集输出包含审计与脱敏统计，审计记录可追溯到 evidence_ref

## M1 — 通用架构可运行
- Orchestrator 支持至少 3 个阶段（探测/基线/目标采证）
- Evidence Store 支持 raw/redacted/parsed 三层存储
- Command Registry 可配置风险等级、依赖、适用平台
- LLM/Agent SDK 通过配置切换且具备回退策略

## M2 — 规则分类可用
- CPU/IO/MEM/GC/NET 五类分类可用
- 分类准确率 >= 80%（基于用例库）
- 分类结果驱动动态路由并可回放

## M3 — 扩展与评估体系
- 用例库 >= 12 个，覆盖至少 6 类问题
- 离线回放 + 回归测试自动化
- 输出稳定性：schema 通过率 >= 98%

## M4 — 产品化接入
- 支持至少 1 个告警/工单入口
- 具备多环境配置与权限治理规范
- 通过安全审计与合规检查

---

# 任务清单 (Task Breakdown)

## Phase 0 — 现状修复
- 增加 `pid/service` 参数校验器与测试
- 引入 action policy filter（READ_ONLY 硬约束）
- 统一 evidence/report schema 与 prompt 内容
- v2/v3 采集链路补齐脱敏与审计哈希
- 修复命令白名单缺失（如 `lsof_pid`）与无效命令路径

## Phase 1 — 通用架构落地
- 抽象 Orchestrator 接口（State/Node/Edge）
- 实现 Evidence Store 及引用机制
- 引入 Command Registry + 风险元数据
- 增加统一执行器（SSH/MCP 可切换）
- 实现 LLM/Agent SDK 适配层与配置切换

## Phase 2 — 规则引擎与分类
- 定义 Rule DSL 或规则配置格式
- 构建分类器输出标准信号（signals）
- 实现动态路由与最小采证策略
- 加入反证机制（counter_evidence）

## Phase 3 — 扩展与评估
- 扩展 K8s/容器场景探针
- 建立离线回放与评估脚本
- 增加稳定性监控（schema/timeout/空证据）
- 形成回归基线与评分报告

## Phase 4 — 产品化
- 对接告警/工单平台输出
- 多租户与权限隔离策略
- 运营与审计报表（命中率/误报率/执行成本）
