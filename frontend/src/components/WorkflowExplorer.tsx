import { useCallback, useEffect, useRef, useState } from 'react';
import { createWorkflowDemo, listWorkflows, loadWorkflow } from '../api/workflows';
import type { WorkflowEvent, WorkflowMetadata, WorkflowRecording } from '../api/workflows';

const phaseLabel = { start: 'Started', end: 'Returned', error: 'Failed', custom: 'Recorded' };

export function WorkflowExplorer({ onBack }: { onBack: () => void }) {
  const [runs, setRuns] = useState<WorkflowMetadata[]>([]);
  const [run, setRun] = useState<WorkflowRecording>();
  const [cursor, setCursor] = useState(0);
  const [mode, setMode] = useState<'demo' | 'live'>('demo');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);

  const accept = useCallback((recording: WorkflowRecording) => {
    setRun(recording);
    setCursor(Math.max(0, recording.events.length - 1));
  }, []);

  const refresh = useCallback(async () => {
    const current = ++generation.current;
    setBusy(true); setError('');
    try {
      const records = await listWorkflows();
      const latest = records.length ? await loadWorkflow(records[0].run_id) : undefined;
      if (current !== generation.current) return;
      setRuns(records);
      if (latest) accept(latest); else setRun(undefined);
    } catch (cause) { if (current === generation.current) setError((cause as Error).message); }
    finally { if (current === generation.current) setBusy(false); }
  }, [accept]);

  useEffect(() => { void refresh(); return () => { generation.current += 1; }; }, [refresh]);

  async function selectRun(id: string) {
    const current = ++generation.current;
    setBusy(true); setError(''); setRun(undefined);
    try {
      const data = await loadWorkflow(id);
      if (current === generation.current) accept(data);
    } catch (cause) { if (current === generation.current) setError((cause as Error).message); }
    finally { if (current === generation.current) setBusy(false); }
  }

  async function create() {
    const current = ++generation.current;
    setBusy(true); setError('');
    try {
      const data = await createWorkflowDemo(mode);
      if (current !== generation.current) return;
      setRuns(records => [data.metadata, ...records]); accept(data);
    } catch (cause) { if (current === generation.current) setError((cause as Error).message); }
    finally { if (current === generation.current) setBusy(false); }
  }

  const events = run?.events ?? [];
  const selected = events[cursor];
  // Replay derives state only from recorded events at or before the selected position.
  const visible = events.slice(0, cursor + 1);
  const starts = visible.filter(event => event.phase === 'start');
  const start = selected && events.find(event => event.span_id === selected.span_id && event.phase === 'start');
  const result = selected && visible.find(event => event.span_id === selected.span_id && ['end', 'error'].includes(event.phase));
  const parent = start && events.find(event => event.span_id === start.parent_span_id && event.phase === 'start');
  const recordedResult = selected && events.find(event => event.span_id === selected.span_id && ['end', 'error'].includes(event.phase));
  const failures = events.filter(event => event.phase === 'error');
  const jump = (event: WorkflowEvent) => setCursor(event.sequence - 1);
  function depth(event: WorkflowEvent) {
    let level = 0, ancestor = event.parent_span_id;
    const seen = new Set<string>();
    while (ancestor && !seen.has(ancestor)) {
      seen.add(ancestor); level += 1;
      ancestor = starts.find(item => item.span_id === ancestor)?.parent_span_id ?? null;
    }
    return Math.min(level, 6);
  }

  return <main className="app-shell workflow-shell">
    <header className="header"><div><p className="eyebrow">AGENT LENS / LANGCHAIN</p><h1>Workflow replay</h1></div>
      <button className="secondary" onClick={onBack}>Back to grid simulations</button></header>
    <section className="workflow-intro" aria-label="Workflow example">
      <h2>When cached inventory is wrong</h2>
      <p>A workflow reads stale stock, attempts a reservation, then checks current stock and reserves an alternative after the tool fails.</p>
      <p>The tools change a local fixture. The workflow controls recovery; the model summarizes the result.</p>
      <div className="workflow-create"><label htmlFor="workflow-mode">Example mode</label>
        <select id="workflow-mode" value={mode} disabled={busy} onChange={event => setMode(event.target.value as 'demo' | 'live')}>
          <option value="demo">Deterministic · no API calls</option><option value="live">Live model summary · one API call</option>
        </select><button className="primary" disabled={busy} onClick={() => void create()}>{busy ? 'Working…' : 'Record workflow example'}</button></div>
      {mode === 'live' && <p>Uses backend/.env. One model call can take up to 60 seconds. API charges apply.</p>}
    </section>
    <section className="toolbar" aria-label="Workflow recordings"><div className="run-picker">
      <label htmlFor="workflow-run">RECORDED WORKFLOW</label><select id="workflow-run" value={run?.metadata.run_id ?? ''} disabled={busy || !runs.length} onChange={event => void selectRun(event.target.value)}>
        {!run && <option value="">{busy ? 'Loading…' : 'No recording selected'}</option>}
        {runs.map(item => <option key={item.run_id} value={item.run_id}>{item.name} · {item.mode} · {item.status} · {item.run_id.slice(-8)}</option>)}
      </select></div><button className="secondary" disabled={busy} onClick={() => void refresh()}>Refresh workflows</button></section>
    {error && <p className="error" role="alert">{error}</p>}
    {run && <>
      <section className="workflow-summary" aria-label="Workflow summary">
        <strong>{run.metadata.status.toUpperCase()}</strong><span>{run.metadata.span_count} calls · {events.length} events · {failures.length} recorded failures</span>
        <span>{run.metadata.mode === 'demo' ? 'Deterministic model fixture' : run.metadata.mode === 'live' ? 'Live model output' : 'External LangChain workflow'}</span>
        <p>Call nesting shows execution relationships. It does not prove which input caused a decision.</p>
      </section>
      {selected ? <div className="workflow-workspace">
        <aside className="workflow-history" aria-label="Workflow history"><p className="eyebrow">RECORDED HISTORY</p>
          <div className="workflow-navigation"><button className="secondary" disabled={cursor === 0} onClick={() => setCursor(value => value - 1)}>Previous event</button>
            <button className="secondary" disabled={cursor === events.length - 1} onClick={() => setCursor(value => value + 1)}>Next event</button></div>
          <label htmlFor="workflow-event">Event {selected.sequence} of {events.length}</label>
          <input id="workflow-event" type="range" min={0} max={events.length - 1} value={cursor} onChange={event => setCursor(Number(event.target.value))} />
          <button className="secondary" disabled={!failures.length} onClick={() => jump(failures.find(event => event.sequence > selected.sequence) ?? failures[0])}>Next failure</button>
          <ol>{events.map(event => <li key={event.event_id}><button aria-pressed={event.event_id === selected.event_id} className={`workflow-event ${event.phase}`} onClick={() => jump(event)}>
            <small>{event.sequence} · {event.category} · {phaseLabel[event.phase]}</small><span>{event.name}</span>
          </button></li>)}</ol>
        </aside>
        <section className="workflow-calls" aria-label="Workflow call tree"><p className="eyebrow">CALLS AT EVENT {selected.sequence}</p><h2>Execution trace</h2>
          <p>Each row is one invocation. Nested rows use recorded parent IDs.</p>
          {starts.map(event => {
            const end = visible.find(item => item.span_id === event.span_id && ['end', 'error'].includes(item.phase));
            return <button key={event.event_id} className={`workflow-call ${end?.phase ?? 'start'}`} style={{ marginLeft: `${depth(event) * 12}px` }} aria-pressed={event.span_id === selected.span_id} onClick={() => jump(event)}>
              <small>{event.category} · {end ? end.phase === 'error' ? 'Failed' : 'Returned' : 'In progress'}</small><strong>{event.name}</strong>
            </button>;
          })}
        </section>
        <section className="workflow-inspector" aria-label="Workflow inspector"><p className="eyebrow">{selected.event_id} · {phaseLabel[selected.phase]}</p><h2>{selected.name}</h2>
          <p>{new Date(selected.timestamp).toLocaleString()}</p>
          <div className="workflow-navigation">{parent && <button className="secondary" onClick={() => jump(parent)}>Inspect parent</button>}
            {recordedResult && recordedResult.sequence !== selected.sequence && <button className="secondary" onClick={() => jump(recordedResult)}>Go to recorded result</button>}</div>
          {selected.phase === 'custom' ? <><h3>Explicit application event</h3><pre>{JSON.stringify(selected.payload, null, 2)}</pre></> : <>
            <h3>Recorded input</h3><pre>{JSON.stringify(start?.payload, null, 2)}</pre>
            <h3>{result?.phase === 'error' ? 'Recorded error' : 'Recorded output'}</h3>
            {result ? <pre className={result.phase === 'error' ? 'workflow-failure' : ''}>{JSON.stringify(result.payload, null, 2)}</pre>
              : <p>No result had been recorded at this event.</p>}
          </>}
          <details><summary>Invocation identifiers</summary><p>Span: {selected.span_id}</p><p>Parent: {selected.parent_span_id ?? 'Root call'}</p></details>
        </section>
      </div> : <p>This recording contains no events.</p>}
    </>}
    <details className="workflow-integration"><summary>Record your own LangChain workflow</summary>
      <p>Run from the backend environment, with the optional LangChain dependencies installed.</p>
      <pre>{`from app.integrations.langchain_recorder import AgentLensRecorder\n\nrecorder = AgentLensRecorder("My workflow")\ntry:\n    result = chain.invoke(inputs, config={"callbacks": [recorder]})\nfinally:\n    recorder.save()`}</pre>
      <p>Pass the callback configuration to nested calls. Then refresh this list. Each execution needs a new recorder.</p>
      <p>The adapter records completed model output, tool calls, retrievals, and explicit custom events. It excludes model reasoning blocks and SDK metadata.</p>
      <p>Inputs and outputs are saved locally. Known credentials are redacted; arbitrary private content is not automatically removed. Large values have explicit truncation markers.</p>
    </details>
    <footer><span>Saved evidence. Replay makes no model calls.</span><span>WORKFLOW REPLAY</span></footer>
  </main>;
}
