import type { EnvironmentDelta, Position } from '../types';

const coordinates = (position: Position) => `(${position.join(', ')})`;

export function EnvironmentChanges({ delta }: { delta?: EnvironmentDelta }) {
  if (!delta) return <p>No environment change recorded.</p>;
  const moved = delta.position.before.some((value, index) => value !== delta.position.after[index]);
  return <div className="delta-details">
    <p>{delta.success ? 'Accepted' : 'Rejected'} · {delta.message}</p>
    <ul>
      {moved && <li>Agent {coordinates(delta.position.before)} → {coordinates(delta.position.after)}</li>}
      {delta.removed_resources.map(position => <li key={position.join(',')}>Resource removed at {coordinates(position)}</li>)}
      {delta.inventory.before !== delta.inventory.after && <li className="delta-emphasis">Inventory {delta.inventory.before} → {delta.inventory.after}</li>}
      {!delta.goal_complete.before && delta.goal_complete.after && <li className="delta-emphasis">Goal complete</li>}
      {!delta.changed_cells.length && <li>No cells changed.</li>}
    </ul>
  </div>;
}
