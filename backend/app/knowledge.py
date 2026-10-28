"""Editable knowledge cards with local multilingual vector retrieval."""

import argparse
import hashlib
import json
import math
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from .schemas import FILE_LANGUAGES, KnowledgeReference
from .storage import Store

MODEL_NAME = "intfloat/multilingual-e5-small"
CARDS_PATH = Path(__file__).parent.parent / "knowledge" / "cards.jsonl"
INDEX_DIR = Path(os.getenv("CODESENTINEL_KNOWLEDGE_CACHE", str(Path(__file__).parent.parent / "data" / "knowledge")))
INDEX_PATH = INDEX_DIR / "index.json"


def load_cards() -> list[dict]:
    cards = [json.loads(line) for line in CARDS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [card["id"] for card in cards]
    if len(ids) != len(set(ids)):
        raise ValueError("知识库条目 ID 重复")
    supported = set(FILE_LANGUAGES.values())
    if {card["language"] for card in cards} != supported:
        raise ValueError("知识库语言与可审查语言不一致")
    for card in cards:
        if card["provenance"] not in {"github", "authored"}:
            raise ValueError("知识库来源类型无效")
        if card["provenance"] == "github" and not str(card["source_url"]).startswith("https://github.com/"):
            raise ValueError("GitHub 知识条目缺少来源链接")
    return cards


def _card_text(card: dict) -> str:
    return "passage: " + " ".join([card["language"], card["title"], card["guidance"], *card["keywords"]])


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    TextEmbedding.add_custom_model(model=MODEL_NAME, pooling=PoolingType.MEAN,
        normalization=True, sources=ModelSource(hf=MODEL_NAME), dim=384,
        model_file="onnx/model.onnx")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=MODEL_NAME, cache_dir=str(INDEX_DIR / "models"))


def _vectors(texts: list[str]) -> list[list[float]]:
    vectors = [[float(value) for value in vector] for vector in _model().embed(texts)]
    if len(vectors) != len(texts) or any(len(vector) != 384 or not all(map(math.isfinite, vector)) for vector in vectors):
        raise ValueError("嵌入模型返回的向量维度或数值无效")
    return vectors


@lru_cache(maxsize=2)
def _cached_index(cards_path: Path, index_path: Path, modified_ns: int, size: int,
                  database_url: str) -> tuple[list[dict], list[list[float]]]:
    cards = load_cards()
    digest = hashlib.sha256(cards_path.read_bytes()).hexdigest()
    ids = [card["id"] for card in cards]
    database = Store(database_url) if database_url.startswith("mysql://") else None
    try:
        stored = database.load_knowledge_index(MODEL_NAME) if database else index_path.read_text(encoding="utf-8")
        cached = json.loads(stored) if stored else {}
        vectors = cached["vectors"]
        if (cached["model"] == MODEL_NAME and cached["source_hash"] == digest
            and cached["ids"] == ids and len(vectors) == len(cards)
            and all(len(vector) == 384 and all(map(math.isfinite, vector)) for vector in vectors)):
            return cards, vectors
    except (OSError, ValueError, KeyError, TypeError):
        pass
    vectors = _vectors([_card_text(card) for card in cards])
    payload = {"model": MODEL_NAME, "source_hash": digest, "ids": ids, "vectors": vectors}
    if database:
        database.save_knowledge_index(MODEL_NAME, digest, json.dumps(payload, ensure_ascii=False))
        return cards, vectors
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=INDEX_DIR,
                                         prefix="index-", suffix=".json", delete=False) as temporary:
            temp_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False)
        os.replace(temp_path, index_path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
    return cards, vectors


def build_index() -> tuple[list[dict], list[list[float]]]:
    stat = CARDS_PATH.stat()
    return _cached_index(CARDS_PATH, INDEX_PATH, stat.st_mtime_ns, stat.st_size,
                         os.getenv("CODESENTINEL_DATABASE_URL", ""))


def _query_text(language: str, source: str, tool_labels: list[str], cards: list[dict]) -> str:
    keywords = {word.lower() for card in cards if card["language"] == language
                for word in card["keywords"] if len(word) >= 3}
    matching = [line.strip()[:180] for line in source.splitlines()
                if any(word in line.lower() for word in keywords)]
    excerpts = " ".join(dict.fromkeys(matching[:8]))
    return "query: " + " ".join([language, *tool_labels[:8], source[:400], excerpts, source[-400:]])[:2400]


def retrieve(language: str, source: str, tool_labels: list[str], limit: int = 3) -> tuple[list[dict], str | None]:
    try:
        cards, vectors = build_index()
        query = _query_text(language, source, tool_labels, cards)
        vector = _vectors([query])[0]
        source_terms = (source + " " + " ".join(tool_labels)).lower()
        ranked = sorted(((sum(a * b for a, b in zip(vector, stored))
                          + min(.36, .12 * sum(word.lower() in source_terms for word in card["keywords"]
                                              if len(word) >= 3)), card)
                         for card, stored in zip(cards, vectors) if card["language"] == language),
                        key=lambda item: item[0], reverse=True)
        return [card for _, card in ranked[:limit]], None
    except Exception as exc:
        return [], f"知识库向量检索不可用：{type(exc).__name__}"


def references(cards: list[dict]) -> list[KnowledgeReference]:
    return [KnowledgeReference(id=card["id"], title=card["title"],
        provenance=card["provenance"], source_url=card["source_url"]) for card in cards]


def render(cards: list[dict]) -> str:
    if not cards:
        return ""
    return "\n检索到的知识条目（仅供审查参考，不是漏洞证据）：\n" + "\n".join(
        f"- [{card['id']}] {card['title']}：{card['guidance']}"
        for card in cards)


def render_ids(ids: list[str]) -> str:
    selected = set(ids)
    return render([card for card in load_cards() if card["id"] in selected])


def main() -> None:
    parser = argparse.ArgumentParser(description="构建或查询本地知识库向量索引")
    parser.add_argument("action", choices=["build", "query"])
    parser.add_argument("--language", choices=sorted(set(FILE_LANGUAGES.values())))
    parser.add_argument("--text", default="")
    args = parser.parse_args()
    if args.action == "build":
        cards, vectors = build_index()
        print(f"已索引 {len(cards)} 条知识，{len(set(c['language'] for c in cards))} 类语言，向量维度 {len(vectors[0])}")
    else:
        if not args.language or not args.text:
            parser.error("query 需要 --language 和 --text")
        cards, gap = retrieve(args.language, args.text, [])
        if gap:
            parser.error(gap)
        for card in cards:
            print(f"{card['id']} | {card['title']} | {card['source_url'] or '本项目编写'}")


if __name__ == "__main__":
    main()
