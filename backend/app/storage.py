"""Persistent identities, projects, jobs, events and audit records.

SQLite is the zero-service development adapter; MySQL is selected by DATABASE_URL.
No submitted source or credential is written to the audit log.
"""

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .config import DATABASE_PATH
from .schemas import ReviewReport
from .score import calculate_score


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: str | None = None) -> str:
    if len(password) < 12:
        raise ValueError("密码至少需要 12 个字符")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return f"{salt}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, expected = stored.split(":", 1)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return secrets.compare_digest(actual.hex(), expected)


class Store:
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("CODESENTINEL_DATABASE_URL") or f"sqlite:///{DATABASE_PATH}"
        self.mysql = self.url.startswith("mysql://")
        if not self.mysql and not self.url.startswith("sqlite:///"):
            raise ValueError("仅支持 sqlite:/// 或 mysql:// 数据库地址")
        if not self.mysql:
            self.path = Path(self.url.removeprefix("sqlite:///"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connection(self):
        if self.mysql:
            import pymysql
            from urllib.parse import urlparse, unquote
            parsed = urlparse(self.url)
            conn = pymysql.connect(host=parsed.hostname, port=parsed.port or 3306,
                user=unquote(parsed.username or ""), password=unquote(parsed.password or ""),
                database=parsed.path.lstrip("/"), charset="utf8mb4", autocommit=False,
                cursorclass=pymysql.cursors.DictCursor)
        else:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _run(self, conn, sql: str, params: tuple = ()):
        if self.mysql:
            cursor = conn.cursor()
            cursor.execute(sql.replace("?", "%s"), params)
            return cursor
        return conn.execute(sql, params)

    def _init(self):
        id_type = "VARCHAR(64)" if self.mysql else "TEXT"
        text_type = "LONGTEXT" if self.mysql else "TEXT"
        with self.connection() as conn:
            statements = [
                f"CREATE TABLE IF NOT EXISTS users (id {id_type} PRIMARY KEY, username VARCHAR(100) UNIQUE NOT NULL, password_hash VARCHAR(256) NOT NULL, is_admin INTEGER NOT NULL)",
                f"CREATE TABLE IF NOT EXISTS sessions (token_hash CHAR(64) PRIMARY KEY, user_id {id_type} NOT NULL, expires_at VARCHAR(40) NOT NULL)",
                f"CREATE TABLE IF NOT EXISTS projects (id {id_type} PRIMARY KEY, owner_id {id_type} NOT NULL, name VARCHAR(200) NOT NULL)",
                f"CREATE TABLE IF NOT EXISTS jobs (id {id_type} PRIMARY KEY, owner_id {id_type} NOT NULL, project_id {id_type} NOT NULL, filename VARCHAR(255) NOT NULL, source {text_type} NOT NULL, source_hash CHAR(64) NOT NULL, status VARCHAR(20) NOT NULL, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL, report_json {text_type}, error {text_type}, review_round INTEGER NOT NULL DEFAULT 0, rule_version VARCHAR(50) NOT NULL, model_version VARCHAR(200), build_version VARCHAR(50) NOT NULL)",
                f"CREATE TABLE IF NOT EXISTS events (id {id_type} PRIMARY KEY, job_id {id_type} NOT NULL, seq INTEGER NOT NULL, kind VARCHAR(40) NOT NULL, detail {text_type} NOT NULL, created_at VARCHAR(40) NOT NULL, UNIQUE(job_id, seq))",
                f"CREATE TABLE IF NOT EXISTS audit (id {id_type} PRIMARY KEY, actor_id {id_type}, action VARCHAR(80) NOT NULL, target_id {id_type}, created_at VARCHAR(40) NOT NULL)",
                f"CREATE TABLE IF NOT EXISTS memories (id {id_type} PRIMARY KEY, owner_id {id_type} NOT NULL, project_id {id_type} NOT NULL, task_id {id_type}, layer VARCHAR(20) NOT NULL, status VARCHAR(20) NOT NULL, content {text_type} NOT NULL, source VARCHAR(200) NOT NULL, version INTEGER NOT NULL, created_at VARCHAR(40) NOT NULL)",
                f"CREATE TABLE IF NOT EXISTS finding_feedback (job_id {id_type} NOT NULL, finding_id {id_type} NOT NULL, owner_id {id_type} NOT NULL, status VARCHAR(20) NOT NULL, note VARCHAR(500) NOT NULL, updated_at VARCHAR(40) NOT NULL, PRIMARY KEY (job_id, finding_id))",
                f"CREATE TABLE IF NOT EXISTS review_scores (job_id {id_type} PRIMARY KEY, score INTEGER NOT NULL, deduction INTEGER NOT NULL, counted_findings INTEGER NOT NULL, pending_findings INTEGER NOT NULL, scoring_version VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL)",
                f"CREATE TABLE IF NOT EXISTS knowledge_index (model VARCHAR(100) PRIMARY KEY, source_hash CHAR(64) NOT NULL, payload {text_type} NOT NULL, updated_at VARCHAR(40) NOT NULL)",
            ]
            for sql in statements:
                self._run(conn, sql)

    def _one(self, sql: str, params: tuple = ()):
        with self.connection() as conn:
            return self._run(conn, sql, params).fetchone()

    def load_knowledge_index(self, model: str) -> str | None:
        row = self._one("SELECT payload FROM knowledge_index WHERE model=?", (model,))
        return row["payload"] if row else None

    def save_knowledge_index(self, model: str, source_hash: str, payload: str) -> None:
        with self.connection() as conn:
            self._run(conn, "DELETE FROM knowledge_index WHERE model=?", (model,))
            self._run(conn, "INSERT INTO knowledge_index (model,source_hash,payload,updated_at) VALUES (?,?,?,?)",
                      (model, source_hash, payload, now()))

    def audit(self, actor_id: str | None, action: str, target_id: str | None = None):
        with self.connection() as conn:
            self._run(conn, "INSERT INTO audit VALUES (?, ?, ?, ?, ?)",
                      (uuid4().hex, actor_id, action, target_id, now()))

    def create_user(self, username: str, password: str, is_admin: bool = False) -> str:
        if not username or len(username) > 100:
            raise ValueError("用户名长度无效")
        user_id = uuid4().hex
        with self.connection() as conn:
            self._run(conn, "INSERT INTO users VALUES (?, ?, ?, ?)",
                      (user_id, username, hash_password(password), int(is_admin)))
        self.audit(user_id, "user_created", user_id)
        return user_id

    def authenticate(self, username: str, password: str) -> tuple[str, str, bool] | None:
        user = self._one("SELECT * FROM users WHERE username=?", (username,))
        if not user or not verify_password(password, user["password_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        with self.connection() as conn:
            self._run(conn, "INSERT INTO sessions VALUES (?, ?, ?)",
                      (hashlib.sha256(token.encode()).hexdigest(), user["id"], expires))
        self.audit(user["id"], "login")
        return token, user["id"], bool(user["is_admin"])

    def session_user(self, token: str):
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = self._one("SELECT users.id, users.username, users.is_admin, sessions.expires_at FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=?", (digest,))
        if not row or row["expires_at"] <= now():
            return None
        return dict(row)

    def logout(self, token: str):
        with self.connection() as conn:
            self._run(conn, "DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def create_project(self, owner_id: str, name: str) -> dict:
        project = {"id": uuid4().hex, "owner_id": owner_id, "name": name}
        with self.connection() as conn:
            self._run(conn, "INSERT INTO projects VALUES (?, ?, ?)", tuple(project.values()))
        self.audit(owner_id, "project_created", project["id"])
        return project

    def projects(self, owner_id: str) -> list[dict]:
        with self.connection() as conn:
            return [dict(row) for row in self._run(conn, "SELECT * FROM projects WHERE owner_id=? ORDER BY name", (owner_id,)).fetchall()]

    def owns_project(self, owner_id: str, project_id: str) -> bool:
        return bool(self._one("SELECT id FROM projects WHERE id=? AND owner_id=?", (project_id, owner_id)))

    def create_job(self, owner_id: str, project_id: str, filename: str, source: str, rule_version: str) -> str:
        from .config import BUILD_VERSION, LLM_MODEL
        job_id = uuid4().hex
        timestamp = now()
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        with self.connection() as conn:
            self._run(conn, "INSERT INTO jobs (id,owner_id,project_id,filename,source,source_hash,status,created_at,updated_at,rule_version,model_version,build_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (job_id, owner_id, project_id, filename, source, source_hash,
                       "queued", timestamp, timestamp, rule_version, LLM_MODEL or None, BUILD_VERSION))
        self.event(job_id, "queued", "任务已创建")
        self.audit(owner_id, "review_created", job_id)
        return job_id

    def event(self, job_id: str, kind: str, detail: str):
        # Job row lock serializes event sequence allocation across workers.
        with self.connection() as conn:
            self._run(conn, "UPDATE jobs SET updated_at=? WHERE id=?", (now(), job_id))
            row = self._run(conn, "SELECT COALESCE(MAX(seq),0)+1 AS next_seq FROM events WHERE job_id=?", (job_id,)).fetchone()
            self._run(conn, "INSERT INTO events VALUES (?,?,?,?,?,?)",
                      (uuid4().hex, job_id, row["next_seq"], kind, detail, now()))

    def events(self, job_id: str, after: int = 0) -> list[dict]:
        with self.connection() as conn:
            return [dict(row) for row in self._run(conn, "SELECT seq,kind,detail,created_at FROM events WHERE job_id=? AND seq>? ORDER BY seq", (job_id, after)).fetchall()]

    def job(self, job_id: str, owner_id: str | None = None):
        sql = "SELECT * FROM jobs WHERE id=?"
        args = (job_id,)
        if owner_id is not None:
            sql += " AND owner_id=?"
            args += (owner_id,)
        row = self._one(sql, args)
        result = dict(row) if row else None
        if result:
            result.pop("source")
            report_json = result.pop("report_json")
            result["report"] = json.loads(report_json) if report_json else None
            if result["report"]:
                score_row = self._one("SELECT score,deduction,counted_findings,pending_findings,scoring_version FROM review_scores WHERE job_id=?", (job_id,))
                result["score"] = ({"value": score_row["score"], "deduction": score_row["deduction"],
                    "counted_findings": score_row["counted_findings"], "pending_findings": score_row["pending_findings"],
                    "version": score_row["scoring_version"]} if score_row else calculate_score(result["report"],
                    self._feedback_statuses(job_id)))
            else:
                result["score"] = None
        return result

    def _feedback_statuses(self, job_id: str) -> dict[str, str]:
        with self.connection() as conn:
            rows = self._run(conn, "SELECT finding_id,status FROM finding_feedback WHERE job_id=?", (job_id,)).fetchall()
        return {row["finding_id"]: row["status"] for row in rows}

    def _save_score(self, job_id: str, report: dict):
        score = calculate_score(report, self._feedback_statuses(job_id))
        with self.connection() as conn:
            self._run(conn, "DELETE FROM review_scores WHERE job_id=?", (job_id,))
            self._run(conn, "INSERT INTO review_scores (job_id,score,deduction,counted_findings,pending_findings,scoring_version,updated_at) VALUES (?,?,?,?,?,?,?)",
                      (job_id, score["value"], score["deduction"], score["counted_findings"],
                       score["pending_findings"], score["version"], now()))

    def job_source(self, job_id: str):
        row = self._one("SELECT filename,source,source_hash,status,owner_id,project_id,review_round,rule_version FROM jobs WHERE id=?", (job_id,))
        return dict(row) if row else None

    def finding_feedback(self, owner_id: str, job_id: str) -> list[dict]:
        if not self.job(job_id, owner_id):
            raise PermissionError("任务不可访问")
        with self.connection() as conn:
            rows = self._run(conn, "SELECT finding_id,status,note,updated_at FROM finding_feedback WHERE job_id=? AND owner_id=?",
                             (job_id, owner_id)).fetchall()
        return [dict(row) for row in rows]

    def save_finding_feedback(self, owner_id: str, job_id: str, finding_id: str,
                              status: str, note: str) -> dict:
        if status not in {"confirmed", "false_positive", "accepted_risk"}:
            raise ValueError("未知判断状态")
        job = self.job(job_id, owner_id)
        if not job or not job["report"] or not any(
                item["id"] == finding_id for item in job["report"]["findings"]):
            raise PermissionError("发现项不可访问")
        timestamp = now()
        with self.connection() as conn:
            self._run(conn, "DELETE FROM finding_feedback WHERE job_id=? AND finding_id=? AND owner_id=?",
                      (job_id, finding_id, owner_id))
            self._run(conn, "INSERT INTO finding_feedback (job_id,finding_id,owner_id,status,note,updated_at) VALUES (?,?,?,?,?,?)",
                      (job_id, finding_id, owner_id, status, note, timestamp))
        self._save_score(job_id, job["report"])
        self.audit(owner_id, "finding_feedback_saved", job_id)
        return {"finding_id": finding_id, "status": status, "note": note,
                "updated_at": timestamp}

    def jobs(self, owner_id: str, project_id: str | None = None) -> list[dict]:
        with self.connection() as conn:
            if project_id is None:
                rows = self._run(conn, "SELECT id FROM jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT 200", (owner_id,)).fetchall()
            else:
                rows = self._run(conn, "SELECT id FROM jobs WHERE owner_id=? AND project_id=? ORDER BY created_at DESC LIMIT 30", (owner_id, project_id)).fetchall()
        return [self.job(row["id"], owner_id) for row in rows]

    def move_job(self, owner_id: str, job_id: str, project_id: str) -> bool:
        with self.connection() as conn:
            job = self._run(conn, "SELECT project_id,status FROM jobs WHERE id=? AND owner_id=?", (job_id, owner_id)).fetchone()
            target = self._run(conn, "SELECT id FROM projects WHERE id=? AND owner_id=?", (project_id, owner_id)).fetchone()
            if not job or not target:
                raise PermissionError("审查记录或目标项目不存在")
            if job["status"] not in {"completed", "failed", "cancelled"}:
                raise ValueError("审查进行中，完成后才能移动")
            if job["project_id"] == project_id:
                return False
            self._run(conn, "UPDATE jobs SET project_id=? WHERE id=? AND owner_id=?", (project_id, job_id, owner_id))
            self._run(conn, "UPDATE memories SET project_id=? WHERE task_id=? AND owner_id=?", (project_id, job_id, owner_id))
        self.audit(owner_id, "review_moved", job_id)
        return True

    def pending_jobs(self) -> list[str]:
        with self.connection() as conn:
            rows = self._run(conn, "SELECT id FROM jobs WHERE status IN ('queued','running')", ()).fetchall()
        return [row["id"] for row in rows]

    def claim(self, job_id: str) -> bool:
        with self.connection() as conn:
            result = self._run(conn, "UPDATE jobs SET status='running',updated_at=? WHERE id=? AND status='queued'", (now(), job_id))
            claimed = result.rowcount == 1
        if claimed:
            self.event(job_id, "running", "Worker 已领取任务")
        return claimed

    def cancel_queued(self, job_id: str, owner_id: str) -> bool:
        with self.connection() as conn:
            result = self._run(conn,
                "UPDATE jobs SET status='cancelled',updated_at=? WHERE id=? AND owner_id=? AND status='queued'",
                (now(), job_id, owner_id))
            cancelled = result.rowcount == 1
        if cancelled:
            self.event(job_id, "cancelled", "用户取消了排队中的任务")
            self.audit(owner_id, "review_cancelled", job_id)
        return cancelled

    def recover(self, job_id: str):
        with self.connection() as conn:
            self._run(conn, "UPDATE jobs SET status='queued',updated_at=? WHERE id=? AND status='running'", (now(), job_id))
        self.event(job_id, "recovered", "Worker 重启后重新入队")

    def set_round(self, job_id: str, round_number: int):
        with self.connection() as conn:
            self._run(conn, "UPDATE jobs SET review_round=? WHERE id=?", (round_number, job_id))

    def finish(self, job_id: str, report: ReviewReport):
        row = self._one("SELECT source_hash,rule_version FROM jobs WHERE id=?", (job_id,))
        if not row or row["source_hash"] != report.source_hash or row["rule_version"] != report.rule_version or report.task_id != job_id:
            raise ValueError("报告的任务、源码哈希或规则版本与任务不一致")
        with self.connection() as conn:
            self._run(conn, "UPDATE jobs SET status='completed',report_json=?,updated_at=? WHERE id=?",
                      (report.model_dump_json(), now(), job_id))
        self._save_score(job_id, report.model_dump())
        self.event(job_id, "completed", "审查报告已保存")

    def fail(self, job_id: str, error: str):
        with self.connection() as conn:
            self._run(conn, "UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?", (error[:500], now(), job_id))
        self.event(job_id, "failed", error[:200])

    def save_memory(self, owner_id: str, project_id: str, layer: str,
                    content: str, source: str, task_id: str | None = None,
                    status: str = "candidate") -> str:
        if layer not in {"task", "project", "experience"}:
            raise ValueError("未知记忆层")
        if status not in {"candidate", "verified", "retired"}:
            raise ValueError("未知记忆状态")
        if layer == "task" and not task_id:
            raise ValueError("任务记忆必须绑定任务")
        if not self.owns_project(owner_id, project_id):
            raise PermissionError("项目不可访问")
        task = self.job(task_id, owner_id) if task_id else None
        if task_id and (not task or task["project_id"] != project_id):
            raise PermissionError("任务不可访问")
        memory_id = uuid4().hex
        with self.connection() as conn:
            self._run(conn, "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (memory_id, owner_id, project_id, task_id, layer, status,
                       content, source, 1, now()))
        self.audit(owner_id, "memory_created", memory_id)
        return memory_id

    def memories(self, owner_id: str, project_id: str, layer: str,
                 task_id: str | None = None) -> list[dict]:
        if not self.owns_project(owner_id, project_id):
            raise PermissionError("项目不可访问")
        sql = "SELECT * FROM memories WHERE owner_id=? AND project_id=? AND layer=?"
        params: tuple = (owner_id, project_id, layer)
        if layer == "task":
            sql += " AND task_id=?"
            params += (task_id,)
        sql += " ORDER BY created_at DESC LIMIT 100"
        with self.connection() as conn:
            return [dict(row) for row in self._run(conn, sql, params).fetchall()]
