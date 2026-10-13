let activeStream: AbortController | null = null;

/** 当前知识库 SSE 生成句柄。切租户或新提问时必须先中止旧流。 */
export function beginKnowledgeStream(): AbortController {
  activeStream?.abort();
  activeStream = new AbortController();
  return activeStream;
}

export function abortKnowledgeStreams(): void {
  activeStream?.abort();
  activeStream = null;
}
