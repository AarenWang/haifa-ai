import json
import logging
import os
from typing import Any, Dict

from anthropic import Anthropic

logger = logging.getLogger(__name__)


def load_schema(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_report(evidence: Dict[str, Any], schema_path: str, model: str) -> Dict[str, Any]:
    """根据证据包生成最终诊断报告"""
    logger.debug(f"  加载报告 Schema: {schema_path}")

    auth_token = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    base_url = os.getenv("ANTHROPIC_BASE_URL")

    if not auth_token:
        raise ValueError("未找到 ANTHROPIC_API_KEY 或 ANTHROPIC_AUTH_TOKEN 环境变量")

    logger.debug(f"  使用模型: {model}")
    if base_url:
        logger.debug(f"  API Base URL: {base_url}")

    client = Anthropic(api_key=auth_token, base_url=base_url)
    schema = load_schema(schema_path)

    prompt = (
        "You are an SRE assistant. Generate a diagnosis report strictly following the given JSON schema. "
        "Use the evidence pack provided. Do not add extra keys.\n\n"
        f"Evidence pack:\n{json.dumps(evidence, ensure_ascii=False)}"
    )

    logger.debug("  发送请求到 Anthropic API...")
    response = client.messages.create(
        model=model,
        max_tokens=1500,
        output_format={
            "type": "json_schema",
            "json_schema": {
                "name": "diagnosis_report",
                "strict": True,
                "schema": schema,
            },
        },
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text if response.content else "{}"
    logger.debug("  API 响应接收完成")

    report = json.loads(text)
    if "summary" in report:
        logger.info(f"  诊断摘要: {report['summary'][:80]}...")
    return report
