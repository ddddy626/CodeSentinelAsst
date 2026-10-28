# CodeSentinel starter checklist

- [x] Contracts and input limits
- [x] Tool adapters and coverage gaps
- [x] LLM adapter and prompt
- [x] Reviewer and persistence
- [x] API and React review flow
- [x] Frontend dependency install and production build
- [x] Run focused backend tests
- [x] Document next steps

## Phase 2: evidence verification

- [x] Require exact source quote from LLM candidates
- [x] Reject invalid locations and deduplicate matching rule/line findings
- [x] Show verification reason in API and React report
- [x] Test forged quote, invalid line, and tool corroboration

## Phase 3: static trigger paths and evaluation

- [x] Add bounded cross-function trigger tracing for dynamic execution
- [x] Add labeled synthetic regression cases and an offline precision/recall command
- [x] Show static trigger paths in reports

## Phase 4: broader review coverage

- [ ] Build an external real-world evaluation set and calibrate severity
- [ ] Expand flow tracing beyond builtin input and dynamic execution
- [x] Add administrator-provisioned authentication and per-project isolation
- [x] Add Redis-backed asynchronous jobs, persistent events, SSE and queued cancellation

## V1 handover checklist

- [x] Run a real LangGraph state graph with Planner, Scanner, Architect and bounded recheck
- [x] Validate model candidates and node handoffs with Pydantic
- [x] Select AST source context with original line mapping and coverage gaps
- [x] Lock Python and frontend dependencies
- [x] Run 16 synthetic A/B/C/D comparisons with the configured model; preserve raw reports
- [x] Verify FastAPI → Redis → Worker → SQLite → SSE locally
- [ ] Verify MySQL 8.4 and Docker Compose runtime on a machine with Docker
- [ ] Browser QA for upload encoding, task cancellation and SSE reconnect
- [ ] Add human-labeled real-project examples before claiming quality improvement
