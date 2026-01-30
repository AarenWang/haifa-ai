#!/usr/bin/env python3
"""
SRE Agent v3 - 使用 LangGraph 编排的智能诊断系统

基于基础信息分析结果，动态选择诊断路径，避免盲目执行所有命令。
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict, Literal

from openai import OpenAI
from jsonschema import validate
from jsonschema.exceptions import ValidationError

# 尝试导入 LangGraph（可选）
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False


def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==================== 状态定义 ====================

class DiagnosticState(TypedDict):
    """诊断状态"""
    # 输入
    host: str
    service: str
    max_depth: int

    # 运行时状态
    round: int
    problem_category: Optional[str]  # CPU_HIGH, IO_WAIT, MEMORY_PRESSURE, UNKNOWN
    java_pid: Optional[str]
    evidence: List[Dict[str, Any]]
    diagnoses: List[Dict[str, Any]]

    # 输出
    final_report: Optional[Dict[str, Any]]
    error: Optional[str]


# ==================== 诊断工具 ====================

class DiagnosticsTool:
    """诊断工具集合"""

    def __init__(self, ssh_user: str = None, ssh_password: str = None,
                 ssh_port: int = 22, logger: logging.Logger = None):
        self.ssh_user = ssh_user or os.getenv("SRE_SSH_USER", "root")
        self.ssh_password = ssh_password or os.getenv("SRE_SSH_PASSWORD", "")
        self.ssh_port = ssh_port
        self.logger = logger or logging.getLogger(__name__)
        self.use_password = bool(self.ssh_password)

        self.READ_ONLY_COMMANDS = {
            # 基础系统信息
            "uptime": "uptime",
            "loadavg": "cat /proc/loadavg",
            "top": "top -b -n 1 | head -n 50",
            "ps_cpu": "ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%cpu | head -n 20",
            "ps_mem": "ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%mem | head -n 15",
            "vmstat": "vmstat 1 5",
            "iostat": "iostat -x 1 3",
            "free": "free -m",
            "mpstat": "mpstat -P ALL 1 1",
            "pidstat": "pidstat -h 1 1",

            # CPU 深度诊断
            "proc_pid_status": "cat /proc/{pid}/status",
            "proc_pid_stat": "cat /proc/{pid}/stat",
            "proc_pid_stack": "cat /proc/{pid}/stack",
            "proc_pid_wchan": "cat /proc/{pid}/wchan",

            # IO 深度诊断
            "proc_pid_io": "cat /proc/{pid}/io",
            "iotop": "iotop -b -n 1 -o | head -n 20",
            "pidstat_io": "pidstat -d 1 2",

            # Java 诊断
            "jps": "jps -l",
            "jstat": "jstat -gcutil {pid} 1 5",
            "jstat_gc": "jstat -gc {pid} 1 1",
            "jstack": "jstack -l {pid}",
            "jcmd_threads": "jcmd {pid} Thread.print",
            "jcmd_heap": "jcmd {pid} GC.heap_info",

            # 系统
            "journalctl": 'journalctl -u {service} --since "30 min ago" --no-pager',
            "dmesg": "dmesg | tail -n 50",
        }

    def run_ssh(self, host: str, command: str, timeout: int = 30) -> Dict[str, Any]:
        """通过 SSH 执行命令"""
        import time
        start_ts = time.time()

        if self.use_password:
            output = self._run_ssh_paramiko(host, command, timeout)
        else:
            output = self._run_ssh_subprocess(host, command, timeout)

        return {
            "command": command,
            "output": output[:15000],
            "elapsed_ms": int((time.time() - start_ts) * 1000),
        }

    def _run_ssh_subprocess(self, host: str, command: str, timeout: int) -> str:
        target = host
        if self.ssh_user and "@" not in host:
            target = f"{self.ssh_user}@{host}"
        import shlex
        wrapper_command = f"bash -l -c {shlex.quote(command)}"
        cmd = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {self.ssh_port} {shlex.quote(target)} {shlex.quote(wrapper_command)}"

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            output = (result.stdout or "") + (f"\n[stderr]\n{result.stderr}" if result.stderr else "")
        except subprocess.TimeoutExpired:
            output = f"命令执行超时 ({timeout}秒)"
        except Exception as e:
            output = f"SSH 执行错误: {type(e).__name__}: {e}"
        return output

    def _run_ssh_paramiko(self, host: str, command: str, timeout: int) -> str:
        try:
            import paramiko
        except ImportError:
            return "错误: 需要安装 paramiko 库"
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(hostname=host, port=self.ssh_port, username=self.ssh_user,
                          password=self.ssh_password, timeout=timeout, allow_agent=False, look_for_keys=False)
            wrapped_command = f"bash -l -c {command!r}"
            stdin, stdout, stderr = client.exec_command(wrapped_command, timeout=timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            return output + (f"\n[stderr]\n{err}" if err else "")
        except Exception as e:
            return f"SSH 连接错误: {type(e).__name__}: {e}"
        finally:
            try:
                client.close()
            except Exception:
                pass

    def execute_by_name(self, host: str, cmd_id: str, service: str = None, pid: str = None) -> Dict[str, Any]:
        if cmd_id not in self.READ_ONLY_COMMANDS:
            return {"error": f"命令不允许: {cmd_id}"}
        template = self.READ_ONLY_COMMANDS[cmd_id]
        command = template.format(service=service or "", pid=pid or "")
        return self.run_ssh(host, command)


# ==================== LLM 调用 ====================

class LLMClient:
    """千问大模型客户端"""

    def __init__(self, api_key: str, base_url: str = None, model: str = "qwen-plus"):
        self.client = OpenAI(api_key=api_key, base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model = model

    def classify_problem(self, evidence_summary: str) -> Dict[str, Any]:
        """分类问题类型：CPU_HIGH, IO_WAIT, MEMORY_PRESSURE, UNKNOWN"""
        prompt = f"""你是一个SRE专家。根据以下系统证据，判断主要问题类型。

