import { useEffect, useState } from 'react';
import type { RunMetadata } from '../types';
interface Summary {
  run_id: string; scenario: string; status: string; turns: number; max_turns: number;
  rejected_actions: number; decision_errors: number; messages: number; model_calls: number;
  input_tokens: number; output_tokens: number; model_duration_ms: number; usage_complete: boolean;
  rejected_by_agent?: Record<string, number>; completed: boolean; models: string[]; prompt_hashes: string[];
}
interface Comparison {
  left: Summary; right: Summary; same_initial_state: boolean; same_models: boolean; same_settings: boolean; same_turn_limit: boolean;
  first_action_difference: { turn: number; agent: string; left_action: unknown; right_action: unknown } | null; note: string;
}
interface Evaluation { evaluation_id: string; mode: string; status: string; repetitions: number; max_turns: number; scope: string; pairs: Comparison[] }
async function read<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error('Comparison could not be loaded. Check the backend and refresh.');
  return response.json() as Promise<T>;
}
export function ComparisonExplorer({ runs, onBack, onInspect }: { runs: RunMetadata[]; onBack: () => void; onInspect: (id: string) => void }) {
  const [left, setLeft] = useState(runs[1]?.run_id ?? runs[0]?.run_id ?? '');
  const [right, setRight] = useState(runs[0]?.run_id ?? '');
  const [comparison, setComparison] = useState<Comparison>();
  const [reports, setReports] = useState<Evaluation[]>([]);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setComparison(undefined); setError('');
    if (left && right) read<Comparison>(`/evaluations/compare?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`)
      .then(value => { if (active) setComparison(value); }).catch(cause => { if (active) setError(String(cause.message)); });
    return () => { active = false; };
  }, [left, right, refresh]);
  useEffect(() => {
    let active = true;
    read<Evaluation[]>('/evaluations').then(value => { if (active) setReports(value); }).catch(cause => { if (active) setError(String(cause.message)); });
    return () => { active = false; };
  }, [refresh]);
  const metrics: [keyof Summary, string][] = [['status', 'Outcome'], ['turns', 'Turns'], ['rejected_actions', 'Rejected actions'], ['decision_errors', 'Decision errors'], ['messages', 'Messages sent'], ['model_calls', 'Model calls'], ['input_tokens', 'Input tokens'], ['output_tokens', 'Output tokens'], ['model_duration_ms', 'Model time (ms)']];
  return <main className="app-shell"><header className="header"><div><p className="eyebrow">AGENT LENS / EVALUATION</p><h1>Compare recorded runs</h1></div><button className="secondary" onClick={onBack}>Back to replay</button></header>
    <section className="workflow-intro"><p>Compare saved evidence. No agents run when you change these selections.</p>
      <label>Baseline<select aria-label="Baseline run" value={left} onChange={event => setLeft(event.target.value)}>{runs.map(run => <option key={run.run_id} value={run.run_id}>{run.scenario_name} · {run.run_id.slice(-8)}</option>)}</select></label>
      <label>Candidate<select aria-label="Candidate run" value={right} onChange={event => setRight(event.target.value)}>{runs.map(run => <option key={run.run_id} value={run.run_id}>{run.scenario_name} · {run.run_id.slice(-8)}</option>)}</select></label>
      <button className="secondary" onClick={() => setRefresh(value => value + 1)}>Refresh comparisons</button>
    </section>
    {error && <p role="alert">{error}</p>}
    {comparison && <section className="workflow-intro" aria-label="Run comparison"><p>Same initial state: {comparison.same_initial_state ? 'Yes' : 'No'} · Same models: {comparison.same_models ? 'Yes' : 'No / unknown'} · Same settings: {comparison.same_settings ? 'Yes' : 'No / unknown'} · Same turn limit: {comparison.same_turn_limit ? 'Yes' : 'No'}</p>
      <table className="comparison-table"><thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th></tr></thead><tbody>{metrics.map(([key, label]) => <tr key={key}><th>{label}</th>{[comparison.left, comparison.right].map((run, index) => <td key={index}>{(key === 'input_tokens' || key === 'output_tokens') && !run.usage_complete ? 'Unavailable / partial' : String(run[key])}</td>)}</tr>)}</tbody></table>
      <p>Models: {comparison.left.models?.join(', ') || 'Unknown'} / {comparison.right.models?.join(', ') || 'Unknown'}</p>
      <p>Rejected actions by agent: {JSON.stringify(comparison.left.rejected_by_agent ?? {})} / {JSON.stringify(comparison.right.rejected_by_agent ?? {})}</p>
      <div className="workflow-navigation"><button className="secondary" onClick={() => onInspect(left)}>Inspect baseline</button><button className="secondary" onClick={() => onInspect(right)}>Inspect candidate</button></div>
      <details><summary>First recorded action difference</summary><pre>{JSON.stringify(comparison.first_action_difference, null, 2)}</pre><p>Later extra actions are visible in the turn counts.</p></details><p>{comparison.note}</p>
    </section>}
    <h2>Repeated experiments</h2><p>Every saved pair is included. Success rates use completed pairs; interrupted reports are labeled.</p>
    {reports.length === 0 && <p>No evaluation report recorded yet.</p>}
    {reports.map(report => <section key={report.evaluation_id} className="workflow-intro" aria-label="Evaluation report"><h3>{report.mode} · {report.status} · {report.pairs.length}/{report.repetitions} pairs</h3><p>{report.scope}</p>
      <p>Baseline completed {report.pairs.filter(pair => pair.left.completed).length}/{report.pairs.length}; candidate completed {report.pairs.filter(pair => pair.right.completed).length}/{report.pairs.length}.</p>
      <table className="comparison-table"><thead><tr><th>Pair</th><th>Baseline turns / rejects</th><th>Candidate turns / rejects</th><th>Inspect</th></tr></thead><tbody>{report.pairs.map((pair, index) => <tr key={index}><td>{index + 1}</td><td>{pair.left.turns} / {pair.left.rejected_actions}</td><td>{pair.right.turns} / {pair.right.rejected_actions}</td><td><button className="secondary" onClick={() => { setLeft(pair.left.run_id); setRight(pair.right.run_id); }}>Compare pair {index + 1}</button></td></tr>)}</tbody></table>
    </section>)}
  </main>;
}
