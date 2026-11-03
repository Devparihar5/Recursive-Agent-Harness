# Product requirements

## Product and users

Recursive Agent Harness helps a developer or researcher run a task with a local agent harness, compare proposed harness changes against observed behavior, and retain supported improvements for future tasks. The primary users are people experimenting with agent prompts, guardrails, memory, tools, and procedures on their own machine.

## Current capabilities

| Area | Expected behavior in this repository |
| --- | --- |
| Task setup | Accept an objective and domain. The CLI accepts local source paths; the dashboard accepts text/PDF uploads and execution settings, or starts one of three bundled examples with one click. Each example offers a short base-only run and a full improvement run. Execution defaults can be saved in the browser for later tasks. |
| Baseline | Run once against `harnesses/base` and persist the resulting deliverable and trace. The API supports base-only execution. |
| Improvement | Run parallel branches or sequential rounds with `k` from 1 to 5; propose invariant and domain edits, validate candidates, probe them, compare behavior, compose changes, and probe successors. |
| Selection | Choose from anonymous deliverables using the task and supplied sources, without exposing harness identity to the selector. |
| Reflection and reuse | Attribute observed effects to components, retain a changed harness only with supported evidence, and retrieve relevant past lessons as context for later editors. |
| Inspection | Show task/run history, a live plain-language stage timeline with current/completed/failed states, output, trajectory, tool calls, candidate evidence, contrasts, composition, and harness files/diffs. Library entries remain available through the API and CLI. |
| Cancellation | Allow an active run to be cancelled from the live view; persist cancelled status and stop its event stream. |
| Configuration | Support Ollama or an OpenAI-compatible chat endpoint through local settings. |
| Evaluation | Report operational metrics separately from model assessments. A separate model judge can score a completed run on demand against the task and an optional private rubric; the dashboard displays saved scores. These are subjective assessments, not hidden-test correctness. |

## Key user journeys

1. Pick a bundled example on the New task page for a quick base-only run or a full improvement run, define a custom task in the dashboard, or run `python -m app run-task --task <path>` from the CLI.
2. Optionally provide local sources, select parallel or sequential improvement and `k`, then start a run. Inspect progress and any failure in the live view.
3. Compare the selected deliverable and harness changes with the recorded trajectory and composition evidence.
4. Inspect retained library entries through the API or CLI. A later task begins from the common base and can use these lessons as editor context.

## Constraints and quality expectations

- Keep source files under the allowed working/source root; generated agent files belong under the run's `output/` directory.
- Persist enough evidence to reproduce what instructions and source material an execution saw.
- Do not equate a longer output, a behavioral difference, or an operational metric with correctness. Benchmark verification belongs outside the improvement loop.
- Show empty, loading, and failure states honestly in the dashboard.
- Treat the timeout setting as a limit for each model request, rather than for the entire improvement run.

## Planned, not yet implemented

Explicit user review gates before composition, on-demand skill invocation, full user adoption flows with written notes, and a dataset-specific hidden-test verifier are future work. The benchmark runner can use a separate model judge or a custom verifier. Script and plugin execution through subprocesses with path and AST checks is implemented; embedding-based library retrieval is implemented with a keyword fallback. See `Tasks.md` for the actionable backlog; do not present these as current features.
