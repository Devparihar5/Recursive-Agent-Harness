# Repository Guidelines

## Project Structure & Module Organization

Python backend code lives in `app/`: `core` defines records and settings, `harness` loads versioned instructions, `executor` runs agents, `improvement` and `orchestration` coordinate experiments, `library` stores reusable lessons, `benchmark` evaluates outputs, and `api` serves the dashboard. The CLI entry point is `app/__main__.py`. React and TypeScript code lives in `frontend/src/`; shared controls are in `frontend/src/components/ui/`. Put Python tests in `tests/test_*.py`, default harness files in `harnesses/base/`, prompt templates in `prompts/`, and sample tasks in `examples/`. Runtime data under `runs/`, `improvement_library/`, and `benchmark_results/` is ignored by Git.

## Build, Test, and Development Commands

- `poetry install -E api -E test`: install backend, API, and test dependencies.
- `poetry run pytest`: run backend tests without a live model.
- `poetry run uvicorn app.api.routes:create_app --factory --reload --port 8000`: start the local API.
- `poetry run python -m app run-task --task examples/customer_issue.md --mode parallel --k 1`: run a sample task from the CLI.
- In `frontend/`, `npm run dev` starts Vite and `npm run build` typechecks and bundles the dashboard.

## Coding Style & Testing

Use four-space indentation and `snake_case` for Python functions and modules; use two-space indentation, `PascalCase` components, and `camelCase` values in TypeScript. Keep backend imports at module scope. Follow existing module boundaries and avoid new dependencies unless requested. Add focused `pytest` cases for changed backend behavior; tests use scripted providers and temporary directories. No coverage threshold or standalone formatter is configured. Check TypeScript with `frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json` when changing the UI.

## Commits & Pull Requests

Recent commits use concise `feat:` or `fix:` subjects. Write an intent-focused subject, explain non-obvious decisions in the body, and add useful trailers such as `Tested:` or `Not-tested:`. Pull requests should describe behavior changes, test results, related issues when available, and screenshots for visible UI changes.

## Boundaries & Project Context

Read the six documents in `docs/` before substantive changes; update `Memory.md` and `Tasks.md` when work is completed. Keep benchmark scores and private rubrics outside improvement prompts. Preserve source-path guards and the common `harnesses/base` starting point.
