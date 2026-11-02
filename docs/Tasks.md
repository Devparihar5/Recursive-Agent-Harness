# Tasks

This is the concise working backlog. The current implementation is described in `PRD.md`; deeper paper-fidelity notes are in the locally ignored `GAPS.md`. Priorities below reflect that gap analysis and should be reviewed before work starts.

## Completed

- [x] Baseline executor with bounded turns, source-path guards, and persisted run evidence.
- [x] Parallel and sequential improvement, candidate probes, composition, blind selection, reflection, and conditional library retention.
- [x] Local FastAPI and React dashboard for tasks, runs, harnesses, library, metrics, and settings.
- [x] Three bundled examples can be launched from New task; quick base-only and full improvement actions are separate. `NewTask` TypeScript errors were resolved (2026-11-02).
- [x] Execution defaults can be saved without creating a task; custom run buttons appear only when an objective is entered (2026-11-02).
- [x] Active runs can be cancelled from the live view; API, run records, and SSE reach a terminal cancelled state (2026-11-02).
- [x] Architecture, design, memory, requirements, rules, and task documents created under `docs/` (2026-11-02).

## Pending

| Priority | Task | Done when |
| --- | --- | --- |
| High | Design isolated execution for C7 scripts and C8 plugins | Untrusted candidate code runs only inside a restricted subprocess; failures and limits are recorded. |
| High | Add embedding-based library retrieval | Entries have searchable vectors, with deterministic fallbacks and retrieval tests. |
| High | Add external benchmark runner/verifier | Task-quality scores can be evaluated without leaking labels or grader output into improvement. |
| High | Add user review and adoption flow | A user can inspect a baseline/composition and explicitly adopt an evidence-backed library entry. |
| Medium | Dispatch harness subagents and invoke skills on demand | Both use explicit tools and respect their own execution boundaries. |
| Medium | Add multi-task stream runner and resource budgets | A task list can run sequentially, and each probe has explicit turn/time/cost limits. |
| Medium | Expand library inspection and management | Users can search/filter entries, inspect diffs against base, and remove or annotate entries. |

## Known bugs and verification gaps

- [ ] Add tests for SSE terminal behavior after normal completion, composer evidence validation, editor retry fallback, retrieval ranking, run comparison, settings round-trip, and source upload.
- [ ] Revisit API-key storage: the settings endpoint currently writes a supplied key to local `.env` in plaintext.
