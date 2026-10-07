import { useEffect, useRef } from 'react';
import type { RecordedEvent } from '../types';
import { formatAction } from './AgentInspector';

const labels: Record<RecordedEvent['type'], string> = {
  model_call: '◇ Model', observation: '◉ Context', local_observation: '◉ Observe', plan: '≡ Plan', action: '▶ Action',
  environment_delta: 'Δ Effect', goal_complete: '✓ Goal', error: '! Error',
  message_send: '↗ Send', message_receive: '↙ Receive', memory_write: '+ Memory',
  memory_retrieve: '↶ Retrieve', scenario_instruction: '! Report', target_occupied: '◎ Target', scenario_complete: '✓ Complete',
};

export function Timeline({ turn, maxTurn, onChange, perspective = 'global', events = [], agents = [], onEvent, selectedEvent }: {
  turn: number; maxTurn: number; onChange: (turn: number) => void; perspective?: 'global' | 'agent'; events?: RecordedEvent[];
  agents?: string[]; onEvent?: (event: RecordedEvent) => void; selectedEvent?: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Scroll only the history panel. Playback must not move the page away from the grid.
    const row = scroller.current?.querySelector<HTMLElement>(`[data-turn="${turn}"]`);
    const panel = scroller.current;
    if (row && panel && (row.offsetTop < panel.scrollTop || row.offsetTop + row.offsetHeight > panel.scrollTop + panel.clientHeight)) {
      panel.scrollTop = row.offsetTop - panel.clientHeight / 3;
    }
  }, [turn]);
  return <section className="timeline" aria-label="Replay timeline">
    <div className="section-heading">
      <div><p className="eyebrow">RECORDED HISTORY</p><h2>Turn by turn</h2></div>
      <span className="turn-label">{String(turn).padStart(2, '0')} <span>/ {maxTurn}</span></span>
    </div>
    <label className="sr-only" htmlFor="turn-slider">Selected turn</label>
    <input id="turn-slider" type="range" min={0} max={maxTurn} step={1} value={turn}
      disabled={maxTurn === 0} onChange={event => onChange(Number(event.target.value))}
      aria-valuetext={turn === 0 ? 'Turn 0, initial state' : `Turn ${turn}, ${perspective === 'agent' ? 'before' : 'after'} action`} />
    <div className="timeline-labels"><span>0 · Initial</span><span>{maxTurn} · Last turn</span></div>
    {agents.length > 0 && <div className="lane-headings"><span>Turn</span>{agents.map(id => <b key={id} className={`text-${id}`}>{id}</b>)}</div>}
    <div ref={scroller} className={`action-timeline ${agents.length ? 'multi-timeline' : ''}`} aria-label="Recorded actions">
      {agents.length ? Array.from({ length: maxTurn }, (_, index) => index + 1).map(value =>
        <div className={`lane-row ${value === turn ? 'current-turn' : ''}`} key={value} data-turn={value}>
          <button className="turn-index" aria-label={`Select turn ${value}`} onClick={() => onChange(value)}>{value}</button>
          {agents.map(id => <div className="agent-lane" key={id} aria-label={`${id} events at turn ${value}`}>
            {events.filter(event => event.turn === value && event.agent_id === id).map(event =>
              <button key={event.event_id} className={`event-chip event-${event.type}`} aria-pressed={selectedEvent === event.event_id}
                title={`${event.event_id} · ${event.type}`} aria-label={`${id}, turn ${value}: ${labels[event.type]}, ${event.event_id}`}
                onClick={() => onEvent?.(event)}>{event.type === 'action' ? formatAction(event.payload.action) : labels[event.type]}</button>)}
          </div>)}
        </div>) : events.filter(event => event.type === 'action' && event.turn <= maxTurn).map(event =>
        event.type === 'action' && <button key={event.event_id} data-turn={event.turn} aria-pressed={event.turn === turn}
          onClick={() => onChange(event.turn)} aria-label={`Inspect turn ${event.turn}: ${formatAction(event.payload.action)}`}>
          <span>Turn {event.turn}</span><code>{formatAction(event.payload.action)}</code><small>{event.event_id}</small>
        </button>)}
    </div>
    <p className="timeline-note">Select recorded events. Replay makes no agent calls.</p>
  </section>;
}
