"""
SRE MCP Server - 只读诊断工具服务器

提供通过 SSH 执行只读诊断命令的 MCP 工具。

环境变量:
    OPS_AGENT_LOG_LEVEL     - 日志级别 (DEBUG, INFO, WARNING, ERROR)
    OPS_AGENT_AUDIT_LOG     - 审计日志文件路径
    SRE_SSH_USER            - SSH 用户名
    SRE_SSH_PASSWORD        - SSH 密码
    SRE_SSH_PORT            - SSH 端口 (默认: 22)
"""

import logging
import os
import shlex
import subprocess
import sys
import time
from typing import Optional, Dict, Any

from mcp.server.fastmcp import FastMCP

from redaction import redact, hash_text
from audit import write_audit, now_iso

# ==================== 日志配置 ====================

LOG_LEVEL = os.getenv("OPS_AGENT_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s [%(levelname)s] [MCP-SRE] %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

# 配置根日志记录器
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("sre-agent")

# ==================== MCP 服务器 ====================

mcp = FastMCP("sre-tools")

# ==================== 配置 ====================

READ_ONLY_COMMANDS = {
    # 基础系统信息
    "uptime": "uptime",
    "loadavg": "cat /proc/loadavg",
    "top": "top -b -n 1 | head -n 40",
    "ps_cpu": "ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%cpu | head -n 15",
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

AUDIT_LOG = os.getenv("OPS_AGENT_AUDIT_LOG", "")
SRE_SSH_USER = os.getenv("SRE_SSH_USER", "")
SRE_SSH_PASSWORD = os.getenv("SRE_SSH_PASSWORD", "")
SRE_SSH_PORT = int(os.getenv("SRE_SSH_PORT", "22") or "22")

# ==================== SSH 执行 ====================

def run_ssh(host: str, remote_cmd: str, timeout: int = 20) -> str:
    """
    使用 subprocess 执行 SSH 命令（密钥认证）

    使用登录 shell (bash -l) 确保加载用户环境变量（PATH 等）
    """
    target = host
    if SRE_SSH_USER and "@" not in host:
        target = f"{SRE_SSH_USER}@{host}"

    # 使用登录 shell 加载环境变量
    wrapped_cmd = f"bash -l -c {shlex.quote(remote_cmd)}"
    cmd = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {SRE_SSH_PORT} {shlex.quote(target)} {shlex.quote(wrapped_cmd)}"

    logger.debug("ssh_exec start: target=%s, cmd=%s", target, remote_cmd[:100])
    logger.info("[SSH] 开始执行: host=%s cmd_id=%s", target, remote_cmd.split()[0])

    start_time = time.time()
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        elapsed = time.time() - start_time

        out = (p.stdout or "")
        if p.stderr:
            logger.warning("[SSH] stderr: host=%s, stderr=%s", target, p.stderr[:200])
            out += "\n[stderr]\n" + p.stderr

        logger.info("[SSH] 完成: host=%s, rc=%d, elapsed=%.2fs, output_bytes=%d",
                   target, p.returncode, elapsed, len(out))

        return out[:12000]

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.error("[SSH] 超时: host=%s, timeout=%ds, elapsed=%.2fs", target, timeout, elapsed)
        return f"命令执行超时 ({timeout}秒)"

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("[SSH] 异常: host=%s, err=%s, elapsed=%.2fs", target, e, elapsed)
        return f"SSH 执行错误: {type(e).__name__}: {e}"


def run_ssh_paramiko(host: str, remote_cmd: str, timeout: int = 20) -> str:
    """
    使用 paramiko 执行 SSH 命令（密码认证）

    使用登录 shell (bash -l) 确保加载用户环境变量（PATH 等）
    """
    try:
        import paramiko
    except Exception as e:
        logger.error("[SSH] paramiko 导入失败: %s", e)
        return f"paramiko not available: {e}"

    username = SRE_SSH_USER or "root"
    password = SRE_SSH_PASSWORD
    port = SRE_SSH_PORT

    logger.debug("paramiko_exec start: host=%s, user=%s, cmd=%s", host, username, remote_cmd[:100])
    logger.info("[SSH] 开始执行: host=%s@%s cmd_id=%s (密码认证)", username, host, remote_cmd.split()[0])

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    start_time = time.time()
    try:
        connect_start = time.time()
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password if password else None,
            look_for_keys=True,
            allow_agent=True,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
        )
        connect_elapsed = time.time() - connect_start
        logger.debug("[SSH] 连接耗时: %.2fs", connect_elapsed)

        # 使用登录 shell
        wrapped_cmd = f"bash -l -c {shlex.quote(remote_cmd)}"
        stdin, stdout, stderr = client.exec_command(wrapped_cmd, timeout=timeout)
        _ = stdin

        out = stdout.read().decode("utf-8", errors="replace") if stdout else ""
        err = stderr.read().decode("utf-8", errors="replace") if stderr else ""

        if err:
            logger.warning("[SSH] stderr: host=%s, stderr=%s", host, err[:200])
            out += "\n[stderr]\n" + err

        elapsed = time.time() - start_time
        logger.info("[SSH] 完成: host=%s, elapsed=%.2fs, output_bytes=%d", host, elapsed, len(out))

        return out[:12000]

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("[SSH] 异常: host=%s, err=%s, elapsed=%.2fs", host, e, elapsed)
        return f"ssh_error: {type(e).__name__}: {e}"

    finally:
        try:
            client.close()
        except Exception:
            pass


# ==================== 命令构建 ====================

def build_command(cmd_id: str, service: Optional[str], pid: Optional[str]) -> str:
    """根据 cmd_id 构建实际执行的命令"""
    if cmd_id not in READ_ONLY_COMMANDS:
        logger.warning("[BUILD] 命令不在白名单: cmd_id=%s", cmd_id)
        raise ValueError(f"cmd_id not allowed: {cmd_id}")

    template = READ_ONLY_COMMANDS[cmd_id]

    if "{service}" in template and not service:
        logger.warning("[BUILD] 命令缺少 service 参数: cmd_id=%s", cmd_id)
        raise ValueError("service is required for this cmd_id")

    if "{pid}" in template and not pid:
        logger.warning("[BUILD] 命令缺少 pid 参数: cmd_id=%s", cmd_id)
        raise ValueError("pid is required for this cmd_id")

    cmd = template.format(service=service or "", pid=pid or "")
    logger.debug("[BUILD] 构建命令: cmd_id=%s -> %s", cmd_id, cmd)

    return cmd


# ==================== MCP 工具 ====================

@mcp.tool()
def sre_diag(host: str, cmd_id: str, service: Optional[str] = None,
             pid: Optional[str] = None) -> Dict[str, Any]:
    """
    Run a read-only diagnostic command on a host via SSH.

    Args:
        host: 目标主机地址
        cmd_id: 命令ID（必须在白名单中）
        service: 服务名称（某些命令需要）
        pid: 进程ID（某些命令需要）

    Returns:
        包含命令执行结果和审计信息的字典
    """
    started_at = now_iso()
    start_ts = time.time()

    logger.info("=" * 60)
    logger.info("[DIAG] 开始诊断: host=%s, cmd_id=%s, service=%s, pid=%s",
               host, cmd_id, service, pid)

    try:
        # 构建命令
        cmd = build_command(cmd_id, service, pid)

        # 执行命令
        if SRE_SSH_PASSWORD:
            logger.debug("[DIAG] 使用密码认证 (paramiko)")
            raw = run_ssh_paramiko(host, cmd)
        else:
            logger.debug("[DIAG] 使用密钥认证 (ssh)")
            raw = run_ssh(host, cmd)

        # 脱敏处理
        logger.debug("[DIAG] 开始脱敏处理...")
        redacted, rules, replaced = redact(raw)
        if replaced > 0:
            logger.info("[DIAG] 脱敏: 替换 %d 处, 规则=%s", replaced, rules)

        elapsed_ms = int((time.time() - start_ts) * 1000)

        # 审计记录
        record = {
            "id": f"{cmd_id}-{int(start_ts)}",
            "cmd_id": cmd_id,
            "cmd": cmd,
            "started_at": started_at,
            "elapsed_ms": elapsed_ms,
            "output_hash": hash_text(redacted),
            "redacted_fields": rules,
        }

        # 写入审计日志
        if AUDIT_LOG:
            try:
                write_audit(AUDIT_LOG, record)
                logger.info("[AUDIT] 已写入: path=%s", AUDIT_LOG)
            except Exception as e:
                logger.error("[AUDIT] 写入失败: %s", e)

        logger.info("[DIAG] 完成: cmd_id=%s, elapsed_ms=%d, output_bytes=%d",
                   cmd_id, elapsed_ms, len(redacted))
        logger.info("=" * 60)

        return {
            "ok": True,
            "cmd_id": cmd_id,
            "cmd": cmd,
            "started_at": started_at,
            "elapsed_ms": elapsed_ms,
            "redaction": {
                "applied": True,
                "rules": rules,
                "replaced_count": replaced
            },
            "output_redacted": redacted,
            "audit": record,
        }

    except ValueError as e:
        logger.error("[DIAG] 参数错误: %s", e)
        return {
            "ok": False,
            "error": str(e),
            "error_type": "ValueError"
        }
    except Exception as e:
        logger.error("[DIAG] 执行异常: %s", e)
        return {
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


@mcp.tool()
def sre_list_commands() -> Dict[str, Any]:
    """
    列出所有可用的诊断命令

    Returns:
        包含所有可用命令ID及其对应命令的字典
    """
    logger.info("[LIST] 查询可用命令: 总数=%d", len(READ_ONLY_COMMANDS))

    return {
        "ok": True,
        "count": len(READ_ONLY_COMMANDS),
        "commands": {
            cmd_id: {
                "command": template,
                "requires_pid": "{pid}" in template,
                "requires_service": "{service}" in template,
            }
            for cmd_id, template in READ_ONLY_COMMANDS.items()
        }
    }


@mcp.tool()
def sre_get_status() -> Dict[str, Any]:
    """
    获取 MCP 服务器状态

    Returns:
        包含服务器配置和状态信息的字典
    """
    logger.debug("[STATUS] 查询服务器状态")

    return {
        "ok": True,
        "server": "sre-tools",
        "version": "1.0.0",
        "config": {
            "ssh_user": SRE_SSH_USER or "(default)",
            "ssh_port": SRE_SSH_PORT,
            "ssh_auth": "password" if SRE_SSH_PASSWORD else "key",
            "audit_log": AUDIT_LOG or "(disabled)",
            "log_level": LOG_LEVEL,
        },
        "capabilities": {
            "total_commands": len(READ_ONLY_COMMANDS),
            "supports_password_auth": True,
            "supports_key_auth": True,
        }
    }


# ==================== 启动 ====================

def print_startup_info():
    """打印启动信息"""
    logger.info("=" * 60)
    logger.info("SRE MCP Server 启动")
    logger.info("配置:")
    logger.info("  - SSH 用户: %s", SRE_SSH_USER or "(default)")
    logger.info("  - SSH 端口: %s", SRE_SSH_PORT)
    logger.info("  - SSH 认证: %s", "密码" if SRE_SSH_PASSWORD else "密钥")
    logger.info("  - 审计日志: %s", AUDIT_LOG or "(禁用)")
    logger.info("  - 日志级别: %s", LOG_LEVEL)
    logger.info("  - 可用命令: %d", len(READ_ONLY_COMMANDS))
    logger.info("=" * 60)


if __name__ == "__main__":
    print_startup_info()
    logger.info("MCP 服务器运行中...")
    mcp.run()
