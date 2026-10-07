import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { WorkflowExplorer } from './WorkflowExplorer';
import { createWorkflowDemo, listWorkflows, loadWorkflow } from '../api/workflows';
import type { WorkflowRecording, WorkflowEvent } from '../api/workflows';

vi.mock('../api/workflows', () => ({ createWorkflowDemo: vi.fn(), listWorkflows: vi.fn(), loadWorkflow: vi.fn() }));
const event = (sequence: number, span: string, phase: WorkflowEvent['phase'], payload: unknown): WorkflowEvent => ({
  event_id: `w-${sequence}`, sequence, timestamp: '2026-10-03T12:00:00Z', span_id: span,
  parent_span_id: span === 'root' ? null : 'root', category: span === 'root' ? 'chain' : 'tool',
  phase, name: span === 'root' ? 'workflow' : 'reserve', payload,
});
const recording: WorkflowRecording = {
  metadata: { run_id: 'workflow-test', name: 'Reservation', created_at: '2026-10-03T12:00:00Z',
    status: 'recovered', mode: 'demo', event_count: 4, span_count: 2 },
  events: [event(1, 'root', 'start', { input: 'request' }), event(2, 'tool', 'start', { input: { sku: 'camera' } }),
    event(3, 'tool', 'error', { error_type: 'StockUnavailable' }), event(4, 'root', 'end', { output: 'Recovered result' })],
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listWorkflows).mockResolvedValue([recording.metadata]);
  vi.mocked(loadWorkflow).mockResolvedValue(recording);
});

it('replays failures and parent calls without executing the workflow or revealing future output', async () => {
  render(<WorkflowExplorer onBack={() => {}} />);
  await screen.findByRole('region', { name: 'Workflow inspector' });
  expect(screen.getByText('RECOVERED')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Next failure' }));
  const inspector = screen.getByRole('region', { name: 'Workflow inspector' });
  expect(within(inspector).getByText(/StockUnavailable/)).toBeVisible();
  expect(within(inspector).getByText(/camera/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Previous event' }));
  expect(within(inspector).getByText('No result had been recorded at this event.')).toBeVisible();
  expect(within(inspector).queryByText(/StockUnavailable/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Go to recorded result' }));
  fireEvent.click(screen.getByRole('button', { name: 'Inspect parent' }));
  expect(within(inspector).getByRole('heading', { name: 'workflow' })).toBeVisible();
  expect(createWorkflowDemo).not.toHaveBeenCalled();
  expect(loadWorkflow).toHaveBeenCalledTimes(1);
});

it('starts a live example only on an explicit create action', async () => {
  vi.mocked(createWorkflowDemo).mockResolvedValue({ ...recording, metadata: { ...recording.metadata, run_id: 'workflow-live', mode: 'live' } });
  render(<WorkflowExplorer onBack={() => {}} />);
  await screen.findByText('RECOVERED');
  fireEvent.change(screen.getByLabelText('Example mode'), { target: { value: 'live' } });
  expect(createWorkflowDemo).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Record workflow example' }));
  await waitFor(() => expect(createWorkflowDemo).toHaveBeenCalledWith('live'));
  expect(await screen.findByText('Live model output')).toBeVisible();
});

it('shows load errors and allows a retry', async () => {
  vi.mocked(listWorkflows).mockRejectedValueOnce(new Error('Backend unavailable'));
  render(<WorkflowExplorer onBack={() => {}} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh workflows' }));
  expect(await screen.findByText('RECOVERED')).toBeVisible();
});
