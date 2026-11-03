# Tasks

This is the concise working backlog. The current implementation is described in `PRD.md`; deeper paper-fidelity notes are in the locally ignored `GAPS.md`. Priorities below reflect that gap analysis and should be reviewed before work starts.

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
- [x] Isolated execution for C7 scripts and C8 plugins: sandboxed subprocess with AST validation, tool actions, and failure/timeout recording (2026-11-02).
- [x] Embedding-based library retrieval: vector index with hybrid ranking and deterministic keyword fallback, plus retrieval tests (2026-11-02).
- [x] External benchmark runner interface with private verifier context and separate result storage; fake-verifier tests cover data isolation (2026-11-03).
- [x] Remove the Improvement library page from the dashboard, add a process health endpoint, and show saved benchmark results on Evaluation (2026-11-03).
- [x] Show completed ordinary runs on Evaluation with an unverified status until an external score exists (2026-11-03).
- [x] Connect a separate model judge to completed runs: optional private rubric, one-click scoring, persisted assessment, and no score feedback into improvement (2026-11-03).
- [x] Hoist backend function-local imports to module scope and preserve the harness path helper's public import path (2026-11-03).
- [x] Add a root contributor guide in `AGENTS.md` after checking that the file was absent (2026-11-03).
- [x] Clarify the live progress label so base-only runs are distinct from parallel or sequential improvement runs (2026-11-03).
- [x] Clarify that example Quick run ignores improvement mode/rounds and display the selected settings on Full improvement (2026-11-03).
c

## Known bugs and verification gaps

- [ ] The current Python AST gate is not a security boundary for untrusted scripts or plugins; subprocess execution needs OS-level isolation before accepting arbitrary candidate code.
- [ ] Model assessments are subjective; add dataset-specific hidden tests or an independent ground-truth verifier before treating scores as benchmark correctness.
- [ ] Add tests for SSE terminal behavior after normal completion, composer evidence validation, editor retry fallback, run comparison, settings round-trip, and source upload.
- [ ] Revisit API-key storage: the settings endpoint currently writes a supplied key to local `.env` in plaintext.
