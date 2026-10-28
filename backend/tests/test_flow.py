from app.evaluate import evaluate
from app.review import create_review
from app.schemas import ReviewRequest
from app.tools import _ast_review


def test_cross_function_path_has_a_trace():
    source = "def run(code):\n    eval(code)\nrun(input())\n"
    drafts, gap = _ast_review(source)
    assert gap is None
    assert len(drafts) == 1
    assert drafts[0].severity == "S1"
    assert "run.code" in drafts[0].evidence
    assert "input()" in drafts[0].evidence


def test_uncalled_function_does_not_claim_a_trigger():
    drafts, gap = _ast_review("def run():\n    eval(input())\n")
    assert gap is None
    assert drafts[0].severity == "S2"
    assert drafts[0].trigger_path is None


def test_review_exposes_the_trigger_path(monkeypatch):
    monkeypatch.setattr(
        "app.review.tools.run_tools",
        lambda source: (_ast_review(source)[0], ["Python AST"], []),
    )
    monkeypatch.setattr(
        "app.review.llm.review_source", lambda source: ([], "LLM 未配置"),
    )
    report = create_review(ReviewRequest(
        source="def run(code):\n    eval(code)\nrun(input())\n",
    ))
    assert report.findings[0].severity == "S1"
    assert "run.code" in report.findings[0].trigger_path
    assert "静态可能路径" in report.findings[0].evidence[0].detail


def test_evaluation_regression_set():
    result = evaluate()
    assert result["cases"] >= 12
    assert result["failures"] == []
