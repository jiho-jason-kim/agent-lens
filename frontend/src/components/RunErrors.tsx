import type { RecordedEvent } from '../types';
import { AgentInspector } from './AgentInspector';

export function RunErrors({ events, goal }: { events: RecordedEvent[]; goal: string }) {
  const errors = events.filter(event => event.type === 'error');
  if (!errors.length) return null;
  return <section className="run-errors" aria-label="Recorded errors">
    <h2>Recorded errors</h2>
    {errors.map(event => event.type === 'error' && <article key={event.event_id}>
      <p>Turn {event.turn} · {event.event_id} · {String(event.payload.message ?? 'The operation failed.')}</p>
      {event.payload.stage === 'decision' && <>
        <p>No action executed. The timeline ends at the last completed turn.</p>
        <details><summary>Inspect failed decision at turn {event.turn}</summary>
          <AgentInspector turn={event.turn} events={events} goal={goal} agentId={event.agent_id} />
        </details>
      </>}
    </article>)}
  </section>;
}
