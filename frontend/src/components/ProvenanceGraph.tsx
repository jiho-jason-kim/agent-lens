import { useEffect, useId, useRef, useState } from 'react';
import type { RecordedEvent } from '../types';
import { artifactSummary, focusedGraph, type Direction } from '../replay/provenance';

export function ProvenanceGraph({ events, selectedId, onSelect }: {
  events: RecordedEvent[]; selectedId?: string; onSelect?: (event: RecordedEvent) => void;
}) {
  const [direction, setDirection] = useState<Direction>('both');
  const [depth, setDepth] = useState(2);
  const canvas = useRef<HTMLDivElement>(null);
  const markerId = useId().replaceAll(':', '');
  const graph = focusedGraph(events, selectedId ?? '', direction, depth);
  const positions = new Map<string, { x: number; y: number }>();
  const columns = new Map<string, number>();
  const rows = new Map<number, number>();
  // Recorded order places parents before their effects. Every line comes from an input reference.
  graph.nodes.forEach(node => {
    const parents = graph.edges.filter(edge => edge.target === node.event_id);
    const column = Math.max(0, ...parents.map(edge => (columns.get(edge.source) ?? -1) + 1));
    columns.set(node.event_id, column);
    const row = rows.get(column) ?? 0;
    rows.set(column, row + 1);
    positions.set(node.event_id, { x: 20 + column * 300, y: 20 + row * 150 });
  });
  const width = Math.max(540, rows.size * 300);
  const height = Math.max(170, ...[...rows.values()].map(count => count * 150 + 20));
  const focusedPosition = positions.get(selectedId ?? '');
  const focusX = focusedPosition?.x ?? 0;
  const focusY = focusedPosition?.y ?? 0;
  useEffect(() => {
    // Center the selected artifact inside the graph without scrolling the replay page.
    if (canvas.current) {
      canvas.current.scrollLeft = Math.max(0, focusX - canvas.current.clientWidth / 2 + 110);
      canvas.current.scrollTop = Math.max(0, focusY - canvas.current.clientHeight / 2 + 55);
    }
  }, [selectedId, focusX, focusY, depth, direction]);
  return <section className="provenance-graph" aria-label="Focused provenance">
    <div className="section-heading"><div><p className="eyebrow">RECORDED LINEAGE</p><h2>Focused provenance</h2></div>
      <div className="graph-controls">
        <label>Direction <select aria-label="Direction" value={direction} onChange={event => setDirection(event.target.value as Direction)}>
          <option value="both">Upstream + downstream</option><option value="upstream">Upstream</option><option value="downstream">Downstream</option>
        </select></label>
        <label>Reference depth <select aria-label="Reference depth" value={depth} onChange={event => setDepth(Number(event.target.value))}>
          {[1, 2, 4, 8].map(value => <option key={value} value={value}>{value} links</option>)}
        </select></label>
      </div>
    </div>
    <p className="scope-note">Arrows follow recorded references. They show available information and recorded effects, not proven decision causes.</p>
    {!graph.nodes.length ? <p>Select an event or action to trace its recorded references.</p> : <>
      <p className="graph-count">{graph.nodes.length} events · {graph.edges.length} references · Focus: {selectedId}
        {graph.omitted > 0 && ` · ${graph.omitted} events omitted by the 40-event display limit. Reduce the depth or select a nearer event.`}</p>
      <div ref={canvas} className="graph-scroll" tabIndex={0} aria-label="Provenance graph canvas">
        <div className="graph-canvas" style={{ width, height }}>
          <svg width={width} height={height} aria-hidden="true">
            <defs><marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#91baa9" /></marker></defs>
            {graph.edges.map(edge => {
              const start = positions.get(edge.source)!;
              const end = positions.get(edge.target)!;
              return <path key={`${edge.source}-${edge.target}`} d={`M ${start.x + 220} ${start.y + 55} C ${start.x + 265} ${start.y + 55}, ${end.x - 45} ${end.y + 55}, ${end.x} ${end.y + 55}`}
                fill="none" stroke="#91baa9" strokeWidth="1.5" markerEnd={`url(#${markerId})`} />;
            })}
          </svg>
          {graph.nodes.map(node => <button key={node.event_id} className={`graph-node text-${node.agent_id}`}
            style={{ left: positions.get(node.event_id)!.x, top: positions.get(node.event_id)!.y }}
            aria-pressed={node.event_id === selectedId} aria-label={`Trace ${node.event_id}, ${node.agent_id}, turn ${node.turn}, ${node.type}`}
            onClick={() => onSelect?.(node)}>
            <small>{node.event_id} · {node.agent_id} · Turn {node.turn}</small>
            <strong>{node.type.replaceAll('_', ' ')}</strong><span>{artifactSummary(node)}</span>
          </button>)}
        </div>
      </div>
      <details className="graph-references" open><summary>Typed references</summary>
        <ul>{graph.edges.map(edge => <li key={`${edge.source}-${edge.target}`}>
          <button onClick={() => onSelect?.(events.find(event => event.event_id === edge.source)!)}>{edge.source}</button>
          <span> → {edge.relationship} → </span>
          <button onClick={() => onSelect?.(events.find(event => event.event_id === edge.target)!)}>{edge.target}</button>
        </li>)}</ul>
        {!graph.edges.length && <p>No references recorded within this selection.</p>}
      </details>
    </>}
  </section>;
}
