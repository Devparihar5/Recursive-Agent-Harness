import { Check, LoaderCircle, X } from 'lucide-react';
import { MarkerType, Position, ReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { getPipelineProgress } from './runProgress';
import type { RunEvent, PhaseStatus } from './runProgress';
import './pipeline-progress.css';

type Props = { mode: string; k: number; events: RunEvent[]; status: string };

const statusLabel: Record<PhaseStatus, string> = {
  pending: 'Next',
  active: 'Working',
  completed: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
  interrupted: 'Interrupted',
};

function StageMark({ status, number }: { status: PhaseStatus; number: number }) {
  if (status === 'completed') return <Check size={17} aria-hidden="true"/>;
  if (status === 'active') return <LoaderCircle size={17} className="spin" aria-hidden="true"/>;
  if (status === 'failed' || status === 'cancelled' || status === 'interrupted') return <X size={17} aria-hidden="true"/>;
  return <span>{number}</span>;
}

export function PipelineProgress({ mode, k, events, status }: Props) {
  const progress = getPipelineProgress(mode, events, status);
  const stages = progress.phases;
  const nodes = stages.map((stage, index) => ({
    id: stage.id,
    position: { x: index * 207, y: 10 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    draggable: false,
    selectable: false,
    className: 'pipeline-flow-node',
    style: { width: 174, padding: 0, border: 0, background: 'transparent', boxShadow: 'none' },
    data: { label: <div className={`pipeline-node pipeline-node--${stage.status}`}>
      <div className="pipeline-node-top"><span className="pipeline-node-mark"><StageMark status={stage.status} number={index + 1}/></span><span className="pipeline-node-state">{statusLabel[stage.status]}</span></div>
      <strong>{stage.title}</strong>
      <small>{stage.description}</small>
    </div> },
  }));
  const edges = stages.slice(1).map((stage, index) => ({
    id: `${stages[index].id}-${stage.id}`,
    source: stages[index].id,
    target: stage.id,
    type: 'straight',
    animated: stage.status === 'active',
    style: { stroke: stages[index].status === 'completed' ? '#8daa6f' : '#d2dac9', strokeWidth: 2 },
    markerEnd: { type: MarkerType.ArrowClosed, color: stages[index].status === 'completed' ? '#8daa6f' : '#d2dac9' },
  }));
  const fraction = (progress.completed + (progress.current >= 0 ? 0.45 : 0)) / stages.length;
  const runKind = mode === 'base' ? 'Single agent run'
    : `${mode === 'sequential' ? 'Sequential' : 'Parallel'} · ${k} ${mode === 'sequential' ? k === 1 ? 'round' : 'rounds' : k === 1 ? 'branch' : 'branches'}`;

  return <div className="pipeline-progress">
    <div className="pipeline-progress-summary" aria-live="polite">
      <div>
        <span className="pipeline-progress-eyebrow">CURRENT STEP · {runKind}</span>
        <h3>{progress.title}</h3>
        <p>{progress.activity}</p>
      </div>
      <span className="pipeline-progress-count">{progress.completed} of {stages.length} done</span>
    </div>
    <div className="pipeline-progress-track" role="progressbar" aria-label="Run stages completed" aria-valuenow={progress.completed} aria-valuemin={0} aria-valuemax={stages.length}>
      <span style={{ width: `${Math.min(fraction * 100, 100)}%` }}/>
    </div>
    <div className="pipeline-flow" aria-label="Run stages">
      <ReactFlow key={mode} nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.12 }} minZoom={0.25} maxZoom={1}
        nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} panOnDrag={false}
        zoomOnScroll={false} zoomOnPinch={false} zoomOnDoubleClick={false} preventScrolling={false}/>
    </div>
    <ol className="pipeline-mobile-stages">
      {stages.map((stage, index) => <li className={`pipeline-mobile-stage pipeline-mobile-stage--${stage.status}`} key={stage.id}>
        <span className="pipeline-node-mark"><StageMark status={stage.status} number={index + 1}/></span>
        <span><strong>{stage.title}</strong><small>{statusLabel[stage.status]}</small></span>
      </li>)}
    </ol>
  </div>;
}
