# Sub-Agent / Multi-Agent Design For sre-agent (Accuracy First)

本文面向 `sre-agent` 的三个核心场景：告警分诊、故障处理、发布守护。目标不是“更快”，而是“更准”：减少误判、减少无证据结论、减少不必要/不安全动作。

与 `docs/multi-stage.md` 的“多轮闭环（Planner -> 执行采证 -> 追加证据 -> 再规划）”相兼容：子 agent 主要承担“证据收集”和“独立验证/挑错”，主 agent 仍做最终决策与输出。

## 1. 结论：是否有必要

在你给定的现状（Top 场景：告警分诊/故障处理/发布守护；主要痛点：准确性）下：

- 建议引入子 agent（Sub-agent）：是，优先级高。
- 建议引入多 agent 并行：有价值，但只在“读多源信息 + 独立验证”上并行；不要并行执行会互相影响的变更动作。

核心思路：把“容易跑偏的推理”拆成可审计的工件（证据、反证、假设树、停止理由），用独立验证机制提升一致性。

## 2. 设计目标（Accuracy KPIs）

- 证据绑定：任何关键判断必须引用 `audit_ref`/evidence_ref（从 EvidenceStore 可追溯）。
- 反证机制：每个候选根因至少给出 1 条反证检查（或声明为何无法获取）。
- 冲突显式化：当证据矛盾时，不“投票”，而是输出冲突点与补证据计划。
- 早停可解释：停止必须给出 deterministic stop_reason（预算/无进展/置信度+覆盖达标/路由池耗尽等）。
- 只读合规：任何 action 必须通过 policy gate（READ_ONLY/LOW）；子 agent 不直接执行。

## 3. 角色划分（推荐最小集合）

以“主 agent + 2 个子 agent”为最小可用形态：

1) Orchestrator / Primary (主 agent)
- 负责编排 multi-stage loop、预算控制、冲突消解、最终 report。
- 仅接受子 agent 的结构化产物；不接受无来源断言。

2) Evidence Collector (子 agent)
- 只做“需要哪些证据、用哪些 cmd_id 去采、每条证据回答什么问题”。
- 输出计划时必须声明：purpose / expected_signal / failure_mode。

3) Verifier / Critic (子 agent)
- 只做“挑错”：找反例、找缺失证据、检查逻辑跳跃、检查结论是否可由证据推出。
- 特别关注发布守护：把“相关变更/发布窗口/错误率/回滚信号”作为优先反证。

可选增强（后续再加）：

4) Release Guard Specialist (子 agent)
- 专门对接发布事件：版本变更、配置变更、灰度比例、依赖升级、feature flag。

## 4. 子 agent 输出契约（必须结构化）

为避免“说得像但不可用”，子 agent 输出必须是 JSON（主 agent 侧做 schema validate）。建议两个 schema：

### 4.1 EvidenceCollectorOutput

```json
{
  "task": "alert_triage|incident_response|release_guard",
  "hypotheses": [
    {
      "category": "CPU|IO|MEM|GC|NET|EXTERNAL_DEP|RELEASE|UNKNOWN",
      "why": "...",
      "confidence": 0.0,
      "required_evidence": [
        {"cmd_id": "...", "purpose": "...", "expected_signal": "..."}
      ],
      "counter_checks": [
        {"cmd_id": "...", "purpose": "...", "expected_signal": "..."}
      ]
    }
  ],
  "next_cmds": [
    {"cmd_id": "...", "purpose": "...", "expected_signal": "...", "timeout_sec": 30, "priority": 1}
  ],
  "missing_info": ["..."],
  "notes": "..."
}
```

约束：
- `cmd_id` 必须来自本轮 `allowed_cmd_pool`（Routing-Restricted），否则主 agent 直接丢弃该条。
- 不允许要求“写操作/重启/kill/改配置”等动作；只允许读证据。

### 4.2 VerifierOutput

```json
{
  "task": "alert_triage|incident_response|release_guard",
  "claims_to_verify": [
    {
      "claim": "...",
      "status": "SUPPORTED|WEAK|CONTRADICTED|UNKNOWN",
      "evidence_refs": ["audit_ref:..."],
      "counter_evidence_refs": ["audit_ref:..."],
      "what_to_check_next": [
        {"cmd_id": "...", "purpose": "...", "expected_signal": "...", "priority": 1}
      ]
    }
  ],
  "logical_gaps": ["..."],
  "risk_flags": ["..."],
  "recommend_stop": false,
  "stop_reason": "..."
}
```

约束：
- `evidence_refs` 必须可落到 EvidenceStore/audit。
- 允许输出 `recommend_stop=true`，但主 agent 仍按 deterministic stop rules 决策。

## 5. 编排模式（与 multi-stage 的结合点）

推荐把“子 agent”嵌入 `docs/multi-stage.md` 的每一轮：

每轮 Round k：

1) 主 agent 汇总本轮输入（meta、signals、snapshots、已执行 cmd、allowed_cmd_pool、budget）。
2) 并行调用（只读推理并行，不执行）：
   - Evidence Collector：产出 next_cmds（补证据计划）。
   - Verifier/Critic：产出需要验证的 claims + 反证检查。
3) 主 agent 合并与裁剪：
   - 去重 cmd_id；
   - 按 priority + coverage 选择 `max_cmds_per_round`；
   - 对冲突点优先补证据而不是下结论。
