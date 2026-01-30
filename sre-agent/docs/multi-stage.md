# Multi-Stage / Multi-Round Diagnose (Routing-Restricted)

本文描述 `sre-agent` 的多轮诊断闭环方案：在“只读、安全、可审计”的前提下，将当前的“两段式（采证 -> 单次 LLM 报告）”升级为“多轮：LLM 规划 -> 执行采证 -> 更新证据 -> 再规划 -> 最终报告”。

默认约束（你已选择）：LLM 只能从 `configs/routing.yaml` 对应类别的候选 `cmd_id` 中选择下一步命令（Routing-Restricted）。

## 1. 现状与问题

当前可运行闭环：
- `python -m src.cli.sre_agent_cli run ...`：确定性采证（baseline -> rules classify -> routing targeted），输出 `evidence_pack.json`
- `python -m src.cli.sre_agent_cli report ...`：将证据一次性喂给 LLM，生成结构化 `diagnosis_report.json`

现状限制：
- `report` 是“单轮生成”：LLM 不会在诊断过程中追加采证，也不会根据缺口迭代。
- 复杂问题（Java GC/死锁/线程饥饿/FD 泄漏/外部依赖等）往往需要“先看现象 -> 再补关键证据 -> 再收敛结论”的多轮流程。

## 2. 目标形态

将诊断改为闭环多轮：
1) baseline（确定性）
2) rules 分类得到 `primary_category`
3) 多轮循环（Round 1..N）：
   - LLM 输出本轮“采证计划”（plan JSON）
   - 系统校验/过滤/执行（只读 + allowlist + 审计 + 脱敏）
   - 将新增证据摘要再喂给 LLM
4) 满足停止条件后，生成最终 `diagnosis_report.json`

核心产物：
- `evidence_pack`：持续追加（raw/redacted/parsed/index）
- `diagnosis_report`：最终结构化报告（仍强制 policy filter）
- `diagnosis_trace`：多轮链路记录（每轮的 plan、执行的 cmd_id、审计引用、停止原因），用于回放/调试/评估

## 3. 推荐架构：LLM 只做 Planner（不直接 tool-call）

为保证安全与可控，推荐将 LLM 的职责限定为“生成下一步计划（plan）”，不让 LLM 直接调用 SSH/命令执行。

系统端负责：
- command allowlist（Routing-Restricted）
- policy gate（READ_ONLY/deny keywords/platform/pid/service 校验）
- 执行（SSH/local）+ 超时控制
- 脱敏（redaction）+ 审计（audit log + output hash）
- 证据存储（EvidenceStore：raw/redacted/parsed/index）

优点：
- 不依赖 tool-calling/function-calling 能力
- 审计链完整，执行动作完全可控
- 便于做预算/限流/早停

## 4. 命令空间约束（Routing-Restricted）

LLM 每轮只能从当前类别的 routing 候选池选择 `cmd_id`：
- `configs/routing.yaml`:
  - `routes[primary_category] = [cmd_id...]`

推荐同时做两条系统端约束：
- 去重：同一个 `cmd_id` 默认只执行一次（除非明确允许重复采样）
- 预算：限制 `max_rounds`、`max_cmds_per_round`、`max_total_cmds`、`time_budget_sec`

备注：如果 routing 候选池覆盖不足，优先通过扩充 `configs/routing.yaml` 与 `configs/commands.yaml` 来解决（而不是放开 LLM 的命令选择范围）。

## 5. 多轮 Plan 输出：新增 plan schema

需要新增 `schemas/plan_schema.json`，要求 LLM 严格返回 JSON（无 markdown/无解释）。建议字段：

- `decision`: `CONTINUE | STOP`
- `current_hypothesis`:
  - `category`: 与 `schemas/report_schema.json` 的根因枚举一致
  - `confidence`: 0~1
  - `why`: 为什么当前倾向该类别
- `next_cmds`: array（当 `decision=CONTINUE`）
  - `cmd_id`: string（必须来自 allowed cmd pool）
  - `purpose`: string（采这个证据要回答什么问题）
  - `expected_signal`: string（希望观察到什么现象/信号）
  - `timeout_sec`: int（建议 10~60）
  - `priority`: int（1~5）
