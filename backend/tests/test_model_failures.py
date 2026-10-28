from app import llm


def test_invalid_model_json_is_explicit_coverage_gap(monkeypatch):
    monkeypatch.setattr(llm.config, "LLM_API_URL", "https://example.invalid/chat/completions")
    monkeypatch.setattr(llm.config, "LLM_API_KEY", "test")
    monkeypatch.setattr(llm.config, "LLM_MODEL", "test")
    monkeypatch.setattr(llm, "_request_json", lambda *args: (_ for _ in ()).throw(ValueError("bad JSON")))
    drafts, gap = llm.review_source("print(1)")
    assert drafts == []
    assert "LLM 输出不可用" in gap
    assessments, gap = llm.architect_review("print(1)", [])
    assert assessments == []
    assert "架构师模型输出不可用" in gap
