# SRE Agent

生产环境只读排障智能体：通过 SSH/MCP 采集可审计的证据（raw/redacted/parsed），基于确定性规则先做分类与路由，再由 LLM 生成结构化结论与只读建议。

本目录提供一个可运行的最小闭环：CLI -> Orchestrator -> Command Registry/Executor -> Evidence Store -> (可选) Report。

## 产品介绍

- 目标用户：生产 SRE/运维工程师
- 解决问题：在不做任何写操作/重启/kill 的前提下，快速定位 Linux/Java 服务性能异常（CPU/IO/MEM/GC/NET/外部依赖）
- 核心产物：
  - `evidence_pack`：结构化证据包（可回放、可回归）
  - `diagnosis_report`：基于 schema 的结构化报告（建议会被策略过滤为只读）

## 架构介绍

Deterministic First 的分层架构：

1) 控制面：`src/orchestrator/graph.py`
   - 基线采证 -> 规则分类 -> 动态路由追加采证 -> 产出 `evidence_pack`
2) 执行面：`src/adapters/exec/*` + `src/registry/commands.py`
   - 命令注册中心（风险/平台/依赖元数据）
   - `ssh` / `local` 执行器
3) 证据面：`src/storage/evidence_store.py`
   - `report/<session_id>/{raw,redacted,parsed,index}/...`
4) 推理面：`src/orchestrator/rules.py` + `src/registry/{parsers.py,signals.py}`
   - 规则引擎做分类，signals 统一口径，支持 counter-evidence
5) 输出面：`src/reporting/report_builder.py`
   - 生成报告前后都强制走 policy filter（只读硬约束）
6) 对接面：`src/integrations/webhook.py`
   - alert payload 标准化 + ticket payload 生成

## 实现方案介绍

### 1) 只读安全与审计

- 参数校验：`src/policy/validators.py`（`service/pid`）
- 命令策略：`configs/policy.yaml` + `src/policy/command_policy.py`
- 输出动作过滤：`src/policy/action_filter.py` + `src/reporting/report_builder.py`
- 审计：`src/storage/audit_store.py`（输出哈希、脱敏替换计数）

### 2) 证据驱动（Evidence Pack）

- Evidence Store：`src/storage/evidence_store.py`
- Schema：`schemas/evidence_schema.json`、`schemas/report_schema.json`
- 回放评估：`src/evaluation/*` + `scripts/replay_suite.py`

### 3) 分类与动态路由

- 规则配置：`configs/rules.yaml`
- 路由配置：`configs/routing.yaml`
- 解析与 signals：`src/registry/parsers.py`、`src/registry/signals.py`

## 配置

配置文件默认在 `configs/`：

- `configs/runtime.yaml`：llm/sdk 选择示例、审计与 evidence 输出目录、baseline 命令（按平台）
- `configs/commands.yaml`：命令注册（cmd_id -> cmd template + 风险/平台）
- `configs/policy.yaml`：只读策略（允许风险等级、deny keywords）
- `configs/rules.yaml`：分类规则
- `configs/routing.yaml`：按分类追加采证命令集

常用环境变量（覆盖/补充 runtime config）：

```bash
export SRE_LLM_VENDOR=qwen
export SRE_LLM_MODEL=qwen-plus
export SRE_AGENT_SDK_VENDOR=claude_sdk

export SRE_SSH_USER=root
export SRE_SSH_PASSWORD=...   # 可选
export SRE_SSH_PORT=22

export OPS_AGENT_AUDIT_LOG=./audit.log
```

## 测试运行

```bash
cd sre-agent
python -m pytest -q
```

可选：离线回放评估

```bash
cd sre-agent
python scripts/replay_suite.py
```

## 正式环境部署与运行

### 1) 安装

```bash
cd sre-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) 运行（采证）

SSH 远程采证（推荐用于 Linux 生产机）：

```bash
cd sre-agent
python -m src.cli.sre_agent_cli run \
  --host 10.0.0.12 \
  --service myapp \
  --window-minutes 30 \
  --exec-mode ssh \
  --platform linux \
  --output report/evidence_pack.json
```

采证完成后运行 LLM 诊断（生成结构化报告）：

```bash
cd sre-agent
python -m src.cli.sre_agent_cli report \
  --evidence report/evidence_pack.json \
  --schema schemas/report_schema.json \
  > report/report.json
```

本机采证（仅用于开发机验证）：

```bash
cd sre-agent
python -m src.cli.sre_agent_cli run \
  --host localhost \
  --service myapp \
  --exec-mode local \
  --platform darwin
```

### 3) 告警/工单对接（可选）

```bash
cd sre-agent
python -m src.cli.sre_agent_cli ingest-alert --payload tests/fixtures/sample_alert.json
python -m src.cli.sre_agent_cli ticket --report path/to/report.json
```

## 文档

- `docs/PRD.md`
- `docs/TECH-DESIGN.md`
- `docs/optimize-sre-agent.md`
