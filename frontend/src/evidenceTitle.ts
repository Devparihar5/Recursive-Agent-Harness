export function evidenceTitle(row: Record<string, unknown>): string {
  const action = row.action;
  const actionName = typeof action === 'string' ? action
    : action && typeof action === 'object' && 'action' in action ? action.action
    : undefined;
  for (const value of [row.type, row.event, actionName, row.component, row.candidate_id]) {
    if (typeof value === 'string' && value.trim()) return value;
  }
  return 'Observation';
}
