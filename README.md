# Recursive Agent Harness

<p align="center">
  <img src="docs/header.svg" alt="Recursive Agent Harness" width="860"/>
</p>


A local Python and React project for running tasks, refining agent harnesses, and reusing evidence-backed lessons across tasks.

## Dashboard demo

![Dashboard walkthrough using sample data](docs/demo.gif)

The walkthrough uses sample data.

## What it does

An LLM agent's performance depends not only on the underlying model but on its **harness** —
the system prompt, guardrails, memory, tool guidance, skills, scripts, subagents, and middleware
that surround it. This project lets you improve that harness automatically and accumulate the
lessons across tasks, without touching model weights and without needing ground-truth labels.

<p align="center">
  <img src="docs/assets/architecture.svg" alt="System Architecture" width="860"/>
</p>

**Task-level recursion** refines the harness for the current task:

1. Execute the current harness as a baseline; record trajectory and deliverable.
2. An `InvariantEditor` proposes changes targeting task-agnostic weaknesses (planning, tool use,
   context management). A `DomainEditor` proposes domain-specific procedures.
3. Each candidate harness is probed on the same task under identical conditions.
4. A `Composer` reads all behavioral contrasts and merges, keeps, drops, or revises changes
   per component — every decision tied to a concrete observed fact, not a presumed score.
5. A `BlindSelector` picks the best output from anonymous deliverables (no harness identity exposed).
6. A `Reflector` attributes behavioral differences to specific components and extracts a reusable lesson.

**Harnessing-level recursion** improves future tasks:

7. If reflection produces a supported lesson and the harness changed, the adopted harness and
   `EXPERIENCE.md` are stored in the improvement library.
8. Future tasks always start from `harnesses/base`. The library is passed to editors as context so
   lessons inform new proposals without being blindly inherited.

---

## Harness components

The harness exposes eight editable component types:

| # | Component | File | When active |
|---|---|---|---|
| C1 | System prompt | `systemprompt.md` | Every model call |
| C2 | Guardrails | `guardrails.md` | Every model call |
| C3 | Memory | `LongTermMEMORY.md` | Every model call |
| C4 | Tool guidance | `tool_guidance.md` | Every model call |
| C5 | Subagents | `sub_agents/*/AGENT.md` | Delegated into a separate bounded context with declared read-only tools |
| C6 | Skills | `skills/*/SKILL.md` | Loaded on demand by name |
| C7 | Scripts | `scripts/*.py` | Invoked from the saved harness snapshot when trusted-code execution is enabled |
| C8 | Plugins / middleware | `plugins/*.py` | Synchronous hooks run automatically when trusted-code execution is enabled |

Harness Python is disabled by default. To run code you have reviewed and trust, obtain its full
hash with `python -m app harness-hash --path harnesses/base`, then set both
`ALLOW_UNSAFE_HARNESS_CODE=true` and `TRUSTED_HARNESS_SHA256=<hash>` in the environment.
Changes to any harness file change the hash and require a new review. These subprocesses do not
provide operating-system filesystem isolation.

<p align="center">
  <img src="docs/assets/harness-components.svg" alt="Harness Components C1–C8" width="860"/>
</p>

---

## Requirements

