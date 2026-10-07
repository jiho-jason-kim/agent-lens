import type { RecordedEvent } from '../types';

const base = { run_id: 'run-lineage', turn: 1, agent_id: 'green', timestamp: '', input_refs: [], effect_refs: [] };
export const lineage: RecordedEvent[] = [
  { ...base, event_id: 'report', type: 'scenario_instruction', payload: { content: 'Two resources near (7, 2).' } },
  { ...base, event_id: 'write-green', type: 'memory_write', input_refs: ['report'], payload: { memory: { memory_id: 'M-green', content: 'Two resources near (7, 2).' } } },
  { ...base, event_id: 'retrieve-green', type: 'memory_retrieve', input_refs: ['write-green'], payload: { memory_ids: ['M-green'] } },
  { ...base, event_id: 'context-green', type: 'observation', input_refs: ['retrieve-green'], payload: { context: { goal: 'Share', inventory: 0, previous_plan: null, recent_history: [], observation: { position: [0, 0], inventory: 0, cells: [] } } } },
  { ...base, event_id: 'plan-green', type: 'plan', input_refs: ['context-green'], payload: { plan: 'Share report.' } },
  { ...base, event_id: 'action-green', type: 'action', input_refs: ['plan-green'], payload: { action: { type: 'send_message', recipient: 'blue', message: 'Two resources near (7, 2).' } } },
  { ...base, event_id: 'send', type: 'message_send', input_refs: ['action-green'], payload: { message: { message_id: 'm-1', sender_id: 'green', recipient_id: 'blue', content: 'Two resources near (7, 2).', sent_turn: 1, delivered_turn: null } } },
  { ...base, event_id: 'receive', agent_id: 'blue', turn: 2, type: 'message_receive', input_refs: ['send'], payload: { message: { message_id: 'm-1', sender_id: 'green', recipient_id: 'blue', content: 'Two resources near (7, 2).', sent_turn: 1, delivered_turn: 2 } } },
  { ...base, event_id: 'write-blue', agent_id: 'blue', turn: 2, type: 'memory_write', input_refs: ['receive'], payload: { memory: { memory_id: 'M-blue', content: 'Green reported two resources.' } } },
  { ...base, event_id: 'retrieve-blue', agent_id: 'blue', turn: 2, type: 'memory_retrieve', input_refs: ['write-blue'], payload: { memory_ids: ['M-blue'] } },
  { ...base, event_id: 'unrelated', type: 'plan', payload: { plan: 'No recorded link.' } },
];
