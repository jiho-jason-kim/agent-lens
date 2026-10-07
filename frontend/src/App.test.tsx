import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { createRun, listRuns, listScenarios, loadEvents, loadStates } from './api/client';
import type { RecordedEvent, RunMetadata, WorldState } from './types';

vi.mock('./api/client', () => ({ listRuns: vi.fn(), listScenarios: vi.fn(), loadEvents: vi.fn(), loadStates: vi.fn(), createRun: vi.fn() }));
const metadata: RunMetadata = {
  schema_version: 1, run_id: 'run-first', created_at: '2026-09-29T10:00:00Z',
  agent: 'MockAgent', goal: 'Collect 3 resources and return home.', status: 'goal_complete', turns: 2, max_turns: 50,
};
const states: WorldState[] = [
  { turn: 0, position: [0, 0], inventory: 0, resources: [[1, 0]], home: [0, 0], goal_complete: false },
  { turn: 1, position: [1, 0], inventory: 0, resources: [[1, 0]], home: [0, 0], goal_complete: false },
  { turn: 2, position: [1, 0], inventory: 1, resources: [], home: [0, 0], goal_complete: false },
];

const events: RecordedEvent[] = [1, 2].flatMap(turn => {
  const base = { run_id: metadata.run_id, turn, agent_id: 'agent-1', timestamp: metadata.created_at, input_refs: [], effect_refs: [] };
  return [
    { ...base, event_id: `obs-${turn}`, type: 'observation' as const, payload: { context: {
      goal: metadata.goal, inventory: 0, previous_plan: turn === 1 ? null : 'Move east.', recent_history: [],
      observation: { position: states[turn - 1].position, inventory: 0, goal_complete: false,
        cells: [{ position: [0, 0] as [number, number], resource: false, home: true },
          { position: [1, 0] as [number, number], resource: true, home: false }] },
    } } },
    { ...base, event_id: `plan-${turn}`, type: 'plan' as const, payload: { plan: turn === 1 ? 'Move east.' : 'Collect here.' } },
    { ...base, event_id: `action-${turn}`, type: 'action' as const,
      payload: { action: turn === 1 ? { type: 'move' as const, direction: 'east' as const } : { type: 'collect' as const } } },
  ];
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listScenarios).mockResolvedValue([]);
  vi.mocked(listRuns).mockResolvedValue([metadata]);
  vi.mocked(loadStates).mockResolvedValue(states);
  vi.mocked(loadEvents).mockResolvedValue(events);
});

