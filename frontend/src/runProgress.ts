export type RunEvent = {
  type?: string;
  phase?: string;
  step?: number;
  count?: number;
  action?: string;
  error?: string;
  status?: string;
};

export type PhaseStatus = 'pending' | 'active' | 'completed' | 'failed' | 'cancelled' | 'interrupted';

type Phase = { id: string; title: string; description: string; status: PhaseStatus };

const basePhases = [
  { id: 'task', title: 'Task ready', description: 'Preparing the objective' },
  { id: 'base', title: 'Agent run', description: 'Producing the answer' },
];

const improvementPhases = [
  { id: 'task', title: 'Task ready', description: 'Preparing the objective' },
  { id: 'base', title: 'Base run', description: 'Observing the starting harness' },
  { id: 'candidates', title: 'Try improvements', description: 'Propose and test changes' },
  { id: 'successor', title: 'Check result', description: 'Compose and test a successor' },
  { id: 'outcome', title: 'Learn and finish', description: 'Select, reflect, and save' },
];

export function getPipelineProgress(mode: string, events: RunEvent[], runStatus: string) {
  const definitions = mode === 'base' ? basePhases : improvementPhases;
  let current = runStatus === 'running' ? 0 : -1;
  let completedThrough = -1;
  let activity = runStatus === 'running' ? 'Preparing the task' : 'Waiting for a run';
  let terminal: PhaseStatus | null = null;

  const enter = (index: number, message: string) => {
    completedThrough = Math.max(completedThrough, index - 1);
    current = index;
    activity = message;
  };

  for (const event of events) {
    const type = event.type || '';
    if (type === 'task.started') enter(1, 'Starting the base agent');
    else if (type === 'probe.started' && event.phase === 'base') enter(1, 'Running the base harness');
    else if (type === 'execution.model_call') activity = `Model call ${(event.step ?? 0) + 1} in progress`;
    else if (type === 'execution.tool_call') activity = event.action ? `Using ${event.action}` : 'Using a workspace tool';
    else if (type === 'execution.completed') {
      if (mode === 'base') {
        completedThrough = definitions.length - 1;
        current = -1;
        activity = 'Agent run finished';
      } else activity = 'Reviewing the execution evidence';
    }
    else if (type === 'probe.completed' && event.phase === 'base') enter(2, 'Preparing improvement ideas');
    else if (type === 'proposal.started') enter(2, `Generating ${event.count ?? 2} candidate changes`);
    else if (type === 'proposal.completed') activity = 'Candidate changes ready for testing';
    else if (type === 'probe.started' && event.phase === 'candidates') enter(2, 'Testing candidate harnesses');
    else if (type === 'probe.completed' && event.phase === 'candidates') enter(3, 'Preparing a combined harness');
    else if (type === 'composition.started') enter(3, 'Combining supported changes');
    else if (type === 'composition.completed') activity = 'Combined harness ready for testing';
    else if (type === 'probe.started' && event.phase === 'successors') enter(3, 'Testing the combined harness');
    else if (type === 'probe.completed' && event.phase === 'successors') enter(4, 'Choosing the output');
    else if (type === 'selection.started') enter(4, 'Choosing an anonymous output');
    else if (type === 'selection.completed') activity = 'Selected output ready for reflection';
    else if (type === 'reflection.started') enter(4, 'Reflecting on observed evidence');
    else if (type === 'reflection.completed') activity = 'Reflection complete';
    else if (type === 'reflection.failed') activity = 'Reflection could not be completed';
    else if (type === 'library.updated') activity = 'Supported lesson saved';
    else if (type === 'task.completed' || type === 'result' && event.status === 'completed') {
      completedThrough = definitions.length - 1;
      current = -1;
      terminal = 'completed';
      activity = 'Run completed';
    }
    else if (type === 'task.failed' || type === 'result' && event.status === 'failed') terminal = 'failed';
    else if (type === 'run.cancelled') terminal = 'cancelled';
    else if (type === 'run.interrupted') terminal = 'interrupted';
  }

  if (runStatus === 'completed') {
    completedThrough = definitions.length - 1;
    current = -1;
    terminal = 'completed';
    activity = 'Run completed';
  } else if (runStatus === 'failed' || runStatus === 'cancelled' || runStatus === 'interrupted') {
    terminal = runStatus;
    if (current < 0 && completedThrough < definitions.length - 1) current = completedThrough + 1;
    activity = runStatus === 'failed' ? 'Run failed. Check Output and Events for details.'
      : runStatus === 'cancelled' ? 'Run cancelled' : 'Run interrupted before completion';
  }

  const phases: Phase[] = definitions.map((phase, index) => ({
    ...phase,
    status: index <= completedThrough ? 'completed'
      : index === current ? terminal && terminal !== 'completed' ? terminal : 'active'
      : 'pending',
  }));
  const currentPhase = current >= 0 ? phases[current] : undefined;
  const title = terminal === 'completed' ? 'Run complete'
    : terminal === 'failed' ? 'Run failed'
    : terminal === 'cancelled' ? 'Run cancelled'
    : terminal === 'interrupted' ? 'Run interrupted'
    : currentPhase?.title || 'Waiting to start';

  return { phases, current, title, activity, completed: phases.filter(phase => phase.status === 'completed').length };
}
