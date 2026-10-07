import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { actionDependencies, ProvenanceView } from './ProvenanceView';
import { EnvironmentChanges } from './EnvironmentChanges';
import type { EnvironmentDelta, RecordedEvent } from '../types';

const base = { run_id: 'run-test', turn: 1, agent_id: 'agent-1', timestamp: '', input_refs: [], effect_refs: [] };
const delta: EnvironmentDelta = {
  success: true, message: 'Resource collected.', position: { before: [0, 0], after: [0, 0] },
  inventory: { before: 2, after: 3 }, removed_resources: [[0, 0]],
  goal_complete: { before: false, after: true }, changed_cells: [[0, 0]],
};
const events: RecordedEvent[] = [
  { ...base, event_id: 'obs', type: 'observation', payload: { context: {
    goal: 'Collect.', inventory: 2, previous_plan: null, recent_history: [],
    observation: { position: [0, 0], inventory: 2, cells: [], goal_complete: false },
  } } },
  { ...base, event_id: 'plan', type: 'plan', input_refs: ['obs'], payload: { plan: 'Collect here.' } },
  { ...base, event_id: 'action', type: 'action', input_refs: ['obs', 'plan'], payload: { action: { type: 'collect' } } },
  { ...base, event_id: 'delta', type: 'environment_delta', input_refs: ['action'], payload: delta },
];

it('renders every recorded edge, including the direct observation-to-action reference', () => {
  render(<ProvenanceView events={events} actionId="action" />);
  const edges = screen.getByLabelText('Recorded dependency edges');
  expect(edges).toHaveTextContent('obs → plan');
  expect(edges).toHaveTextContent('obs → action');
  expect(edges).toHaveTextContent('plan → action');
  expect(edges).toHaveTextContent('action → delta');
  expect(screen.getByText('Inventory 2 → 3')).toBeInTheDocument();
  expect(screen.getByText('Goal complete')).toBeInTheDocument();
});

it('does not invent dependencies from matching turn numbers', () => {
  const unlinked = events.map(event => ({ ...event, input_refs: [] }));
  const dependencies = actionDependencies(unlinked, 'action');
  expect(dependencies?.nodes.map(node => node.event_id)).toEqual(['action']);
  expect(dependencies?.edges).toEqual([]);
  render(<ProvenanceView events={unlinked} actionId="action" />);
  expect(screen.getAllByText('Not linked')).toHaveLength(3);
  expect(screen.getByText('No dependency edges recorded.')).toBeInTheDocument();
});

it('reports movement and rejected actions without inventing changed cells', () => {
  const { rerender } = render(<EnvironmentChanges delta={{ ...delta, position: { before: [1, 0], after: [0, 0] } }} />);
  expect(screen.getByText('Agent (1, 0) → (0, 0)')).toBeInTheDocument();
  rerender(<EnvironmentChanges delta={{ ...delta, success: false, message: 'No resource.', changed_cells: [], removed_resources: [],
    inventory: { before: 0, after: 0 }, goal_complete: { before: false, after: false } }} />);
  expect(screen.getByText('Rejected · No resource.')).toBeInTheDocument();
  expect(within(screen.getByRole('list')).getAllByRole('listitem')).toHaveLength(1);
});

it('shows decision evidence exactly as recorded without inventing source links', () => {
  const enriched: RecordedEvent[] = events.map(event => event.type === 'observation' ? {
    ...event, payload: { context: { ...event.payload.context,
      recent_messages: [{ message_id: 'm-1', sender_id: 'green', recipient_id: 'blue', content: 'Unverified report.', sent_turn: 1, delivered_turn: 2 }],
      retrieved_memories: [{ memory_id: 'M-1', content: 'Remembered report.', created_turn: 1, source_event_id: 'missing' }],
    } },
  } : event);
  render(<ProvenanceView events={enriched} actionId="action" />);
  const evidence = screen.getByLabelText('Recorded decision evidence');
  expect(evidence).toHaveTextContent('Unverified report.');
  expect(evidence).toHaveTextContent('Remembered report.');
  expect(within(evidence).queryAllByRole('button')).toHaveLength(0);
  expect(screen.getByText('→ action_effect →')).toBeInTheDocument();
});