describe('recorded grid replay', () => {
  it('exposes a failed first decision without inventing an action or snapshot', async () => {
    vi.mocked(listRuns).mockResolvedValue([{ ...metadata, status: 'error', turns: 0 }]);
    vi.mocked(loadStates).mockResolvedValue([states[0]]);
    vi.mocked(loadEvents).mockResolvedValue([events[0], {
      run_id: metadata.run_id, turn: 1, agent_id: 'agent-1', timestamp: metadata.created_at,
      event_id: 'failure', input_refs: ['obs-1'], effect_refs: [], type: 'error',
      payload: { stage: 'decision', message: 'Agent decision failed. No action was executed.' },
    }]);
    render(<App />);
    await screen.findByRole('grid');
    const errors = screen.getByRole('region', { name: 'Recorded errors' });
    expect(errors).toHaveTextContent('Agent decision failed.');
    fireEvent.click(within(errors).getByText('Inspect failed decision at turn 1'));
    expect(within(errors).getByText('No action recorded.')).toBeVisible();
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Play' })).toBeDisabled();
  });
  it('plays, pauses, stops at the end, and restarts without making replay requests', async () => {
    render(<App />);
    await screen.findByRole('grid');
    vi.useFakeTimers();
    try {
      expect(screen.getByRole('button', { name: 'Previous turn' })).toBeDisabled();
      fireEvent.click(screen.getByRole('button', { name: 'Play' }));
      act(() => vi.advanceTimersByTime(1000));
      expect(screen.getByRole('slider')).toHaveValue('1');
      fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
      act(() => vi.advanceTimersByTime(3000));
      expect(screen.getByRole('slider')).toHaveValue('1');
      fireEvent.click(screen.getByRole('button', { name: 'Next turn' }));
      expect(screen.getByRole('button', { name: 'Next turn' })).toBeDisabled();
      fireEvent.click(screen.getByRole('button', { name: 'Play' }));
      expect(screen.getByRole('slider')).toHaveValue('0');
      act(() => vi.advanceTimersByTime(1000));
      act(() => vi.advanceTimersByTime(1000));
      expect(screen.getByRole('slider')).toHaveValue('2');
      expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Previous turn' }));
      expect(screen.getByRole('slider')).toHaveValue('1');
      expect(loadStates).toHaveBeenCalledTimes(1);
      expect(loadEvents).toHaveBeenCalledTimes(1);
      expect(createRun).not.toHaveBeenCalled();
    } finally { vi.useRealTimers(); }
  });

  it('selects an action from the timeline and pauses playback', async () => {
    render(<App />);
    await screen.findByRole('grid');
    fireEvent.click(screen.getByRole('button', { name: 'Play' }));
    fireEvent.click(screen.getByRole('button', { name: 'Inspect turn 2: collect()' }));
    expect(screen.getByRole('slider')).toHaveValue('2');
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Action dependencies' })).toHaveTextContent('action-2');
  });
  it('uses pre-action observations and updates the inspector with the selected turn', async () => {
    render(<App />);
    await screen.findByRole('grid');
    fireEvent.change(screen.getByRole('slider'), { target: { value: '1' } });
    expect(within(screen.getByRole('region', { name: 'Agent Inspector' })).getByText('move(east)')).toBeInTheDocument();
    expect(screen.getByTestId('explicit-plan')).toHaveTextContent('Move east.');
    expect(screen.getByTestId('position')).toHaveTextContent('(1, 0)');
    fireEvent.click(screen.getByRole('button', { name: 'Agent View' }));
    expect(screen.getByTestId('position')).toHaveTextContent('(0, 0)');
    expect(screen.getByRole('gridcell', { name: 'Cell (7, 7): unknown' })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('slider'), { target: { value: '2' } });
    expect(screen.getByTestId('explicit-plan')).toHaveTextContent('Collect here.');
    expect(within(screen.getByRole('region', { name: 'Agent Inspector' })).getByText('collect()')).toBeInTheDocument();
    // The resource still exists in the recorded observation before collection.
    expect(screen.getByRole('gridcell', { name: 'Cell (1, 0): agent, resource' })).toBeInTheDocument();
    expect(screen.getByTestId('inventory')).toHaveTextContent('0 / 3');
    fireEvent.click(screen.getByRole('button', { name: 'Global View' }));
    expect(screen.getByRole('gridcell', { name: 'Cell (1, 0): agent' })).toBeInTheDocument();
    expect(screen.getByTestId('inventory')).toHaveTextContent('1 / 3');
    expect(loadStates).toHaveBeenCalledTimes(1);
    expect(loadEvents).toHaveBeenCalledTimes(1);
    expect(createRun).not.toHaveBeenCalled();
  });

  it('does not infer visibility from global state when no observation is recorded', async () => {
    vi.mocked(loadEvents).mockResolvedValue([]);
    render(<App />);
    await screen.findByRole('grid');
    fireEvent.click(screen.getByRole('button', { name: 'Agent View' }));
    expect(screen.getAllByRole('gridcell', { name: /unknown/ })).toHaveLength(64);
    fireEvent.change(screen.getByRole('slider'), { target: { value: '1' } });
    expect(screen.getAllByRole('gridcell', { name: /unknown/ })).toHaveLength(64);
    expect(screen.getByText('No observation recorded for this turn.')).toBeInTheDocument();
    expect(screen.getByText('No plan recorded.')).toBeInTheDocument();
    expect(screen.getByText('No action recorded.')).toBeInTheDocument();
  });

  it('renders all cells and changes snapshots without any replay requests', async () => {
    render(<App />);
    await screen.findByRole('grid');
    expect(screen.getAllByRole('gridcell')).toHaveLength(64);
    expect(screen.getByRole('gridcell', { name: 'Cell (0, 0): agent, home' })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('slider'), { target: { value: '1' } });
    expect(screen.getByRole('gridcell', { name: 'Cell (1, 0): agent, resource' })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('slider'), { target: { value: '2' } });
    expect(screen.getByTestId('inventory')).toHaveTextContent('1 / 3');
    expect(screen.getByRole('gridcell', { name: 'Cell (1, 0): agent' })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('slider'), { target: { value: '0' } });
    expect(screen.getByTestId('inventory')).toHaveTextContent('0 / 3');
    expect(loadStates).toHaveBeenCalledTimes(1);
    expect(loadEvents).toHaveBeenCalledTimes(1);
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(createRun).not.toHaveBeenCalled();
  });

  it('shows an empty state and creates a run only after a button click', async () => {
    vi.mocked(listRuns).mockResolvedValue([]);
    vi.mocked(createRun).mockResolvedValue(metadata);
    render(<App />);
    await screen.findByText('Start with one run.');
    expect(createRun).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '+ New mock run' }));
    await screen.findByRole('grid');
    expect(createRun).toHaveBeenCalledTimes(1);
  });

  it('discards stale responses when the user selects another run', async () => {
    const second = { ...metadata, run_id: 'run-second' };
    vi.mocked(listRuns).mockResolvedValue([metadata, second]);
    let resolveFirst!: (value: WorldState[]) => void;
    vi.mocked(loadStates).mockImplementation(id => id === 'run-first'
      ? new Promise(resolve => { resolveFirst = resolve; })
      : Promise.resolve([{ ...states[0], position: [7, 7] }]));
    render(<App />);
    await waitFor(() => expect(loadStates).toHaveBeenCalledWith('run-first'));
    fireEvent.change(screen.getByLabelText('RECORDED RUN'), { target: { value: 'run-second' } });
    await screen.findByRole('grid');
    await act(async () => resolveFirst(states));
    expect(screen.getByTestId('position')).toHaveTextContent('(7, 7)');
    expect(screen.getByRole('slider')).toBeDisabled();
  });

  it('shows a failed request and retries it', async () => {
    vi.mocked(loadStates).mockRejectedValueOnce(new Error('Recording unavailable.')).mockResolvedValue(states);
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Recording unavailable.');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await screen.findByRole('grid');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('resets the selected turn when switching recordings', async () => {
    vi.mocked(listRuns).mockResolvedValue([metadata, { ...metadata, run_id: 'run-second' }]);
    render(<App />);
    await screen.findByRole('grid');
    fireEvent.change(screen.getByRole('slider'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('RECORDED RUN'), { target: { value: 'run-second' } });
    await screen.findByRole('grid');
    expect(screen.getByRole('slider')).toHaveValue('0');
  });

  it('rejects recordings with missing turns', async () => {
    vi.mocked(loadStates).mockResolvedValue([states[0], states[2]]);
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('invalid snapshot sequence');
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  });
});

