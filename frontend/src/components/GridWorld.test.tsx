import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { GridWorld } from './GridWorld';
import type { Observation, WorldState } from '../types';

it('marks changed cells only in the post-action global view', () => {
  const state: WorldState = { turn: 1, position: [1, 0], home: [0, 0], resources: [], inventory: 0, goal_complete: false };
  const observation: Observation = { position: [0, 0], inventory: 0, goal_complete: false,
    cells: [{ position: [0, 0], resource: false, home: true }] };
  const { rerender } = render(<GridWorld state={state} changedCells={[[0, 0], [1, 0]]} />);
  expect(screen.getAllByRole('gridcell', { name: /changed/ })).toHaveLength(2);
  rerender(<GridWorld state={state} perspective="agent" observation={observation} changedCells={[[0, 0], [1, 0]]} />);
  expect(screen.queryAllByRole('gridcell', { name: /changed/ })).toHaveLength(0);
  expect(screen.getByRole('gridcell', { name: 'Cell (1, 0): unknown' })).toBeInTheDocument();
});

it('keeps hidden global resources, home, and position out of Agent View markup', () => {
  const state: WorldState = { turn: 1, position: [7, 7], home: [6, 6], resources: [[5, 5]], inventory: 3, goal_complete: false };
  const observation: Observation = { position: [0, 0], inventory: 0, goal_complete: false,
    cells: [{ position: [0, 0], resource: false, home: false }] };
  const { container, rerender } = render(<GridWorld state={state} perspective="agent" observation={observation} />);
  const firstMarkup = container.innerHTML;
  rerender(<GridWorld state={{ ...state, position: [4, 4], home: [3, 3], resources: [[2, 2]] }} perspective="agent" observation={observation} />);
  expect(container.innerHTML).toBe(firstMarkup);
  expect(screen.getAllByRole('gridcell', { name: /unknown/ })).toHaveLength(63);
  expect(screen.getByRole('gridcell', { name: 'Cell (0, 0): agent' })).toBeInTheDocument();
});
