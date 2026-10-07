import type { RecordedEvent, Snapshot } from '../types';
const base = { run_id: 'r', timestamp: '', effect_refs: [], input_refs: [], agent_id: 'blue', turn: 1 };
export const archiveEvents: RecordedEvent[] = [
  { ...base, event_id: 'obs', type: 'local_observation', payload: {} },
  { ...base, event_id: 'write', type: 'memory_write', input_refs: ['obs'], payload: { memory: { memory_id: 'M-blue', content: 'Resource observed at (1, 0).', source_type: 'observation', source_event_id: 'obs', created_turn: 1, resource_position: [1, 0] } } },
  { ...base, event_id: 'send', type: 'message_send', payload: { message: { message_id: 'm1', sender_id: 'blue', recipient_id: 'red', content: 'Resource at (1, 0).', sent_turn: 1, delivered_turn: null } } },
  { ...base, event_id: 'receipt', agent_id: 'red', turn: 2, type: 'message_receive', input_refs: ['send'], payload: { message: { message_id: 'm1', sender_id: 'blue', recipient_id: 'red', content: 'Resource at (1, 0).', sent_turn: 1, delivered_turn: 2 } } },
  { ...base, event_id: 'red-write', agent_id: 'red', turn: 2, type: 'memory_write', input_refs: ['receipt'], payload: { memory: { memory_id: 'M-red', content: 'Blue reported a resource.', source_event_id: 'receipt', source_type: 'message', created_turn: 2 } } },
  { ...base, event_id: 'red-retrieve', agent_id: 'red', turn: 2, type: 'memory_retrieve', input_refs: ['red-write'], payload: { memory_ids: ['M-red'] } },
  { ...base, event_id: 'retrieve', turn: 3, type: 'memory_retrieve', input_refs: ['write'], payload: { memory_ids: ['M-blue'] } },
  { ...base, event_id: 'retrieve-again', turn: 4, type: 'memory_retrieve', input_refs: ['write'], payload: { memory_ids: ['M-blue'] } },
];
export const finalState: Snapshot = { turn: 4, resources: [], obstacles: [], targets: [], agents: [
  { agent_id: 'blue', position: [0, 0], inventory: 0, home: [0, 0], goal_complete: false },
  { agent_id: 'red', position: [1, 0], inventory: 1, home: [7, 0], goal_complete: true },
] };
