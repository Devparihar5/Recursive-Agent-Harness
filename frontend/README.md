# Frontend

React + TypeScript dashboard for the local Recursive Agent Harness API.

```powershell
cd frontend
npm install
npm run dev
```

The Vite server proxies `/api` to `http://127.0.0.1:8000`. Start the API separately. `npm run build` typechecks and emits `dist/`.

The interface includes tasks, source uploads, live improvement stages, trajectory/candidate/contrast/composition evidence, harness exploration, Monaco diffs, library, evaluation, and local model preferences. The default model is `qwen3.5:4b`. PDF and text uploads are sent to the task source endpoint before starting a run. SSE listeners refresh run evidence; periodic refresh also recovers missed events.

No example data is presented as real workspace activity. API errors and empty states are shown explicitly.
