import type { RecordedEvent } from '../types';

export type Direction = 'upstream' | 'downstream' | 'both';
export interface Edge { source: string; target: string; relationship: string }

export function relationship(source: RecordedEvent, target: RecordedEvent): string {
  if (source.type === 'environment_delta' && target.type === 'local_observation') return 'observed_after';
  if (target.type === 'model_call') return 'submitted_to';
  if (source.type === 'model_call') return 'returned_as';
  if (target.type === 'memory_write') return 'stored_as';
  if (source.type === 'memory_write' && target.type === 'memory_retrieve') return 'retrieved_for';
  if (source.type === 'message_send' && target.type === 'message_receive') return 'received_as';
  if (source.type === 'action' && target.type === 'message_send') return 'sent_to';
  if (source.type === 'action' && target.type === 'environment_delta') return 'action_effect';
  if (source.type === 'local_observation' && target.type === 'observation') return 'observed_as';
  if (target.type === 'observation' || source.type === 'observation') return 'available_to';
  if (source.type === 'plan' && target.type === 'action') return 'followed_by';
  // Unknown event pairs retain an honest label instead of implying a causal relationship.
  return 'recorded_reference';
}

export function recordedEdges(events: RecordedEvent[]): Edge[] {
  const byId = new Map(events.map(event => [event.event_id, event]));
  return events.flatMap(target => [...new Set(target.input_refs)].flatMap(id => {
    const source = byId.get(id);
    return source ? [{ source: id, target: target.event_id, relationship: relationship(source, target) }] : [];
  }));
}

export function focusedGraph(events: RecordedEvent[], selectedId: string, direction: Direction, depth: number) {
  const edges = recordedEdges(events);
  const byId = new Map(events.map(event => [event.event_id, event]));
  if (!byId.has(selectedId)) return { nodes: [], edges: [], omitted: 0 };
  const distances = new Map([[selectedId, 0]]);
  // Traverse each direction separately. Do not include unrelated siblings of an ancestor.
  for (const upstream of direction === 'both' ? [true, false] : [direction === 'upstream']) {
    let frontier = [selectedId];
    const visited = new Set(frontier);
    for (let level = 1; level <= depth && frontier.length; level++) {
      const next = edges.filter(edge => frontier.includes(upstream ? edge.target : edge.source))
        .map(edge => upstream ? edge.source : edge.target).filter(id => !visited.has(id));
      frontier = [...new Set(next)];
      for (const id of frontier) {
        visited.add(id);
        if (!distances.has(id)) distances.set(id, level);
      }
    }
  }
  // Keep a large recording usable. The UI states this display limit explicitly.
  const kept = [...distances].sort((a, b) => a[1] - b[1]).slice(0, 40).map(([id]) => id);
  return { nodes: events.filter(event => kept.includes(event.event_id)),
    edges: edges.filter(edge => kept.includes(edge.source) && kept.includes(edge.target)),
    omitted: distances.size - kept.length };
}

export function artifactSummary(event: RecordedEvent): string {
  if (event.type === 'plan') return event.payload.plan;
  if (event.type === 'message_send' || event.type === 'message_receive') {
    const message = event.payload.message;
    return `${message.sender_id} → ${message.recipient_id}: ${message.content}`;
  }
  if (event.type === 'memory_write') {
    const memory = event.payload.memory as { memory_id?: string; content?: string } | undefined;
    return `${memory?.memory_id ?? 'Memory'}: ${memory?.content ?? ''}`;
  }
  if (event.type === 'memory_retrieve') return `Retrieved ${(event.payload.memory_ids as string[] ?? []).join(', ') || 'no memories'}`;
  if (event.type === 'observation') return `Decision context · ${event.payload.context.observation.cells.length} visible cells`;
  if (event.type === 'environment_delta') return event.payload.message;
  if (event.type === 'scenario_instruction') return String(event.payload.content ?? 'Scenario report');
  if (event.type === 'action') return event.payload.action.type === 'send_message'
    ? `send_message(${event.payload.action.recipient}): ${event.payload.action.message}`
    : event.payload.action.type === 'move' ? `move(${event.payload.action.direction})` : `${event.payload.action.type}()`;
  return event.type.replaceAll('_', ' ');
}