const multiMetadata: RunMetadata = { ...metadata, schema_version: 2, scenario_id: 'hidden-information',
  scenario_name: 'Hidden Information', agents: [
    { agent_id: 'blue', goal: 'Blue private goal', target: 2 },
    { agent_id: 'red', goal: 'Red private goal', target: 2 },
    { agent_id: 'green', goal: 'Green private goal', target: 2 },
  ] };
const multiStates = [0, 1, 2].map(turn => ({ turn, resources: [[3, 2] as [number, number]], obstacles: [], targets: [], agents: [
  { agent_id: 'blue', position: [turn ? 2 : 1, 2] as [number, number], inventory: 0, home: [1, 2] as [number, number], goal_complete: false },
  { agent_id: 'red', position: [4, 2] as [number, number], inventory: 0, home: [4, 2] as [number, number], goal_complete: false },
  { agent_id: 'green', position: [7, 7] as [number, number], inventory: 0, home: [7, 7] as [number, number], goal_complete: false },
] }));
const multiEvents: RecordedEvent[] = events.map(event => {
  const id = event.turn === 1 ? 'blue' : 'red';
  if (event.type !== 'observation') return { ...event, agent_id: id };
  return { ...event, agent_id: id, payload: { context: { ...event.payload.context, agent_id: id,
    goal: `${id} recorded goal`, recent_messages: [], retrieved_memories: [],
    observation: { position: [id === 'blue' ? 1 : 4, 2], inventory: 0,
      cells: [{ position: [id === 'blue' ? 1 : 4, 2], resource: false, home: true },
        { position: [3, 2], resource: true, home: false }], visible_agents: [] },
  } } };
});

