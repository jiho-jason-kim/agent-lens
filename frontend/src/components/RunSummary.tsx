import type { RecordedEvent, RunMetadata, Snapshot } from '../types';
import { runStatistics } from '../replay/inspectors';

export function RunSummary({ events, finalState, run }: { events: RecordedEvent[]; finalState: Snapshot; run: RunMetadata }) {
  const stats = runStatistics(events, finalState, run);
  return <section className="run-summary" aria-label="Run statistics">
    <p className="eyebrow">COMPLETE RECORDING</p><h2>Run statistics</h2>
    <p>Scenario result: <strong>{run.status.replaceAll('_', ' ')}</strong> · {stats.turns} turns</p>
    <p>{stats.messages} messages sent · {stats.retrievals} retrieval events · {stats.invalid} rejected actions · {stats.decisionErrors} decision errors</p>
    <div className="summary-table"><table><caption>Final results from all recorded events. These counts do not change during replay.</caption>
      <thead><tr>{['Agent', 'Resources', 'Sent', 'Received', 'Memories created', 'Retrieval events', 'Memories retrieved', 'Rejected actions', 'Goal'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{stats.rows.map(row => <tr key={row.agentId}><th scope="row">{row.agentId}</th><td>{row.resources}</td><td>{row.sent}</td><td>{row.received}</td>
        <td>{row.memories}</td><td>{row.retrievals}</td><td>{row.retrievedItems}</td><td>{row.invalid}</td><td>{row.goalComplete ? 'Complete' : 'Incomplete'}</td></tr>)}</tbody>
    </table></div>
    <p className="scope-note">Memories retrieved counts items across retrieval events, including repeated retrievals. Counts use recorded artifacts only.</p>
  </section>;
}
