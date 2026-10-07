import type { RecordedEvent } from '../types';
import { investigationMoments } from '../replay/moments';

export function InvestigationGuide({ events, scenarioId, agentMode, onSelect }: {
  events: RecordedEvent[]; scenarioId?: string; agentMode?: string | null; onSelect: (event: RecordedEvent) => void;
}) {
  if (!['handoff-race', 'verified-handoff'].includes(scenarioId ?? '')) return null;
  const moments = investigationMoments(events);
  return <section className="investigation-guide" aria-label="Investigation guide">
    <p className="eyebrow">COMMUNICATION EXPERIMENT · {agentMode === 'langchain' ? 'LANGCHAIN MODEL DECISIONS' : agentMode === 'llm' ? 'MODEL DECISIONS' : 'RECORDED POLICY'}</p><h2>{scenarioId === 'handoff-race' ? 'When a true report becomes wrong' : 'Check the report before acting'}</h2>
    <p>Green reports what it sees. Red collects independently. Blue must decide whether to trust the report or check current evidence.</p>
    <p>The baseline deliberately trusts reports despite contradictory evidence. The verified policy checks observations. Live outcomes can vary.</p>
    <p>Compare Handoff Failure and Verified Handoff on the same map. These are separate executions, not a counterfactual replay.</p>
    <ol>{moments.map(({ event, title, detail }) => <li key={`${event.event_id}-${title}`}>
      <button onClick={() => onSelect(event)}><strong>Turn {event.turn} · {event.agent_id} · {title}</strong><span>{detail}</span><small>Inspect {event.event_id}</small></button>
    </li>)}</ol>
    {!moments.length && <p>No investigation moments recorded yet.</p>}
    <p className="scope-note">Bookmarks come from recorded messages, observations, action results, and completion events. They do not establish decision causality.</p>
  </section>;
}
