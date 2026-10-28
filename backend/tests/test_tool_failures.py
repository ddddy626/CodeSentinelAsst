import subprocess

from app import tools


def test_tool_findings_exit_one_is_not_execution_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(tools.shutil, "which", lambda command: command)
    monkeypatch.setattr(tools.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 1, '[{"code":"F401"}]', ""))
    data, gap = tools._run_json_tool(["ruff", "check", "--output-format", "json"],
                                     tmp_path / "x.py")
    assert gap is None
    assert data[0]["code"] == "F401"


def test_tool_process_error_marks_coverage_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(tools.shutil, "which", lambda command: command)
    monkeypatch.setattr(tools.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 2, '{"results": []}', "bad config"))
    data, gap = tools._run_json_tool(["semgrep", "scan"], tmp_path / "x.py")
    assert data is None
    assert "退出码 2" in gap


def test_invalid_json_marks_coverage_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(tools.shutil, "which", lambda command: command)
    monkeypatch.setattr(tools.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 0, "not JSON", ""))
    data, gap = tools._run_json_tool(["ruff", "check"], tmp_path / "x.py")
    assert data is None
    assert "JSONDecodeError" in gap
