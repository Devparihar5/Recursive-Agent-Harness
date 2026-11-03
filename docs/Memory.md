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

- Audited the supplied Harness² paper against current code; findings and code evidence are in `PAPER_ALIGNMENT.md`. The base prompt length is consistent with the paper's sparse stock harness, but C5–C8 activation, `k=1` selection, cross-task adoption, and benchmark reproduction are materially incomplete (2026-11-03).
- Diagnosed a live example run as `base, k=0` with source notes embedded in the task description, matching the Quick run action. Clarified example button labels and which execution settings apply to full improvement (2026-11-03).
- Clarified the run progress header: base jobs now say `Base only · no improvement`, and the eyebrow says `RUN TYPE` rather than implying the mode is the current step. Saved parallel jobs still render their branch count (2026-11-03).
- Fixed the harness loader's `safe_path` re-export after an import error exposed the missing binding; `tests/test_runtime.py` now imports that public name at collection time (2026-11-03).
- Added a concise root `AGENTS.md` contributor guide after verifying none existed; it records current structure, commands, conventions, and evidence expectations (2026-11-03).
- Moved backend function-local imports to module scope. Relocated `safe_path` to the harness model and re-exported it from the loader to break their import cycle without changing callers. The dashboard calls the verifier through its module so test and integration patching still works (2026-11-03).
- Connected a separate model judge to saved completed runs through `POST /api/tasks/{task_id}/verify`. Evaluation offers an optional rubric and a score action, then reads the persisted assessment. The rubric and score stay out of task and pipeline records. A live Ollama call scored a saved run successfully; model scores remain subjective assessments (2026-11-03).
- Evaluation now lists completed ordinary runs as unverified, so a completed task appears even before external scoring. Real verifier scores remain distinct; ordinary completion does not imply task correctness (2026-11-03).
- Removed the Improvement library dashboard page and overview count while retaining the library backend. Added `/health` and `/api/health`. Evaluation now reads persisted external benchmark results from `BENCHMARK_RESULTS_ROOT` and displays actual scores separately from operational metrics (2026-11-03).
- Added a Python benchmark runner interface that passes private verification context only to a verifier, stores scores outside `runs/`, and has isolation tests. No real verifier adapter is configured (2026-11-03).
- Repaired script path escape checks and awaited script/plugin tool actions within the executor. Fixed pending library adoption so it accepts a stored harness path and preserved its version; retrieval tests now adopt before expecting reuse. Fixed synchronous embeddings inside an active event loop (2026-11-03).
- Implemented baseline execution, parallel and sequential improvement, candidate validation, composition, blind selection, reflection, and conditional library retention.
- Added a local dashboard with task creation, run inspection, harness diff/explorer, library, evaluation metrics, and model settings.
- Added scripted-provider pipeline tests, runtime/path tests, and basic API tests in `tests/`.
- Added three bundled examples and one-click runs from the New task page; the example API serves allowlisted task and source files. Removed the manual server-side source-path input from the UI; custom tasks use uploads. Quick example runs place their notes in the objective, execute only the base harness, and cap at eight agent turns with a 300-second per-call timeout; full improvement remains available separately (2026-11-02).
- New task execution defaults are saved in browser `localStorage` under `harness-task-defaults`; saving them does not create or start a task. Quick example limits remain fixed. Custom run buttons appear only after an objective is entered.
- Added cancellation for active jobs through the live-run UI and `DELETE /api/runs/{run_id}`. Cancelled jobs and mid-execution records persist a terminal status, and SSE closes (2026-11-02).
- Background job completion now has a final status guard so an unexpectedly stopped task does not remain marked `running` in its persisted job record.
- After an API restart, loading a job left as `running` now persists an `interrupted` event and status instead of leaving the disk record stale.
- Replaced the dense run graph with five high-level improvement phases or two base-run phases. The view derives current/completed/terminal status from persisted events, updates on SSE, and has a mobile list (2026-11-02).
- Fixed the Tools tab blank-screen crash: tool actions arrive as objects and are now reduced to a string action name for the evidence heading, while the full record stays visible below (2026-11-02).
- Created the six project context documents under `docs/` on 2026-11-02; this was documentation only.

## Known issues and limitations

- Harness subagents remain data-only; skills are activated by keyword at startup rather than through an on-demand tool. Script and plugin subprocess helpers exist, but harness script mounting and plugin dispatch are incomplete; AST checks do not provide OS-level isolation.
- Library retrieval uses embedding similarity with a keyword fallback; the embedding service must be reachable for vector search (falls back gracefully).
- There is no user review gate before composition or full manual library adoption flow yet (pending entries + adopt API exist; end-to-end UX pending).
- Evaluation shows operational metrics and separate persisted model assessments. The optional rubric is sent only to the verifier, not the improvement pipeline. There is no hidden-test or dataset-specific ground-truth grader yet.
- A full improvement run makes multiple model calls across baseline, proposal, probe, composition, selection, and reflection stages. The local `qwen3.5:4b` model running on CPU can take several minutes even for the baseline.
- `PUT /settings` writes an API key to local `.env` in plaintext when one is supplied. Treat this as a known local security limitation.

`Tasks.md` tracks actionable follow-up. `GAPS.md` contains a more detailed comparison with the paper, but is ignored by Git and should not be the sole record of important gaps.
