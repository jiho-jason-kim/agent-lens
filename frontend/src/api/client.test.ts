import { afterEach, expect, it, vi } from 'vitest';
import { createRun, listRuns, listScenarios } from './client';

afterEach(() => vi.unstubAllGlobals());
it('combines both recording versions in chronological order', async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => [{ run_id: 'old', created_at: '2026-01-01' }] })
    .mockResolvedValueOnce({ ok: true, json: async () => [{ run_id: 'new', created_at: '2026-02-01' }] });
  vi.stubGlobal('fetch', fetch);
  expect((await listRuns()).map(run => run.run_id)).toEqual(['new', 'old']);
  expect(fetch.mock.calls.map(call => call[0])).toEqual(['/runs', '/runs?schema_version=2']);
});
it('sends the selected scenario only through the explicit create request', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  vi.stubGlobal('fetch', fetch);
  await listScenarios();
  expect(fetch).toHaveBeenCalledWith('/scenarios', undefined);
  await createRun('coordination');
  expect(fetch).toHaveBeenLastCalledWith('/runs', expect.objectContaining({ method: 'POST',
    body: JSON.stringify({ scenario_id: 'coordination', agent: 'mock' }) }));
});

it('sends LangChain mode when selected and explains missing configuration', async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    .mockResolvedValueOnce({ ok: false, status: 503 });
  vi.stubGlobal('fetch', fetch);
  await createRun('handoff-race', 'langchain');
  expect(fetch).toHaveBeenLastCalledWith('/runs', expect.objectContaining({
    body: JSON.stringify({ scenario_id: 'handoff-race', agent: 'langchain' }),
  }));
  await expect(createRun('handoff-race', 'langchain')).rejects.toThrow('OPENAI_MODEL');
});