- `missing_info`: array[string]（还缺什么关键证据/信号）
- `stop_reason`: string（当 `decision=STOP`）

系统端必须对 plan 做：
- JSON Schema validate
- routing allowlist 校验（cmd_id 必须在 pool 内）
- policy 校验（READ_ONLY/deny keywords/platform/pid/service）
- 过滤后如果 `next_cmds` 为空：直接 STOP（并记录原因）

## 6. 证据输入给 LLM：压缩 + 脱敏 + 可引用

原则：LLM 只看“脱敏后的摘要/结构化信号”，不直接吃 raw 全量输出。

每轮建议输入：
- `meta`: host/service/env/platform/window/session_id
- 已执行命令清单：`cmd_id -> audit_ref -> elapsed_ms`
- `snapshots`：已有 `cmd_id/signal/summary/audit_ref`
- `signals`：结构化信号口径（数值/布尔/枚举）
- 当前分类：rule engine 的 `hypothesis`（含 counter-evidence）
- `allowed_cmd_pool`: 本轮可选 cmd_id（routing 候选集减去已执行/被禁用）
- budget：`max_rounds/max_cmds_per_round/max_total_cmds/time_budget_sec`

输出引用：
- LLM 在 plan/report 中引用证据时，使用 `audit_ref` 或 `cmd_id` + `audit_ref`
- 最终 `report.evidence_table[*].evidence_ref` 需要能落到 EvidenceStore 的 index/audit 中

## 7. 停止条件（deterministic）

满足任一条件 STOP：
- LLM plan: `decision=STOP`
- 达到预算：`max_rounds` / `max_total_cmds` / `time_budget_sec`
- routing pool 耗尽或全部被 policy 拦截
- 连续 K 轮无有效增量信号（no_progress）
- 置信度达到阈值（例如 `confidence >= 0.85`）且证据覆盖达到最低要求（按类别定义关键 cmd_id）

STOP 后执行 Final Report：
- 调用 `build_report(...)` 生成 `schemas/report_schema.json` 对齐的输出
- report 的 `next_actions` 继续走 `policy.action_filter`（READ_ONLY/LOW 硬约束）

## 8. 产物与存储（trace 可回放）

基于现有 EvidenceStore：`report/<session_id>/{raw,redacted,parsed,index}/...`，增加多轮 trace：

- `index/llm_round_001.json`
- `index/llm_round_002.json`
- ...

每轮 trace 建议包含：
- round 序号、allowed cmd pool
- LLM 输入摘要（或 hash）
- plan JSON（原文 + validate 结果）
- 被过滤/拦截的 cmd_id 列表及原因
- 实际执行 cmd_id -> audit_ref -> elapsed_ms
- 新增 signals/snapshots 的 delta
- stop_reason（若停止）

最终：
- `index/evidence_pack.json`
- `index/diagnosis_report.json`
- `index/diagnosis_trace.json`（聚合所有轮次）

## 9. CLI 建议：新增 `diagnose` 子命令

为保持语义清晰，建议新增：
- `python -m src.cli.sre_agent_cli diagnose ...`

语义：
- `run`：只做确定性采证（可回放/可回归）
- `diagnose`：采证 + 多轮闭环 + 最终报告（端到端体验）

建议参数（含默认值）：
- 继承 `run`：`--host --service --pid --window-minutes --exec-mode --platform --config-dir`
- 多轮控制：
  - `--max-rounds 3`
  - `--max-cmds-per-round 3`
  - `--max-total-cmds 12`
  - `--time-budget-sec 120`
  - `--confidence-threshold 0.85`
  - `--output-evidence report/evidence_pack.json`
  - `--output-report report/report.json`

## 10. 改造范围（最小可行版本）

新增：
- `schemas/plan_schema.json`
- planner prompt builder（建议放 `src/orchestrator/` 下）
- 多轮诊断 loop orchestrator（建议新增文件，不强侵入现有 `graph.py`）
- trace/index 写入（复用 `EvidenceStore.write_index`）
- CLI `diagnose` 子命令

修改：
- `configs/runtime.yaml`（可选：增加 diagnose 默认预算配置段）
- `README.md`（增加 diagnose 的推荐运行方式）

保持不变：
- 现有 policy/审计/脱敏链路仍是强约束（必须复用而不是重写）