- **Python 3.11+**
- A running [Ollama](https://ollama.com) instance **or** any OpenAI-compatible endpoint
- **Node 18+** for the web dashboard

```sh
python -m pip install -e ".[test,api]"
ollama pull qwen3.5:4b
ollama pull nomic-embed-text:latest
```

With Poetry:

```sh
poetry install -E api
```

---

## Quick start

<p align="center">
  <img src="docs/assets/pipeline-parallel.svg" alt="Parallel Recursion k=3" width="860"/>
</p>

### CLI

```sh
# Baseline run only (no improvement)
python -m app run-task --task examples/customer_issue.md

# One improvement round (parallel, k=1)
python -m app run-task --task examples/customer_issue.md --mode parallel --k 1

# Three parallel improvement branches
python -m app run-task --task examples/customer_issue.md --mode parallel --k 3

# Three sequential improvement steps
python -m app run-task --task examples/customer_issue_2.md --mode sequential --k 3

# Process multiple tasks in order; adoption is optional and explicit
python -m app run-stream --task examples/customer_issue.md --task examples/incident_review.md --adopt-supported
```

Attach source files explicitly or let them be discovered from an adjacent `<task>_sources/` folder:

```sh
python -m app run-task --task examples/customer_issue.md \
  --source examples/customer_issue_sources/order.md \
  --source examples/customer_issue_sources/account.md
```

Source paths must remain within the working directory. The agent can read sources and write
only into its run's `output/` directory.

### Library

```sh
python -m app library list
python -m app library list --domain customer_support --query evidence
python -m app library inspect entry_001
python -m app library diff entry_001
python -m app library pending
python -m app library adopt <pending_id> --note "Reviewed the evidence"
python -m app library annotate <entry_id> "Review note"
python -m app library archive <entry_id> --reason "Not currently applicable"
python -m app library restore <entry_id>
```

### Compare two runs

```sh
python -m app compare-runs <execution_id_1> <execution_id_2>
```

---

## Web dashboard

```sh
# API server
poetry run uvicorn app.api.routes:create_app --factory --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to the FastAPI backend.

| Page | What it shows |
|---|---|
| Overview | Task count, library entries, active runs |
| New task | Objective, domain, source uploads, improvement mode and k |
| Tasks | All tasks with search |
| Live run | Pipeline graph with SSE updates; Output / Trajectory / Tools / Harness / Metrics / Candidates / Contrasts / Composition / Events tabs |
| Harness diff | Monaco side-by-side diff of base vs. every candidate component |
| Harness explorer | Browse harness versions and their files |
| Evaluation | Completed runs, on-demand model assessments, and separate operational metrics |
| Settings | Provider, model, base URL, API key |

API keys entered in the dashboard stay in the running backend process only. Existing `.env`
contents are preserved; use the environment to provide a key again after a restart.

---

## Run records

Every task and execution is persisted under `runs/<task_id>/`:

```
runs/<task_id>/
  task.json                  task definition
  pipeline.json              full pipeline result (steps, metrics, library entry)
  jobs/<run_id>.json         SSE event log for this run
  <execution_id>/
    task.json                task snapshot
    harness/                 exact harness snapshot used for this execution
    workspace/               copied source files + agent output/
    execution.json           full ExecutionRecord
    trajectory.json          every model request/response and tool call
    tool_calls.json          tool calls only
    deliverable.md           final agent deliverable
    metadata.json            status, timing, token usage
```

The improvement library stores complete adopted harnesses:

```
improvement_library/<domain>/entry_###/
  EXPERIENCE.md              cue, lesson, evidence, attributions
  harness/                   full harness snapshot at adoption
```

---

## Tests

```sh
pytest
```

Tests cover:

- Full pipeline with a scripted provider (no live model needed)
- Parallel and sequential recursion width and depth
- Experience retrieval without replacing the base harness
- Executor harness snapshots and path-escape guards
- Basic API job-status responses

---

## Project structure

```
app/
  core/          Shared models, config, enums
  harness/       Harness loading, validation, diffing, cloning
  executor/      AgentExecutor — bounded execution with durable records
  improvement/   Editors, ProbeRunner, Composer, BlindSelector, Reflector
  orchestration/ Pipeline (task-level + harnessing-level recursion)
  library/       ImprovementLibrary — LanceDB index + filesystem store
  llm/           Provider abstraction (Ollama / OpenAI-compatible)
  api/           FastAPI routes and SSE streaming dashboard
frontend/        React + Vite SPA (React Flow pipeline graph, Monaco diff editor)
harnesses/base/  Default harness (C1–C8 component files)
prompts/         Stage prompts (reflector, selector, composer, editors)
examples/        Sample tasks and source files
tests/           pytest test suite
```

---

## Scope and correctness note

Behavioral contrasts identify observable differences in trajectory and deliverable. They do not
establish task correctness. A candidate that produces a longer or more structured output is not
automatically better — that is why the `BlindSelector` evaluates anonymous deliverables against
the task description, and why `Reflector` requires attributions to be grounded in quoted evidence.
Benchmark scores are reserved for external evaluation and are never exposed to the improvement loop.

To assess a completed dashboard run, open **Evaluation**, optionally enter a rubric, and select
**Score with model**. The verifier uses `VERIFIER_MODEL` when set, otherwise the configured task
model. Its score is stored under `BENCHMARK_RESULTS_ROOT` and is a model assessment, not a
hidden-test correctness score. A custom `ExternalVerifier` can be supplied to the Python
`BenchmarkRunner` for dataset-specific grading.
