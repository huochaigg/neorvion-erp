export interface SseHandlers {
  onEvent: (event: string, data: unknown) => void;
}

function parseData(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

/** 解析 text/event-stream，按空行切分 event/data。 */
export async function consumeSse(response: Response, handlers: SseHandlers): Promise<void> {
  if (!response.body) {
    throw new Error('响应不支持流式读取');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventName = 'message';
  const dataLines: string[] = [];

  const flush = () => {
    if (dataLines.length === 0) {
      eventName = 'message';
      return;
    }
    handlers.onEvent(eventName, parseData(dataLines.join('\n')));
    dataLines.length = 0;
    eventName = 'message';
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.replace(/\r$/, '');
      if (trimmed === '') {
        flush();
        continue;
      }
      if (trimmed.startsWith('event:')) {
        eventName = trimmed.slice(6).trim();
        continue;
      }
      if (trimmed.startsWith('data:')) {
        dataLines.push(trimmed.slice(5).trimStart());
      }
    }
  }
  if (buffer.trim()) {
    const trimmed = buffer.replace(/\r$/, '');
    if (trimmed.startsWith('event:')) {
      eventName = trimmed.slice(6).trim();
    } else if (trimmed.startsWith('data:')) {
      dataLines.push(trimmed.slice(5).trimStart());
    }
  }
  flush();
}