系统证据:
{evidence_summary}

请返回JSON:
{{
  "category": "CPU_HIGH|IO_WAIT|MEMORY_PRESSURE|UNKNOWN|MULTIPLE",
  "confidence": "high|medium|low",
  "reasoning": "判断依据",
  "problem_pid": "异常进程PID（如果有）",
  "suggested_checks": ["建议的检查命令列表"]
}}

只返回JSON，无其他内容。"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        return self._extract_json(response.choices[0].message.content)

    def analyze_cpu_deep(self, evidence: str) -> Dict[str, Any]:
        """深度分析 CPU 问题"""
        prompt = f"""分析CPU高负载的根因。

证据:
{evidence}

关注点:
1. 是用户态(us)高还是系统态(sy)高？
2. 上下文切换是否过多？(voluntary_ctxt_switches vs nonvoluntary_ctxt_switches)
3. 是否有特定线程/代码占用CPU？(proc_pid_stack)
4. 是Java应用吗？GC频率如何？

返回JSON:
{{
  "root_cause": "具体根因",
  "confidence": "high|medium|low",
  "evidence_refs": ["证据引用"],
  "next_checks": ["需要进一步检查的命令"]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000,
        )
        return self._extract_json(response.choices[0].message.content)

    def analyze_io_deep(self, evidence: str) -> Dict[str, Any]:
        """深度分析 IO 问题"""
        prompt = f"""分析IO等待的根因。

证据:
{evidence}

关注点:
1. 哪个进程IO最高？(pidstat_io, proc_pid_io)
2. 是读还是写导致的？
3. 磁盘响应时间如何？(iostat await)
4. 是否有日志/数据库在大量写入？

