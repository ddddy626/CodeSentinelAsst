"""Local review history. Replace this adapter when multi-user storage lands."""

import sqlite3
from pathlib import Path

from .config import DATABASE_PATH
from .schemas import ReviewReport
from .storage import Store


class MemoryService:
    """Three isolated memory layers with explicit provenance and trust state.

    Advanced retrieval and automatic rule learning are later milestones.
    """

    def __init__(self, store: Store):
        self.store = store

    def remember(self, owner_id: str, project_id: str, layer: str, content: str,
                 source: str, task_id: str | None = None,
                 status: str = "candidate") -> str:
        return self.store.save_memory(owner_id, project_id, layer, content,
                                      source, task_id, status)

    def recall(self, owner_id: str, project_id: str, layer: str,
               task_id: str | None = None) -> list[dict]:
        return self.store.memories(owner_id, project_id, layer, task_id)


class MemoryStore:
    def __init__(self, path: Path = DATABASE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS reviews "
                "(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, report_json TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(self, report: ReviewReport) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reviews (id, created_at, report_json) VALUES (?, ?, ?)",
                (report.id, report.created_at, report.model_dump_json()),
            )

    def get(self, review_id: str) -> ReviewReport | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM reviews WHERE id = ?", (review_id,)
            ).fetchone()
        return ReviewReport.model_validate_json(row[0]) if row else None

    def recent(self, limit: int = 20) -> list[ReviewReport]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT report_json FROM reviews ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [ReviewReport.model_validate_json(row[0]) for row in rows]
