import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ComparisonExplorer } from './ComparisonExplorer';
import { ModelCallInspector } from './ModelCallInspector';
import type { RecordedEvent, RunMetadata } from '../types';

afterEach(() => vi.unstubAllGlobals());
it('compares saved evidence and links to replay without creating a run', async () => {
  const summary = { run_id: 'run-a', status: 'turn_limit', turns: 36, rejected_actions: 2, decision_errors: 0,
    messages: 6, model_calls: 36, input_tokens: 1000, output_tokens: 100, model_duration_ms: 200,
    usage_complete: true, completed: false };
  const fetch = vi.fn().mockImplementation(async (url: string) => ({ ok: true, json: async () => url === '/evaluations' ? [] : {
    left: summary, right: { ...summary, run_id: 'run-b', rejected_actions: 1 }, same_initial_state: true,
    same_models: true, same_settings: true, same_turn_limit: true, first_action_difference: null,
    note: 'Separate executions.',
  } }));
  vi.stubGlobal('fetch', fetch);
  const inspect = vi.fn();
  render(<ComparisonExplorer runs={[{ run_id: 'run-a', scenario_name: 'Baseline' }, { run_id: 'run-b', scenario_name: 'Verified' }] as RunMetadata[]} onBack={() => {}} onInspect={inspect} />);
  await screen.findByRole('region', { name: 'Run comparison' });
  expect(screen.getByText(/Same initial state: Yes/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Inspect candidate' }));
  expect(inspect).toHaveBeenCalledWith('run-a');
  fireEvent.change(screen.getByLabelText('Candidate run'), { target: { value: 'run-b' } });
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/evaluations/compare?left=run-b&right=run-b'));
  expect(fetch.mock.calls.every(call => call.length === 1)).toBe(true);
});

it('shows recorded model diagnostics and exact request artifacts', () => {
  render(<ModelCallInspector event={{ event_id: 'e-1', run_id: 'run-a', turn: 1, agent_id: 'blue', timestamp: '2026-10-04T00:00:00Z', input_refs: [], effect_refs: [], type: 'model_call', payload: { model: 'test-model', duration_ms: 100,
    error_category: 'rate_limit', system_instructions: 'Recorded policy', context_json: '{"inventory":0}',
    usage: { input_tokens: 50, output_tokens: 10 }, settings: {}, validated_response: null,
    prompt_version: 'v2', prompt_sha256: 'hash' } } as RecordedEvent} />);
  expect(screen.getByRole('status')).toHaveTextContent('rate_limit');
  expect(screen.getByText('50 input tokens · 10 output tokens')).toBeVisible();
  fireEvent.click(screen.getByText('Exact system instructions'));
  expect(screen.getByText('Recorded policy')).toBeVisible();
});
