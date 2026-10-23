import { describe, expect, it } from 'vitest';
import { consumeSse } from './sse';

describe('consumeSse', () => {
  it('解析跨 chunk UTF-8、evidence 与完成事件', async () => {
    const bytes = new TextEncoder().encode(
      'event: message\ndata: {"delta":"库存"}\n\n' +
      'event: evidence\ndata: {"citation_id":"E1","source_type":"ERP"}\n\n' +
      'event: done\ndata: {"answer":"完成"}\n\n',
    );
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 25));
        controller.enqueue(bytes.slice(25, 70));
        controller.enqueue(bytes.slice(70));
        controller.close();
      },
    });
    const items: Array<{ event: string; data: Record<string, unknown> }> = [];
    await consumeSse(new Response(body), (item) => items.push(item));
    expect(items).toEqual([
      { event: 'message', data: { delta: '库存' } },
      { event: 'evidence', data: { citation_id: 'E1', source_type: 'ERP' } },
      { event: 'done', data: { answer: '完成' } },
    ]);
  });
});
