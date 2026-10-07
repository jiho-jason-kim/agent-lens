export function ReplayControls({ turn, maxTurn, playing, onChange, onPlay, onPause }: {
  turn: number; maxTurn: number; playing: boolean;
  onChange: (turn: number) => void; onPlay: () => void; onPause: () => void;
}) {
  return <div className="replay-controls" role="group" aria-label="Replay controls">
    <button className="secondary" disabled={turn === 0} onClick={() => onChange(turn - 1)}>Previous turn</button>
    <button className="primary" disabled={maxTurn === 0} onClick={playing ? onPause : onPlay}>{playing ? 'Pause' : 'Play'}</button>
    <button className="secondary" disabled={turn === maxTurn} onClick={() => onChange(turn + 1)}>Next turn</button>
    <span>{playing ? 'Playing · 1 turn / second' : 'Paused'}</span>
  </div>;
}