it('keeps each agent view on its own recorded context without exposing hidden agents', async () => {
  vi.mocked(listRuns).mockResolvedValue([multiMetadata]);
  vi.mocked(loadStates).mockResolvedValue(multiStates);
  vi.mocked(loadEvents).mockResolvedValue(multiEvents);
  render(<App />);
  await screen.findByRole('grid');
  expect(screen.getByRole('gridcell', { name: 'Cell (4, 2): red, home' })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('slider'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Blue' }));
  expect(screen.getByTestId('position')).toHaveTextContent('(1, 2)');
  expect(screen.getByRole('gridcell', { name: 'Cell (4, 2): unknown' })).toBeInTheDocument();
  expect(screen.getByText('Recorded observation before action 1 · blue.')).toBeVisible();
  const inspector = screen.getByRole('region', { name: 'Agent Inspector' });
  expect(inspector).toHaveTextContent('blue recorded goal');
  expect(inspector).not.toHaveTextContent('red recorded goal');
  fireEvent.click(screen.getByRole('button', { name: 'Green' }));
  expect(screen.getAllByRole('gridcell', { name: /unknown/ })).toHaveLength(64);
  expect(screen.getByTestId('position')).toHaveTextContent('Unknown');
  expect(loadEvents).toHaveBeenCalledTimes(1);
  expect(createRun).not.toHaveBeenCalled();
});

it('selects an agent event from its vertical lane and pauses replay', async () => {
  vi.mocked(listRuns).mockResolvedValue([multiMetadata]);
  vi.mocked(loadStates).mockResolvedValue(multiStates);
  vi.mocked(loadEvents).mockResolvedValue(multiEvents);
  render(<App />);
  await screen.findByRole('grid');
  fireEvent.click(screen.getByRole('button', { name: 'Play' }));
  fireEvent.click(screen.getByRole('button', { name: 'red, turn 2: ≡ Plan, plan-2' }));
  expect(screen.getByRole('button', { name: 'Red' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('slider')).toHaveValue('2');
  expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
  expect(screen.getByText('plan-2 · plan')).toBeVisible();
  expect(screen.getByTestId('explicit-plan')).toHaveTextContent('Collect here.');
});

it('creates only the selected scenario from its card', async () => {
  vi.mocked(listScenarios).mockResolvedValue([{ id: 'coordination', name: 'Coordination', description: 'Occupy targets together.', concepts: ['Communication'], agent_count: 3 }]);
  vi.mocked(createRun).mockResolvedValue({ ...multiMetadata, run_id: 'run-coordination', scenario_name: 'Coordination' });
  render(<App />);
  await screen.findByRole('grid');
  fireEvent.click(screen.getByRole('button', { name: 'Scenarios' }));
  expect(screen.getByText('3 agents · Communication')).toBeVisible();
  expect(createRun).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Start Coordination' }));
  await waitFor(() => expect(createRun).toHaveBeenCalledWith('coordination', 'mock'));
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Scenario selection' })).not.toBeInTheDocument());
});

it('shows only the selected agent messages and retrieved memories', async () => {
  vi.mocked(listRuns).mockResolvedValue([multiMetadata]);
  vi.mocked(loadStates).mockResolvedValue(multiStates);
  vi.mocked(loadEvents).mockResolvedValue(multiEvents.map(event => event.type === 'observation' ? {
    ...event, payload: { context: { ...event.payload.context,
      recent_messages: [{ message_id: `message-${event.agent_id}`, sender_id: 'green', recipient_id: event.agent_id,
        content: `${event.agent_id} private report`, sent_turn: 0, delivered_turn: event.turn }],
      retrieved_memories: [{ memory_id: `memory-${event.agent_id}`, content: `${event.agent_id} private memory`, source_event_id: 'source', created_turn: 1 }],
    } },
  } : event));
  render(<App />);
  await screen.findByRole('grid');
  fireEvent.change(screen.getByRole('slider'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Blue' }));
  const inspector = screen.getByRole('region', { name: 'Agent Inspector' });
  expect(inspector).toHaveTextContent('blue private report');
  expect(inspector).toHaveTextContent('blue private memory');
  expect(inspector).not.toHaveTextContent('red private');
  fireEvent.click(screen.getByRole('button', { name: 'Red' }));
  expect(inspector).toHaveTextContent('red private report');
  expect(inspector).not.toHaveTextContent('blue private');
});

it('jumps to the recorded agent and turn when a provenance node is selected', async () => {
  vi.mocked(listRuns).mockResolvedValue([multiMetadata]);
  vi.mocked(loadStates).mockResolvedValue(multiStates);
  vi.mocked(loadEvents).mockResolvedValue(multiEvents.map(event => event.event_id === 'plan-2'
    ? { ...event, input_refs: ['action-1'] } : event));
  render(<App />);
  await screen.findByRole('grid');
  fireEvent.click(screen.getByRole('button', { name: 'red, turn 2: ≡ Plan, plan-2' }));
  fireEvent.click(screen.getByRole('button', { name: 'Trace action-1, blue, turn 1, action' }));
  expect(screen.getByRole('slider')).toHaveValue('1');
  expect(screen.getByRole('button', { name: 'Blue' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'Trace action-1, blue, turn 1, action' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByTestId('explicit-plan')).toHaveTextContent('Move east.');
  expect(createRun).not.toHaveBeenCalled();
  expect(loadEvents).toHaveBeenCalledTimes(1);
});

it('keeps saved replay available when scenario descriptions fail', async () => {
  vi.mocked(listScenarios).mockRejectedValue(new Error('Unavailable'));
  render(<App />);
  await screen.findByRole('grid');
  fireEvent.click(screen.getByRole('button', { name: 'Scenarios' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Scenario descriptions could not be loaded');
  expect(screen.getByRole('grid')).toBeInTheDocument();
});

it('shows empty archives before events and keeps final statistics independent of the replay turn', async () => {
  vi.mocked(listRuns).mockResolvedValue([multiMetadata]);
  vi.mocked(loadStates).mockResolvedValue(multiStates);
  vi.mocked(loadEvents).mockResolvedValue(multiEvents);
  render(<App />);
  await screen.findByRole('grid');
  fireEvent.click(screen.getByRole('button', { name: 'Memory' }));
  expect(screen.getByRole('region', { name: 'Memory inspector' })).toHaveTextContent('No memories recorded');
  fireEvent.click(screen.getByRole('button', { name: 'Messages' }));
  expect(screen.getByRole('region', { name: 'Message inspector' })).toHaveTextContent('No messages available');
  const result = screen.getByRole('region', { name: 'Run statistics' }).textContent;
  fireEvent.click(screen.getByRole('button', { name: 'Next turn' }));
  expect(screen.getByRole('region', { name: 'Run statistics' }).textContent).toBe(result);
});

it('shows a recoverable error for malformed event data', async () => {
  vi.mocked(loadEvents).mockResolvedValue(null as unknown as RecordedEvent[]);
  render(<App />);
  expect(await screen.findByRole('alert')).toHaveTextContent('invalid event data');
  expect(screen.queryByRole('grid')).not.toBeInTheDocument();
});

it('creates a LangChain run only after the user starts a scenario', async () => {
  vi.mocked(listScenarios).mockResolvedValue([{ id: 'handoff-race', name: 'Handoff Failure', description: 'Report a resource.', concepts: ['Communication'], agent_count: 3 }]);
  vi.mocked(createRun).mockResolvedValue({ ...metadata, agent_mode: 'langchain' });
  render(<App />);
  await screen.findByRole('grid');
  fireEvent.click(screen.getByRole('button', { name: 'Scenarios' }));
  fireEvent.change(screen.getByLabelText('Agent control'), { target: { value: 'langchain' } });
  expect(createRun).not.toHaveBeenCalled();
  expect(screen.getByText(/API charges apply/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Start Handoff Failure' }));
  await waitFor(() => expect(createRun).toHaveBeenCalledWith('handoff-race', 'langchain'));
});
