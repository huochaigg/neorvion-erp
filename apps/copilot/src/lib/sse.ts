import type { StreamEvent } from '@/types';

function isAbortError(error: unknown) {
  return error instanceof DOMException
    ? error.name === 'AbortError'
    : error instanceof Error && error.name === 'AbortError';
}

export async function consumeSse(
  response: Response,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
) {
  if (!response.body) throw new Error('响应不支持流式读取');
  if (signal?.aborted) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let name = 'message';
  let data: string[] = [];
  const flush = () => {
    if (!data.length) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(data.join('\n'));
    } catch {
      parsed = { message: data.join('\n') };
    }
    onEvent({
      event: name,
      data:
        typeof parsed === 'object' && parsed !== null
          ? (parsed as Record<string, unknown>)
          : { value: parsed },
    });
    name = 'message';
    data = [];
  };
  const cancelReader = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener('abort', cancelReader, { once: true });
  try {
    while (!signal?.aborted) {
      const { done, value } = await reader.read();
      if (signal?.aborted) break;
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const raw of lines) {
        if (signal?.aborted) return;
        const line = raw.replace(/\r$/, '');
        if (!line) {
          flush();
        } else if (line.startsWith('event:')) {
          name = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          data.push(line.slice(5).trimStart());
        }
      }
      if (done) break;
    }
    if (!signal?.aborted) {
      if (buffer.startsWith('data:')) data.push(buffer.slice(5).trimStart());
      flush();
    }
  } catch (error) {
    if (signal?.aborted || isAbortError(error)) return;
    throw error;
  } finally {
    signal?.removeEventListener('abort', cancelReader);
    cancelReader();
  }
}
