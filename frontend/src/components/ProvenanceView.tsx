import type { RecordedEvent } from '../types';
import { formatAction } from './AgentInspector';
import { ProvenanceGraph } from './ProvenanceGraph';
import { EnvironmentChanges } from './EnvironmentChanges';

export function actionDependencies(events: RecordedEvent[], actionId?: string) {
  const action = events.find(event => event.event_id === actionId && event.type === 'action');
  if (!action || action.type !== 'action') return undefined;
  const plan = events.find(event => action.input_refs.includes(event.event_id) && event.type === 'plan');
  const observation = events.find(event => event.type === 'observation' &&
    (action.input_refs.includes(event.event_id) || plan?.input_refs.includes(event.event_id)));
  const delta = events.find(event => event.type === 'environment_delta' && event.input_refs.includes(action.event_id));
  // Follow saved references. Matching turn numbers alone do not establish a dependency.
  const nodes = [observation, plan, action, delta].filter((event): event is RecordedEvent => Boolean(event));
  const edges = nodes.flatMap(target => target.input_refs.filter(id => nodes.some(node => node.event_id === id))
    .map(source => ({ source, target: target.event_id })));
  return { action, plan, observation, delta, nodes, edges };
}

export function ProvenanceView({ events, actionId, selectedId, onSelect }: { events: RecordedEvent[]; actionId?: string; selectedId?: string; onSelect?: (event: RecordedEvent) => void }) {
  const dependencies = actionDependencies(events, actionId);
  const context = dependencies?.observation?.type === 'observation' ? dependencies.observation.payload.context : undefined;
  function reference(id: string) {
    const event = events.find(item => item.event_id === id);
    return event ? <button className="artifact-link" onClick={() => onSelect?.(event)}>{id}</button> : <span>Reference unavailable</span>;
  }
  return <section className="provenance" aria-label="Action dependencies">
    <p className="eyebrow">ACTION INSPECTION</p><h2>Why this action?</h2>
    <p className="scope-note">Recorded dependencies connect observable artifacts. They do not establish causality or expose hidden reasoning.</p>
    {!dependencies ? <p>Select a recorded action in the timeline.</p> : <>
      <div className="artifact-cards">
        <article><h3>Observation</h3><small>{dependencies.observation?.event_id ?? 'Not linked'}</small>
          {dependencies.observation?.type === 'observation' && <p>
            Position ({dependencies.observation.payload.context.observation.position.join(', ')}), inventory {dependencies.observation.payload.context.inventory}.
            {' '}{dependencies.observation.payload.context.observation.cells.length} visible cells.
          </p>}</article>
        <article><h3>Explicit plan</h3><small>{dependencies.plan?.event_id ?? 'Not linked'}</small>
          {dependencies.plan?.type === 'plan' && <p>{dependencies.plan.payload.plan}</p>}</article>
        <article><h3>Action</h3><small>{dependencies.action.event_id}</small><p>{formatAction(dependencies.action.payload.action)}</p></article>
        <article><h3>Environment change</h3><small>{dependencies.delta?.event_id ?? 'Not linked'}</small>
          <EnvironmentChanges delta={dependencies.delta?.type === 'environment_delta' ? dependencies.delta.payload : undefined} /></article>
      </div>
      {context && <div className="decision-evidence" aria-label="Recorded decision evidence">
        <article><h3>Messages available to this decision</h3>
          {context.recent_messages?.length ? context.recent_messages.map(message => {
            const receipt = events.find(event => event.type === 'message_receive' && event.payload.message.message_id === message.message_id
              && dependencies.observation?.input_refs.includes(event.event_id));
            return <div key={message.message_id}><p><strong>{message.sender_id} → {message.recipient_id}</strong>: {message.content}</p>
              <small>{message.message_id} · Sent {message.sent_turn} · Received {message.delivered_turn}</small>
              {receipt && reference(receipt.event_id)}</div>;
          }) : <p>No new messages recorded in this context.</p>}
        </article>
        <article><h3>Memories available to this decision</h3>
          {context.retrieved_memories?.length ? context.retrieved_memories.map(memory => {
            // Show a write link only when a referenced retrieval also references that write.
            const retrievals = events.filter(event => event.type === 'memory_retrieve' && dependencies.observation?.input_refs.includes(event.event_id));
            const write = events.find(event => event.type === 'memory_write' &&
              (event.payload.memory as { memory_id?: string })?.memory_id === memory.memory_id && retrievals.some(item => item.input_refs.includes(event.event_id)));
            return <div key={memory.memory_id}><p><strong>{memory.memory_id}</strong>: {memory.content}</p>
              <small>Created turn {memory.created_turn}</small>{write && reference(write.event_id)}</div>;
          }) : <p>No retrieved memories recorded in this context.</p>}
        </article>
        {!!context.scenario_instructions?.length && <article><h3>Received scenario reports</h3>
          {context.scenario_instructions.map(report => <p key={report}>{report}</p>)}
        </article>}
      </div>}
      <div className="dependency-edges" aria-label="Recorded dependency edges">
        {dependencies.edges.length ? dependencies.edges.map(edge => <span key={`${edge.source}-${edge.target}`}>
          {edge.source} <b aria-label="references">→</b> {edge.target}
        </span>) : <p>No dependency edges recorded.</p>}
      </div>
    </>}
    <ProvenanceGraph events={events} selectedId={selectedId ?? actionId} onSelect={onSelect} />
  </section>;
}
