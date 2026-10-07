import type { RecordedEvent } from '../types';

export function investigationMoments(events: RecordedEvent[]) {
  const moments: { event: RecordedEvent; title: string; detail: string }[] = [];
  const seen = new Set<string>();
  for (const event of events) {
    if (event.type === 'message_send') {
      const message = event.payload.message;
      if (message.content.startsWith('RESOURCE ')) moments.push({ event, title: 'Scout reports a resource', detail: message.content });
      if (message.content.startsWith('UPDATE:')) moments.push({ event, title: 'Agent requests a correction', detail: message.content });
    }
    if (event.type === 'observation') {
      const context = event.payload.context;
      // Compare only artifacts present in this recorded context. Do not invent a decision explanation.
      const reports = [...(context.recent_messages ?? []).map(message => message.content),
        ...(context.retrieved_memories ?? []).map(memory => memory.content)];
      for (const report of reports) {
        const match = report.match(/RESOURCE \((\d), (\d)\)/);
        if (!match) continue;
        const x = Number(match[1]), y = Number(match[2]);
        const cell = context.observation.cells.find(cell => cell.position[0] === x && cell.position[1] === y);
        const key = `${event.agent_id}:${x},${y}`;
        if (cell && !cell.resource && !seen.has(key)) {
          seen.add(key);
          moments.push({ event, title: 'Report conflicts with local evidence',
            detail: `A report available to ${event.agent_id} names (${x}, ${y}). Its recorded observation shows that cell empty.` });
        }
      }
    }
    if (event.type === 'environment_delta' && !event.payload.success) {
      moments.push({ event, title: 'Action rejected', detail: event.payload.message });
    }
    if (event.type === 'scenario_complete') moments.push({ event, title: 'Scenario completed', detail: 'The recorded completion condition was met.' });
  }
  return moments;
}
