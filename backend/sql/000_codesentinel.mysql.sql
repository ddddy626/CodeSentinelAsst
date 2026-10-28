-- CodeSentinel MySQL 8.4 schema, matching backend/app/storage.py Store._init.
-- Safe to rerun: existing databases and tables are retained.
CREATE DATABASE IF NOT EXISTS `codesentinel`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `codesentinel`;

CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(64) PRIMARY KEY,
  username VARCHAR(100) UNIQUE NOT NULL,
  password_hash VARCHAR(256) NOT NULL,
  is_admin INTEGER NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sessions (
  token_hash CHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  expires_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS projects (
  id VARCHAR(64) PRIMARY KEY,
  owner_id VARCHAR(64) NOT NULL,
  name VARCHAR(200) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jobs (
  id VARCHAR(64) PRIMARY KEY,
  owner_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  filename VARCHAR(255) NOT NULL,
  source LONGTEXT NOT NULL,
  source_hash CHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at VARCHAR(40) NOT NULL,
  updated_at VARCHAR(40) NOT NULL,
  report_json LONGTEXT,
  error LONGTEXT,
  review_round INTEGER NOT NULL DEFAULT 0,
  rule_version VARCHAR(50) NOT NULL,
  model_version VARCHAR(200),
  build_version VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS events (
  id VARCHAR(64) PRIMARY KEY,
  job_id VARCHAR(64) NOT NULL,
  seq INTEGER NOT NULL,
  kind VARCHAR(40) NOT NULL,
  detail LONGTEXT NOT NULL,
  created_at VARCHAR(40) NOT NULL,
  UNIQUE KEY uq_events_job_seq (job_id, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS audit (
  id VARCHAR(64) PRIMARY KEY,
  actor_id VARCHAR(64),
  action VARCHAR(80) NOT NULL,
  target_id VARCHAR(64),
  created_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS memories (
  id VARCHAR(64) PRIMARY KEY,
  owner_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64),
  layer VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL,
  content LONGTEXT NOT NULL,
  source VARCHAR(200) NOT NULL,
  version INTEGER NOT NULL,
  created_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finding_feedback (
  job_id VARCHAR(64) NOT NULL,
  finding_id VARCHAR(64) NOT NULL,
  owner_id VARCHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL,
  note VARCHAR(500) NOT NULL,
  updated_at VARCHAR(40) NOT NULL,
  PRIMARY KEY (job_id, finding_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Added with the code score page. Existing review scores are stored here.
CREATE TABLE IF NOT EXISTS review_scores (
  job_id VARCHAR(64) PRIMARY KEY,
  score INTEGER NOT NULL,
  deduction INTEGER NOT NULL,
  counted_findings INTEGER NOT NULL,
  pending_findings INTEGER NOT NULL,
  scoring_version VARCHAR(40) NOT NULL,
  updated_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The local embedding model still runs from disk; its 384-dimension index is stored here.
CREATE TABLE IF NOT EXISTS knowledge_index (
  model VARCHAR(100) PRIMARY KEY,
  source_hash CHAR(64) NOT NULL,
  payload LONGTEXT NOT NULL,
  updated_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
