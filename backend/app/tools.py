"""Read-only source analyzers and optional scanner adapters."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .flow import scan_dynamic_exec
from .schemas import FILE_LANGUAGES, Language

TOOL_MESSAGES_ZH = {
    "F401": "导入后未使用",
    "I001": "导入语句顺序或格式不符合规范",
    "B307": "使用可能不安全的 eval()",
    "B311": "伪随机数不适合安全用途",
    "codesentinel.python.dynamic-exec": "动态执行需要可信且受约束的输入",
    "codesentinel.web.dynamic-eval": "动态执行需要可信且受约束的输入",
    "codesentinel.web.inner-html": "直接写入 innerHTML 可能引入脚本注入",
    "codesentinel.java.process-exec": "执行外部命令需核查输入",
    "codesentinel.java.spring-wildcard-cors": "Spring 跨域来源配置为通配符",
    "codesentinel.go.process-exec": "执行外部命令需核查输入",
    "codesentinel.c.system-call": "系统命令调用需核查输入",
    "codesentinel.cpp.system-call": "系统命令调用需核查输入",
    "codesentinel.csharp.process-start": "启动进程需核查输入",
    "codesentinel.rust.process-command": "启动进程需核查输入",
    "codesentinel.php.dynamic-eval": "动态执行需核查输入",
    "codesentinel.ruby.dynamic-eval": "动态执行需核查输入",
    "codesentinel.kotlin.process-exec": "执行外部命令需核查输入",
    "codesentinel.swift.force-try": "强制 try 可能导致程序终止",
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


def _config_review(source: str, language: str) -> tuple[list[ToolDraft], list[str], list[str]]:
    findings: list[ToolDraft] = []
    if language == "sql":
        masked = re.sub(r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"",
                        lambda item: re.sub(r"[^\r\n]", " ", item.group()), source, flags=re.S)
        for match in re.finditer(r"\b(?:DELETE\s+FROM|UPDATE)\b[^;]*;", masked, re.I | re.S):
            statement = match.group()
            if re.search(r"\bWHERE\b", statement, re.I):
                continue
            line = source.count("\n", 0, match.start()) + 1
            findings.append(ToolDraft("codesentinel.sql.unbounded-write", "更新或删除语句缺少 WHERE 条件",
                "该语句可能影响整张表；仅凭单文件无法确认是否有意如此。", line, "S2", "SQL 静态规则",
                f"第 {line} 行开始的语句未包含 WHERE 条件", "确认影响范围；若只需部分记录，请添加明确的 WHERE 条件。"))
    elif language == "xml":
        for match in re.finditer(r"<(?:[\w.-]+:)?password\s*>([^<]+)</(?:[\w.-]+:)?password\s*>", source, re.I):
            value = match.group(1).strip()
            if not value or value.startswith(("${", "#{", "ENC(")):
                continue
            line = source.count("\n", 0, match.start()) + 1
            findings.append(ToolDraft("codesentinel.xml.password", "XML 中可能包含明文口令",
                "配置文件中的口令值可能进入版本库或构建产物。", line, "S2", "XML 静态规则",
                f"第 {line} 行的 password 元素有非占位值；值已隐藏", "改用受保护的环境变量或凭据存储。"))
        for match in re.finditer(r"<!DOCTYPE[^>]+\b(?:SYSTEM|PUBLIC)\b[^>]*>", source, re.I | re.S):
            line = source.count("\n", 0, match.start()) + 1
            findings.append(ToolDraft("codesentinel.xml.external-doctype", "XML 声明了外部 DTD",
                "外部 DTD 的实际影响取决于下游解析器配置。", line, "S2", "XML 静态规则",
                f"第 {line} 行声明了外部 DTD", "确认消费该文件的解析器已禁用外部实体解析。"))
    else:
        parents: list[tuple[int, str]] = []
        for line_number, line in enumerate(source.splitlines(), 1):
            if not line.strip() or line.lstrip().startswith(("#", "!")):
                continue
            if language == "yaml":
                entry = re.match(r"^(\s*)([\w.-]+)\s*:\s*(.*?)\s*$", line)
                if not entry:
                    continue
                indent, key, value = len(entry.group(1)), entry.group(2), entry.group(3)
                while parents and parents[-1][0] >= indent:
                    parents.pop()
                path = ".".join([item[1] for item in parents] + [key]).lower()
                if not value:
                    parents.append((indent, key))
                    continue
            else:
                entry = re.match(r"^\s*([\w.-]+)\s*[=:]\s*(.*?)\s*$", line)
                if not entry:
                    continue
                path, value = entry.group(1).lower(), entry.group(2)
            clean = value.strip().strip("\"'").strip()
            if (path.endswith((".password", ".secret", ".token")) or path in {"password", "secret", "token"}) \
                    and clean and clean.lower() not in {"null", "~"} \
                    and not clean.startswith(("${", "#{", "ENC(")):
                findings.append(ToolDraft("codesentinel.config.plaintext-secret", "配置中可能包含明文凭据",
                    "配置值可能进入版本库或构建产物；已隐藏具体值。", line_number, "S2", "配置静态规则",
                    f"第 {line_number} 行的 {path} 有非占位值；值已隐藏", "改用环境变量或受保护的凭据存储。"))
            if path == "management.endpoints.web.exposure.include" and "*" in clean:
                findings.append(ToolDraft("codesentinel.spring.actuator-exposure", "Actuator 端点配置为全部暴露",
                    "是否可被外部访问仍取决于网络和安全配置。", line_number, "S2", "配置静态规则",
                    f"第 {line_number} 行设置 {path} 包含 *", "只开放必需端点，并核查认证与网络访问限制。"))
    return findings, [f"{language.upper()} 单文件静态规则"], ["未运行项目、数据库或 Spring Boot 服务；跨文件与运行时条件未验证"]


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


def run_tools(source: str, language: Language = "python") -> tuple[list[ToolDraft], list[str], list[str]]:
    if language not in set(FILE_LANGUAGES.values()):
        raise ValueError("不支持的编程语言")
    if language in {"sql", "xml", "yaml", "properties"}:
        return _config_review(source, language)
    drafts, ast_gap = _ast_review(source) if language == "python" else ([], None)
    completed = ["Python AST"] if language == "python" and ast_gap is None else []
    gaps = [ast_gap] if ast_gap else []
    with tempfile.TemporaryDirectory(prefix="codesentinel-") as temporary:
        suffix = next(suffix for suffix, name in FILE_LANGUAGES.items() if name == language)
        path = Path(temporary) / f"source{suffix}"
        path.write_text(source, encoding="utf-8")
        commands = [
            ("Ruff", ["ruff", "check", "--output-format", "json"]),
            ("Bandit", ["bandit", "-f", "json", "-q"]),
        ] if language == "python" else []
        rules_dir = Path(__file__).parent.parent / "rules"
        if language == "python":
            semgrep_rules = os.getenv("CODESENTINEL_SEMGREP_RULES", "").strip()
        elif language in {"javascript", "typescript"}:
            semgrep_rules = os.getenv("CODESENTINEL_WEB_SEMGREP_RULES", "").strip() or str(rules_dir / "web-v1.yaml")
        else:
            semgrep_rules = os.getenv("CODESENTINEL_MAINSTREAM_SEMGREP_RULES", "").strip() or str(rules_dir / "mainstream-v1.yaml")
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
