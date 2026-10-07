import { expect, it } from 'vitest';
import { focusedGraph, recordedEdges } from './provenance';

import { lineage } from './lineage.fixture';

it('traces message and memory lineage across agent boundaries using saved references', () => {
  const graph = focusedGraph(lineage, 'receive', 'both', 8);
  expect(graph.nodes.map(node => node.event_id)).toContain('report');
  expect(graph.nodes.map(node => node.event_id)).toContain('retrieve-blue');
  expect(graph.nodes.map(node => node.event_id)).not.toContain('unrelated');
  expect(graph.edges).toContainEqual({ source: 'send', target: 'receive', relationship: 'received_as' });
  expect(graph.edges).toContainEqual({ source: 'receive', target: 'write-blue', relationship: 'stored_as' });
  expect(graph.edges).toContainEqual({ source: 'write-blue', target: 'retrieve-blue', relationship: 'retrieved_for' });
  expect(graph.edges).toContainEqual({ source: 'plan-green', target: 'action-green', relationship: 'followed_by' });
});
it('limits direction and depth without adding siblings or dangling references', () => {
  expect(focusedGraph(lineage, 'receive', 'upstream', 1).nodes.map(node => node.event_id)).toEqual(['send', 'receive']);
  expect(focusedGraph(lineage, 'receive', 'downstream', 1).nodes.map(node => node.event_id)).toEqual(['receive', 'write-blue']);
  expect(recordedEdges([{ ...lineage[0], input_refs: ['missing'] }])).toEqual([]);
  expect(focusedGraph(lineage, 'missing', 'both', 8).nodes).toEqual([]);
});
it('does not infer links from matching text, agent, turn, or unpaired effect references', () => {
  expect(recordedEdges(lineage.map(event => ({ ...event, input_refs: [], effect_refs: ['unrelated'] })))).toEqual([]);
});
it('bounds large traversals and tolerates cycles', () => {
  const many = Array.from({ length: 60 }, (_, index) => ({ ...lineage[0], event_id: `n-${index}`, input_refs: index ? ['n-0'] : ['n-1'] }));
  const graph = focusedGraph(many, 'n-0', 'both', 8);
  expect(graph.nodes).toHaveLength(40);
  expect(graph.omitted).toBe(20);
});
