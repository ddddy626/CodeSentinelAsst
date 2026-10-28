import json

from app import config, knowledge, llm, tools
from app.review import create_review
from app.schemas import FILE_LANGUAGES, ReviewRequest


def test_cards_cover_every_review_language_with_provenance():
    cards = knowledge.load_cards()
    assert len(cards) == 51
    assert {card["language"] for card in cards} == set(FILE_LANGUAGES.values())
    assert all(sum(card["language"] == language for card in cards) >= 3
               for language in set(FILE_LANGUAGES.values()))
    assert any(card["provenance"] == "github" for card in cards)
    assert any(card["provenance"] == "authored" for card in cards)


def test_vector_index_reuses_cache_and_rebuilds_after_catalog_change(tmp_path, monkeypatch):
    cards_path = tmp_path / "cards.jsonl"
    cards_path.write_bytes(knowledge.CARDS_PATH.read_bytes())
    monkeypatch.setattr(knowledge, "CARDS_PATH", cards_path)
    monkeypatch.setattr(knowledge, "INDEX_DIR", tmp_path)
    monkeypatch.setattr(knowledge, "INDEX_PATH", tmp_path / "index.json")
    calls = []
    def embed(texts):
        calls.append(len(texts))
        return [[1.0] + [0.0] * 383 for _ in texts]
    monkeypatch.setattr(knowledge, "_vectors", embed)
    cards, vectors = knowledge.build_index()
    assert len(vectors) == len(cards) == 51
    knowledge.build_index()
    assert calls == [51]
    with cards_path.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    knowledge.build_index()
    assert calls == [51, 51]
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))["model"] == knowledge.MODEL_NAME


def test_mysql_vector_index_persists_and_reloads_without_local_index(tmp_path, monkeypatch):
    cards_path = tmp_path / "cards.jsonl"
    cards_path.write_bytes(knowledge.CARDS_PATH.read_bytes())
    monkeypatch.setattr(knowledge, "CARDS_PATH", cards_path)
    monkeypatch.setattr(knowledge, "INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setenv("CODESENTINEL_DATABASE_URL", "mysql://test@localhost/test")
    saved = {}

    class FakeStore:
        def __init__(self, url):
            assert url.startswith("mysql://")

        def load_knowledge_index(self, model):
            return saved.get(model)

        def save_knowledge_index(self, model, source_hash, payload):
            assert source_hash == json.loads(payload)["source_hash"]
            saved[model] = payload

    calls = []
    monkeypatch.setattr(knowledge, "Store", FakeStore)
    monkeypatch.setattr(knowledge, "_vectors", lambda texts:
                        (calls.append(len(texts)) or [[1.0] + [0.0] * 383 for _ in texts]))
    knowledge._cached_index.cache_clear()
    try:
        cards, vectors = knowledge.build_index()
        knowledge._cached_index.cache_clear()
        reloaded, stored_vectors = knowledge.build_index()
        assert len(cards) == len(reloaded) == len(vectors) == len(stored_vectors) == 51
        assert calls == [51]
        assert not (tmp_path / "index.json").exists()
    finally:
        knowledge._cached_index.cache_clear()


def test_vector_search_filters_language_before_ranking(monkeypatch):
    cards = knowledge.load_cards()
    vectors = [[1.0] + [0.0] * 383 if card["id"] == "sql.unbounded-write"
               else [0.0, 1.0] + [0.0] * 382 for card in cards]
    monkeypatch.setattr(knowledge, "build_index", lambda: (cards, vectors))
    monkeypatch.setattr(knowledge, "_vectors", lambda texts: [[1.0] + [0.0] * 383])
    found, gap = knowledge.retrieve("sql", "DELETE FROM users;", [], limit=2)
    assert gap is None
    assert found[0]["id"] == "sql.unbounded-write"
    assert all(card["language"] == "sql" for card in found)


def test_late_source_pattern_reaches_query_and_relevant_card(monkeypatch):
    cards = knowledge.load_cards()
    monkeypatch.setattr(knowledge, "build_index", lambda: (cards, [[1.0] + [0.0] * 383 for _ in cards]))
    queries = []
    monkeypatch.setattr(knowledge, "_vectors", lambda texts: (queries.extend(texts) or [[1.0] + [0.0] * 383]))
    source = "safe = 1\n" * 500 + "value = pickle.loads(payload)\n"
    found, gap = knowledge.retrieve("python", source, [], limit=1)
    assert gap is None
    assert "pickle.loads(payload)" in queries[0]
    assert found[0]["id"] == "python.unsafe-deserialization"


def test_retrieved_cards_reach_model_and_report(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_URL", "https://example.invalid/chat/completions")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(tools, "run_tools", lambda source: ([], ["Python AST"], []))
    card = next(card for card in knowledge.load_cards() if card["id"] == "python.dynamic-exec")
    monkeypatch.setattr(knowledge, "retrieve", lambda language, source, labels: ([card], None))
    seen = []
    monkeypatch.setattr(llm, "review_source", lambda source: (seen.append(source) or [], None))
    report = create_review(ReviewRequest(source="print(1)"))
    assert "python.dynamic-exec" in seen[0]
    assert report.knowledge_refs[0].source_url == card["source_url"]
    assert "知识库向量检索" in report.coverage.completed


def test_retrieval_failure_is_visible_as_coverage_gap(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_URL", "https://example.invalid/chat/completions")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(tools, "run_tools", lambda source: ([], ["Python AST"], []))
    monkeypatch.setattr(knowledge, "retrieve", lambda language, source, labels: ([], "知识库向量检索不可用：OSError"))
    monkeypatch.setattr(llm, "review_source", lambda source: ([], None))
    report = create_review(ReviewRequest(source="print(1)"))
    assert "知识库向量检索不可用：OSError" in report.coverage.gaps
    assert report.decision == "comment"
