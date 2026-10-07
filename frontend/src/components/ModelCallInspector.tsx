import type { RecordedEvent } from '../types';

export function ModelCallInspector({ event }: { event?: RecordedEvent }) {
  if (!event || event.type !== 'model_call') return null;
  const call = event.payload;
  const usage = call.usage as Record<string, number> | undefined;
  return <section aria-label="Model request" className="recording-details">
    <p className="eyebrow">RECORDED MODEL REQUEST</p>
    <p>{String(call.model)} · {Number(call.duration_ms).toFixed(0)} ms</p>
    <p>{usage?.input_tokens ?? 'Unknown'} input tokens · {usage?.output_tokens ?? 'Unknown'} output tokens</p>
    {Boolean(call.error_category) && <p role="status">Failure category: {String(call.error_category)}</p>}
    <details><summary>Exact system instructions</summary><pre>{String(call.system_instructions)}</pre></details>
    <details><summary>Exact submitted context</summary><pre>{String(call.context_json)}</pre></details>
    <details><summary>Validated response and settings</summary><pre>{JSON.stringify({ response: call.validated_response, settings: call.settings, prompt_version: call.prompt_version, prompt_sha256: call.prompt_sha256 }, null, 2)}</pre></details>
    <p>Recorded request and output. No hidden reasoning is captured.</p>
  </section>;
}
