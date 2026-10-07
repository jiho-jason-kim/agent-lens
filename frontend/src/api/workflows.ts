export interface WorkflowMetadata {
  run_id: string;
  name: string;
  mode: 'demo' | 'live' | 'external';
  status: 'completed' | 'recovered' | 'error' | 'incomplete';
  created_at: string;
  event_count: number;
  span_count: number;
}
export interface WorkflowEvent {
  event_id: string;
  sequence: number;
  timestamp: string;
  span_id: string;
  parent_span_id: string | null;
  category: 'chain' | 'model' | 'tool' | 'retriever' | 'custom';
  phase: 'start' | 'end' | 'error' | 'custom';
  name: string;
  payload: unknown;
}
export interface WorkflowRecording { metadata: WorkflowMetadata; events: WorkflowEvent[] }

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(path, options); }
  catch { throw new Error('Cannot reach the backend. Start the API on port 8000.'); }
  if (!response.ok) {
    if (response.status === 503) throw new Error('Install backend/requirements-langchain.txt. Live mode also needs OPENAI_API_KEY and OPENAI_MODEL in backend/.env.');
    if (response.status === 404) throw new Error('This workflow recording is no longer available. Refresh the list.');
    throw new Error('The workflow request failed. Check the backend and retry.');
  }
  return response.json() as Promise<T>;
}
export const listWorkflows = () => request<WorkflowMetadata[]>('/workflows');
export const loadWorkflow = (id: string) => request<WorkflowRecording>(`/workflows/${encodeURIComponent(id)}`);
export const createWorkflowDemo = (mode: 'demo' | 'live') => request<WorkflowRecording>('/workflows/demo', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }),
});
