"""Optional OpenAI-compatible chat adapter. Never executes reviewed source."""

import json
from pathlib import Path
from urllib import request

from . import config

PROMPT = (Path(__file__).parent / "prompts" / "review.md").read_text(encoding="utf-8")
ARCHITECT_PROMPT = (Path(__file__).parent / "prompts" / "architect.md").read_text(encoding="utf-8")


def _request_json(prompt: str, content: str) -> dict:
    payload = {
        "model": config.LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
    }
    req = request.Request(
        config.LLM_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}",
                 "Content-Type": "application/json"}, method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        body = json.load(response)
    return json.loads(body["choices"][0]["message"]["content"])


def review_source(source: str) -> tuple[list[dict], str | None]:
    if not (config.LLM_API_URL and config.LLM_API_KEY and config.LLM_MODEL):
        return [], "LLM 未配置；仅运行本地静态检查"

    try:
        parsed = _request_json(PROMPT, "Python source:\n" + source)
        findings = parsed["findings"]
        if not isinstance(findings, list):
            raise ValueError("findings must be a list")
        return [item for item in findings[:12] if isinstance(item, dict)], None
    except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
        return [], f"LLM 输出不可用：{type(exc).__name__}"


def architect_review(source: str, findings: list[dict]) -> tuple[list[dict], str | None]:
    if not (config.LLM_API_URL and config.LLM_API_KEY and config.LLM_MODEL):
        return [], "架构师模型未配置"
    try:
        parsed = _request_json(ARCHITECT_PROMPT,
            json.dumps({"source": source, "findings": findings[:12]}, ensure_ascii=False))
        assessments = parsed["assessments"]
        if not isinstance(assessments, list):
            raise ValueError("assessments must be a list")
        return [item for item in assessments[:12] if isinstance(item, dict)], None
    except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
        return [], f"架构师模型输出不可用：{type(exc).__name__}"
