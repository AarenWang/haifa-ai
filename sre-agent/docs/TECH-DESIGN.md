# sre-agent TECH-DESIGN (Current)

本文描述当前 `sre-agent` 的技术设计与代码结构，强调三条硬约束：

- 只读：所有执行动作必须来自白名单 cmd_id 且通过策略校验。
- 可审计：每次命令执行都记录审计信息与输出哈希，可回放。
- 证据驱动：结论必须能引用到 evidence/audit（避免无证据断言）。

相关补充：

- 多轮闭环：见 `sre-agent/docs/multi-stage.md`
- 子 agent / 多 agent（准确性优先）：见 `sre-agent/docs/multi-and-sub-agent.md`

## 1. 总体架构

当前实现是“确定性优先 + 可选多轮规划”的双路径：

1) Deterministic Orchestrator
- discovery/baseline -> rules classify -> routing targeted
- 输出 `evidence_pack.json`

2) Multi-round Diagnose (routing-restricted)
- 先跑 Deterministic Orchestrator 作为 baseline
- LLM 仅产出 plan JSON（不直接 tool-call）
- 系统按 allowlist 执行 cmd_id，追加证据，再迭代
- 输出：`evidence_pack.json` + `diagnosis_report.json` + `diagnosis_trace.json`

## 2. 代码模块与职责

CLI / 入口

- `sre-agent/src/cli/sre_agent_cli.py`：统一命令入口（exec/run/diagnose/report/ingest-alert/ticket）

编排层 (Orchestrator)

- `sre-agent/src/orchestrator/graph.py`：确定性编排（baseline + rules + routing）与单条命令执行 `exec_cmd()`
- `sre-agent/src/orchestrator/multi_stage.py`：多轮诊断 loop（LLM planner -> 执行 -> 更新 signals -> 再规划）
- `sre-agent/src/orchestrator/planner_prompt.py`：plan prompt builder（强制 allowlist 与 schema）
- `sre-agent/src/orchestrator/rules.py`：规则分类器（从 signals 推导 hypothesis）

执行层 (Execution)

- `sre-agent/src/adapters/exec/ssh.py`：SSH 执行器（支持密码/免密；支持 shell init 与 JAVA_HOME best-effort）
- `sre-agent/src/adapters/exec/local.py`：本地执行器（用于开发/回放）
- `sre-agent/src/adapters/exec/mcp.py`：MCP 执行适配器（当前为 stub，未接入）

注册与解析 (Registry)

- `sre-agent/src/registry/commands.py`：加载 `configs/commands.yaml`，render 命令模板（{service}/{pid}）
- `sre-agent/src/registry/parsers.py`：将命令输出解析为结构化 parsed
- `sre-agent/src/registry/signals.py`：从 parsed 提取标准化 signals

安全策略 (Policy)

- `sre-agent/src/policy/command_policy.py`：命令风险与 deny_keywords 校验
- `sre-agent/src/policy/validators.py`：`service/pid` 参数校验（防注入）
- `sre-agent/src/policy/action_filter.py`：过滤报告中的 `next_actions`（只允许 READ_ONLY/LOW）

存储与审计 (Storage)

- `sre-agent/src/storage/evidence_store.py`：证据落盘（raw/redacted/parsed/index）
- `sre-agent/src/storage/redaction.py`：脱敏与输出哈希
- `sre-agent/src/storage/audit_store.py`：审计日志（jsonl）

报告生成 (Reporting)

- `sre-agent/src/reporting/report_builder.py`：LLM 生成 `diagnosis_report` + 再做 action filter
- `sre-agent/src/reporting/schema_validate.py`：JSON Schema 校验

## 3. 配置与 Schema

配置文件（默认 `sre-agent/configs/`）：

- `sre-agent/configs/runtime.yaml`：运行时默认值（vendor、ssh、evidence base_dir、baseline cmds）
- `sre-agent/configs/commands.yaml`：cmd_id 白名单与模板命令
- `sre-agent/configs/rules.yaml`：规则分类配置
- `sre-agent/configs/routing.yaml`：分类到 cmd_id 的路由（routing-restricted 的 allowlist 来源）
- `sre-agent/configs/policy.yaml`：执行/动作过滤策略（allowed_risks、deny_keywords）

Schema（默认 `sre-agent/schemas/`）：

- `sre-agent/schemas/evidence_schema.json`：`evidence_pack` 结构
- `sre-agent/schemas/plan_schema.json`：多轮 planner 的 plan 输出结构
- `sre-agent/schemas/report_schema.json`：最终 `diagnosis_report` 结构

配置覆盖：

- CLI 会加载 yaml 并应用环境变量覆盖（例如 `SRE_LLM_VENDOR`、`SRE_SSH_USER`、`OPS_AGENT_AUDIT_LOG`）。

## 4. 数据流与产物

### 4.1 Evidence Pack

主产物：`evidence_pack`（schema：`sre-agent/schemas/evidence_schema.json`）

- `meta`：host/service/env/session_id/platform/timestamp
- `snapshots`：轻量摘要（cmd_id + 首行信号 + audit_ref）
- `signals`：结构化信号（供 rules 与 planner 使用）
- `hypothesis`：规则分类输出（category/confidence/why/evidence_refs）
- `policy`：本次运行的策略快照（用于 report action filter）

### 4.2 Evidence Store Layout

落盘目录：`{evidence.base_dir}/{session_id}/`