4) 系统端执行（现有安全链路）：policy gate -> exec -> redaction -> audit -> EvidenceStore。
5) 产出本轮 trace（记录子 agent 建议、被过滤的原因、实际执行 cmd）。

为什么这能提高“准”：
- Evidence Collector 防止“凭感觉下结论”，强迫先把证据缺口补齐。
- Verifier 强迫“反证”和“逻辑闭合”，降低幻觉与过拟合。

## 6. 三个场景的推荐工作流

### 6.1 告警分诊（Alert Triage）

目标：快速把告警分到可行动类别，并把不确定性显式化。

- 输入：告警 payload（指标、阈值、触发时刻、受影响对象）、最近变更窗口。
- 首轮偏好：用确定性规则（signals）先分类（CPU/IO/MEM/GC/NET/RELEASE/UNKNOWN）。
- 子 agent 重点：
  - Evidence Collector：列出最少的 2~4 条“能区分路径”的 cmd_id。
  - Verifier：检查“是否可能是发布/依赖/外部故障”，要求至少 1 个反证检查。
- 输出：
  - 分诊结论（含置信度）+ 下一步采证/升级建议（只读）。

### 6.2 故障处理（Incident Response）

目标：在预算内收敛到可执行的缓解建议（仍只读建议），并确保关键结论可被证据支撑。

- 子 agent 重点：
  - Evidence Collector：围绕“止血所需信号”补证据（例如错误率/饱和/排队/依赖超时）。
  - Verifier：对每个候选根因给反证；对“单点解释”提出替代假设（至少 2 个）。
- 冲突处理：
  - 若 CPU 高但 iowait 也高：Verifier 触发“同时存在”或“采样偏差”提示，要求补充更直接证据（例如 per-thread/per-disk 维度）。

### 6.3 发布守护（Release Guard）

目标：把“是否与发布相关”作为一等公民，不被系统层噪声淹没。

- 建议新增/强化 signals：
  - `release_window_overlap`: 是否在发布窗口内
  - `change_detected`: 版本/配置/flag 是否变
  - `error_rate_shift`: 错误率是否阶跃
  - `latency_shift`: P95/P99 是否阶跃
- 子 agent 重点：
  - Evidence Collector：优先验证“变更 -> 指标阶跃 -> 回滚信号/灰度对比”。
  - Verifier：要求对“非发布原因”给反证（例如主机资源/依赖/网络）。

注意：如果当前工具链尚未接入发布系统数据源，可以先用“手动输入变更摘要”作为 meta 字段，仍能提升推理准确性。

## 7. 并行策略（只用于提高准确性）

允许并行的部分：
- 多源信息归纳：不同数据源的摘要（监控/日志/审计/变更记录）相互独立时。
- 独立验证：Verifier 与 Evidence Collector 同时工作。

不建议并行的部分：
- 命令执行本身（除非已证明不会产生负载风险且工具侧有并发控制）；
- 任何可能改变远端状态的动作（本项目默认已禁用）。

## 8. 主 agent 的合并与裁剪规则（避免“多 agent 多噪声”）

主 agent 合并子 agent 输出时使用硬规则：

- allowlist：`cmd_id` 不在 `allowed_cmd_pool` 直接丢弃。
- safety：命令参数与 policy 校验失败的建议直接丢弃并记录原因。
- evidence-first：当 Verifier 标记关键 claim 为 WEAK/UNKNOWN 时，优先选择其 `what_to_check_next`。
- progress：优先选择“能区分两个假设的证据”，而不是“只增强同一假设的证据”。
- budget：强制 `max_cmds_per_round`、`max_total_cmds`、`time_budget_sec`。

## 9. 评估方法（专门面向“准”）

建议把准确性拆成可量化指标：

- Evidence Coverage Rate：report 中关键结论（root_cause、top 3 claims）是否都有 evidence_ref。
- Contradiction Rate：Verifier 标记 CONTRADICTED 的 claim 占比；或冲突未在报告中显式披露的比例。
- Reopen Rate（事后指标）：人工复盘/二次告警证明根因不一致的比例。
- No-Progress Stop：连续 K 轮无增量信号触发停止的占比（过高说明 routing/commands 覆盖不足）。

落地方式：复用 `src/evaluation/` 的回放框架，对比：
- 单 agent（无子 agent） vs 主+子 agent
- 关注：schema 通过率不变的前提下，Evidence Coverage 和 Contradiction 是否改善。

## 10. 渐进式落地计划（最小改造）

Phase 1（只加 Verifier，不改执行链）：
- 在 `report` 生成前插入 Verifier pass：对报告中的 claims 做一致性校验，不通过则降级为 UNKNOWN 或补充缺失证据说明。

Phase 2（加 Evidence Collector，驱动补证据）：
- 在 multi-stage loop 中并行调用 Evidence Collector 与 Verifier，驱动下一轮采证计划。

Phase 3（发布守护专精）：
- 引入 release/change signals；必要时新增只读数据源适配器（不影响现有 SSH 采证）。

## 11. 与现有文档的关系

- 多轮闭环与安全链路：见 `docs/multi-stage.md`。
- 整体架构与审计/脱敏：见 `docs/TECH-DESIGN.md`。
- 目标与约束：见 `docs/PRD.md`。
