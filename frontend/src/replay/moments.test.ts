import { expect, it } from 'vitest';
import { investigationMoments } from './moments';
import type { RecordedEvent } from '../types';

const base = { run_id: 'r', event_id: 'obs', turn: 10, agent_id: 'blue', timestamp: '', input_refs: [], effect_refs: [] };
const observation: RecordedEvent = { ...base, type: 'observation', payload: { context: {
  goal: 'Collect', inventory: 0, previous_plan: null, recent_history: [],
  observation: { position: [1, 2], inventory: 0, cells: [{ position: [3, 2], resource: false, home: false }] },
  retrieved_memories: [{ memory_id: 'm', created_turn: 1, source_event_id: 'source', content: 'green reported: RESOURCE (3, 2): I can see it now.' }],
} } };
it('bookmarks a contradiction only when both report and empty cell occur in the recorded context', () => {
  expect(investigationMoments([observation])[0].event.event_id).toBe('obs');
  if (observation.type !== 'observation') throw new Error('Fixture invalid');
  const hidden: RecordedEvent = { ...observation, payload: { context: { ...observation.payload.context,
    observation: { ...observation.payload.context.observation, cells: [] } } } };
  expect(investigationMoments([hidden])).toEqual([]);
  const noReport: RecordedEvent = { ...observation, payload: { context: { ...observation.payload.context, retrieved_memories: [] } } };
  expect(investigationMoments([noReport])).toEqual([]);
});
it('deduplicates repeated contradictions and preserves the first recorded turn', () => {
  const moments = investigationMoments([observation, { ...observation, event_id: 'later', turn: 13 }]);
  expect(moments).toHaveLength(1);
  expect(moments[0].event.turn).toBe(10);
});
