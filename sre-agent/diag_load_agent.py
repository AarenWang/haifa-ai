import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from report_generator import generate_report


def ensure_api_key_env() -> None:
    """
    确保 ANTHROPIC_API_KEY 环境变量已设置。
    如果只有 ANTHROPIC_AUTH_TOKEN，则自动复制给 ANTHROPIC_API_KEY。
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")

    if not api_key and auth_token:
        os.environ["ANTHROPIC_API_KEY"] = auth_token
        logging.getLogger(__name__).debug("  已将 ANTHROPIC_AUTH_TOKEN 复制到 ANTHROPIC_API_KEY")

    base_url = os.getenv("ANTHROPIC_BASE_URL")
    if base_url:
        logging.getLogger(__name__).debug(f"  API Base URL: {base_url}")


def setup_logging(verbose: bool = False) -> None:
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


def build_prompt(host: str, service: str, window_minutes: int) -> str:
    return f"""
You are an SRE diagnosing high Linux load on a production host running a Java service.

Constraints:
- Read-only diagnosis ONLY. Do NOT restart services, kill processes, edit files, or change system settings.
- Use the MCP tool `sre_diag(host, cmd_id, service?, pid?)` only. Do NOT run arbitrary shell commands.
- Collect evidence first, then form hypotheses, then propose next verification steps.
- Always cite which command outputs support each conclusion.

Target host: {host}
Target service: {service}
Collection window: {window_minutes} minutes

Steps (use cmd_id list below):
1) uptime, loadavg
2) top snapshot, ps cpu/mem
3) vmstat, iostat, free, df
4) jps to find Java pid, then jstat + jstack or jcmd_threads
5) journalctl for last {window_minutes} minutes

Allowed cmd_id:
- uptime, loadavg, top, ps_cpu, ps_mem, vmstat, iostat, free, df, jps, jstat, jstack, jcmd_threads, journalctl

