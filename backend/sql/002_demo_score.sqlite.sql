-- SQLite demo data. Run after registering at least one account.
-- The demo belongs to the alphabetically first registered username.
-- It is illustrative data, not the result of a live scan.
BEGIN;

INSERT OR IGNORE INTO projects (id, owner_id, name)
SELECT 'demo-score-project-v1', id, '评分页面示例'
FROM users ORDER BY username LIMIT 1;

INSERT OR IGNORE INTO jobs
  (id, owner_id, project_id, filename, source, source_hash, status,
   created_at, updated_at, report_json, review_round, rule_version, model_version, build_version)
SELECT
  'demo-score-job-v1', owner_id, id, 'demo_score.py',
  'eval(input())' || char(10),
  'cfff7d6cb4b71eef8f9b6579d4e9a2078c1207077c9939ca863f52c17229fd43',
  'completed', strftime('%Y-%m-%dT%H:%M:%f+00:00','now'),
  strftime('%Y-%m-%dT%H:%M:%f+00:00','now'),
  '{"id":"demo-score-report-v1","task_id":"demo-score-job-v1","filename":"demo_score.py","language":"python","created_at":"2026-10-26T00:00:00+00:00","decision":"request_changes","findings":[{"id":"demo-finding-1","rule_id":"SEC-DYNAMIC-EXEC","title":"动态执行不可信输入","explanation":"输入内容直接进入 eval，可能执行任意表达式。","line":1,"severity":"S1","evidence_level":"medium","disposition":"suggested","evidence":[{"origin":"tool","source":"Python AST","detail":"第 1 行调用 eval(input())"}],"suggestion":"移除 eval，使用明确的解析逻辑。","verification":{"status":"located","reason":"已在源码第 1 行定位调用。"}},{"id":"demo-finding-2","rule_id":"DEMO-INPUT-CHECK","title":"输入约束待核验","explanation":"演示一条证据不足、暂不扣分的发现。","line":1,"severity":"S2","evidence_level":"weak","disposition":"uncertain","evidence":[{"origin":"llm","source":"demo","detail":"仅供页面演示。"}],"suggestion":"确认预期输入范围。"}],"coverage":{"completed":["Python AST 静态检查"],"gaps":["示例记录未运行真实模型与外部扫描器"]},"rule_version":"v1-5","source_hash":"cfff7d6cb4b71eef8f9b6579d4e9a2078c1207077c9939ca863f52c17229fd43","build_version":"v1-5"}',
  1, 'v1-5', NULL, 'v1-5'
FROM projects WHERE id = 'demo-score-project-v1';

INSERT OR IGNORE INTO review_scores
  (job_id, score, deduction, counted_findings, pending_findings, scoring_version, updated_at)
SELECT id, 80, 20, 1, 1, 'severity-v1', strftime('%Y-%m-%dT%H:%M:%f+00:00','now')
FROM jobs WHERE id = 'demo-score-job-v1';

COMMIT;
