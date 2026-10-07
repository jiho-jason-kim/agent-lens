import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { archiveEvents, finalState } from '../replay/archive.fixture';
import { MemoryInspector } from './MemoryInspector';
import { MessageInspector } from './MessageInspector';

it('shows stale memory evidence and selects its recorded source', () => {
  const select = vi.fn();
  render(<MemoryInspector events={archiveEvents} agentId="blue" turn={3} state={finalState} onSelect={select} />);
  expect(screen.getByText('Possibly stale')).toBeVisible();
  expect(screen.queryByText('M-red')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Retrieved at turn 4' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Source obs' }));
  expect(select).toHaveBeenCalledWith(archiveEvents[0]);
});
it('shows pending and delivered message states at their actual turns', () => {
  const select = vi.fn();
  const { rerender } = render(<MessageInspector events={archiveEvents} agentId="blue" turn={1} onSelect={select} />);
  expect(screen.getByText('Pending')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Receipt receipt' })).not.toBeInTheDocument();
  rerender(<MessageInspector events={archiveEvents} agentId="red" turn={2} onSelect={select} />);
  expect(screen.getByText('M-red')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Receipt receipt' }));
  expect(select).toHaveBeenCalledWith(archiveEvents[3]);
});
