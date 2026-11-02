# Project memory

## Purpose and status

This is a local implementation of contrastive, two-loop harness improvement. The Python CLI, FastAPI dashboard API, React dashboard, run records, and improvement library are present. The project-root `README.md` explains operation; the six documents in `docs/` hold the current project context.

## Decisions to preserve

- Every task starts from `harnesses/base`. Retrieved library lessons inform editors; an adopted harness is not automatically used as the next task's base.
- The selector evaluates anonymous deliverables. Behavioral contrast records observed differences, not task correctness; external benchmark scores must remain outside the improvement loop.
- Reflection must have supported evidence and a helped attribution before a changed harness is retained in the library.
- Executions persist their exact harness snapshot, tool calls, trajectory, metadata, and deliverable under `runs/` for inspection.
- The executor treats supplied sources as data, validates their paths, and limits writes to the run workspace's `output/` directory.

## Completed work

- Implemented baseline execution, parallel and sequential improvement, candidate validation, composition, blind selection, reflection, and conditional library retention.
- Added a local dashboard with task creation, run inspection, harness diff/explorer, library, evaluation metrics, and model settings.
- Added scripted-provider pipeline tests, runtime/path tests, and basic API tests in `tests/`.
- Added three bundled examples and one-click runs from the New task page; the example API serves allowlisted task and source files. Removed the manual server-side source-path input from the UI; custom tasks use uploads. Quick example runs place their notes in the objective, execute only the base harness, and cap at eight agent turns with a 300-second per-call timeout; full improvement remains available separately (2026-11-02).
- New task execution defaults are saved in browser `localStorage` under `harness-task-defaults`; saving them does not create or start a task. Quick example limits remain fixed. Custom run buttons appear only after an objective is entered.
- Added cancellation for active jobs through the live-run UI and `DELETE /api/runs/{run_id}`. Cancelled jobs and mid-execution records persist a terminal status, and SSE closes (2026-11-02).
- Background job completion now has a final status guard so an unexpectedly stopped task does not remain marked `running` in its persisted job record.
- After an API restart, loading a job left as `running` now persists an `interrupted` event and status instead of leaving the disk record stale.
- Created the six project context documents under `docs/` on 2026-11-02; this was documentation only.

## Known issues and limitations

- Harness subagents, scripts, and plugins are data-only; skills are activated by keyword at startup rather than through an on-demand tool.
- Library retrieval uses lexical ranking, not embeddings. LanceDB currently indexes metadata only.
- There is no user review gate before composition or manual library adoption flow.
- The dashboard evaluation view contains operational metrics; there is no benchmark runner or external verifier.
- A full improvement run makes multiple model calls across baseline, proposal, probe, composition, selection, and reflection stages. The local `qwen3.5:4b` model running on CPU can take several minutes even for the baseline.
- `PUT /settings` writes an API key to local `.env` in plaintext when one is supplied. Treat this as a known local security limitation.

`Tasks.md` tracks actionable follow-up. `GAPS.md` contains a more detailed comparison with the paper, but is ignored by Git and should not be the sole record of important gaps.
