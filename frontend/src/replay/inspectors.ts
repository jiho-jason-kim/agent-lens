import type { Memory, RecordedEvent, RunMetadata, Snapshot } from '../types';

export function memoryHistory(events: RecordedEvent[], agentId: string, turn: number, state: Snapshot) {
  const available = events.filter(event => event.turn <= turn);
  return available.filter(event => event.type === 'memory_write' && event.agent_id === agentId).map(write => {
    const memory = (write.payload as { memory: Memory }).memory;
    const source = available.find(event => event.event_id === memory.source_event_id && write.input_refs.includes(event.event_id));
    const retrievals = available.filter(event => event.type === 'memory_retrieve' && event.agent_id === agentId
      && event.input_refs.includes(write.event_id) && (event.payload.memory_ids as string[]).includes(memory.memory_id));
    // This comparison belongs to the debugger. It never changes an agent's recorded context.
    const stale = !!memory.resource_position && !state.resources.some(position => position.join(',') === memory.resource_position?.join(','));
    return { memory, write, source, retrievals, stale };
  });
}

export function messageHistory(events: RecordedEvent[], turn: number, agentId?: string) {
  const available = events.filter(event => event.turn <= turn);
  return available.filter(event => event.type === 'message_send').flatMap(send => {
    if (send.type !== 'message_send') return [];
    const message = send.payload.message;
    const receipt = available.find(event => event.type === 'message_receive' && event.input_refs.includes(send.event_id)
      && event.payload.message.message_id === message.message_id);
    // A recipient cannot inspect an incoming message before its recorded receipt.
    if (agentId && agentId !== message.sender_id && !(agentId === message.recipient_id && receipt)) return [];
    const writes = receipt ? available.filter(event => event.type === 'memory_write' && event.input_refs.includes(receipt.event_id)) : [];
    const retrievals = available.filter(event => event.type === 'memory_retrieve' && writes.some(write => event.input_refs.includes(write.event_id)));
    return [{ message, send, receipt, writes, retrievals }];
  });
}

export function runStatistics(events: RecordedEvent[], state: Snapshot, run: RunMetadata) {
  const agents = 'agents' in state ? state.agents : [{ ...state, agent_id: 'agent-1' }];
  const rows = agents.map(agent => {
    const own = events.filter(event => event.agent_id === agent.agent_id);
    return { agentId: agent.agent_id, resources: agent.inventory, goalComplete: agent.goal_complete,
      sent: own.filter(event => event.type === 'message_send').length,
      received: own.filter(event => event.type === 'message_receive').length,
      memories: own.filter(event => event.type === 'memory_write').length,
      retrievals: own.filter(event => event.type === 'memory_retrieve').length,
      retrievedItems: own.filter(event => event.type === 'memory_retrieve').reduce((sum, event) => sum + (event.type === 'memory_retrieve' ? (event.payload.memory_ids as string[]).length : 0), 0),
      invalid: own.filter(event => event.type === 'environment_delta' && !event.payload.success).length };
  });
  return { rows, turns: run.turns, messages: rows.reduce((sum, row) => sum + row.sent, 0),
    retrievals: rows.reduce((sum, row) => sum + row.retrievals, 0), invalid: rows.reduce((sum, row) => sum + row.invalid, 0),
    decisionErrors: events.filter(event => event.type === 'error' && event.payload.stage === 'decision').length };
}
