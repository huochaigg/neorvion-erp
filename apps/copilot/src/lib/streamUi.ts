import type { StreamEvent } from '@/types';

export function shouldApplyStreamEvent(input: {
  runId: string;
  activeRunId: string;
  pendingConversationId: number | null;
  selectedConversationId: number | null;
}) {
  if (input.runId !== input.activeRunId) return false;
  if (
    input.pendingConversationId != null &&
    input.selectedConversationId != null &&
    input.pendingConversationId !== input.selectedConversationId
  ) {
    return false;
  }
  return true;
}

function mergeMessageEvent(queue: StreamEvent[], event: StreamEvent) {
  const last = queue.at(-1);
  if (last?.event === 'message') {
    last.data = {
      ...last.data,
      ...event.data,
      delta: `${String(last.data.delta ?? '')}${String(event.data.delta ?? '')}`,
    };
    return;
  }
  queue.push({ event: event.event, data: { ...event.data } });
}

export function createStreamFrameQueue(options: {
  onEvent: (event: StreamEvent) => void;
  schedule?: (cb: () => void) => number;
  cancel?: (id: number) => void;
}) {
  const schedule = options.schedule ?? ((cb) => requestAnimationFrame(cb));
  const cancel = options.cancel ?? ((id) => cancelAnimationFrame(id));
  let queued: StreamEvent[] = [];
  let frame = 0;
  let closed = false;

  const flush = () => {
    if (frame) {
      cancel(frame);
      frame = 0;
    }
    if (!queued.length) return;
    const batch = queued;
    queued = [];
    for (const event of batch) options.onEvent(event);
  };

  return {
    push(event: StreamEvent) {
      if (closed) return false;
      if (event.event === 'message') {
        mergeMessageEvent(queued, event);
        if (!frame) frame = schedule(flush);
        return true;
      }
      flush();
      options.onEvent(event);
      return true;
    },
    flush,
    close() {
      closed = true;
      if (frame) cancel(frame);
      frame = 0;
      queued = [];
    },
    get pending() {
      return queued.length;
    },
    get closed() {
      return closed;
    },
  };
}

export type StreamFrameQueue = ReturnType<typeof createStreamFrameQueue>;
