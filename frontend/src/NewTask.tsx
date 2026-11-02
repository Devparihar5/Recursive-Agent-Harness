import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { GitBranch, LoaderCircle, Play, Plus, Terminal, X } from 'lucide-react';

import { api } from './api';
import { Button } from './components/ui/button';
import { Panel } from './components/ui/card';
import './new-task.css';

type ExampleTask = {
  id: string;
  title: string;
  summary: string;
  domain: string;
  description: string;
  sources: { name: string; content: string }[];
};

type RunRequest = { example?: ExampleTask; baseOnly?: boolean };
type TaskDefaults = {
  mode: 'parallel' | 'sequential';
  k: number;
  model: string;
  maxSteps: number;
  timeoutSeconds: number;
};

function readTaskDefaults(): TaskDefaults {
  let saved: Partial<TaskDefaults> = {};
  try {
    saved = JSON.parse(localStorage.getItem('harness-task-defaults') || '{}');
  } catch {
    // Invalid saved preferences fall back to the normal defaults.
  }
  const bounded = (value: unknown, minimum: number, maximum: number, fallback: number) =>
    typeof value === 'number' && Number.isInteger(value) && value >= minimum && value <= maximum ? value : fallback;
  return {
    mode: saved.mode === 'sequential' ? 'sequential' : 'parallel',
    k: bounded(saved.k, 1, 5, 1),
    model: localStorage.getItem('harness-model') || (typeof saved.model === 'string' && saved.model.trim()) || 'qwen3.5:4b',
    maxSteps: bounded(saved.maxSteps, 1, 100, 50),
    timeoutSeconds: bounded(saved.timeoutSeconds, 1, 1800, 300),
  };
}

async function uploadSource(file: File) {
  if (file.name.toLowerCase().endsWith('.pdf')) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return { name: file.name, content_base64: btoa(binary) };
  }
  return { name: file.name, content: await file.text() };
}

