import {
  knowledgeBasesQueryKey,
  knowledgeConversationQueryKey,
  knowledgeConversationsQueryKey,
  KNOWLEDGE_MESSAGE_ROLE,
  KNOWLEDGE_MESSAGE_STATUS,
  type KnowledgeCitation,
  type KnowledgeConversation,
  type KnowledgeMessage,
} from '@neorvion/shared';
import { DeleteOutlined, PlusOutlined, StopOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Empty, Input, Popconfirm, Select, Space, Spin, Tag } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchKnowledgeBases } from '@/api/knowledge-bases';
import { fetchChunk } from '@/api/documents';
import {
  createConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  streamConversationMessage,
} from '@/api/rag';
import { ChatMarkdown } from '@/components/ChatMarkdown';
import { abortKnowledgeStreams } from '@/lib/knowledge-stream';
import { usePermissions } from '@/hooks/usePermissions';

interface StreamCitation extends KnowledgeCitation {
  snippet: string;
}

function asRecord(data: unknown): Record<string, unknown> {
  return data && typeof data === 'object' ? (data as Record<string, unknown>) : {};
}

export function ChatPage() {
  const { id } = useParams();
  const conversationId = id ? Number(id) : null;
  const navigate = useNavigate();
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [streamCitations, setStreamCitations] = useState<StreamCitation[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [baseIds, setBaseIds] = useState<number[]>([]);
  const [activeCitation, setActiveCitation] = useState<StreamCitation | null>(null);
  const [chunkBody, setChunkBody] = useState<string>('');
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return () => abortKnowledgeStreams();
  }, [tenantId, conversationId]);

  const listQuery = useQuery({
    queryKey: knowledgeConversationsQueryKey(tenantId, { page: 1, pageSize: 50 }),
    queryFn: ({ signal }) => fetchConversations({ page: 1, pageSize: 50 }, signal),
    enabled: tenantId != null,
  });

  const detailQuery = useQuery({
    queryKey: knowledgeConversationQueryKey(tenantId, Number.isFinite(conversationId) ? conversationId : null),
    queryFn: ({ signal }) => fetchConversation(conversationId as number, signal),
    enabled: tenantId != null && conversationId != null && Number.isFinite(conversationId),
  });

  const basesQuery = useQuery({
    queryKey: knowledgeBasesQueryKey(tenantId, { page: 1, pageSize: 100, status: 'ACTIVE' }),
    queryFn: ({ signal }) => fetchKnowledgeBases({ page: 1, pageSize: 100, status: 'ACTIVE' }, signal),
    enabled: tenantId != null,
  });

  const createMutation = useMutation({
    mutationFn: () => createConversation({ knowledge_base_ids: baseIds.length ? baseIds : undefined }),
    onSuccess: (row) => {
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-conversations'] });
      navigate(`/chat/${row.id}`);
    },
    onError: (error: Error) => message.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: (_, deletedId) => {
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-conversations'] });
      if (conversationId === deletedId) {
        navigate('/chat');
      }
    },
    onError: (error: Error) => message.error(error.message),
  });

  const messages: KnowledgeMessage[] = detailQuery.data?.messages ?? [];
  const conversations: KnowledgeConversation[] = listQuery.data?.items ?? [];

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, streamText]);

  const baseOptions = useMemo(
    () => (basesQuery.data?.items ?? []).map((item) => ({ value: item.id, label: item.name })),
    [basesQuery.data],
  );

  const ask = async (content: string, regenerateOf?: number) => {
    if (!conversationId || !content.trim() || streaming) {
      return;
    }
    setStreaming(true);
    setStreamText('');
    setStreamCitations([]);
    setStreamError(null);
    try {
      await streamConversationMessage(conversationId, {
        content: content.trim(),
        strategy: 'HYBRID',
        rerank: true,
        regenerate_of: regenerateOf,
      }, (event, data) => {
        const payload = asRecord(data);
        if (event === 'token' && typeof payload.text === 'string') {
          setStreamText((current) => current + payload.text);
        }
        if (event === 'citation') {
          setStreamCitations((current) => [
            ...current,
            {
              chunk_id: Number(payload.chunk_id),
              document_id: Number(payload.document_id),
              knowledge_base_id: Number(payload.knowledge_base_id),
              filename: String(payload.filename ?? ''),
              page_no: payload.page_no == null ? null : Number(payload.page_no),
              heading: payload.heading == null ? null : String(payload.heading),
              snippet: String(payload.snippet ?? ''),
              rank: Number(payload.rank ?? 0),
              vector_score: payload.vector_score == null ? null : Number(payload.vector_score),
              keyword_score: payload.keyword_score == null ? null : Number(payload.keyword_score),
              rrf_score: payload.rrf_score == null ? null : Number(payload.rrf_score),
              rerank_score: payload.rerank_score == null ? null : Number(payload.rerank_score),
            },
          ]);
        }
        if (event === 'error') {
          setStreamError(String(payload.message ?? '生成失败'));
        }
      });
      setInput('');
      await detailQuery.refetch();
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-conversations'] });
      setStreamText('');
      setStreamCitations([]);
    } catch (error) {
      if ((error as { name?: string }).name === 'AbortError') {
        setStreamError('已停止生成');
      } else {
        setStreamError(error instanceof Error ? error.message : '生成失败');
      }
    } finally {
      setStreaming(false);
    }
  };

  const lastAssistant = [...messages].reverse().find((item) => item.role === KNOWLEDGE_MESSAGE_ROLE.assistant);

  const openCitation = async (citation: StreamCitation) => {
    setActiveCitation(citation);
    setChunkBody(citation.snippet);
    try {
      const chunk = await fetchChunk(citation.chunk_id);
      setChunkBody(chunk.content);
    } catch {
      setChunkBody(citation.snippet);
    }
  };

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <aside className="flex w-[260px] shrink-0 flex-col border-r border-slate-200 bg-[#fafbfc]">
        <div className="flex items-center justify-between px-3 py-3">
          <span className="text-sm font-medium">会话</span>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => createMutation.mutate()}>
            新建
          </Button>
        </div>
        <div className="px-3 pb-2">
          <Select
            mode="multiple"
            allowClear
            placeholder="限定知识库（可选）"
            value={baseIds}
            onChange={setBaseIds}
            options={baseOptions}
            className="w-full"
            size="small"
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {conversations.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无会话" />
          ) : (
            conversations.map((item) => (
              <div
                key={item.id}
                className={`flex cursor-pointer items-center justify-between px-3 py-2 text-sm ${
                  item.id === conversationId ? 'bg-white text-[#1890ff]' : 'text-slate-700'
                }`}
                onClick={() => navigate(`/chat/${item.id}`)}
              >
                <span className="truncate">{item.title}</span>
                <Popconfirm title="删除该会话？" onConfirm={() => deleteMutation.mutate(item.id)}>
                  <Button type="text" size="small" icon={<DeleteOutlined />} onClick={(event) => event.stopPropagation()} />
                </Popconfirm>
              </div>
            ))
          )}
        </div>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col">
        {!conversationId ? (
          <div className="flex h-full items-center justify-center">
            <Empty description="选择或新建会话后开始提问" />
          </div>
        ) : detailQuery.isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Spin />
          </div>
        ) : (
          <>
            <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {messages.length === 0 && !streaming ? <Empty description="向知识库提问，回答会附带来源引用" /> : null}
              {messages.map((item) => (
                <div key={item.id} className={`mb-4 ${item.role === KNOWLEDGE_MESSAGE_ROLE.user ? 'text-right' : ''}`}>
                  <div
                    className={`inline-block max-w-[80%] rounded-lg px-3 py-2 text-left ${
                      item.role === KNOWLEDGE_MESSAGE_ROLE.user ? 'bg-[#e6f4ff]' : 'bg-slate-50'
                    }`}
                  >
                    {item.role === KNOWLEDGE_MESSAGE_ROLE.assistant ? (
                      <ChatMarkdown text={item.content || item.error_message || ''} />
                    ) : (
                      <div className="whitespace-pre-wrap text-sm">{item.content}</div>
                    )}
                    {item.citations?.length ? (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {item.citations.map((citation) => (
                          <Tag
                            key={`${item.id}-${citation.chunk_id}`}
                            className="cursor-pointer"
                            onClick={() => void openCitation(citation)}
                          >
                            [{citation.rank}] {citation.filename}
                          </Tag>
                        ))}
                      </div>
                    ) : null}
                    {item.status === KNOWLEDGE_MESSAGE_STATUS.failed ? (
                      <div className="mt-1 text-xs text-red-500">{item.error_message}</div>
                    ) : null}
                  </div>
                </div>
              ))}
              {streaming ? (
                <div className="mb-4">
                  <div className="inline-block max-w-[80%] rounded-lg bg-slate-50 px-3 py-2">
                    <ChatMarkdown text={streamText || '正在检索与生成…'} />
                    {streamCitations.length ? (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {streamCitations.map((citation) => (
                          <Tag key={citation.chunk_id} className="cursor-pointer" onClick={() => void openCitation(citation)}>
                            [{citation.rank}] {citation.filename}
                          </Tag>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {streamError ? <div className="mb-3 text-sm text-red-500">{streamError}</div> : null}
            </div>
            <div className="border-t border-slate-200 px-4 py-3">
              <Space.Compact className="w-full">
                <Input.TextArea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  autoSize={{ minRows: 1, maxRows: 4 }}
                  placeholder="输入问题，回答仅基于当前企业知识库"
                  onPressEnter={(event) => {
                    if (!event.shiftKey) {
                      event.preventDefault();
                      void ask(input);
                    }
                  }}
                />
                {streaming ? (
                  <Button icon={<StopOutlined />} onClick={() => abortKnowledgeStreams()}>
                    停止
                  </Button>
                ) : (
                  <Button type="primary" onClick={() => void ask(input)} disabled={!input.trim()}>
                    发送
                  </Button>
                )}
              </Space.Compact>
              <div className="mt-2">
                <Button
                  type="link"
                  size="small"
                  disabled={!lastAssistant || streaming}
                  onClick={() => void ask('重新生成', lastAssistant?.id)}
                >
                  重新生成
                </Button>
              </div>
            </div>
          </>
        )}
      </section>
      <Drawer title={activeCitation?.filename} open={activeCitation != null} onClose={() => setActiveCitation(null)} width={560}>
        <div className="whitespace-pre-wrap text-sm leading-6">{chunkBody}</div>
      </Drawer>
    </div>
  );
}
