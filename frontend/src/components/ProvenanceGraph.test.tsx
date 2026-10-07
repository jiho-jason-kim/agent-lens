import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ProvenanceGraph } from './ProvenanceGraph';
import { lineage } from '../replay/lineage.fixture';

it('selects nodes, highlights the focus, and filters direction', () => {
  const select = vi.fn();
  render(<ProvenanceGraph events={lineage} selectedId="receive" onSelect={select} />);
  const graph = screen.getByLabelText('Provenance graph canvas');
  const focus = within(graph).getByRole('button', { name: 'Trace receive, blue, turn 2, message_receive' });
  expect(focus).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(within(graph).getByRole('button', { name: 'Trace send, green, turn 1, message_send' }));
  expect(select).toHaveBeenCalledWith(lineage.find(event => event.event_id === 'send'));
  fireEvent.change(screen.getByLabelText('Direction'), { target: { value: 'downstream' } });
  expect(within(graph).queryByRole('button', { name: /Trace send,/ })).not.toBeInTheDocument();
  expect(within(graph).getByRole('button', { name: /Trace write-blue,/ })).toBeInTheDocument();
});
