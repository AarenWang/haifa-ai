#!/usr/bin/env python3
"""
SRE Agent v2 - 使用阿里云百炼平台千问大模型的只读诊断智能体

环境变量配置:
    export DASHSCOPE_API_KEY="your-api-key"
    export SRE_SSH_USER="username"
    export SRE_SSH_PASSWORD="password"  # 可选
    export OPS_AGENT_AUDIT_LOG="./audit.log"  # 可选
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

from openai import OpenAI
from jsonschema import validate
from jsonschema.exceptions import ValidationError


def setup_logging(verbose: bool = False) -> logging.Logger:
    """配置日志输出格式"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_prompt(host: str, service: str, window_minutes: int, round_num: int = 1) -> str:
    round_context = {
        1: "这是第1轮诊断。请分析基础系统状态，找出异常进程，并确定是 CPU 饱和、IO 等待还是其他问题。",
        2: "这是第2轮诊断。基于第1轮发现的问题，深入分析进程级细节（/proc/pid/*），确定具体原因。",
        3: "这是第3轮诊断。对Java进程进行深度分析（jstat, jstack），找出GC、线程、锁等问题。",
        4: "这是第4轮诊断。分析IO瓶颈（iotop, pidstat -d），检查是否是磁盘或网络IO导致。",
        5: "这是第5轮最终诊断。综合所有证据，给出确定的根因分析和建议。",
    }

    return f"""你是一个经验丰富的 SRE 运维专家，正在诊断 Linux 生产主机上 Java 服务的高负载问题。

{round_context.get(round_num, "继续深入诊断...")}

**诊断重点:**

1. **CPU 高负载分析** → 关注:
   - load average vs CPU核心数比例
   - 单进程 %CPU 是否异常高（>100%表示多核使用）
   - 系统态 CPU (sy) 是否高 → 可能是系统调用过多/锁竞争
   - 用户态 CPU (us) 高 → 应用代码问题
   - /proc/pid/status 中的 voluntary_ctxt_switches vs nonvoluntary_ctxt_switches

2. **IO Wait 分析** → 关注:
   - iostat %iowait > 20% → IO瓶颈
   - iostat await/svctm → 磁盘响应时间
   - pidstat -d 显示具体进程的IO
   - /proc/pid/io 显示进程读写统计

3. **Java 问题** → 关注:
   - jstat GC: Full GC频率、YGC时间、FGC时间
   - 线程数异常（>500）
   - jstack 中大量线程阻塞在同一个锁/方法

**可用命令 (cmd_id):**
基础: uptime, loadavg, top, ps_cpu, ps_mem, vmstat, iostat, free, mpstat, pidstat
进程: proc_pid_status, proc_pid_stat, proc_pid_stack, proc_pid_sched, proc_pid_wchan
IO: proc_pid_io, iotop, pidstat_io
Java: jps, jstat, jstat_gc, jstack, jcmd_threads, jcmd_heap, jcmd_vm
系统: journalctl, dmesg, netstat, ss

**目标主机:** {host}
**目标服务:** {service}
**时间窗口:** {window_minutes} 分钟

**请按照以下JSON格式返回:**

{{
  "meta": {{"host": "{host}", "service": "{service}", "timestamp": "{now_iso()}", "round": {round_num}}},
  "analysis": {{"current_findings": "当前发现", "suspected_cause": "疑似原因"}},
  "snapshots": [已收集证据的总结],
  "hypothesis": [
    {{
      "category": "CPU_HIGH|IO_WAIT|MEMORY_PRESSURE|GC_ISSUE|THREAD_CONTENTION|LOCK_CONTENTION|UNKNOWN",
      "confidence": "high|medium|low",
      "why": "详细原因分析，引用具体数值",
      "evidence_refs": ["cmd_id"]
    }}
  ],
  "next_checks": [
    {{"cmd_id": "具体命令", "purpose": "为什么要执行这个命令"}}
  ]
}}

**重要:** 只返回有效的JSON，不要有其他内容。
"""