export function NewTaskPage() {
  const navigate = useNavigate();
  const [defaults] = useState(readTaskDefaults);
  const examples = useQuery<ExampleTask[]>({
    queryKey: ['examples'],
    queryFn: () => api('/examples'),
  });
  const [description, setDescription] = useState('');
  const [domain, setDomain] = useState('customer_support');
  const [mode, setMode] = useState(defaults.mode);
  const [k, setK] = useState(defaults.k);
  const [maxSteps, setMaxSteps] = useState(defaults.maxSteps);
  const [timeoutSeconds, setTimeoutSeconds] = useState(defaults.timeoutSeconds);
  const [uploads, setUploads] = useState<File[]>([]);
  const [model, setModel] = useState(defaults.model);
  const [saveStatus, setSaveStatus] = useState('');

  function saveDefaults() {
    if (!/^[A-Za-z0-9._:/-]{1,120}$/.test(model)
      || !Number.isInteger(k) || k < 1 || k > 5
      || !Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > 100
      || !Number.isInteger(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 1800) {
      setSaveStatus('Enter a model name and keep each number within its shown range.');
      return;
    }
    try {
      localStorage.setItem('harness-task-defaults', JSON.stringify({ mode, k, model, maxSteps, timeoutSeconds }));
      localStorage.setItem('harness-model', model);
      setSaveStatus('Saved for future tasks in this browser. Quick example runs keep their shorter limits.');
    } catch {
      setSaveStatus('Could not save settings in this browser.');
    }
  }

  const create = useMutation({
    mutationFn: async ({ example, baseOnly = false }: RunRequest) => {
      const quickExample = Boolean(example && baseOnly);
      const taskDescription = quickExample && example
        ? [example.description.trim(), ...example.sources.map(source => `## Source note: ${source.name}\n${source.content.trim()}`)].join('\n\n')
        : example?.description ?? description;
      const task = await api('/tasks', {
        description: taskDescription,
        domain: example?.domain ?? domain,
        source_files: [],
        metadata: { model },
      });
      const taskId = task.task_id || task.id;
      const sources = quickExample ? [] : example?.sources ?? await Promise.all(uploads.map(uploadSource));
      if (sources.length) await api(`/tasks/${taskId}/sources`, { files: sources });
      const run = await api(`/tasks/${taskId}/run`, {
        mode: baseOnly ? 'base' : mode,
        k: baseOnly ? 0 : k,
        model,
        max_steps: quickExample ? 8 : maxSteps,
        timeout_seconds: quickExample ? 300 : timeoutSeconds,
      });
      return { taskId, runId: run.run_id || run.id };
    },
    onSuccess: ({ taskId, runId }) => navigate(`/tasks/${taskId}/run?run=${runId}`),
  });

  return <>
    <div className="heading">
      <div>
        <div className="eyebrow">WORKSPACE / NEW TASK</div>
        <h1>Start with an example.</h1>
        <p>Pick a ready-made task to see the improvement process, or define your own below.</p>
      </div>
    </div>

    <section className="examples-section" aria-labelledby="examples-heading">
      <div className="examples-heading">
        <div>
          <div className="eyebrow">QUICK START</div>
          <h2 id="examples-heading">Run a sample task</h2>
          <p>Quick run includes the sample notes in one prompt and executes once. Full improvement compares candidates and takes longer on local models.</p>
        </div>
      </div>
      {examples.isLoading && <p className="muted">Loading examples…</p>}
      {examples.error && <div className="notice error"><X size={16}/>Could not load examples. Check that the API is running.</div>}
      <div className="example-grid">
        {examples.data?.map(example => <div className="example-card" key={example.id}>
          <span className="badge">{example.domain.replace('_', ' ')}</span>
          <h3>{example.title}</h3>
          <p>{example.summary}</p>
          <small>{example.sources.length ? `${example.sources.length} source notes included` : 'No source files needed'}</small>
          <Button
            onClick={() => create.mutate({ example, baseOnly: true })}
            disabled={create.isPending}
            aria-label={`Quick run: ${example.title}`}
          >
            {create.isPending && create.variables?.example?.id === example.id
              ? <LoaderCircle className="spin" size={16}/>
              : <Play size={16}/>}
            {create.isPending && create.variables?.example?.id === example.id ? 'Starting…' : 'Quick run'}
          </Button>
          <Button secondary onClick={() => create.mutate({ example })} disabled={create.isPending}>
            Full improvement (slower)
          </Button>
        </div>)}
      </div>
      {create.error && create.variables?.example && <div className="notice error"><X size={16}/>{create.error.message}</div>}
    </section>

    <div className="eyebrow">OR CREATE YOUR OWN</div>
    <form onSubmit={event => { event.preventDefault(); create.mutate({}); }} className="form-grid">
      <Panel title="Task definition"><div className="form-body">
        <label>Objective <span>REQUIRED</span><textarea required rows={7} placeholder="Describe what success looks like. Include constraints and expected deliverables…" value={description} onChange={event => setDescription(event.target.value)}/></label>
        <label>Domain<select value={domain} onChange={event => setDomain(event.target.value)}><option value="coding">Coding</option><option value="research">Research</option><option value="customer_support">Customer support</option><option value="operations">Operations</option><option value="general">General</option></select></label>
        <label>Upload source files <span>PDF / TEXT / MARKDOWN</span><input type="file" multiple accept=".pdf,.txt,.md,.csv,.json,.py,.ts,.tsx,.js" onChange={event => setUploads(Array.from(event.target.files || []))}/></label>
      </div></Panel>
      <Panel title="Execution settings"><div className="form-body">
        <label>Improvement mode<select value={mode} onChange={event => { setMode(event.target.value as TaskDefaults['mode']); setSaveStatus(''); }}><option value="parallel">Parallel candidates</option><option value="sequential">Sequential refinement</option></select></label>
        <label>Improvement rounds<input type="number" min={1} max={5} value={k} onChange={event => { setK(Number(event.target.value)); setSaveStatus(''); }}/></label>
        <label>Model<input value={model} onChange={event => { setModel(event.target.value); setSaveStatus(''); }}/></label>
        <label>Max agent turns<input type="number" min={1} max={100} value={maxSteps} onChange={event => { setMaxSteps(Number(event.target.value)); setSaveStatus(''); }}/></label>
        <label>Model timeout per call (seconds)<input type="number" min={1} max={1800} value={timeoutSeconds} onChange={event => { setTimeoutSeconds(Number(event.target.value)); setSaveStatus(''); }}/></label>
        <div className="hint"><GitBranch size={18}/><p>Independent candidates are tested against the same task. The composer selects improvements using behavioral evidence.</p></div>
        <Button secondary onClick={saveDefaults}>Save execution defaults</Button>
        {saveStatus && <p className="settings-feedback" role="status">{saveStatus}</p>}
        {description.trim() && <>
          <Button type="submit" disabled={create.isPending}>{create.isPending && !create.variables?.example ? <LoaderCircle className="spin" size={16}/> : <Plus size={16}/>}Create & run task</Button>
          <Button secondary disabled={create.isPending} onClick={() => create.mutate({ baseOnly: true })}><Terminal size={16}/>Run without improvement</Button>
        </>}
        {create.error && !create.variables?.example && <div className="notice error"><X size={16}/>{create.error.message}</div>}
      </div></Panel>
    </form>
  </>;
}
