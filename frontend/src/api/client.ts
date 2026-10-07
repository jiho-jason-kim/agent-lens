import type { RecordedEvent, RunMetadata, Snapshot, Scenario } from '../types';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error('Cannot reach the backend. Start the API on port 8000, then retry.');
  }
  if (!response.ok) {
    if (response.status === 503) {
      throw new Error('LangChain is unavailable. Install backend/requirements-langchain.txt and set OPENAI_API_KEY and OPENAI_MODEL in backend/.env, then restart the backend.');
    }
    if (response.status === 404) throw new Error('This recording is no longer available. Refresh the run list.');
    throw new Error(`The request failed (HTTP ${response.status}). Check the backend and retry.`);
  }
  try {
    return await response.json() as T;
  } catch {
    throw new Error('The backend returned unreadable data. Check the API connection, then retry.');
  }
}

// Fetch both recording versions. Sorting preserves one chronological run selector.
export const listRuns = async () => (await Promise.all([request<RunMetadata[]>('/runs'),
  request<RunMetadata[]>('/runs?schema_version=2')])).flat().sort((a, b) => b.created_at.localeCompare(a.created_at));
export const listScenarios = () => request<Scenario[]>('/scenarios');
export const loadStates = (runId: string) => request<Snapshot[]>(`/runs/${encodeURIComponent(runId)}/states`);
export const loadEvents = (runId: string) => request<RecordedEvent[]>(`/runs/${encodeURIComponent(runId)}/events`);
// Creating a simulation is an explicit action. Moving the slider never calls this function.
export const createRun = (scenarioId = 'tutorial', agent: 'mock' | 'langchain' = 'mock') => request<RunMetadata>('/runs', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ scenario_id: scenarioId, agent }),
});