- `raw/`：原始输出（仅用于回放/调试；仍会写入，注意权限与保留策略）
- `redacted/`：脱敏输出（默认供后续阅读/复盘）
- `parsed/`：解析后的结构化 JSON
- `index/`：索引与 trace（包括每条 event、evidence_pack、diagnosis_report、diagnosis_trace 等）

### 4.3 Audit Log

审计日志：`runtime.yaml` 的 `audit_log`（默认 `./audit.log`，jsonl）

- 记录 cmd_id、执行时间、耗时、脱敏规则、redacted output hash
- `audit_ref` 采用 `{cmd_id}-{timestamp}`，用于把 report/evidence_table 追溯到执行记录

## 5. 执行流程

### 5.1 单条命令 exec

入口：`sre-agent/src/cli/sre_agent_cli.py` -> `exec`

流程：

1) 从 `configs/commands.yaml` 取 `cmd_id` 元信息
2) policy 校验（risk + deny_keywords）
3) 参数校验（{service}/{pid}）
4) SSH/local 执行
5) 脱敏 + hash
6) 可选写入 audit log

### 5.2 run（确定性采证）

入口：`sre-agent/src/cli/sre_agent_cli.py` -> `run`

流程（`sre-agent/src/orchestrator/graph.py`）：

1) baseline：按 `runtime.yaml` 的 baseline cmds 执行
2) 解析/提取 signals
3) rules 分类得到 primary category
4) routing：按 `routing.yaml` 执行 targeted cmds
5) 再次 rules 分类更新 hypothesis
6) 输出 evidence_pack 并写入 EvidenceStore index

### 5.3 diagnose（多轮闭环）

入口：`sre-agent/src/cli/sre_agent_cli.py` -> `diagnose`

关键原则：LLM 不直接执行命令，只输出 plan（严格 schema + allowlist）。

流程（`sre-agent/src/orchestrator/multi_stage.py`）：

1) 先跑 `Orchestrator.run()` 得到 baseline evidence_pack
2) 取 primary category，并从 `routing.yaml` 获取 allowed_cmd_pool
3) Round 1..N：
   - 仅向 LLM 提供 signals + snapshots（无 raw 全量输出）
   - `planner_prompt` 强制 allowlist 与 `plan_schema`
   - system 过滤 plan（not_in_pool / duplicate / unknown_cmd_id）
   - 执行保留的 cmd_id 并追加 snapshots/signals
   - rules re-classify 更新 hypothesis
   - 写入 per-round trace：`index/llm_round_XXX.json`
4) STOP：预算/路由耗尽/LLM stop/置信度阈值
5) 最终调用 `report_builder` 生成 `diagnosis_report` 并写入 index

## 6. 安全设计

只读与可控的强约束来自三层：

1) 命令白名单
- 所有执行必须通过 `cmd_id -> commands.yaml` 映射

2) 参数校验
- `service` 仅允许安全字符集；`pid` 必须为数字（见 `sre-agent/src/policy/validators.py`）

3) Policy Gate
- `allowed_risks` + `deny_keywords`（见 `sre-agent/configs/policy.yaml`）
- 报告动作再过滤：`sre-agent/src/policy/action_filter.py`

附加设计点：

- planner allowlist：多轮诊断中 LLM 只能在 `allowed_cmd_pool` 中选 cmd_id（routing-restricted）
- 脱敏：默认对 IP/邮箱/secret/path/user 等做替换（见 `sre-agent/src/storage/redaction.py`）

## 7. 可观测性与评估

- 运行日志：CLI 通过 `--log-level` / `SRE_LOG_LEVEL` 控制
- Trace：多轮诊断保存 `diagnosis_trace` 与每轮 `llm_round_XXX.json`
- 回放与评估：`sre-agent/src/evaluation/replay.py`、`sre-agent/src/evaluation/metrics.py`

建议关注“准确性优先”的指标体系：见 `sre-agent/docs/multi-and-sub-agent.md`。

## 8. 运行方式（当前 CLI）

```bash
# 查看当前 LLM / SDK 选择与能力
python -m src.cli.sre_agent_cli info

# 只执行一个 cmd_id（受 policy 限制）
python -m src.cli.sre_agent_cli exec --host 1.2.3.4 --cmd-id uptime

# 确定性采证，输出 evidence_pack
python -m src.cli.sre_agent_cli run --host 1.2.3.4 --service myapp --output report/evidence_pack.json

# 多轮诊断：采证 + 规划 + 报告 + trace
python -m src.cli.sre_agent_cli diagnose --host 1.2.3.4 --service myapp \
  --output-evidence report/evidence_pack.json \
  --output-report report/report.json \
  --output-trace report/diagnosis_trace.json

# 从 evidence_pack 生成 report（不做执行）
python -m src.cli.sre_agent_cli report --evidence report/evidence_pack.json --schema schemas/report_schema.json
```

## 9. 扩展点

- 新命令：在 `sre-agent/configs/commands.yaml` 增加 cmd_id，并在 `sre-agent/src/registry/parsers.py` / `sre-agent/src/registry/signals.py` 增加解析与信号提取
- 新分类：在 `sre-agent/configs/rules.yaml` 增加规则；在 `sre-agent/configs/routing.yaml` 增加路由候选池
- 新执行后端：实现与 `SSHExecutor` 相同的 `run(host, command, timeout)` 接口即可接入 `Orchestrator`
- 子 agent / 多 agent：先以“Verifier pass”增强报告准确性，再进入多 agent 并行（见 `sre-agent/docs/multi-and-sub-agent.md`）
