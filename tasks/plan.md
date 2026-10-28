# CodeSentinel implementation plan

## First vertical slice

Build a local Python single-file review: React submits source, FastAPI validates it, static tools and an optional LLM produce draft findings, a reviewer normalizes them, SQLite stores the report, and the UI displays evidence and coverage gaps.

## Architecture decisions

- Keep `llm.py`, `tools.py`, `memory.py`, and `prompts/` as ordinary, independently editable files.
- Use synchronous requests in this starter so the first path can run without Redis, MySQL, or Docker. The review service is isolated for a later worker/queue replacement.
- Treat LLM-only findings as uncertain until corroborated. Never execute or modify submitted source.
- Keep the API contract in Pydantic models and mirror it in frontend TypeScript.

## Tasks

1. Define review request/report contracts and source validation. Verify accepted and rejected inputs.
2. Add AST and optional static-tool adapters. Verify real line numbers and coverage reporting.
3. Add prompt and optional OpenAI-compatible LLM adapter. Verify malformed output does not become a finding.
4. Add reviewer and SQLite report persistence. Verify evidence classification and report retrieval.
5. Add FastAPI endpoints and a React workspace. Verify the basic submit-to-report path.
6. Document setup, limitations, and next increments.

## Next increments

Authentication and project isolation; asynchronous jobs/events; MySQL/Redis; independent verifier and bounded review loops; benchmark and rule-version governance.