Return ONLY valid JSON with keys:
- meta: {"host","service","timestamp"}
- snapshots: [{"cmd_id","signal","summary","audit_ref"}]
- hypothesis: [{"category","confidence","why","evidence_refs"}]
- next_checks: [{"cmd_id","purpose"}]
"""


def extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(match.group(0))


def load_schema(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def main() -> None:
    ap = argparse.ArgumentParser(description="SRE Agent - 生产只读诊断智能体")
    ap.add_argument("--host", required=True, help="目标主机地址")
    ap.add_argument("--service", required=True, help="目标服务名称")
    ap.add_argument("--window-minutes", type=int, default=30, help="诊断时间窗口（分钟）")
    ap.add_argument("--evidence-schema", default="evidence_schema.json", help="证据包 Schema 文件")
    ap.add_argument("--report-schema", default="report_schema.json", help="报告 Schema 文件")
    ap.add_argument("--final-report", action="store_true", help="生成最终诊断报告")
    ap.add_argument("--model", default="claude-sonnet-4.5", help="使用的模型")
    ap.add_argument("-v", "--verbose", action="store_true", help="详细日志输出")
    args = ap.parse_args()

    logger = setup_logging(args.verbose)

    # 确保环境变量正确设置
    ensure_api_key_env()

    # ========== 1. 打印诊断任务信息 ==========
    logger.info("=" * 60)
    logger.info("SRE Agent - 只读诊断任务启动")
    logger.info("=" * 60)
    logger.info(f"目标主机:   {args.host}")
    logger.info(f"目标服务:   {args.service}")
    logger.info(f"时间窗口:   {args.window_minutes} 分钟")
    logger.info(f"输出模式:   {'最终报告' if args.final_report else '证据包'}")
    logger.info(f"使用模型:   {args.model}")
    logger.info("-" * 60)

    # ========== 2. 初始化 MCP 服务器 ==========
    logger.info("[1/6] 初始化 MCP 服务器...")

    # 获取当前 Python 解释器路径（确保使用 venv 中的 Python）
    current_python = sys.executable
    logger.debug(f"  使用 Python: {current_python}")
    logger.debug(f"  MCP 服务: sre -> mcp_server_sre.py")

    # 构建环境变量，确保子进程能使用自定义 API endpoint
    api_env = {
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN", ""),
        "ANTHROPIC_BASE_URL": os.getenv("ANTHROPIC_BASE_URL", ""),
    }
    if api_env["ANTHROPIC_API_KEY"]:
        logger.debug(f"  API Key: {api_env['ANTHROPIC_API_KEY'][:20]}...")
    if api_env["ANTHROPIC_BASE_URL"]:
        logger.info(f"  API Base URL: {api_env['ANTHROPIC_BASE_URL']}")

    options = ClaudeAgentOptions(
        mcp_servers={
            "sre": {
                "command": [current_python, "mcp_server_sre.py"],
            }
        },
        env=api_env,
    )
    logger.info("  MCP 服务器配置完成")

    # ========== 3. 构建 Prompt ==========
    logger.info("[2/6] 构建诊断 Prompt...")
    prompt = build_prompt(args.host, args.service, args.window_minutes)
    logger.debug(f"  Prompt 长度: {len(prompt)} 字符")

    # ========== 4. 发送查询并接收响应 ==========
    logger.info("[3/6] 连接到 Claude Agent SDK...")
    try:
        async with ClaudeSDKClient(options=options) as client:
            logger.info("  连接成功，发送诊断请求...")
            logger.info("[4/6] 等待 AI 分析（可能需要 10-30 秒）...")

            await client.query(prompt)

            content = ""
            chunk_count = 0
            async for msg in client.receive_response():
                content += str(msg)
                chunk_count += 1
                if chunk_count % 10 == 0:
                    logger.debug(f"  已接收 {chunk_count} 个响应块...")

            logger.info(f"  响应接收完成，共 {chunk_count} 个块")
            logger.debug(f"  响应内容长度: {len(content)} 字符")

    except Exception as e:
        logger.error(f"Claude SDK 通信失败: {e}")
        logger.error("  请检查: 1) Claude Code 是否已登录 2) 网络连接")
        sys.exit(1)

    # ========== 5. 解析和校验 ==========
    logger.info("[5/6] 解析诊断结果...")

    # 5.1 提取 JSON
    try:
        evidence = extract_json(content)
        logger.info("  JSON 解析成功")
    except json.JSONDecodeError as e:
        logger.error(f"  JSON 解析失败: {e}")
        logger.debug("  原始响应:")
        logger.debug(content)
        sys.exit(1)

    # 5.2 Schema 校验
    logger.debug(f"  加载 Schema: {args.evidence_schema}")
    schema = load_schema(args.evidence_schema)
    try:
        validate(instance=evidence, schema=schema)
        logger.info("  Schema 校验通过")
    except ValidationError as e:
        logger.error(f"  Schema 校验失败: {e.path[-1]} - {e.message}")
        print(json.dumps({"error": "evidence_schema_validation_failed", "detail": str(e)}, ensure_ascii=False))
        sys.exit(1)

    # 打印证据摘要
    if "snapshots" in evidence:
        logger.info(f"  收集证据: {len(evidence['snapshots'])} 条")
    if "hypothesis" in evidence:
        logger.info(f"  诊断假设: {len(evidence['hypothesis'])} 条")

    # ========== 6. 输出结果 ==========
    logger.info("[6/6] 输出结果...")
    logger.info("-" * 60)

    if not args.final_report:
        # 输出证据包
        result = json.dumps(evidence, ensure_ascii=False, indent=2)
        print(result)
        logger.debug(f"  输出长度: {len(result)} 字符")
    else:
        # 生成最终报告
        logger.info("  生成最终诊断报告...")
        try:
            report = generate_report(evidence, args.report_schema, args.model)
            logger.info("  报告生成完成")
            result = json.dumps(report, ensure_ascii=False, indent=2)
            print(result)
        except Exception as e:
            logger.error(f"  报告生成失败: {e}")
            logger.error("  请检查 ANTHROPIC_API_KEY 环境变量")
            sys.exit(1)

    # ========== 完成 ==========
    logger.info("-" * 60)
    logger.info("诊断任务完成!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
