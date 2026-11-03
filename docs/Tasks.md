# Tasks

This is the concise working backlog. The current implementation is described in `PRD.md` and `IMPLEMENTATION_STATUS.md`. Review priorities before work starts.

## Completed

- [x] Baseline executor with bounded turns, source-path guards, and persisted run evidence.
- [x] Parallel and sequential improvement, candidate probes, composition, blind selection, reflection, and conditional library retention.
- [x] Local FastAPI and React dashboard for tasks, runs, harnesses, library, metrics, and settings.
- [x] Three bundled examples can be launched from New task; quick base-only and full improvement actions are separate. `NewTask` TypeScript errors were resolved (2026-11-02).
- [x] Execution defaults can be saved without creating a task; custom run buttons appear only when an objective is entered (2026-11-02).
- [x] Active runs can be cancelled from the live view; API, run records, and SSE reach a terminal cancelled state (2026-11-02).
- [x] Run progress uses a readable phase timeline with live completion/current status and a narrow-screen list (2026-11-02).
- [x] Tools evidence tab renders object-valued actions without crashing the page (2026-11-02).
- [x] Architecture, design, memory, requirements, rules, and task documents created under `docs/` (2026-11-02).
- [x] Subprocess helpers and direct tests for C7 scripts and C8 plugins; harness mounting and automatic plugin integration remain incomplete (2026-11-02).
- [x] Embedding-based library retrieval: vector index with hybrid ranking and deterministic keyword fallback, plus retrieval tests (2026-11-02).
- [x] External benchmark runner interface with private verifier context and separate result storage; fake-verifier tests cover data isolation (2026-11-03).
- [x] Remove the Improvement library page from the dashboard, add a process health endpoint, and show saved benchmark results on Evaluation (2026-11-03).
- [x] Show completed ordinary runs on Evaluation with an unverified status until an external score exists (2026-11-03).
- [x] Connect a separate model judge to completed runs: optional private rubric, one-click scoring, persisted assessment, and no score feedback into improvement (2026-11-03).
- [x] Hoist backend function-local imports to module scope and preserve the harness path helper's public import path (2026-11-03).
- [x] Add a root contributor guide in `AGENTS.md` after checking that the file was absent (2026-11-03).
- [x] Clarify the live progress label so base-only runs are distinct from parallel or sequential improvement runs (2026-11-03).
- [x] Clarify that example Quick run ignores improvement mode/rounds and display the selected settings on Full improvement (2026-11-03).
- [x] Align parallel baseline counts and select the executed successor directly at `k=1` (2026-11-03).
- [x] Add CLI review/adoption with notes, preserve pending entries when adoption fails, and pass retrieved lessons and prior history to composition (2026-11-03).
- [x] Add a sequential task-stream CLI with explicit optional adoption between tasks (2026-11-03).
- [x] Add library search/filter and diff-against-base operations through the API and CLI (2026-11-03).
- [x] Add append-only library annotations and recoverable archive/restore operations through the API and CLI (2026-11-03).
- [x] Add on-demand skills and separate bounded subagent contexts with declared read-only tools (2026-11-03).
- [x] Add coverage for normal SSE termination, composition evidence validation, editor retries, run comparison, nonsecret settings, and text/PDF uploads (2026-11-03).
- [x] Keep newly submitted API keys in the current server session only, preserving existing `.env` contents (2026-11-03).

## Pending

| Priority | Task | Done when |
| --- | --- | --- |
| High | Integrate an external benchmark | Add a local dataset and grader, then evaluate task streams against comparable baselines without exposing scores to improvement. |
| Medium | Add enforceable per-probe monetary cost limits | Turn, model/tool wait-time, and reported-token limits exist; a cost cap needs trustworthy provider pricing and usage. |

## Known bugs and verification gaps

- [ ] The current Python AST gate is not a security boundary for untrusted scripts or plugins; subprocess execution needs OS-level isolation before accepting arbitrary candidate code.
- [ ] Model assessments are subjective; add dataset-specific hidden tests or an independent ground-truth verifier before treating scores as benchmark correctness.
- [ ] Existing API keys already present in `.env` remain plaintext until the user removes or moves them; new settings submissions do not write keys there.
