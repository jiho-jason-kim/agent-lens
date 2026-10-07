import { useCallback, useEffect, useRef, useState } from 'react';
import { createRun, listRuns, listScenarios, loadEvents, loadStates } from './api/client';
import { ModelCallInspector } from './components/ModelCallInspector';
import { ComparisonExplorer } from './components/ComparisonExplorer';
import { WorkflowExplorer } from './components/WorkflowExplorer';
import { AgentInspector } from './components/AgentInspector';
import { GridWorld } from './components/GridWorld';
import { Timeline } from './components/Timeline';
import { actionDependencies, ProvenanceView } from './components/ProvenanceView';
import { ReplayControls } from './components/ReplayControls';
import { EnvironmentChanges } from './components/EnvironmentChanges';
import { MemoryInspector } from './components/MemoryInspector';
import { MessageInspector } from './components/MessageInspector';
import { InvestigationGuide } from './components/InvestigationGuide';
import { RunSummary } from './components/RunSummary';
import { RunErrors } from './components/RunErrors';
import type { RecordedEvent, RunMetadata, Snapshot, Scenario } from './types';

const statusLabels = { goal_complete: 'Goal complete', turn_limit: 'Turn limit reached', error: 'Agent error', resources_exhausted: 'Resources exhausted' };

export default function App() {
  const [view, setView] = useState<'grid' | 'workflow' | 'comparison'>('grid');
  const [inspectorTab, setInspectorTab] = useState<'decision' | 'memory' | 'messages'>('decision');
  const [runs, setRuns] = useState<RunMetadata[]>([]);
  const [selected, setSelected] = useState('');
  const [states, setStates] = useState<Snapshot[]>([]);
  const [events, setEvents] = useState<RecordedEvent[]>([]);
  const [scenarioError, setScenarioError] = useState('');
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [agentMode, setAgentMode] = useState<'mock' | 'langchain'>('mock');
  const [showScenarios, setShowScenarios] = useState(false);
  const [agentId, setAgentId] = useState('agent-1');
  const [selectedEvent, setSelectedEvent] = useState('');
  const [perspective, setPerspective] = useState<'global' | 'agent'>('global');
  const [turn, setTurn] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError('');
    setScenarioError('');
    try {
      // Saved replay remains available when the optional scenario catalog fails.
      const [data, catalog] = await Promise.all([listRuns(), listScenarios().catch(() => {
        setScenarioError('Scenario descriptions could not be loaded. Refresh to retry.');
        return [];
      })]);
      setScenarios(catalog);
      setRuns(data);
      setSelected(current => data.some(run => run.run_id === current) ? current : data[0]?.run_id ?? '');
    } catch (cause) {
      setError((cause as Error).message);
    } finally { setBusy(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    // Discard stale responses when the selected run changes during a request.
    const current = ++generation.current;
    setInspectorTab('decision');
    setStates([]);
    setEvents([]);
    setTurn(0);
    setPerspective('global');
    setSelectedEvent('');
    setPlaying(false);
    if (!selected) { setLoading(false); return; }
    setLoading(true);
    setError('');
    Promise.all([loadStates(selected), loadEvents(selected)]).then(([data, recordedEvents]) => {
      if (current !== generation.current) return;
      if (!Array.isArray(data) || !data.length || data.some((state, index) => state.turn !== index)) {
        throw new Error('This recording has an invalid snapshot sequence.');
      }
      if (!Array.isArray(recordedEvents) || recordedEvents.some(event => !event || typeof event.event_id !== 'string'
        || !event.payload || !Array.isArray(event.input_refs) || !Array.isArray(event.effect_refs))) {
        throw new Error('This recording has invalid event data. Refresh or select another recording.');
      }
      setAgentId('agents' in data[0] ? data[0].agents[0].agent_id : 'agent-1');
      setStates(data);
      setEvents(recordedEvents);
    }).catch(cause => {
      if (current === generation.current) setError((cause as Error).message);
    }).finally(() => {
      if (current === generation.current) setLoading(false);
    });
    return () => { generation.current += 1; };
  }, [selected, retry]);

  useEffect(() => {
    if (!playing) return;
    if (turn >= states.length - 1) { setPlaying(false); return; }
    // Playback advances loaded snapshots only. Clean the timer after every transition.
    const timer = window.setTimeout(() => setTurn(current => current + 1), 1000);
    return () => window.clearTimeout(timer);
  }, [playing, turn, states.length]);

  function selectTurn(value: number) {
    setPlaying(false);
    setTurn(value);
    setSelectedEvent('');
  }

  function selectEvent(event: RecordedEvent) {
    // A failed decision may follow the final snapshot. Keep that snapshot and inspect the event.
    selectTurn(Math.min(event.turn, states.length - 1));
    setInspectorTab('decision');
    setAgentId(event.agent_id);
    setPerspective('agent');
    setSelectedEvent(event.event_id);
  }

  async function startRun(scenarioId = 'tutorial') {
    setBusy(true);
    setError('');
    try {
      const metadata = await createRun(scenarioId, agentMode);
      setRuns(current => [metadata, ...current]);
      setSelected(metadata.run_id);
      setShowScenarios(false);
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  if (view === 'comparison') return <ComparisonExplorer runs={runs} onBack={() => setView('grid')} onInspect={id => { void listRuns().then(data => { setRuns(data); setSelected(id); setView('grid'); }).catch(cause => setError(String(cause.message))); }} />;
  if (view === 'workflow') return <WorkflowExplorer onBack={() => setView('grid')} />;

  const run = runs.find(item => item.run_id === selected);
  const state = states[turn];
  const multi = state && 'agents' in state;
  const actor = events.find(event => event.turn === turn)?.agent_id ?? agentId;
  const inspectedAgent = perspective === 'global' ? actor : agentId;
  // Other agents retain their latest recorded decision. Never reconstruct it from global state.
  const inspectionTurn = events.find(event => event.event_id === selectedEvent)?.turn ?? turn;
  const observation = events.filter(event => event.turn <= inspectionTurn && event.agent_id === inspectedAgent && event.type === 'observation').at(-1);
  const decisionTurn = multi ? observation?.turn ?? 0 : turn;
  const local = observation?.type === 'observation' && (multi || observation.turn === turn) ? observation.payload.context.observation : undefined;
  const globalAgent = state && ('agents' in state ? state.agents.find(item => item.agent_id === inspectedAgent) : state);
  const displayed = perspective === 'agent' ? local : globalAgent;
  const action = events.find(event => event.turn === decisionTurn && event.agent_id === inspectedAgent && event.type === 'action');
  const linkedDelta = actionDependencies(events, action?.event_id)?.delta;
  const currentAction = events.find(event => event.turn === turn && event.type === 'action');
  const currentDelta = actionDependencies(events, currentAction?.event_id)?.delta;
  const delta = linkedDelta?.type === 'environment_delta' ? linkedDelta.payload : undefined;
  const changedCells = currentDelta?.type === 'environment_delta' ? currentDelta.payload.changed_cells : undefined;
  const config = run?.agents?.find(item => item.agent_id === inspectedAgent);
  const selectedArtifact = events.find(item => item.event_id === selectedEvent);

  return (
    <main className="app-shell">
      <header className="header">
        <div className="brand"><div className="brand-icon" aria-hidden="true">⌘</div><div>
          <p className="eyebrow">AGENT LENS / REPLAY LAB</p><h1>AI Agent Replay Debugger</h1>
        </div></div>
        <span className="local-badge"><i /> LOCAL · RECORDED REPLAY</span>
      </header>

      <section className="toolbar" aria-label="Run selection">
        <div className="run-picker"><label htmlFor="run-select">RECORDED RUN</label>
          <select id="run-select" value={selected} disabled={busy || !runs.length} onChange={event => setSelected(event.target.value)}>
            {!runs.length && <option value="">No recordings yet</option>}
            {runs.map(item => <option key={item.run_id} value={item.run_id}>{item.scenario_name ?? 'Tutorial'}{item.agent_mode ? ` · ${item.agent_mode}` : ''} · {item.run_id} · {statusLabels[item.status]}</option>)}
          </select>
        </div>
        <button className="secondary" disabled={busy} onClick={() => { void refresh(); setRetry(value => value + 1); }}>Refresh</button>
        <button className="secondary" disabled={busy} onClick={() => { setPlaying(false); setShowScenarios(value => !value); }}>{showScenarios ? 'Close scenarios' : 'Scenarios'}</button>
        <button className="secondary" onClick={() => { setPlaying(false); setView('workflow'); }}>Workflows</button>
        <button className="secondary" onClick={() => { setPlaying(false); setView('comparison'); }}>Compare</button>
        <button className="primary" disabled={busy} onClick={() => void startRun()}>{busy ? 'Working…' : `+ New ${agentMode} run`}</button>
      </section>

      {showScenarios && <section className="scenario-selection" aria-label="Scenario selection">
        <p className="eyebrow">NEW SIMULATION</p><h2>Choose a scenario</h2>
        <label htmlFor="agent-mode">Agent control </label>
        <select id="agent-mode" value={agentMode} disabled={busy} onChange={event => setAgentMode(event.target.value as 'mock' | 'langchain')}>
          <option value="mock">Mock · repeatable demonstration</option>
          <option value="langchain">LangChain · live model decisions</option>
        </select>
        {agentMode === 'langchain' && <p>Uses the backend OPENAI_MODEL and API key. Runs can make up to 50 model calls and take several minutes. API charges apply. Mock outcomes are not guaranteed.</p>}
        {scenarioError && <p role="alert">{scenarioError}</p>}
        {!scenarios.length && !scenarioError && <p>No scenarios available. Refresh to retry.</p>}
        <div className="scenario-cards">{scenarios.map(scenario => <article key={scenario.id}>
          <h3>{scenario.name}</h3><p>{scenario.description}</p>
          <small>{scenario.agent_count} {scenario.agent_count === 1 ? 'agent' : 'agents'} · {scenario.concepts.join(' · ')}</small>
          <button className="primary" disabled={busy} onClick={() => void startRun(scenario.id)}>Start {scenario.name}</button>
        </article>)}</div>
      </section>}

      {error && <div className="error" role="alert">{error} <button onClick={() => { void refresh(); setRetry(value => value + 1); }}>Retry</button></div>}

      {state && run ? <>
        <RunErrors events={events} goal={run.goal} />
        <div className="workspace">
          <aside className="history-panel">
            <ReplayControls turn={turn} maxTurn={states.length - 1} playing={playing} onChange={selectTurn}
              onPause={() => setPlaying(false)} onPlay={() => { setSelectedEvent(''); if (turn === states.length - 1) setTurn(0); setPlaying(true); }} />
            <Timeline turn={turn} maxTurn={states.length - 1} onChange={selectTurn} perspective={perspective} events={events}
              agents={run.agents?.map(item => item.agent_id)} selectedEvent={selectedEvent}
              onEvent={selectEvent} />
          </aside>
          <section className="world-panel" aria-label="Grid world">
            <div className="section-heading"><div><p className="eyebrow">ENVIRONMENT / 8 × 8</p><h2>{run.scenario_name ?? 'Grid world'}</h2></div>
              <div className="perspective" role="group" aria-label="Grid perspective">
                <button aria-pressed={perspective === 'global'} onClick={() => { setPerspective('global'); setSelectedEvent(''); }}>Global View</button>
                {multi ? state.agents.map(item => <button key={item.agent_id} aria-pressed={perspective === 'agent' && agentId === item.agent_id}
                  onClick={() => { setAgentId(item.agent_id); setPerspective('agent'); setSelectedEvent(''); }}>{item.agent_id[0].toUpperCase() + item.agent_id.slice(1)}</button>)
                  : <button aria-pressed={perspective === 'agent'} onClick={() => setPerspective('agent')}>Agent View</button>}
              </div></div>
            <details className="scenario-description"><summary>About this scenario</summary><p>{scenarios.find(item => item.id === run.scenario_id)?.description ?? run.goal}</p></details>
            <p className="view-timing">{perspective === 'global'
              ? turn === 0 ? 'Initial global state.' : `Global state after action ${turn}.`
              : local ? `Recorded observation before action ${decisionTurn}${multi ? ` · ${inspectedAgent}` : ''}.` : 'No observation recorded. All cells are unknown.'}</p>
            <GridWorld state={state} perspective={perspective} observation={local} changedCells={changedCells} agentId={inspectedAgent} />
            {delta && <p className="view-timing">{perspective === 'global' ? 'Amber corners mark cells changed by this action.' : 'Change markers appear in Global View after the action.'}</p>}
            <div className="legend"><span><b className="legend-agent">{multi ? 'B / R / G' : 'A'}</b> {multi ? 'Agents' : 'Agent'}</span><span><b className="legend-home">H</b> Home</span><span><b className="legend-resource">◆</b> Resource</span>{perspective === 'agent' && <span>· Unknown</span>}</div>
            <div className="snapshot-tag">{perspective === 'agent' ? local ? `BEFORE ACTION ${decisionTurn} · OBSERVATION` : 'NO RECORDED OBSERVATION' : turn === 0 ? 'INITIAL STATE' : `AFTER TURN ${turn}`}</div>
            <dl className="metrics">
              <div><dt>Agent position</dt><dd data-testid="position">{displayed ? `(${displayed.position.join(', ')})` : 'Unknown'}</dd></div>
              <div><dt>Collected resources</dt><dd data-testid="inventory">{displayed?.inventory ?? 'Unknown'}{!multi && <span> / 3</span>}</dd></div>
              <div><dt>{perspective === 'agent' ? 'Visible resources' : 'Resources on grid'}</dt><dd>{perspective === 'agent' ? local?.cells.filter(cell => cell.resource).length ?? 'Unknown' : state.resources.length}</dd></div>
              <div><dt>Goal at this state</dt><dd className={displayed?.goal_complete ? 'complete' : ''}>{displayed ? displayed.goal_complete === undefined ? 'Not in observation' : displayed.goal_complete ? 'Complete' : 'In progress' : 'Unknown'}</dd></div>
            </dl>
            <section className="changes" aria-label="Environment changes"><h3>After-action changes{multi && ` · ${inspectedAgent} · Turn ${decisionTurn}`}</h3><EnvironmentChanges delta={delta} /></section>
          </section>
          <aside className="summary" aria-label="Decision and recording">
            {multi && <div className="inspector-tabs" role="group" aria-label="Inspector views">
              {(['decision', 'memory', 'messages'] as const).map(tab => <button key={tab} aria-pressed={inspectorTab === tab} onClick={() => setInspectorTab(tab)}>{tab[0].toUpperCase() + tab.slice(1)}</button>)}
            </div>}
            {(!multi || inspectorTab === 'decision') && <AgentInspector turn={decisionTurn} events={events} goal={config?.goal ?? run.goal} agentId={inspectedAgent} multi={multi} />}
            {multi && inspectorTab === 'memory' && <MemoryInspector events={events} agentId={inspectedAgent} turn={turn} state={state} onSelect={selectEvent} />}
            {multi && inspectorTab === 'messages' && <MessageInspector events={events} agentId={perspective === 'global' ? undefined : inspectedAgent} turn={turn} onSelect={selectEvent} />}
            {selectedArtifact && <details className="selected-artifact" open><summary>{selectedArtifact.event_id} · {selectedArtifact.type}</summary>
              <pre>{JSON.stringify(selectedArtifact.payload, null, 2)}</pre>
            </details>}
            <ModelCallInspector event={events.find(event => event.type === 'model_call' && event.agent_id === inspectedAgent && event.turn === decisionTurn)} />
            <div className="recording-details"><p className="eyebrow">RUN RESULT</p><p>{statusLabels[run.status]} · {run.turns} turns</p><p className="muted">{new Date(run.created_at).toLocaleString()}</p></div>
          </aside>
        </div>
        <InvestigationGuide events={events} scenarioId={run.scenario_id} agentMode={run.agent_mode} onSelect={event => {
          selectEvent(event);
          document.querySelector('.workspace')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
        }} />
        <RunSummary events={events} finalState={states[states.length - 1]} run={run} />
        <ProvenanceView events={events} actionId={action?.event_id} selectedId={selectedEvent || undefined} onSelect={selectEvent} />
      </> : <section className="empty" role="status">
        <p className="eyebrow">REPLAY WORKSPACE</p>
        <h2>{loading || busy ? 'Loading recording…' : error ? 'Recording unavailable' : 'Start with one run.'}</h2>
        <p>{error ? 'Check the backend, then retry.' : 'Create a mock run to explore the agent’s recorded path through the grid.'}</p>
      </section>}
      <footer><span>Observable artifacts. Recorded history.</span><span>GRID REPLAY</span></footer>
    </main>
  );
}
