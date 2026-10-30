"""Dashboard resources and replayable server-sent pipeline events."""
from __future__ import annotations

import asyncio
import base64
import binascii
import difflib
import inspect
import json
import re
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.models import Task, utc_now


def register_dashboard_api(app, service):
    root = Path(service.workspace_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    jobs, active = {}, set()
    app.state.pipeline, app.state.jobs = service, jobs

    def safe(value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", value):
            raise HTTPException(400, "Invalid identifier")
        return value

    def inside(path):
        path = path.resolve()
        if not path.is_relative_to(root):
            raise HTTPException(400, "Path outside workspace")
        return path

    def read(path):
        return json.loads(inside(path).read_text(encoding="utf-8"))

    def write(path, data):
        path = inside(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def task_for(identifier):
        path = inside(root / safe(identifier) / "task.json")
        if not path.is_file():
            raise HTTPException(404, "Task not found")
        return Task.model_validate(read(path))

    def route(method, path):
        def decorate(function):
            getattr(app, method)(path)(function)
            getattr(app, method)("/api" + path)(function)
            return function
        return decorate

    @route("get", "/tasks")
    async def list_tasks():
        return [read(path) for path in sorted(root.glob("*/task.json"))]

    @route("post", "/tasks")
    async def create_task(task: Task):
        task.task_id = safe(task.task_id or task.id)
        write(root / task.task_id / "task.json", task.model_dump(mode="json"))
        return {"task_id": task.task_id}

    @route("get", "/tasks/{task_id}")
    async def get_task(task_id: str):
        return task_for(task_id)

    @route("post", "/tasks/{task_id}/sources")
    async def sources(task_id: str, request: Request):
        task = task_for(task_id)
        data = await request.json()
        files = data.get("files", [data])
        if not isinstance(files, list) or len(files) > 100:
            raise HTTPException(400, "Provide up to 100 files")
        prepared = []
        total_bytes = 0
        for item in files:
            name, content = item.get("name", ""), item.get("content", "")
            if (not isinstance(name, str) or not name or "\\" in name or ":" in name
                    or Path(name).is_absolute() or ".." in Path(name).parts):
                raise HTTPException(400, "Invalid source name")
            if name.lower().endswith(".pdf"):
                try:
                    payload = base64.b64decode(item.get("content_base64", ""), validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise HTTPException(400, "Invalid PDF base64 content") from exc
                if not payload.startswith(b"%PDF-") or len(payload) > 5 * 1024 * 1024:
                    raise HTTPException(400, "PDF must be valid and at most 5 MB")
            else:
                if not isinstance(content, str):
                    raise HTTPException(400, "Invalid text content")
                payload = content.encode("utf-8")
                if len(payload) > 128 * 1024:
                    raise HTTPException(400, "Text source exceeds 128 KB")
            total_bytes += len(payload)
            target = inside(root / task_id / "sources" / name)
            source_root = Path(getattr(service.config, "source_root", Path.cwd())).resolve()
            if not target.is_relative_to(source_root):
                raise HTTPException(400, "Upload workspace must be within the configured source root")
            prepared.append((target, payload))
        if total_bytes > 10 * 1024 * 1024:
            raise HTTPException(400, "Source files exceed 10 MB total")
        for path, payload in prepared:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            source = path.relative_to(source_root).as_posix()
            if source not in task.source_files:
                task.source_files.append(source)
        write(root / task_id / "task.json", task.model_dump(mode="json"))
        return {"source_files": task.source_files}

    async def invoke(task, mode, k, callback=None, runner=None):
        runner = runner or service
        if mode == "base":
            kwargs = {"event_callback": callback} if callback else {}
            return await runner.run_base(task, **kwargs)
        kwargs = {"mode": mode, "k": k}
        if callback and "event_callback" in inspect.signature(runner.run).parameters:
            kwargs["event_callback"] = callback
        return await runner.run(task, **kwargs)

    @route("post", "/tasks/{task_id}/execute")
    async def execute(task_id: str):
        return await invoke(task_for(task_id), "base", 0)

    @route("post", "/tasks/{task_id}/improve")
    async def improve(task_id: str, mode: str = "parallel", k: int = 1):
        try:
            return await invoke(task_for(task_id), mode, k)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @route("post", "/tasks/{task_id}/run")
    async def start(task_id: str, request: Request):
        task = task_for(task_id)
        body = await request.body()
        try:
            data = json.loads(body) if body else {}
            mode, k = data.get("mode", "parallel"), data.get("k", 1)
        except (ValueError, AttributeError) as exc:
            raise HTTPException(400, "Expected a JSON object") from exc
        if (mode == "base" and k != 0) or (mode != "base" and
                (mode not in {"parallel", "sequential"} or type(k) is not int or not 1 <= k <= 5)):
            raise HTTPException(400, "mode must be base with k=0, or parallel/sequential with k=1..5")
        requested_model = data.get("model") or task.metadata.get("model")
        overrides = {}
        if requested_model and requested_model != service.config.model:
            if not isinstance(requested_model, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,120}", requested_model):
                raise HTTPException(400, "Invalid model name")
            overrides["model"] = requested_model
        if "max_steps" in data:
            if type(data["max_steps"]) is not int or not 1 <= data["max_steps"] <= 100:
                raise HTTPException(400, "max_steps must be 1..100")
            overrides["max_steps"] = data["max_steps"]
        if "timeout_seconds" in data:
            if type(data["timeout_seconds"]) not in {int, float} or not 1 <= data["timeout_seconds"] <= 1800:
                raise HTTPException(400, "timeout_seconds must be 1..1800")
            overrides["timeout_seconds"] = data["timeout_seconds"]
        runner = service
        if overrides:
            from app.orchestration.pipeline import Pipeline
            runner = Pipeline(service.config.model_copy(update=overrides),
                              library_root=service.library.root, workspace_root=root)
        identifier = uuid4().hex
        job = {"run_id": identifier, "task_id": task_id, "status": "running", "events": [], "created_at": utc_now()}
        jobs[identifier] = job
        def emit(event):
            job["events"].append({"id": len(job["events"]) + 1, **event})
            write(root / task_id / "jobs" / f"{identifier}.json", job)
        emit({"type": "stage", "stage": "TASK RECEIVED"})
        async def work():
            try:
                job["result"] = await invoke(task, mode, k, emit, runner)
                job["status"] = "completed" if job["result"].get("deliverable") else "failed"
                emit({"type": "result", "selected_execution_id": job["result"].get("selected_execution_id"),
                      "library_entry": job["result"].get("library_entry"), "status": job["status"]})
            except Exception as exc:
                job["status"] = "failed"
                emit({"type": "error", "error": str(exc)})
        future = asyncio.create_task(work())
        active.add(future)
        future.add_done_callback(active.discard)
        return {"run_id": identifier, "status": "running", "stream_url": f"/api/runs/{identifier}/stream"}

    def job_for(identifier):
        safe(identifier)
        if identifier in jobs:
            return jobs[identifier]
        paths = list(root.glob(f"*/jobs/{identifier}.json"))
        if len(paths) != 1:
            raise HTTPException(404, "Run not found")
        job = read(paths[0])
        if job["status"] == "running":
            job["status"] = "interrupted"
        return job

    @route("get", "/runs/{run_id}/stream")
    async def stream_run(run_id: str, request: Request):
        job = job_for(run_id)
        try:
            cursor = max(0, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            cursor = 0
        async def stream():
            nonlocal cursor
            while True:
                for event in job["events"][cursor:]:
                    cursor += 1
                    yield f"id: {cursor}\nevent: {event.get('type', 'stage')}\ndata: {json.dumps(event)}\n\n"
                if job["status"] != "running" or await request.is_disconnected():
                    break
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.25)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @route("get", "/tasks/{task_id}/runs")
    async def task_runs(task_id: str):
        task_for(task_id)
        jobs_for_task = [read(path) for path in root.glob(f"{safe(task_id)}/jobs/*.json")]
        if jobs_for_task:
            return sorted(jobs_for_task, key=lambda job: job.get("created_at", ""))
        executions = [read(path) for path in root.glob(f"{safe(task_id)}/*/execution.json")]
        return sorted(executions, key=lambda record: record.get("started_at", ""))

    @route("get", "/runs")
    async def runs():
        return [read(path) for path in sorted(root.glob("*/*/execution.json"))]

    @route("get", "/runs/{run_id}")
    async def run_record(run_id: str):
        paths = list(root.glob(f"*/{safe(run_id)}/execution.json"))
        return read(paths[0]) if len(paths) == 1 else job_for(run_id)

    @route("get", "/runs/{run_id}/{section}")
    async def run_section(run_id: str, section: str):
        record = await run_record(run_id)
        result = record.get("result", record)
        steps = result.get("steps", [])
        if section == "events":
            return record.get("events", [])
        if section == "trajectory":
            execution_id = result.get("selected_execution_id")
            if execution_id and "trajectory" not in record:
                paths = list(root.glob(f"*/{safe(execution_id)}/trajectory.json"))
                return read(paths[0]) if len(paths) == 1 else []
            return record.get("trajectory", [])
        if section in {"output", "tools", "harness", "metrics"}:
            execution_id = result.get("selected_execution_id") or record.get("execution_id")
            if section == "output" and not execution_id:
                status = record.get("status")
                if status == "running":
                    return {"deliverable": "", "status": status, "error": None}
                if status in {"failed", "interrupted"}:
                    errors = [event.get("error") for event in record.get("events", [])
                              if event.get("type") == "error" and event.get("error")]
                    return {"deliverable": "", "status": status,
                            "error": errors[-1] if errors else None}
            paths = list(root.glob(f"*/{safe(execution_id)}/execution.json")) if execution_id else []
            if len(paths) != 1:
                raise HTTPException(404, "Selected execution not found")
            execution = read(paths[0])
            if section == "output":
                return {"deliverable": execution.get("deliverable", ""),
                        "status": execution.get("status"), "error": execution.get("error")}
            if section == "tools":
                return execution.get("tool_calls", [])
            if section == "metrics":
                return {"latency_seconds": execution.get("latency"),
                        "model_calls": sum(item.get("event") == "model_request" for item in execution.get("trajectory", [])),
                        "tool_calls": len(execution.get("tool_calls", [])),
                        "token_usage": execution.get("token_usage", {})}
            harness_root = paths[0].parent / "harness"
            return {file.relative_to(harness_root).as_posix(): file.read_text(encoding="utf-8")
                    for file in harness_root.rglob("*") if file.is_file()}
        fields = {"candidates": "candidate_harnesses", "contrasts": "probe_results", "composition": "composition_decisions", "diff": "candidate_harnesses"}
        if section not in fields:
            raise HTTPException(404, "Unknown run section")
        values = [item for step in steps for item in step.get(fields[section], [])]
        if section != "diff":
            return values
        from app.harness.loader import load_harness
        base = load_harness(Path(service.config.harnesses_root) / "base")
        components = []
        for candidate in values:
            path_value = candidate.get("harness_path") or candidate.get("modified_harness_path")
            if not path_value:
                continue
            path = Path(path_value).resolve()
            if not (path.is_relative_to(root) or path == base.path):
                continue
            try:
                changed = load_harness(path)
            except (ValueError, OSError):
                continue
            for name in sorted(base.files.keys() | changed.files.keys()):
                before, after = base.files.get(name, ""), changed.files.get(name, "")
                if before == after:
                    continue
                diff = "".join(difflib.unified_diff(before.splitlines(keepends=True),
                    after.splitlines(keepends=True), fromfile="base/" + name,
                    tofile="candidate/" + name))
                components.append({"candidate_id": candidate.get("id"),
                    "scope": candidate.get("scope"), "component": name,
                    "before": before, "after": after, "diff": diff,
                    "added": sum(line.startswith("+") and not line.startswith("+++")
                                 for line in diff.splitlines()),
                    "removed": sum(line.startswith("-") and not line.startswith("---")
                                   for line in diff.splitlines())})
        return components

    @route("get", "/compare")
    async def compare(run1: str, run2: str):
        from app.orchestration.pipeline import compare_runs
        try:
            return compare_runs(root, run1, run2)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @route("get", "/tasks/{task_id}/pipeline")
    async def pipeline_result(task_id: str):
        task_for(task_id)
        path = root / task_id / "pipeline.json"
        if not path.exists():
            raise HTTPException(404, "Pipeline result not found")
        return read(path)

    @route("get", "/tasks/{task_id}/harness")
    async def task_harness(task_id: str):
        task_for(task_id)
        from app.harness.loader import load_harness
        harness = load_harness(Path(service.config.harnesses_root) / "base")
        return {"version": harness.version, "files": harness.files}

    @route("get", "/harnesses")
    async def harnesses():
        from app.harness.loader import load_harness
        results = []
        for path in sorted(Path(service.config.harnesses_root).glob("*")):
            if path.is_dir():
                try:
                    harness = load_harness(path)
                    results.append({"name": path.name, "version": harness.version, "files": harness.files})
                except (ValueError, FileNotFoundError):
                    continue
        return results

    @route("get", "/harnesses/{harness_id}")
    async def harness_detail(harness_id: str):
        from app.harness.loader import load_harness
        path = Path(service.config.harnesses_root) / safe(harness_id)
        try:
            harness = load_harness(path)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"name": harness_id, "version": harness.version, "files": harness.files}

    @route("get", "/harnesses/{harness_id}/files")
    async def harness_files(harness_id: str):
        detail = await harness_detail(harness_id)
        return sorted(detail["files"])

    @route("get", "/library")
    async def library():
        return service.library.list_entries()

    @route("get", "/library/{entry_id}")
    async def entry(entry_id: str):
        result = service.library.inspect(entry_id)
        if result is None:
            raise HTTPException(404, "Entry not found")
        reused_by = []
        for path in root.glob("*/pipeline.json"):
            run = read(path)
            if result["id"] in run.get("retrieved_experiences", []):
                reused_by.append({"task_id": run.get("task_id"),
                                  "selected_execution_id": run.get("selected_execution_id")})
        return {**result, "reused_by": reused_by, "reuse_count": len(reused_by)}

    @route("get", "/settings")
    async def settings():
        data = service.config.model_dump(mode="json")
        data.pop("api_key", None)
        return {**data, "has_api_key": bool(service.config.api_key)}

    @route("get", "/models")
    async def models():
        names = [{"name": service.config.model}]
        status = "unavailable"
        if service.config.provider == "ollama":
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(service.config.base_url.rstrip("/") + "/api/tags")
                    response.raise_for_status()
                    names = [{"name": item["name"], "size": item.get("size")}
                             for item in response.json().get("models", [])]
                status = "connected"
            except (ValueError, KeyError, OSError, httpx.HTTPError):
                pass
        return {"provider": service.config.provider, "active_model": service.config.model,
                "models": names, "status": status}

    @route("put", "/settings")
    async def update_settings(request: Request):
        from app.core.config import Settings
        from app.llm.providers import create_provider
        data = await request.json()
        allowed = {"provider", "model", "base_url", "api_key", "timeout_seconds", "max_steps", "max_tokens"}
        if not isinstance(data, dict) or set(data) - allowed:
            raise HTTPException(400, "Unsupported settings field")
        try:
            config = Settings.model_validate({**service.config.model_dump(), **data})
            provider = create_provider(config)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if any("\n" in str(value) or "\r" in str(value) for value in data.values()):
            raise HTTPException(400, "Settings cannot contain line breaks")
        env_path = Path.cwd() / ".env"
        existing = {}
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    existing[key.strip()] = value
        env_keys = {"provider": "LLM_PROVIDER", "model": "LLM_MODEL",
                    "base_url": "LLM_BASE_URL", "api_key": "LLM_API_KEY",
                    "timeout_seconds": "LLM_TIMEOUT_SECONDS", "max_steps": "LLM_MAX_STEPS",
                    "max_tokens": "LLM_MAX_TOKENS"}
        for field, value in data.items():
            existing[env_keys[field]] = str(value)
        temporary = env_path.with_suffix(".env.tmp")
        temporary.write_text("\n".join(f"{key}={value}" for key, value in existing.items()) + "\n",
                             encoding="utf-8")
        temporary.replace(env_path)
        service.config, service.provider = config, provider
        return await settings()

    @route("post", "/settings/test")
    @route("post", "/models/test")
    async def test_settings():
        try:
            response = await service.provider.generate([{"role": "user", "content": "Reply with OK."}])
            return {"ok": True, "model": response.model, "response": response.content}
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc

    @route("get", "/evaluation")
    async def evaluation():
        results = [read(path) for path in sorted(root.glob("*/pipeline.json"))]
        return {"tasks": len(results), "runs": results, "metrics": [item.get("metrics", {}) for item in results]}