返回JSON:
{{
  "root_cause": "具体根因",
  "confidence": "high|medium|low",
  "evidence_refs": ["证据引用"],
  "next_checks": ["需要进一步检查的命令"]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000,
        )
        return self._extract_json(response.choices[0].message.content)

    def analyze_memory_deep(self, evidence: str) -> Dict[str, Any]:
        """深度分析内存问题"""
        prompt = f"""分析内存压力的根因。

证据:
{evidence}

关注点:
1. 是物理内存不足还是swap用完？
2. 哪个进程占用内存最多？
3. 是Java应用吗？堆内存如何？GC是否频繁？
4. 是否有内存泄漏迹象？

返回JSON:
{{
  "root_cause": "具体根因",
  "confidence": "high|medium|low",
  "evidence_refs": ["证据引用"],
  "next_checks": ["需要进一步检查的命令"]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000,
        )
        return self._extract_json(response.choices[0].message.content)

    def generate_final_report(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成最终报告"""
        prompt = f"""生成最终诊断报告。

诊断过程:
{json.dumps(state, ensure_ascii=False, indent=2)}

请生成符合以下结构的JSON报告:
{{
  "meta": {{
    "host": "主机",
    "service": "服务",
    "timestamp": "时间",
    "rounds": "轮数",
    "category": "问题类别"
  }},
  "root_cause": {{
    "category": "CPU_HIGH|IO_WAIT|MEMORY_PRESSURE|GC_ISSUE|THREAD_CONTENTION|UNKNOWN",
    "summary": "简洁的根因描述",
    "confidence": 0.0-1.0,
    "details": "详细分析"
  }},
  "evidence_summary": ["证据列表"],
  "recommended_actions": [
    {{"action": "建议操作", "risk": "READ_ONLY|LOW|MEDIUM", "expected_effect": "预期效果"}}
  ]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        return self._extract_json(response.choices[0].message.content)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        return {"error": "无法解析JSON", "raw": text}


# ==================== 诊断节点 ====================

def collect_basic_info(state: DiagnosticState, tool: DiagnosticsTool,
                       llm: LLMClient, logger: logging.Logger) -> DiagnosticState:
    """节点1: 收集基础信息"""
    logger.info("[节点1] 收集基础信息...")

    host = state["host"]
    commands = [
        ("uptime", "系统负载"),
        ("loadavg", "负载详情"),
        ("top", "进程快照"),
        ("ps_cpu", "CPU排序"),
        ("vmstat", "系统统计"),
        ("iostat", "IO统计"),
        ("free", "内存状态"),
    ]

    evidence = []
    for cmd_id, desc in commands:
        logger.info(f"  执行: {cmd_id}")
        result = tool.execute_by_name(host, cmd_id)
        if "error" not in result:
            evidence.append({
                "cmd_id": cmd_id,
                "description": desc,
                "output": result["output"][:2000],
            })

    # 提取 Java PID
    jps_result = tool.execute_by_name(host, "jps")
    evidence.append({
        "cmd_id": "jps",
        "description": "Java进程",
        "output": jps_result["output"][:500],
    })
    import re
    match = re.search(r'(\d+)\s', jps_result.get("output", ""))
    state["java_pid"] = match.group(1) if match else None

    state["evidence"] = evidence
    state["round"] = 1
    return state


def classify_and_route(state: DiagnosticState, tool: DiagnosticsTool,
                       llm: LLMClient, logger: logging.Logger) -> DiagnosticState:
    """节点2: 分类问题并决定路由"""
    logger.info("[节点2] AI分类决策...")

    # 构建证据摘要
    evidence_summary = "\n".join([
        f"[{e['cmd_id']}] {e.get('output', '')[:500]}"
        for e in state["evidence"]
    ])

    classification = llm.classify_problem(evidence_summary)
    logger.info(f"  分类结果: {classification.get('category')} (置信度: {classification.get('confidence')})")
    logger.info(f"  推理: {classification.get('reasoning')}")

    state["problem_category"] = classification.get("category", "UNKNOWN")

    # 记录分类结果到诊断历史
    state["diagnoses"].append({
        "round": 2,
        "action": "classify",
        "result": classification,
    })

    return state


def cpu_deep_dive(state: DiagnosticState, tool: DiagnosticsTool,
                  llm: LLMClient, logger: logging.Logger) -> DiagnosticState:
    """节点3a: CPU 深度诊断"""
    logger.info("[节点3a] CPU深度诊断...")

    host = state["host"]
    pid = state.get("java_pid") or state.get("problem_pid")

    commands = [
        "mpstat",
        "proc_pid_status",
        "proc_pid_stack",
    ]
    if pid:
        commands.append("jstat")
        commands.append("jstack")

    for cmd_id in commands:
        logger.info(f"  执行: {cmd_id}")
        result = tool.execute_by_name(host, cmd_id, pid=pid)
        state["evidence"].append({
            "cmd_id": cmd_id,
            "output": result.get("output", "")[:1500],
        })

    evidence_summary = json.dumps(state["evidence"], ensure_ascii=False)
    analysis = llm.analyze_cpu_deep(evidence_summary)
    logger.info(f"  分析: {analysis.get('root_cause')}")

    state["diagnoses"].append({
        "round": 3,
        "action": "cpu_analysis",
        "result": analysis,
    })
    state["round"] = 3
    return state


def io_deep_dive(state: DiagnosticState, tool: DiagnosticsTool,
                 llm: LLMClient, logger: logging.Logger) -> DiagnosticState:
    """节点3b: IO 深度诊断"""
    logger.info("[节点3b] IO深度诊断...")

    host = state["host"]
    pid = state.get("java_pid") or state.get("problem_pid")

    commands = [
        "pidstat_io",
        "proc_pid_io",
    ]
    if pid:
        commands.append("lsof_pid")

    for cmd_id in commands:
        logger.info(f"  执行: {cmd_id}")
        result = tool.execute_by_name(host, cmd_id, pid=pid)
        state["evidence"].append({
            "cmd_id": cmd_id,
            "output": result.get("output", "")[:1500],
        })

    evidence_summary = json.dumps(state["evidence"], ensure_ascii=False)
    analysis = llm.analyze_io_deep(evidence_summary)
    logger.info(f"  分析: {analysis.get('root_cause')}")

    state["diagnoses"].append({
        "round": 3,
        "action": "io_analysis",
        "result": analysis,
    })
    state["round"] = 3
    return state


def memory_deep_dive(state: DiagnosticState, tool: DiagnosticsTool,
                     llm: LLMClient, logger: logging.Logger) -> DiagnosticState:
    """节点3c: Memory 深度诊断"""
    logger.info("[节点3c] Memory深度诊断...")

    host = state["host"]
    pid = state.get("java_pid")

    commands = ["ps_mem"]
    if pid:
        commands.append("jstat_gc")
        commands.append("jcmd_heap")

    for cmd_id in commands:
        logger.info(f"  执行: {cmd_id}")
        result = tool.execute_by_name(host, cmd_id, pid=pid)
        state["evidence"].append({
            "cmd_id": cmd_id,
            "output": result.get("output", "")[:1500],
        })

    evidence_summary = json.dumps(state["evidence"], ensure_ascii=False)
    analysis = llm.analyze_memory_deep(evidence_summary)
    logger.info(f"  分析: {analysis.get('root_cause')}")

    state["diagnoses"].append({
        "round": 3,
        "action": "memory_analysis",
        "result": analysis,
    })
    state["round"] = 3
    return state


def generate_report(state: DiagnosticState, tool: DiagnosticsTool,
                    llm: LLMClient, logger: logging.Logger) -> DiagnosticState:
    """节点4: 生成最终报告"""
    logger.info("[节点4] 生成最终报告...")

    report = llm.generate_final_report(state)
    report["meta"]["host"] = state["host"]
    report["meta"]["service"] = state["service"]
    report["meta"]["timestamp"] = now_iso()
    report["meta"]["rounds"] = state["round"]
    report["meta"]["category"] = state.get("problem_category", "UNKNOWN")

    state["final_report"] = report
    return state


# ==================== 路由函数 ====================

def route_after_classification(state: DiagnosticState) -> str:
    """分类后的路由决策"""
    category = state.get("problem_category", "UNKNOWN")

    if category == "CPU_HIGH":
        return "cpu_dive"
    elif category == "IO_WAIT":
        return "io_dive"
    elif category == "MEMORY_PRESSURE":
        return "memory_dive"
    elif category == "MULTIPLE":
        # 多问题，优先处理最严重的
        return "cpu_dive"  # 默认先看CPU
    else:
        return "generate_report"


# ==================== 主程序 ====================

def run_diagnostic_graph(host: str, service: str, ssh_user: str, ssh_password: str,
                         api_key: str, model: str, max_depth: int,
                         logger: logging.Logger) -> Dict[str, Any]:
    """运行诊断流程"""

    # 初始化状态
    initial_state: DiagnosticState = {
        "host": host,
        "service": service,
        "max_depth": max_depth,
        "round": 0,
        "problem_category": None,
        "java_pid": None,
        "evidence": [],
        "diagnoses": [],
        "final_report": None,
        "error": None,
    }

    # 初始化工具
    tool = DiagnosticsTool(ssh_user=ssh_user, ssh_password=ssh_password, logger=logger)
    llm = LLMClient(api_key=api_key, model=model)

    # 使用 LangGraph（如果可用）
    if HAS_LANGGRAPH:
        logger.info("使用 LangGraph 编排诊断流程")

        # 构建图
        builder = StateGraph(DiagnosticState)

        # 添加节点
        builder.add_node("collect_basic", lambda s: collect_basic_info(s, tool, llm, logger))
        builder.add_node("classify", lambda s: classify_and_route(s, tool, llm, logger))
        builder.add_node("cpu_dive", lambda s: cpu_deep_dive(s, tool, llm, logger))
        builder.add_node("io_dive", lambda s: io_deep_dive(s, tool, llm, logger))
        builder.add_node("memory_dive", lambda s: memory_deep_dive(s, tool, llm, logger))
        builder.add_node("generate_report", lambda s: generate_report(s, tool, llm, logger))

        # 添加边
        builder.set_entry_point("collect_basic")
        builder.add_edge("collect_basic", "classify")
        builder.add_conditional_edges(
            "classify",
            route_after_classification,
            {
                "cpu_dive": "cpu_dive",
                "io_dive": "io_dive",
                "memory_dive": "memory_dive",
                "generate_report": "generate_report",
            }
        )
        builder.add_edge("cpu_dive", "generate_report")
        builder.add_edge("io_dive", "generate_report")
        builder.add_edge("memory_dive", "generate_report")
        builder.add_edge("generate_report", END)

        # 编译并运行
        graph = builder.compile()

        # 执行
        result = graph.invoke(initial_state)
        return result.get("final_report", {})

    else:
        # 降级到简单流程
        logger.info("使用简单流程 (未安装 LangGraph)")

        state = initial_state
        state = collect_basic_info(state, tool, llm, logger)
        state = classify_and_route(state, tool, llm, logger)

        category = state.get("problem_category")
        if category == "CPU_HIGH":
            state = cpu_deep_dive(state, tool, llm, logger)
        elif category == "IO_WAIT":
            state = io_deep_dive(state, tool, llm, logger)
        elif category == "MEMORY_PRESSURE":
            state = memory_deep_dive(state, tool, llm, logger)

        state = generate_report(state, tool, llm, logger)
        return state.get("final_report", {})


async def main() -> None:
    ap = argparse.ArgumentParser(description="SRE Agent v3 - LangGraph 智能诊断")
    ap.add_argument("--host", required=True, help="目标主机地址")
    ap.add_argument("--service", required=True, help="目标服务名称")
    ap.add_argument("--ssh-user", default=None, help="SSH 用户名")
    ap.add_argument("--ssh-password", default=None, help="SSH 密码")
    ap.add_argument("--ssh-port", type=int, default=22, help="SSH 端口")
    ap.add_argument("--model", default="qwen-plus", help="模型")
    ap.add_argument("--output", "-o", default=None, help="输出文件")
    ap.add_argument("--max-depth", type=int, default=3, help="最大深度")
    ap.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    args = ap.parse_args()

    logger = setup_logging(args.verbose)

    logger.info("=" * 60)
    logger.info("SRE Agent v3 - LangGraph 智能诊断")
    logger.info("=" * 60)

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        logger.error("错误: 未设置 DASHSCOPE_API_KEY")
        sys.exit(1)

    if HAS_LANGGRAPH:
        logger.info("✓ LangGraph 已启用")
    else:
        logger.warning("✗ LangGraph 未安装 (pip install langgraph)，使用降级模式")

    ssh_user = args.ssh_user or os.getenv("SRE_SSH_USER", "root")
    ssh_password = args.ssh_password or os.getenv("SRE_SSH_PASSWORD", "")

    logger.info(f"目标: {ssh_user}@{args.host}")
    logger.info(f"服务: {args.service}")
    logger.info("-" * 60)

    try:
        report = run_diagnostic_graph(
            host=args.host,
            service=args.service,
            ssh_user=ssh_user,
            ssh_password=ssh_password,
            api_key=api_key,
            model=args.model,
            max_depth=args.max_depth,
            logger=logger,
        )

        # 输出
        result_json = json.dumps(report, ensure_ascii=False, indent=2)
        logger.info("-" * 60)

        if args.output:
            os.makedirs("report", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            output_path = f"report/{timestamp}.json"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result_json)
            logger.info(f"报告已保存: {output_path}")
        else:
            print(result_json)

    except Exception as e:
        logger.error(f"诊断失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("诊断完成!")


if __name__ == "__main__":
    asyncio.run(main())
