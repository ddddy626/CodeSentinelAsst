-- SQLite schema for review scores. The backend also creates this table on startup.
CREATE TABLE IF NOT EXISTS review_scores (
    job_id TEXT PRIMARY KEY,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    deduction INTEGER NOT NULL CHECK (deduction BETWEEN 0 AND 100),
    counted_findings INTEGER NOT NULL CHECK (counted_findings >= 0),
    pending_findings INTEGER NOT NULL CHECK (pending_findings >= 0),
    scoring_version VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL
);
