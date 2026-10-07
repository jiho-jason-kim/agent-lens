import type { RecordedEvent, Snapshot } from '../types';
import { memoryHistory } from '../replay/inspectors';

export function MemoryInspector({ events, agentId, turn, state, onSelect }: {
  events: RecordedEvent[]; agentId: string; turn: number; state: Snapshot; onSelect: (event: RecordedEvent) => void;
}) {
  const memories = memoryHistory(events, agentId, turn, state);
  return <section className="archive-inspector" aria-label="Memory inspector">
    <p className="eyebrow">{agentId.toUpperCase()} MEMORY</p><h2>Stored memories</h2>
    <p className="scope-note">Recorded through turn {turn}. Stale status compares memory with this turn’s global snapshot.</p>
    {!memories.length && <p>No memories recorded for this agent yet.</p>}
    {memories.map(({ memory, write, source, retrievals, stale }) => <article key={memory.memory_id}>
      <h3>{memory.memory_id}</h3><p>{memory.content}</p>
      <dl><dt>Created</dt><dd>Turn {memory.created_turn}</dd><dt>Source</dt><dd>{memory.source_type ?? 'Recorded artifact'}</dd>
        <dt>Retrieved</dt><dd>{retrievals.length ? retrievals.map(event => event.turn).join(', ') : 'Never'}</dd>
        <dt>Status</dt><dd className={stale ? 'stale-memory' : ''}>{stale ? 'Possibly stale' : memory.resource_position ? 'Resource still present' : 'Not assessed'}</dd></dl>
      <div className="archive-links">{source && <button onClick={() => onSelect(source)}>Source {source.event_id}</button>}
        <button onClick={() => onSelect(write)}>Trace {write.event_id}</button>
        {retrievals.map(event => <button key={event.event_id} onClick={() => onSelect(event)}>Retrieved at turn {event.turn}</button>)}
      </div>
    </article>)}
  </section>;
}
