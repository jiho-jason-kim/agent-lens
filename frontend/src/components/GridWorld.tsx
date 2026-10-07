import type { Observation, Position, Snapshot } from '../types';

export function GridWorld({ state, perspective = 'global', observation, changedCells = [], agentId = 'agent-1' }: {
  state: Snapshot; agentId?: string; perspective?: 'global' | 'agent'; observation?: Observation; changedCells?: Position[];
}) {
  // Deltas describe post-action changes and must not alter the pre-action Agent View.
  const changed = new Set(perspective === 'global' ? changedCells.map(position => position.join(',')) : []);
  const resources = new Set(state.resources.map(([x, y]) => `${x},${y}`));
  const visibleCells = new Map(observation?.cells.map(cell => [cell.position.join(','), cell]));
  const multi = 'agents' in state;
  const occupants = perspective === 'agent'
    ? [...(observation ? [{ agent_id: agentId, position: observation.position }] : []), ...(observation?.visible_agents ?? [])]
    : multi ? state.agents : [{ agent_id: 'agent-1', position: state.position }];
  return (
    <div className="board-wrap">
      <div className="axis-x" aria-hidden="true">{Array.from({ length: 8 }, (_, x) => <span key={x}>{x}</span>)}</div>
      <div className="board-row">
        <div className="axis-y" aria-hidden="true">{Array.from({ length: 8 }, (_, y) => <span key={y}>{y}</span>)}</div>
        <div className="board" role="grid" aria-label={`${perspective === 'global' ? 'Global' : 'Agent'} grid at turn ${state.turn}`}>
          {Array.from({ length: 8 }, (_, y) => (
            <div role="row" className="grid-row" key={y}>
              {Array.from({ length: 8 }, (_, x) => {
                // Agent View reads recorded cells only, never the global cell contents.
                const cell = visibleCells.get(`${x},${y}`);
                const isChanged = changed.has(`${x},${y}`);
                const hidden = perspective === 'agent' && !cell;
                const agents = hidden ? [] : occupants.filter(item => item.position[0] === x && item.position[1] === y);
                const agent = agents.length > 0;
                const home = perspective === 'agent' ? cell?.home : (multi ? state.agents.some(item => item.home[0] === x && item.home[1] === y) : state.home[0] === x && state.home[1] === y);
                const resource = perspective === 'agent' ? cell?.resource : resources.has(`${x},${y}`);
                const obstacle = perspective === 'agent' ? cell?.obstacle : multi && state.obstacles?.some(p => p[0] === x && p[1] === y);
                const target = perspective === 'agent' ? cell?.target : multi && state.targets?.some(p => p[0] === x && p[1] === y);
                const contents = [agent && (multi ? agents.map(item => item.agent_id).join(', ') : 'agent'), home && 'home', resource && 'resource', obstacle && 'obstacle', target && 'target'].filter(Boolean).join(', ');
                return (
                  <div key={x} role="gridcell" className={`cell ${isChanged ? 'changed-cell' : ''} ${hidden ? 'unknown-cell' : ''} ${home ? 'home-cell' : ''} ${agent ? 'agent-cell' : ''} ${obstacle ? 'obstacle-cell' : ''} ${target ? 'target-cell' : ''}`}
                    aria-label={`Cell (${x}, ${y}): ${hidden ? 'unknown' : contents || 'empty'}${isChanged ? ', changed' : ''}`}>
                    {hidden && <span className="unknown-mark" aria-hidden="true">·</span>}
                    {home && <span className="home-mark" aria-hidden="true">H</span>}
                    {resource && <span className={`resource-mark ${agent ? 'shared' : ''}`} aria-hidden="true">◆</span>}
                    {target && <span className="target-mark" aria-hidden="true">◎</span>}
                    {obstacle && <span aria-hidden="true">▧</span>}
                    {agents.length > 0 && <span className="occupants">{agents.map(item => <span key={item.agent_id} className={`agent-mark agent-${item.agent_id}`} aria-hidden="true">{multi ? item.agent_id[0].toUpperCase() : 'A'}</span>)}</span>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
