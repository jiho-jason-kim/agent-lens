import type { RecordedEvent } from '../types';
import { messageHistory } from '../replay/inspectors';

export function MessageInspector({ events, agentId, turn, onSelect }: {
  events: RecordedEvent[]; agentId?: string; turn: number; onSelect: (event: RecordedEvent) => void;
}) {
  const messages = messageHistory(events, turn, agentId);
  return <section className="archive-inspector" aria-label="Message inspector">
    <p className="eyebrow">{agentId?.toUpperCase() ?? 'GLOBAL'} COMMUNICATION</p><h2>Recorded messages</h2>
    <p className="scope-note">Recorded through turn {turn}. Pending incoming messages remain hidden in agent views. Delivery and memory links show debugger records.</p>
    {!messages.length && <p>No messages available at this turn.</p>}
    {messages.map(({ message, send, receipt, writes, retrievals }) => <article key={message.message_id}>
      <h3>{message.sender_id} → {message.recipient_id}</h3><p>{message.content}</p>
      <dl><dt>Message</dt><dd>{message.message_id}</dd><dt>Sent</dt><dd>Turn {message.sent_turn}</dd>
        <dt>Received</dt><dd>{receipt ? `Turn ${receipt.turn}` : 'Pending'}</dd>
        <dt>Stored as</dt><dd>{writes.map(write => (write.payload as { memory: { memory_id: string } }).memory.memory_id).join(', ') || 'Not recorded'}</dd>
        <dt>Later retrieved</dt><dd>{retrievals.map(event => event.turn).join(', ') || 'Not recorded'}</dd></dl>
      <div className="archive-links"><button onClick={() => onSelect(send)}>Send {send.event_id}</button>
        {receipt && <button onClick={() => onSelect(receipt)}>Receipt {receipt.event_id}</button>}
        {writes.map(write => <button key={write.event_id} onClick={() => onSelect(write)}>Memory {write.event_id}</button>)}
        {retrievals.map(event => <button key={event.event_id} onClick={() => onSelect(event)}>Retrieved at turn {event.turn}</button>)}
      </div>
    </article>)}
  </section>;
}
