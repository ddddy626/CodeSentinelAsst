import hashlib

import pytest
from pydantic import ValidationError

from app.context import select_context
from app.schemas import ModelCandidate, ReviewRequest
from app.review import validate_source
from app import tools
from fastapi import HTTPException


def test_strict_model_candidate_rejects_line_coercion_and_extra():
    valid = dict(rule_id="LOG-001", title="t", explanation="e", line=1,
                 code_quote="print(1)", severity="S2", suggestion="s")
    assert ModelCandidate.model_validate(valid).line == 1
    with pytest.raises(ValidationError):
        ModelCandidate.model_validate({**valid, "line": "1"})
    with pytest.raises(ValidationError):
        ModelCandidate.model_validate({**valid, "unsupported": "field"})
    with pytest.raises(ValidationError):
        ReviewRequest.model_validate({"filename": "a.py", "source": "print(1)", "extra": 1})


def test_ast_context_keeps_original_lines_and_marks_omissions():
    source = "import os\n" + "\n".join(f"value_{i} = {i}" for i in range(300)) + "\neval(input())\n"
    focus = len(source.splitlines())
    result = select_context(source, {focus}, max_chars=400)
    assert result.source_hash == hashlib.sha256(source.encode()).hexdigest()
    assert f"{focus}: eval(input())" in result.text
    assert result.omitted_ranges
    assert result.selected_chars < result.original_chars


def test_syntax_error_has_line_number():
    with pytest.raises(HTTPException) as exc:
        validate_source(ReviewRequest(source="def broken(:\n    pass\n"))
    assert exc.value.status_code == 422
    assert "第 1 行" in exc.value.detail


def test_static_review_does_not_execute_uploaded_python(tmp_path, monkeypatch):
    marker = tmp_path / "should-not-exist"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    monkeypatch.setattr(tools, "_run_json_tool", lambda command, path: ({"results": []} if command[0] != "ruff" else [], None))
    drafts, completed, gaps = tools.run_tools(source)
    assert drafts == []
    assert "Python AST" in completed
    assert not marker.exists()
