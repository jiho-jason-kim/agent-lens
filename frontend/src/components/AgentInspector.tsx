import type { Action, RecordedEvent } from '../types';

export function formatAction(action: Action): string {
  if (action.type === 'send_message') return `send_message(${action.recipient})`;
  return action.type === 'move' ? `move(${action.direction})` : `${action.type}()`;
}

export function AgentInspector({ turn, events, goal, agentId, multi = false }: { turn: number; events: RecordedEvent[]; goal: string; agentId?: string; multi?: boolean }) {
  const selected = events.filter(event => event.turn === turn && (!agentId || event.agent_id === agentId));
  const context = selected.find(event => event.type === 'observation')?.payload.context;
  const plan = selected.find(event => event.type === 'plan')?.payload.plan;
  const action = selected.find(event => event.type === 'action')?.payload.action;
  const observation = context?.observation;
  return <section className="inspector" aria-label="Agent Inspector">
    <p className="eyebrow">AGENT INSPECTOR</p><h2>{multi ? agentId?.toUpperCase() : 'Available at the decision'}</h2>
    <div className="inspector-field"><h3>Goal</h3><p>{context?.goal ?? goal}</p></div>
    {turn === 0 ? <p className="scope-note">{multi ? 'No decision recorded for this agent at this point. Advance the replay to inspect its next decision.' : 'Initial state. Select turn 1 or later to inspect a recorded decision.'}</p> : <>
      <p className="snapshot-tag">BEFORE ACTION · TURN {turn}</p>
      <div className="inspector-field"><h3>Local observation</h3>
        {observation ? <>
          <p>Position ({observation.position.join(', ')}). Inventory: {context.inventory}{multi ? '' : ' / 3'}.</p>
          <p>{observation.cells.length} cells recorded as visible.</p>
          <p>Visible resources: {observation.cells.filter(cell => cell.resource).map(cell => `(${cell.position.join(', ')})`).join(', ') || 'None'}.</p>
          <p>Visible home: {observation.cells.filter(cell => cell.home).map(cell => `(${cell.position.join(', ')})`).join(', ') || 'Not visible'}.</p>
          <details><summary>Recorded visible cells</summary><ul className="cell-list">
            {observation.cells.map(cell => <li key={cell.position.join(',')}>
              ({cell.position.join(', ')}): {[cell.resource && 'resource', cell.home && 'home', cell.obstacle && 'obstacle', cell.target && 'target', ...(cell.agents ?? [])].filter(Boolean).join(', ') || 'empty'}
            </li>)}
          </ul></details>
        </> : <p>No observation recorded for this turn.</p>}
      </div>
      {multi && <>
        <div className="inspector-field"><h3>Recent messages</h3>
          {context?.recent_messages?.length ? context.recent_messages.map(message => <p key={message.message_id}>
            <strong>{message.sender_id} → {message.recipient_id}</strong>: {message.content}
          </p>) : <p>No messages received for this decision.</p>}
        </div>
        <div className="inspector-field"><h3>Retrieved memories</h3>
          {context?.retrieved_memories?.length ? context.retrieved_memories.map(memory => <p key={memory.memory_id}>
            <strong>{memory.memory_id}</strong> · Created turn {memory.created_turn}<br />{memory.content}
          </p>) : <p>No memories retrieved for this decision.</p>}
        </div>
        {!!context?.scenario_instructions?.length && <div className="inspector-field"><h3>Received scenario report</h3>
          {context.scenario_instructions.map(text => <p key={text}>{text}</p>)}
        </div>}
      </>}
      <div className="inspector-field"><h3>Explicit plan</h3><p data-testid="explicit-plan">{plan ?? 'No plan recorded.'}</p></div>
      <div className="inspector-field"><h3>Selected action</h3><code>{action ? formatAction(action) : 'No action recorded.'}</code></div>
      {context && <details className="context-details"><summary>Previous plan and recent actions</summary>
        <h3>Previous plan</h3><p>{context.previous_plan ?? 'No previous plan.'}</p>
        <h3>Recent actions</h3>
        {context.recent_history.length ? <ul>{context.recent_history.map(entry => <li key={entry.turn}>
          Turn {entry.turn}: {formatAction(entry.action)} · {entry.success ? 'Succeeded' : 'Rejected'}. {entry.message}
        </li>)}</ul> : <p>No recent actions.</p>}
      </details>}
    </>}
    <p className="scope-note">Plans are explicit recorded artifacts. They do not expose hidden reasoning.</p>
  </section>;
}
