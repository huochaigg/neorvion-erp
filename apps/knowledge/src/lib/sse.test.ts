import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { consumeSse } from './sse';

describe('consumeSse', () => {
  it('解析 token/citation/done 事件', async () => {
    const body = [
      'event: token',
      'data: {"text":"你好"}',
      '',
      'event: citation',
      'data: {"chunk_id":1}',
      '',
      'event: done',
      'data: {"message_id":9}',
      '',
      '',
    ].join('\n');
    const response = new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
    const events: Array<{ event: string; data: unknown }> = [];
    await consumeSse(response, {
      onEvent: (event, data) => events.push({ event, data }),
    });
    assert.equal(events.length, 3);
    assert.equal(events[0]?.event, 'token');
    assert.deepEqual(events[0]?.data, { text: '你好' });
    assert.equal(events[1]?.event, 'citation');
    assert.equal(events[2]?.event, 'done');
  });
});
