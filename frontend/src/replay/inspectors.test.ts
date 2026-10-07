import { expect, it } from 'vitest';
import { memoryHistory, messageHistory, runStatistics } from './inspectors';
import type { RecordedEvent, RunMetadata, Snapshot } from '../types';

import { archiveEvents, finalState } from './archive.fixture';
const run: RunMetadata = { schema_version: 2, run_id: 'r', created_at: '', agent: 'MultiAgent', goal: 'Collect', status: 'turn_limit', turns: 4, max_turns: 4 };

it('filters memories by agent and replay turn and assesses only resource locations', () => {
  expect(memoryHistory(archiveEvents, 'blue', 0, finalState)).toEqual([]);
  const memories = memoryHistory(archiveEvents, 'blue', 3, finalState);
  expect(memories).toHaveLength(1);
  expect(memories[0].stale).toBe(true);
  expect(memories[0].retrievals.map(event => event.turn)).toEqual([3]);
  expect(memories[0].source?.event_id).toBe('obs');
  expect(memoryHistory(archiveEvents, 'blue', 1, { ...finalState, resources: [[1, 0]] })[0].stale).toBe(false);
  expect(memoryHistory(archiveEvents, 'red', 4, finalState)[0].stale).toBe(false);
});
it('hides incoming messages before receipt and never exposes unrelated messages', () => {
  expect(messageHistory(archiveEvents, 1, 'red')).toEqual([]);
  expect(messageHistory(archiveEvents, 4, 'green')).toEqual([]);
  expect(messageHistory(archiveEvents, 1, 'blue')[0].receipt).toBeUndefined();
  expect(messageHistory(archiveEvents, 1)[0].writes).toEqual([]);
  const delivered = messageHistory(archiveEvents, 2, 'red')[0];
  expect(delivered.receipt?.event_id).toBe('receipt');
  expect(delivered.writes.map(event => event.event_id)).toEqual(['red-write']);
  expect(delivered.retrievals.map(event => event.event_id)).toEqual(['red-retrieve']);
});
it('requires references for memory source and retrieval links', () => {
  const unlinked = archiveEvents.map(event => ({ ...event, input_refs: [] }));
  expect(memoryHistory(unlinked, 'blue', 4, finalState)[0].source).toBeUndefined();
  expect(memoryHistory(unlinked, 'blue', 4, finalState)[0].retrievals).toEqual([]);
  expect(messageHistory(unlinked, 4, 'red')).toEqual([]);
});
it('counts repeated retrievals and actual sends rather than action attempts', () => {
  const stats = runStatistics(archiveEvents, finalState, run);
  expect(stats.messages).toBe(1);
  expect(stats.retrievals).toBe(3);
  expect(stats.rows[0]).toMatchObject({ sent: 1, received: 0, memories: 1, retrievals: 2, retrievedItems: 2 });
  expect(stats.rows[1]).toMatchObject({ received: 1, goalComplete: true, resources: 1 });
});
it('counts a rejected action once and keeps decision errors separate', () => {
  const base = { run_id: 'r', timestamp: '', effect_refs: [], input_refs: [], agent_id: 'blue', turn: 1 };
  const extra: RecordedEvent[] = [
    { ...base, event_id: 'delta', type: 'environment_delta', payload: { success: false, message: 'Rejected', position: { before: [0, 0], after: [0, 0] }, inventory: { before: 0, after: 0 }, removed_resources: [], changed_cells: [], goal_complete: { before: false, after: false } } },
    { ...base, event_id: 'error', type: 'error', payload: { stage: 'environment' } },
    { ...base, event_id: 'decision-error', type: 'error', payload: { stage: 'decision' } },
  ];
  const stats = runStatistics([...archiveEvents, ...extra], finalState, run);
  expect(stats.invalid).toBe(1);
  expect(stats.decisionErrors).toBe(1);
});
it('supports tutorial recordings without memory or message events', () => {
  const tutorial: Snapshot = { turn: 0, position: [0, 0], inventory: 0, home: [0, 0], resources: [], goal_complete: false };
  const stats = runStatistics([], tutorial, { ...run, schema_version: 1, turns: 0 });
  expect(stats.rows[0]).toMatchObject({ agentId: 'agent-1', memories: 0, sent: 0 });
});
