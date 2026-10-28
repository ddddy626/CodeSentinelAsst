"""Read-only source analyzers and optional scanner adapters."""

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .flow import scan_dynamic_exec

TOOL_MESSAGES_ZH = {
    "F401": "导入后未使用",
    "I001": "导入语句顺序或格式不符合规范",
    "B307": "使用可能不安全的 eval()",
    "B311": "伪随机数不适合安全用途",
    "codesentinel.python.dynamic-exec": "动态执行需要可信且受约束的输入",
    "codesentinel.web.dynamic-eval": "动态执行需要可信且受约束的输入",
    "codesentinel.web.inner-html": "直接写入 innerHTML 可能引入脚本注入",
}


@dataclass
class ToolDraft:
    rule_id: str
    title: str
    explanation: str
    line: int
    severity: str
    tool: str
    evidence: str
    suggestion: str
    trigger_path: str | None = None


def _ast_review(source: str) -> tuple[list[ToolDraft], str | None]:
    try:
        sinks = scan_dynamic_exec(source)
    except SyntaxError as exc:
        return [], f"AST 无法解析源码：第 {exc.lineno or '?'} 行语法错误"
    findings = []
    for sink in sinks:
        trigger = sink.trigger
        evidence = (
            "静态可能路径：" + " → ".join(trigger.steps)
            if trigger else f"第 {sink.line} 行调用 {sink.name}()；文件内未找到受控输入路径"
        )
        findings.append(ToolDraft(
            "SEC-DYNAMIC-EXEC", f"动态执行：{sink.name}",
            (
                "文件内存在从 input() 到动态执行的静态可能路径；仍需核查实际可达性。"
                if trigger else
                "动态执行调用的输入来源在当前文件中未得到确认。"
            ),
            sink.line, "S1" if trigger else "S2", "ast",
            evidence,
            "避免动态执行；若不可避免，先验证输入来源及允许的表达式。",
            evidence if trigger else None,
        ))
    return findings, None


def _run_json_tool(command: list[str], path: Path) -> tuple[dict | None, str | None]:
    executable = shutil.which(command[0])
    if not executable:
        return None, f"{command[0]} 未安装"
    try:
        result = subprocess.run(
            [executable, *command[1:], str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=45 if command[0] == "semgrep" else 20, check=False,
            env={**os.environ, "PYTHONUTF8": "1"} if command[0] == "semgrep" else None,
        )
        if not result.stdout.strip():
            return None, f"{command[0]} 无法完成（退出码 {result.returncode}）：{result.stderr[:160]}"
        data = json.loads(result.stdout)
        if result.returncode > 1:
            return None, f"{command[0]} 执行失败（退出码 {result.returncode}）：{result.stderr[:160]}"
        if isinstance(data, dict) and data.get("errors"):
            return None, f"{command[0]} 报告扫描错误：{str(data['errors'])[:160]}"
        return data, None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return None, f"{command[0]} 无法完成：{type(exc).__name__}"


def run_tools(source: str, language: str = "python") -> tuple[list[ToolDraft], list[str], list[str]]:
    if language not in {"python", "javascript", "typescript"}:
        raise ValueError("不支持的编程语言")
    drafts, ast_gap = _ast_review(source) if language == "python" else ([], None)
    completed = ["Python AST"] if language == "python" and ast_gap is None else []
    gaps = [ast_gap] if ast_gap else []
    with tempfile.TemporaryDirectory(prefix="codesentinel-") as temporary:
        suffix = {"python": ".py", "javascript": ".js", "typescript": ".ts"}[language]
        path = Path(temporary) / f"source{suffix}"
        path.write_text(source, encoding="utf-8")
        commands = [
            ("Ruff", ["ruff", "check", "--output-format", "json"]),
            ("Bandit", ["bandit", "-f", "json", "-q"]),
        ] if language == "python" else []
        semgrep_rules = (os.getenv("CODESENTINEL_SEMGREP_RULES", "").strip()
                         if language == "python" else
                         os.getenv("CODESENTINEL_WEB_SEMGREP_RULES", "").strip()
                         or str(Path(__file__).parent.parent / "rules" / "web-v1.yaml"))
        if semgrep_rules and Path(semgrep_rules).is_file():
            commands.append((
                "Semgrep", ["semgrep", "scan", "--config", semgrep_rules,
                            "--json", "--no-git-ignore", "--metrics=off"],
            ))
        else:
            gaps.append("Semgrep 规则文件未配置")
        for name, command in commands:
            data, gap = _run_json_tool(command, path)
            if gap:
                gaps.append(gap)
                continue
            rows = data if name == "Ruff" else data.get("results", []) if isinstance(data, dict) else None
            if not isinstance(rows, list):
                gaps.append(f"{name} 输出格式无效")
                continue
            completed.append(name)
            for item in rows[:100]:
                try:
                    if name == "Ruff":
                        code = item["code"]
                        line = item["location"]["row"]
                        severity = "S3"
                    elif name == "Bandit":
                        code = item["test_id"]
                        line = item["line_number"]
                        severity = {"HIGH": "S1", "MEDIUM": "S2", "LOW": "S3"}.get(
                            str(item.get("issue_severity", "")).upper(), "S3",
                        )
                    else:
                        code = item["check_id"]
                        line = item["start"]["line"]
                        severity = {"ERROR": "S1", "WARNING": "S2", "INFO": "S3"}.get(
                            str(item["extra"].get("severity", "")).upper(), "S3",
                        )
                    label = next((text for rule, text in TOOL_MESSAGES_ZH.items()
                                  if str(code).endswith(rule)), None)
                    title = label or f"{name} 报告规则 {code}"
                    explanation = (f"第 {line} 行：{title}。" if label
                                   else f"第 {line} 行触发 {name} 规则 {code}；原始诊断保留在证据中。")
                    drafts.append(ToolDraft(
                        str(code), title, explanation, int(line),
                        severity, name,
                        json.dumps(item, ensure_ascii=False)[:2000], "检查该工具发现并修正相应代码。",
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
    return drafts, completed, gaps