def load_schema(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class DiagnosticsTool:
    """诊断工具集合，通过 SSH 执行只读命令"""

    def __init__(self, ssh_user: str = None, ssh_password: str = None, ssh_port: int = 22,
                 audit_log: str = None, logger: logging.Logger = None):
        self.ssh_user = ssh_user or os.getenv("SRE_SSH_USER", "root")
        self.ssh_password = ssh_password or os.getenv("SRE_SSH_PASSWORD", "")
        self.ssh_port = ssh_port
        self.audit_log = audit_log or os.getenv("OPS_AGENT_AUDIT_LOG", "")
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
            "df": "df -h",
            "mpstat": "mpstat -P ALL 1 1",
            "pidstat": "pidstat -h 1 1",

            # 进程深度诊断（CPU）
            "proc_pid_status": "cat /proc/{pid}/status",
            "proc_pid_stat": "cat /proc/{pid}/stat",
            "proc_pid_stack": "cat /proc/{pid}/stack",
            "proc_pid_sched": "cat /proc/{pid}/sched",
            "proc_pid_wchan": "cat /proc/{pid}/wchan",
            "lsof_pid": "lsof -p {pid} 2>/dev/null | head -n 50",

            # 进程深度诊断（IO）
            "proc_pid_io": "cat /proc/{pid}/io",
            "iotop": "iotop -b -n 1 -o | head -n 20",
            "pidstat_io": "pidstat -d 1 2",

            # Java 特定
            "jps": "jps -l",
            "jstat": "jstat -gcutil {pid} 1 5",
            "jstat_gc": "jstat -gc {pid} 1 1",
            "jstack": "jstack -l {pid}",
            "jcmd_threads": "jcmd {pid} Thread.print",
            "jcmd_heap": "jcmd {pid} GC.heap_info",
            "jcmd_vm": "jcmd {pid} VM.version",
            "jcmd_flags": "jcmd {pid} VM.flags",

            # 系统日志
            "journalctl": 'journalctl -u {service} --since "30 min ago" --no-pager',
            "dmesg": "dmesg | tail -n 50",

            # 网络诊断
            "netstat": "netstat -tnp 2>/dev/null | head -n 30",
            "ss": "ss -tnp | head -n 30",
        }

    def run_ssh(self, host: str, command: str, timeout: int = 30) -> Dict[str, Any]:
        """通过 SSH 执行命令"""
        started_at = now_iso()
        import time
        start_ts = time.time()

        # 如果提供了密码，使用 paramiko
        if self.use_password:
            output = self._run_ssh_paramiko(host, command, timeout)
        else:
            output = self._run_ssh_subprocess(host, command, timeout)

        elapsed_ms = int((time.time() - start_ts) * 1000)

        record = {
            "host": host,
            "command": command,
            "started_at": started_at,
            "elapsed_ms": elapsed_ms,
            "output_length": len(output),
        }

        if self.audit_log:
            self._write_audit(record)

        return {
            "command": command,
            "output": output[:15000],
            "elapsed_ms": elapsed_ms,
            "truncated": len(output) > 15000,
        }

    def _run_ssh_subprocess(self, host: str, command: str, timeout: int) -> str:
        """使用 subprocess 调用 ssh 命令（密钥认证）"""
        target = host
        if self.ssh_user and "@" not in host:
            target = f"{self.ssh_user}@{host}"

        import shlex
        # 使用登录 shell 加载环境变量，确保 PATH 正确
        wrapper_command = f"bash -l -c {shlex.quote(command)}"
        cmd = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {self.ssh_port} {shlex.quote(target)} {shlex.quote(wrapper_command)}"

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = (result.stdout or "")
            if result.stderr:
                output += "\n[stderr]\n" + result.stderr
        except subprocess.TimeoutExpired:
            output = f"命令执行超时 ({timeout}秒)"
        except Exception as e:
            output = f"SSH 执行错误: {type(e).__name__}: {e}"

        return output

    def _run_ssh_paramiko(self, host: str, command: str, timeout: int) -> str:
        """使用 paramiko 进行密码认证的 SSH 连接"""
        try:
            import paramiko
        except ImportError:
            return "错误: 需要安装 paramiko 库来支持密码认证 (pip install paramiko)"

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=host,
                port=self.ssh_port,
                username=self.ssh_user,
                password=self.ssh_password,
                timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
            )
            # 使用登录 shell 加载环境变量
            wrapped_command = f"bash -l -c {command!r}"
            stdin, stdout, stderr = client.exec_command(wrapped_command, timeout=timeout)

            output = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")

            if err:
                output += "\n[stderr]\n" + err

            return output

        except Exception as e:
            return f"SSH 连接错误: {type(e).__name__}: {e}"
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _write_audit(self, record: Dict[str, Any]) -> None:
        """写入审计日志"""
        try:
            with open(self.audit_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            self.logger.warning(f"写入审计日志失败: {e}")

    def get_allowed_commands(self) -> List[str]:
        """获取允许的命令列表"""
        return list(self.READ_ONLY_COMMANDS.keys())

    def execute_by_name(self, host: str, cmd_id: str, service: str = None, pid: str = None) -> Dict[str, Any]:
        """通过命令名称执行命令"""
        if cmd_id not in self.READ_ONLY_COMMANDS:
            return {
                "error": f"命令不允许: {cmd_id}",
                "allowed": self.get_allowed_commands(),
            }

        template = self.READ_ONLY_COMMANDS[cmd_id]
        command = template.format(service=service or "", pid=pid or "")

        return self.run_ssh(host, command)


def collect_evidence(host: str, service: str, tool: DiagnosticsTool,
                     logger: logging.Logger) -> Dict[str, Any]:
    """收集初步证据"""
    logger.info("  收集初步证据...")

    evidence = {
        "meta": {
            "host": host,
            "service": service,
            "timestamp": now_iso(),
        },
        "snapshots": [],
    }

    # 基础命令序列 - 第1轮收集
    commands = [
        ("uptime", "检查系统负载"),
        ("loadavg", "查看负载平均值"),
        ("top", "查看进程快照"),
        ("ps_cpu", "查看 CPU 占用高的进程"),
        ("free", "查看内存使用"),
        ("vmstat", "查看系统统计"),
        ("iostat", "查看IO统计"),
        ("mpstat", "查看CPU各核心使用"),
        ("pidstat", "查看进程统计"),
    ]

    for cmd_id, desc in commands:
        logger.info(f"    执行: {cmd_id} - {desc}")
        result = tool.execute_by_name(host, cmd_id)
        output = result.get("output", "")
        # 检查命令是否失败
        if "command not found" not in output.lower():
            evidence["snapshots"].append({
                "cmd_id": cmd_id,
                "description": desc,
                "output": output[:3000],
                "elapsed_ms": result.get("elapsed_ms", 0),
            })
        else:
            logger.debug(f"      跳过 {cmd_id} (命令不可用)")

    # 尝试查找 Java 进程
    logger.info(f"    查找 Java 进程...")
    jps_result = tool.execute_by_name(host, "jps")
    jps_output = jps_result.get("output", "")
    evidence["snapshots"].append({
        "cmd_id": "jps",
        "description": "查找 Java 进程",
        "output": jps_output[:1000],
        "elapsed_ms": jps_result.get("elapsed_ms", 0),
    })

    # 如果有 Java 进程，尝试获取 GC 信息
    import re
    match = re.search(r'(\d+)\s', jps_output)
    if match:
        java_pid = match.group(1)
        logger.info(f"    发现 Java PID: {java_pid}")

        jstat_result = tool.execute_by_name(host, "jstat", service=service, pid=java_pid)
        evidence["snapshots"].append({
            "cmd_id": "jstat",
            "description": "Java GC 统计",
            "output": jstat_result.get("output", "")[:2000],
            "elapsed_ms": jstat_result.get("elapsed_ms", 0),
        })

    return evidence


def call_qianwen_api(prompt: str, evidence: str, model: str,
                     api_key: str, base_url: str, logger: logging.Logger) -> str:
    """调用阿里云千问大模型 API"""
    logger.info(f"  调用千问大模型: {model}")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    full_prompt = f"""以下是从生产环境收集的诊断证据：

{evidence}

{prompt}

请基于上述证据进行分析，返回 JSON 格式的诊断结果。"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个经验丰富的 SRE 运维专家，擅长诊断 Linux 系统和 Java 应用的性能问题。"},
                {"role": "user", "content": full_prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
        )

        content = response.choices[0].message.content
        logger.info(f"  API 响应完成，输出长度: {len(content)} 字符")
        return content

    except Exception as e:
        logger.error(f"  API 调用失败: {e}")
        raise


def extract_json(text: str) -> Dict[str, Any]:
    """从文本中提取 JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试查找 JSON 块
    import re
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # 尝试查找 ```json ... ``` 块
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError("无法从响应中提取有效的 JSON")


async def main() -> None:
    ap = argparse.ArgumentParser(description="SRE Agent v2 - 阿里云千问大模型版本")
    ap.add_argument("--host", required=True, help="目标主机地址")
    ap.add_argument("--service", required=True, help="目标服务名称")
    ap.add_argument("--ssh-user", default=None, help="SSH 用户名 (默认: root)")
    ap.add_argument("--ssh-password", default=None, help="SSH 密码 (使用密码认证)")
    ap.add_argument("--ssh-port", type=int, default=22, help="SSH 端口 (默认: 22)")
    ap.add_argument("--window-minutes", type=int, default=30, help="诊断时间窗口（分钟）")
    ap.add_argument("--evidence-schema", default="evidence_schema.json", help="证据包 Schema 文件")
    ap.add_argument("--model", default="qwen-plus", help="使用的模型 (qwen-plus, qwen-turbo, qwen-max)")
    ap.add_argument("--output", "-o", default=None, help="输出报告到文件 (默认: 终端输出)")
    ap.add_argument("--max-rounds", type=int, default=5, help="最大迭代轮数 (默认: 5)")
    ap.add_argument("-v", "--verbose", action="store_true", help="详细日志输出")
    ap.add_argument("--no-collect", action="store_true", help="跳过自动收集，只分析")
    args = ap.parse_args()

    logger = setup_logging(args.verbose)

    # ========== 1. 检查环境变量 ==========
    logger.info("=" * 60)
    logger.info("SRE Agent v2 - 阿里云千问大模型诊断")
    logger.info("=" * 60)

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        logger.error("错误: 未设置 DASHSCOPE_API_KEY 环境变量")
        logger.error("  请设置: export DASHSCOPE_API_KEY='your-api-key'")
        sys.exit(1)

    # 确定 SSH 认证方式
    ssh_user = args.ssh_user or os.getenv("SRE_SSH_USER", "root")
    ssh_password = args.ssh_password or os.getenv("SRE_SSH_PASSWORD", "")

    logger.info(f"目标主机:   {args.host}")
    logger.info(f"目标服务:   {args.service}")
    logger.info(f"SSH 用户:   {ssh_user}")
    logger.info(f"SSH 认证:   {'密码' if ssh_password else '密钥'}")
    logger.info(f"使用模型:   {args.model}")
    logger.info(f"API Key:    {api_key[:20]}...")
    logger.info("-" * 60)

    # ========== 2. 初始化诊断工具 ==========
    logger.info("[1/4] 初始化诊断工具...")
    tool = DiagnosticsTool(
        ssh_user=ssh_user,
        ssh_password=ssh_password,
        ssh_port=args.ssh_port,
        logger=logger
    )
    logger.info(f"  允许命令: {len(tool.get_allowed_commands())} 个")

    # ========== 3. 收集证据 ==========
    evidence = None
    if not args.no_collect:
        logger.info("[2/4] 收集系统证据...")
        evidence = collect_evidence(args.host, args.service, tool, logger)
        logger.info(f"  收集完成: {len(evidence['snapshots'])} 个快照")
    else:
        logger.info("[2/4] 跳过证据收集")
        evidence = {
            "meta": {"host": args.host, "service": args.service, "timestamp": now_iso()},
            "snapshots": [],
        }

    evidence_text = json.dumps(evidence, ensure_ascii=False, indent=2)
    logger.debug(f"  证据数据长度: {len(evidence_text)} 字符")

    # ========== 4. 多轮迭代诊断 ==========
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    max_rounds = args.max_rounds
    result = None
    java_pid = None

    for round_num in range(1, max_rounds + 1):
        logger.info(f"[3/4] 第 {round_num} 轮分析...")

        prompt = build_prompt(args.host, args.service, args.window_minutes, round_num)

        try:
            response_text = call_qianwen_api(
                prompt=prompt,
                evidence=evidence_text,
                model=args.model,
                api_key=api_key,
                base_url=base_url,
                logger=logger,
            )
        except Exception as e:
            logger.error(f"  大模型调用失败: {e}")
            sys.exit(1)

        # 解析结果
        try:
            result = extract_json(response_text)
            logger.info(f"  第 {round_num} 轮 JSON 解析成功")
        except ValueError as e:
            logger.error(f"  JSON 解析失败: {e}")
            if round_num == 1:
                logger.info("  原始响应:")
                print(response_text)
            sys.exit(1)

        # 提取 Java PID（用于后续命令）
        for snap in evidence.get("snapshots", []):
            if snap.get("cmd_id") == "jps":
                output = snap.get("output", "")
                import re
                match = re.search(r'(\d+)\s', output)
                if match:
                    java_pid = match.group(1)
                    logger.debug(f"  发现 Java PID: {java_pid}")

        # 检查是否有 next_checks
        next_checks = result.get("next_checks", [])
        if not next_checks:
            logger.info(f"  第 {round_num} 轮完成，无需进一步检查")
            break

        if round_num >= max_rounds:
            logger.info(f"  达到最大轮数 ({max_rounds})，停止迭代")
            break

        # 执行 next_checks
        logger.info(f"  执行进一步检查 ({len(next_checks)} 条)...")
        new_snapshots = []

        for check in next_checks:
            cmd_id = check.get("cmd_id")
            purpose = check.get("purpose", "N/A")

            if not cmd_id:
                continue

            logger.info(f"    执行: {cmd_id} - {purpose}")

            # 替换 pid 参数
            pid = java_pid if cmd_id in ["jstat", "jstack", "jcmd_threads"] else None
            result_cmd = tool.execute_by_name(args.host, cmd_id, service=args.service, pid=pid)

            new_snapshots.append({
                "cmd_id": cmd_id,
                "purpose": purpose,
                "output": result_cmd.get("output", "")[:2000],
                "elapsed_ms": result_cmd.get("elapsed_ms", 0),
            })

        # 将新证据加入
        if new_snapshots:
            evidence["snapshots"].extend(new_snapshots)
            evidence_text = json.dumps(evidence, ensure_ascii=False, indent=2)
            logger.info(f"  新增证据: {len(new_snapshots)} 条")

    # ========== 5. 最终结果处理 ==========
    logger.info("[4/4] 生成最终报告...")

    # Schema 校验
    schema = load_schema(args.evidence_schema)
    try:
        validate(instance=result, schema=schema)
        logger.info("  Schema 校验通过")
    except ValidationError as e:
        logger.warning(f"  Schema 校验警告: {e.path[-1]} - {e.message}")

    # 打印摘要
    if "hypothesis" in result:
        logger.info(f"  诊断假设: {len(result['hypothesis'])} 条")
        for h in result.get("hypothesis", []):
            logger.info(f"    - {h.get('category', 'unknown')}: {h.get('confidence', 'unknown')} 置信度")

    # ========== 6. 输出结果 ==========
    logger.info("-" * 60)

    result_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        output_path = args.output
        # 自动创建 report 目录
        if "/" not in output_path and "\\" not in output_path:
            os.makedirs("report", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            output_path = f"report/{timestamp}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result_json)
        logger.info(f"  报告已保存: {output_path}")
    else:
        print(result_json)

    logger.info("-" * 60)
    logger.info("诊断完成!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
