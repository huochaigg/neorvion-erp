import {
  DEFAULT_PAGE_SIZE,
  knowledgeEvalDatasetsQueryKey,
  knowledgeEvalExperimentsQueryKey,
  knowledgeEvalResultsQueryKey,
  knowledgeEvalInterruptLabel,
  knowledgeEvalRunsQueryKey,
  knowledgeEvalStageLabel,
  knowledgeRetrievalStrategyLabel,
  knowledgeRunStatusColor,
  knowledgeRunStatusLabel,
  KNOWLEDGE_RETRIEVAL_STRATEGY,
  PERMISSION_CODE,
  type KnowledgeEvalExperiment,
  type KnowledgeEvalResult,
  type KnowledgeEvalRun,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Alert, Button, Descriptions, Drawer, Form, Input, InputNumber, Modal, Progress, Select, Space, Switch, Tag, Tooltip } from 'antd';
import type { TableProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  cancelEvalRun,
  copyEvalExperiment,
  createEvalExperiment,
  fetchEvalDatasets,
  fetchEvalExperiments,
  fetchEvalResults,
  fetchEvalRun,
  fetchEvalRuns,
  pauseEvalRun,
  resumeEvalRun,
  retryFailedEvalRun,
  startEvalRun,
} from '@/api/evaluation';
import { fetchRetrievalDefaults } from '@/api/rag';
import { ActionCell, AppTable, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { EvalCaseResultPanel } from '@/components/EvalCaseResultPanel';
import { FormLabelHelp } from '@/components/FormLabelHelp';
import { MetricBars } from '@/components/MetricBars';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';
import {
  comparabilityWarning,
  EVAL_METRIC_HELP,
  evalRunMetrics,
  evalRunProgressText,
  formatEvalCount,
  formatEvalMetric,
  formatLatencyMs,
  formatRunDuration,
  latestRunStatus,
  metricMissingReason,
  usageNumber,
  type EvalMetricContext,
} from '@/lib/evalMetrics';
import {
  candidateKHelp,
  keywordTopKHelp,
  rerankHelp,
  rrfKHelp,
  similarityThresholdHelp,
  topKHelp,
  vectorTopKHelp,
} from '@/lib/retrievalHelp';
import { snapshotParam } from '@/lib/snapshotParam';

const RUN_STATUS_FILTERS = ['NEVER_RUN', 'QUEUED', 'RUNNING', 'PAUSED', 'SUCCESS', 'FAILED', 'CANCELLED'];
const RUN_RECORD_STATUS_FILTERS = ['QUEUED', 'RUNNING', 'PAUSED', 'SUCCESS', 'FAILED', 'CANCELLED'];
const METRIC_SORT_KEYS = new Set(['recall', 'mrr', 'ndcg', 'hit_rate', 'latency_p95', 'id']);

function metricNumber(metrics: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = metrics?.[key];
  return typeof value === 'number' ? value : null;
}

function sortOrderOf(sortBy: string, sortOrder: string, key: string) {
  if (sortBy !== key) {
    return undefined;
  }
  return sortOrder === 'asc' ? 'ascend' : 'descend';
}

function MetricCell({
  value,
  run,
  help,
}: {
  value: number | null | undefined;
  run: EvalMetricContext;
  help: string;
}) {
  const text = formatEvalMetric(value);
  const extra =
    text === '-'
      ? metricMissingReason(run)
      : [run?.k != null ? `K=${run.k}` : null, run?.supervised_count != null ? `有效题 ${run.supervised_count}` : null]
          .filter(Boolean)
          .join('，');
  return (
    <Tooltip title={<div className="max-w-xs text-xs leading-5">{`${help}${extra ? ` ${extra}` : ''}`}</div>}>
      <span>{text}</span>
    </Tooltip>
  );
}

function ExperimentStatusCell({
  run,
}: {
  run: { status: string; progress?: number; error_message?: string | null } | null | undefined;
}) {
  const status = latestRunStatus(run);
  const progressStatus =
    run?.status === 'FAILED'
      ? 'exception'
      : run?.status === 'SUCCESS'
        ? 'success'
        : run?.status === 'QUEUED' || run?.status === 'RUNNING'
          ? 'active'
          : 'normal';
  const error = run && 'error_message' in run ? run.error_message : null;
  const interrupt =
    run && 'interrupt_reason' in run && typeof run.interrupt_reason === 'string'
      ? knowledgeEvalInterruptLabel(run.interrupt_reason)
      : '';
  return (
    <div className="flex min-w-[110px] flex-col gap-1">
      <Tooltip title={error || interrupt || undefined}>
        <Tag color={knowledgeRunStatusColor(status)}>{knowledgeRunStatusLabel(status)}</Tag>
      </Tooltip>
      {run && typeof run.progress === 'number' ? (
        <Progress percent={run.progress} size="small" status={progressStatus} />
      ) : (
        <span className="text-xs text-slate-400">未开始</span>
      )}
      {run?.status === 'PAUSED' && (interrupt || error) ? (
        <span className="line-clamp-2 text-xs text-amber-600" title={error || interrupt}>
          {interrupt || error}
        </span>
      ) : null}
      {run?.status === 'FAILED' && error ? (
        <span className="line-clamp-2 text-xs text-red-500" title={error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

export function EvaluationExperimentsPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [datasetId, setDatasetId] = useState<number | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [strategy, setStrategy] = useState<string | undefined>();
  const [sortBy, setSortBy] = useState('id');
  const [sortOrder, setSortOrder] = useState('desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [runsPage, setRunsPage] = useState(1);
  const [runsPageSize, setRunsPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [runsStatus, setRunsStatus] = useState<string | undefined>();
  const [runsSortBy, setRunsSortBy] = useState('id');
  const [runsSortOrder, setRunsSortOrder] = useState('desc');
  const [selectedMap, setSelectedMap] = useState<Record<number, KnowledgeEvalExperiment>>({});
  const [creating, setCreating] = useState(false);
  const [activeRun, setActiveRun] = useState<KnowledgeEvalRun | null>(null);
  const [activeResult, setActiveResult] = useState<KnowledgeEvalResult | null>(null);
  const [resumeTarget, setResumeTarget] = useState<KnowledgeEvalRun | null>(null);
  const [form] = Form.useForm();
  const [resumeForm] = Form.useForm();

  useEffect(() => {
    setDatasetId(undefined);
    setStatus(undefined);
    setStrategy(undefined);
    setSortBy('id');
    setSortOrder('desc');
    setPage(1);
    setPageSize(DEFAULT_PAGE_SIZE);
    setRunsPage(1);
    setRunsPageSize(DEFAULT_PAGE_SIZE);
    setRunsStatus(undefined);
    setRunsSortBy('id');
    setRunsSortOrder('desc');
    setSelectedMap({});
    setActiveRun(null);
    setActiveResult(null);
    setResumeTarget(null);
  }, [tenantId]);

  const defaultsQuery = useQuery({
    queryKey: ['tenant', tenantId, 'knowledge-retrieval-defaults'],
    queryFn: ({ signal }) => fetchRetrievalDefaults(signal),
    enabled: tenantId != null,
  });
  const defaults = defaultsQuery.data;
  const datasetsQuery = useQuery({
    queryKey: knowledgeEvalDatasetsQueryKey(tenantId, { page: 1, pageSize: 100 }),
    queryFn: ({ signal }) => fetchEvalDatasets({ page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });

  const listQuery = useQuery({
    queryKey: knowledgeEvalExperimentsQueryKey(tenantId, {
      datasetId,
      status,
      strategy,
      sortBy,
      sortOrder,
      page,
      pageSize,
    }),
    queryFn: ({ signal }) =>
      fetchEvalExperiments({ datasetId, status, strategy, sortBy, sortOrder, page, pageSize }, signal),
    enabled: tenantId != null,
    refetchInterval: (current) => {
      const items = current.state.data?.items ?? [];
      return items.some((item) => item.latest_run?.status === 'QUEUED' || item.latest_run?.status === 'RUNNING')
        ? 2000
        : false;
    },
  });

  const runsQuery = useQuery({
    queryKey: knowledgeEvalRunsQueryKey(tenantId, {
      status: runsStatus,
      sortBy: runsSortBy,
      sortOrder: runsSortOrder,
      page: runsPage,
      pageSize: runsPageSize,
    }),
    queryFn: ({ signal }) =>
      fetchEvalRuns(
        { status: runsStatus, sortBy: runsSortBy, sortOrder: runsSortOrder, page: runsPage, pageSize: runsPageSize },
        signal,
      ),
    enabled: tenantId != null,
    refetchInterval: (current) => {
      const items = current.state.data?.items ?? [];
      return items.some((item) => item.status === 'QUEUED' || item.status === 'RUNNING') ? 2000 : false;
    },
  });

  const resultsQuery = useQuery({
    queryKey: knowledgeEvalResultsQueryKey(tenantId, activeRun?.id ?? null),
    queryFn: ({ signal }) => fetchEvalResults(activeRun!.id, signal),
    enabled: tenantId != null && activeRun != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-experiments'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-runs'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-results'] });
  };

  const createMutation = useMutation({
    mutationFn: createEvalExperiment,
    onSuccess: () => {
      message.success('已创建实验');
      setCreating(false);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const selectedIds = useMemo(() => Object.keys(selectedMap).map(Number), [selectedMap]);
  const selectedExperiments = useMemo(
    () =>
      selectedIds
        .map((id) => (listQuery.data?.items ?? []).find((item) => item.id === id) ?? selectedMap[id])
        .filter((item): item is KnowledgeEvalExperiment => item != null),
    [listQuery.data?.items, selectedIds, selectedMap],
  );
  const compareHint = comparabilityWarning(selectedExperiments);
  const datasetName = (id: number) =>
    datasetsQuery.data?.items.find((item) => item.id === id)?.name ?? `数据集 #${id}`;

  const goCompare = () => {
    const ready = selectedExperiments.filter((item) => item.latest_run?.status === 'SUCCESS' && item.latest_run.id);
    if (ready.length < 2 || ready.length > 3 || ready.length !== selectedExperiments.length) {
      message.warning('请选择 2～3 个评测成功的实验');
      return;
    }
    const runIds = ready.map((item) => item.latest_run!.id).join(',');
    navigate(`/experiments/compare?run_ids=${runIds}`);
  };

  const handleRunsTableChange: TableProps<KnowledgeEvalRun>['onChange'] = (pagination, _filters, sorter) => {
    const current = Array.isArray(sorter) ? sorter[0] : sorter;
    const columnKey = String(current?.columnKey ?? current?.field ?? 'id');
    if ((current?.order === 'ascend' || current?.order === 'descend') && METRIC_SORT_KEYS.has(columnKey)) {
      setRunsSortBy(columnKey);
      setRunsSortOrder(current.order === 'ascend' ? 'asc' : 'desc');
    } else {
      setRunsSortBy('id');
      setRunsSortOrder('desc');
    }
    setRunsPage(pagination.current ?? 1);
    setRunsPageSize(pagination.pageSize ?? DEFAULT_PAGE_SIZE);
  };

  const handleTableChange: TableProps<KnowledgeEvalExperiment>['onChange'] = (pagination, _filters, sorter) => {
    const current = Array.isArray(sorter) ? sorter[0] : sorter;
    const columnKey = String(current?.columnKey ?? current?.field ?? 'id');
    if ((current?.order === 'ascend' || current?.order === 'descend') && METRIC_SORT_KEYS.has(columnKey)) {
      setSortBy(columnKey);
      setSortOrder(current.order === 'ascend' ? 'asc' : 'desc');
    } else {
      setSortBy('id');
      setSortOrder('desc');
    }
    setPage(pagination.current ?? 1);
    setPageSize(pagination.pageSize ?? DEFAULT_PAGE_SIZE);
  };

  const experimentColumns: ColumnsType<KnowledgeEvalExperiment> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 70,
      sorter: true,
      sortOrder: sortOrderOf(sortBy, sortOrder, 'id'),
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 160,
      ellipsis: true,
      onCell: () => ({ style: { maxWidth: 160 } }),
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '状态',
      width: 140,
      render: (_, record) => <div className="pr-10 pb-2">
        <ExperimentStatusCell run={record.latest_run} />
      </div>,
    },
    {
      title: '策略',
      width: 100,
      render: (_, record) =>
        'strategy' in record.config
          ? knowledgeRetrievalStrategyLabel(String(record.config.strategy ?? ''))
          : '未记录',
    },
    { title: '最终 Top-K', width: 100, render: (_, record) => snapshotParam(record.config, 'top_k') },
    { title: 'Rerank', width: 80, render: (_, record) => snapshotParam(record.config, 'rerank') },
    {
      title: <FormLabelHelp label="Recall@K">{EVAL_METRIC_HELP.recall}</FormLabelHelp>,
      key: 'recall',
      width: 110,
      sorter: true,
      sortDirections: ['descend', 'ascend'],
      sortOrder: sortOrderOf(sortBy, sortOrder, 'recall'),
      render: (_, record) => <MetricCell value={record.latest_run?.recall} run={record.latest_run} help={EVAL_METRIC_HELP.recall} />,
    },
    {
      title: <FormLabelHelp label="MRR">{EVAL_METRIC_HELP.mrr}</FormLabelHelp>,
      key: 'mrr',
      width: 90,
      sorter: true,
      sortDirections: ['descend', 'ascend'],
      sortOrder: sortOrderOf(sortBy, sortOrder, 'mrr'),
      render: (_, record) => <MetricCell value={record.latest_run?.mrr} run={record.latest_run} help={EVAL_METRIC_HELP.mrr} />,
    },
    {
      title: <FormLabelHelp label="nDCG@K">{EVAL_METRIC_HELP.ndcg}</FormLabelHelp>,
      key: 'ndcg',
      width: 110,
      sorter: true,
      sortDirections: ['descend', 'ascend'],
      sortOrder: sortOrderOf(sortBy, sortOrder, 'ndcg'),
      render: (_, record) => <MetricCell value={record.latest_run?.ndcg} run={record.latest_run} help={EVAL_METRIC_HELP.ndcg} />,
    },
    {
      title: <FormLabelHelp label="Hit@K">{EVAL_METRIC_HELP.hit_rate}</FormLabelHelp>,
      key: 'hit_rate',
      width: 90,
      sorter: true,
      sortDirections: ['descend', 'ascend'],
      sortOrder: sortOrderOf(sortBy, sortOrder, 'hit_rate'),
      render: (_, record) => (
        <MetricCell value={record.latest_run?.hit_rate} run={record.latest_run} help={EVAL_METRIC_HELP.hit_rate} />
      ),
    },
    {
      title: <FormLabelHelp label="P95">{EVAL_METRIC_HELP.p95}</FormLabelHelp>,
      key: 'latency_p95',
      width: 90,
      sorter: true,
      sortDirections: ['ascend', 'descend'],
      sortOrder: sortOrderOf(sortBy, sortOrder, 'latency_p95'),
      render: (_, record) => (
        <Tooltip
          title={
            record.latest_run?.latency_p95_ms == null
              ? metricMissingReason(record.latest_run)
              : EVAL_METRIC_HELP.p95
          }
        >
          <span>{formatLatencyMs(record.latest_run?.latency_p95_ms)}</span>
        </Tooltip>
      ),
    },
    {
      title: <FormLabelHelp label="有效题">{EVAL_METRIC_HELP.supervised}</FormLabelHelp>,
      width: 80,
      render: (_, record) => formatEvalCount(record.latest_run?.supervised_count),
    },
    {
      title: '执行时间',
      width: 100,
      render: (_, record) => (
        <Tooltip
          title={
            record.latest_run?.started_at && record.latest_run.finished_at
              ? `${formatDateTime(record.latest_run.started_at)} → ${formatDateTime(record.latest_run.finished_at)}`
              : metricMissingReason(record.latest_run)
          }
        >
          <span>{formatRunDuration(record.latest_run)}</span>
        </Tooltip>
      ),
    },
    {
      title: '操作',
      width: 210,
      fixed: 'right',
      render: (_, record) => (
        <ActionCell>
          {record.latest_run ? (
            <Button
              type="link"
              size="small"
              onClick={() => {
                const cached = (runsQuery.data?.items ?? []).find((item) => item.id === record.latest_run?.id);
                if (cached) {
                  setActiveRun(cached);
                  return;
                }
                void fetchEvalRun(record.latest_run!.id)
                  .then((run) => setActiveRun(run))
                  .catch((error: Error) => message.error(error.message));
              }}
            >
              明细
            </Button>
          ) : null}
          <Can permission={PERMISSION_CODE.knowledgeCreate}>
            <Button
              type="link"
              size="small"
              onClick={() => {
                void startEvalRun(record.id)
                  .then((run) => {
                    if (run.status === 'SUCCESS') {
                      message.success('评测完成');
                      setActiveRun(run);
                    } else {
                      message.success('已开始评测');
                    }
                    setRunsPage(1);
                    invalidate();
                  })
                  .catch((error: Error) => message.error(error.message));
              }}
            >
              运行
            </Button>
            <Button
              type="link"
              size="small"
              onClick={() =>
                copyEvalExperiment(record.id)
                  .then(() => {
                    message.success('已复制');
                    invalidate();
                  })
                  .catch((error: Error) => message.error(error.message))
              }
            >
              复制
            </Button>
          </Can>
        </ActionCell>
      ),
    },
  ];

  const runColumns: ColumnsType<KnowledgeEvalRun> = [
    {
      title: 'Run ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      sorter: true,
      sortOrder: sortOrderOf(runsSortBy, runsSortOrder, 'id'),
    },
    {
      title: '状态',
      width: 150,
      render: (_, record) => <ExperimentStatusCell run={record} />,
    },
    {
      title: '进度',
      width: 200,
      render: (_, record) => {
        const text = evalRunProgressText(record);
        const stage = record.current_stage ? knowledgeEvalStageLabel(record.current_stage) : null;
        return (
          <div className="text-xs leading-5">
            <div>{text || '-'}</div>
            {record.current_case_id ? (
              <div className="text-slate-500">
                当前题 {record.current_case_id}
                {stage ? ` · ${stage}` : ''}
              </div>
            ) : null}
          </div>
        );
      },
    },
    {
      title: 'Token',
      width: 150,
      render: (_, record) => {
        const used =
          (usageNumber(record.usage, 'prompt_tokens') ?? 0) + (usageNumber(record.usage, 'completion_tokens') ?? 0);
        const budget = record.token_budget;
        const remaining = budget == null ? null : Math.max(budget - used, 0);
        const estimated = record.usage?.token_estimated === true;
        return (
          <Tooltip title={estimated ? 'Token 为估算值，不是供应商精确计数' : undefined}>
            <span>
              {used}
              {budget != null ? ` / ${budget}` : ''}
              {remaining != null ? `（剩 ${remaining}）` : ''}
              {estimated ? ' · 估算' : ''}
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: '策略',
      width: 100,
      render: (_, record) =>
        'strategy' in record.config_snapshot
          ? knowledgeRetrievalStrategyLabel(String(record.config_snapshot.strategy ?? ''))
          : '未记录',
    },
    { title: '最终 Top-K', width: 100, render: (_, record) => snapshotParam(record.config_snapshot, 'top_k') },
    { title: 'Rerank', width: 80, render: (_, record) => snapshotParam(record.config_snapshot, 'rerank') },
    {
      title: <FormLabelHelp label="Recall@K">{EVAL_METRIC_HELP.recall}</FormLabelHelp>,
      key: 'recall',
      width: 110,
      sorter: true,
      sortDirections: ['descend', 'ascend'],
      sortOrder: sortOrderOf(runsSortBy, runsSortOrder, 'recall'),
      render: (_, record) => {
        const view = evalRunMetrics(record);
        return <MetricCell value={view.recall} run={view} help={EVAL_METRIC_HELP.recall} />;
      },
    },
    {
      title: <FormLabelHelp label="MRR">{EVAL_METRIC_HELP.mrr}</FormLabelHelp>,
      key: 'mrr',
      width: 90,
      sorter: true,
      sortDirections: ['descend', 'ascend'],
      sortOrder: sortOrderOf(runsSortBy, runsSortOrder, 'mrr'),
      render: (_, record) => {
        const view = evalRunMetrics(record);
        return <MetricCell value={view.mrr} run={view} help={EVAL_METRIC_HELP.mrr} />;
      },
    },
    {
      title: <FormLabelHelp label="nDCG@K">{EVAL_METRIC_HELP.ndcg}</FormLabelHelp>,
      key: 'ndcg',
      width: 110,
      sorter: true,
      sortDirections: ['descend', 'ascend'],
      sortOrder: sortOrderOf(runsSortBy, runsSortOrder, 'ndcg'),
      render: (_, record) => {
        const view = evalRunMetrics(record);
        return <MetricCell value={view.ndcg} run={view} help={EVAL_METRIC_HELP.ndcg} />;
      },
    },
    {
      title: <FormLabelHelp label="Hit@K">{EVAL_METRIC_HELP.hit_rate}</FormLabelHelp>,
      key: 'hit_rate',
      width: 90,
      sorter: true,
      sortDirections: ['descend', 'ascend'],
      sortOrder: sortOrderOf(runsSortBy, runsSortOrder, 'hit_rate'),
      render: (_, record) => {
        const view = evalRunMetrics(record);
        return <MetricCell value={view.hit_rate} run={view} help={EVAL_METRIC_HELP.hit_rate} />;
      },
    },
    {
      title: <FormLabelHelp label="P95">{EVAL_METRIC_HELP.p95}</FormLabelHelp>,
      key: 'latency_p95',
      width: 90,
      sorter: true,
      sortDirections: ['ascend', 'descend'],
      sortOrder: sortOrderOf(runsSortBy, runsSortOrder, 'latency_p95'),
      render: (_, record) => {
        const view = evalRunMetrics(record);
        return (
          <Tooltip title={view.latency_p95_ms == null ? metricMissingReason(view) : EVAL_METRIC_HELP.p95}>
            <span>{formatLatencyMs(view.latency_p95_ms)}</span>
          </Tooltip>
        );
      },
    },
    {
      title: <FormLabelHelp label="有效题">{EVAL_METRIC_HELP.supervised}</FormLabelHelp>,
      width: 100,
      render: (_, record) => {
        const view = evalRunMetrics(record);
        return `${formatEvalCount(view.supervised_count)} / ${formatEvalCount(view.case_count)}`;
      },
    },
    {
      title: '版本',
      width: 140,
      render: (_, record) => (
        <Tooltip
          title={`数据集 ${datasetName(record.dataset_id)}；Embedding ${snapshotParam(record.config_snapshot, 'embedding_model')} / ${snapshotParam(record.config_snapshot, 'embedding_dimensions')}`}
        >
          <span>
            v{record.dataset_version} · {snapshotParam(record.config_snapshot, 'embedding_model')}
          </span>
        </Tooltip>
      ),
    },
    {
      title: '执行时间',
      width: 100,
      render: (_, record) => (
        <Tooltip
          title={
            record.started_at && record.finished_at
              ? `${formatDateTime(record.started_at)} → ${formatDateTime(record.finished_at)}`
              : metricMissingReason(record)
          }
        >
          <span>{formatRunDuration(record)}</span>
        </Tooltip>
      ),
    },
    {
      title: '操作',
      width: 220,
      fixed: 'right',
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => setActiveRun(record)}>
            明细
          </Button>
          {record.status === 'QUEUED' || record.status === 'RUNNING' ? (
            <Button
              type="link"
              size="small"
              onClick={() =>
                pauseEvalRun(record.id)
                  .then(() => {
                    message.success('已请求暂停');
                    invalidate();
                  })
                  .catch((error: Error) => message.error(error.message))
              }
            >
              暂停
            </Button>
          ) : null}
          {record.status === 'QUEUED' || record.status === 'RUNNING' || record.status === 'PAUSED' ? (
            <Button
              type="link"
              size="small"
              onClick={() =>
                cancelEvalRun(record.id)
                  .then(() => {
                    message.success('已请求取消');
                    invalidate();
                  })
                  .catch((error: Error) => message.error(error.message))
              }
            >
              取消
            </Button>
          ) : null}
          {record.status === 'PAUSED' || record.status === 'FAILED' ? (
            <Button
              type="link"
              size="small"
              onClick={() => {
                setResumeTarget(record);
                resumeForm.setFieldsValue({
                  token_budget: record.token_budget,
                  cost_budget_usd: record.cost_budget_usd,
                });
              }}
            >
              继续运行
            </Button>
          ) : null}
          {record.status === 'FAILED' ||
          record.status === 'CANCELLED' ||
          record.status === 'PAUSED' ||
          (record.status === 'SUCCESS' && (usageNumber(record.usage, 'failed_count') ?? 0) > 0) ? (
            <Button
              type="link"
              size="small"
              onClick={() =>
                retryFailedEvalRun(record.id)
                  .then((run) => {
                    message.success('已重试失败题目');
                    if (run.status === 'SUCCESS') {
                      setActiveRun(run);
                    }
                    setRunsPage(1);
                    invalidate();
                  })
                  .catch((error: Error) => message.error(error.message))
              }
            >
              重试失败
            </Button>
          ) : null}
        </ActionCell>
      ),
    },
  ];

  const resultColumns: ColumnsType<KnowledgeEvalResult> = [
    {
      title: '问题',
      dataIndex: 'question',
      width: 300,
      ellipsis: true,
      // AppTable 使用 scroll.x=max-content，仅设 width 会被长文本撑开；用 maxWidth + EllipsisCell 固定可视宽度
      onCell: () => ({ style: { maxWidth: 300 } }),
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '阶段',
      width: 180,
      render: (_, record) => {
        const stages = record.stages ?? {};
        const names = ['RETRIEVE', 'RERANK', 'GENERATE', 'JUDGE', 'METRICS'];
        return (
          <Space size={4} wrap>
            {names.map((name) => {
              const entry = stages[name];
              const status = entry && typeof entry === 'object' && 'status' in entry ? String(entry.status) : 'PENDING';
              const color =
                status === 'SUCCESS' || status === 'SKIPPED' || status === 'DEGRADED'
                  ? 'success'
                  : status === 'FAILED'
                    ? 'error'
                    : 'default';
              return (
                <Tag key={name} color={color}>
                  {knowledgeEvalStageLabel(name)}
                </Tag>
              );
            })}
          </Space>
        );
      },
    },
    { title: '耗时', dataIndex: 'latency_ms', width: 80, render: (value: number) => `${value}ms` },
    {
      title: 'Recall',
      width: 90,
      render: (_, record) => metricNumber(record.retrieval_metrics, 'recall')?.toFixed(3) ?? (record.is_unanswerable ? '无答案' : '-'),
    },
    {
      title: 'Hit',
      width: 80,
      render: (_, record) => metricNumber(record.retrieval_metrics, 'hit_rate')?.toFixed(0) ?? '-',
    },
    {
      title: '错误',
      ellipsis: true,
      onCell: () => ({ style: { maxWidth: 240 } }),
      render: (_, record) => <EllipsisCell value={record.error_message || record.judge_error || '-'} />,
    },
    {
      title: '明细',
      width: 80,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => setActiveResult(record)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader
        title="检索评测"
        description="选择数据集、配置检索参数并异步跑批。指标由代码计算，不使用 LLM 给 Recall/nDCG 打分。生成质量评测可选，以避免额外费用。"
        extra={
          <Space>
            <Button disabled={selectedIds.length < 2} onClick={goCompare}>
              对比已选（{selectedIds.length}）
            </Button>
            <Button onClick={() => navigate('/experiments/compare')}>实验对比</Button>
            <Can permission={PERMISSION_CODE.knowledgeCreate}>
              <Button type="primary" onClick={() => setCreating(true)}>
                新建实验
              </Button>
            </Can>
          </Space>
        }
      />
      {compareHint ? <Alert className="mb-3" type="warning" showIcon message={compareHint} /> : null}
      <ListToolbar>
        <Space wrap>
          <Select
            allowClear
            placeholder="筛选数据集"
            style={{ width: 220 }}
            value={datasetId}
            onChange={(value) => {
              setDatasetId(value);
              setPage(1);
            }}
            options={(datasetsQuery.data?.items ?? []).map((item) => ({ value: item.id, label: item.name }))}
          />
          <Select
            allowClear
            placeholder="运行状态"
            style={{ width: 140 }}
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={RUN_STATUS_FILTERS.map((value) => ({ value, label: knowledgeRunStatusLabel(value) }))}
          />
          <Select
            allowClear
            placeholder="检索策略"
            style={{ width: 140 }}
            value={strategy}
            onChange={(value) => {
              setStrategy(value);
              setPage(1);
            }}
            options={Object.values(KNOWLEDGE_RETRIEVAL_STRATEGY).map((value) => ({
              value,
              label: knowledgeRetrievalStrategyLabel(value),
            }))}
          />
        </Space>
      </ListToolbar>
      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_minmax(0,1fr)] gap-3 overflow-hidden">
        <ListTableArea>
          <AppTable
            rowKey="id"
            loading={listQuery.isLoading}
            columns={experimentColumns}
            dataSource={listQuery.data?.items ?? []}
            onChange={handleTableChange}
            rowSelection={{
              preserveSelectedRowKeys: true,
              selectedRowKeys: selectedIds,
              onChange: (keys, rows) => {
                const nextKeys = (keys as number[]).slice(0, 3);
                if (keys.length > 3) {
                  message.warning('最多选择 3 个实验对比');
                }
                setSelectedMap((prev) => {
                  const next: Record<number, KnowledgeEvalExperiment> = {};
                  for (const id of nextKeys) {
                    next[id] = rows.find((row) => row.id === id) ?? prev[id];
                  }
                  return next;
                });
              },
            }}
            expandable={{
              expandedRowRender: (record) => {
                const run = record.latest_run;
                return (
                  <Descriptions size="small" column={4} bordered>
                    <Descriptions.Item label="数据集">{datasetName(record.dataset_id)}</Descriptions.Item>
                    <Descriptions.Item label="数据集版本">{run?.dataset_version ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="Vector Top-K">{snapshotParam(record.config, 'vector_k')}</Descriptions.Item>
                    <Descriptions.Item label="Keyword Top-K">{snapshotParam(record.config, 'keyword_k')}</Descriptions.Item>
                    <Descriptions.Item label="RRF k">{snapshotParam(record.config, 'rrf_k')}</Descriptions.Item>
                    <Descriptions.Item label="候选召回">{snapshotParam(record.config, 'candidate_k')}</Descriptions.Item>
                    <Descriptions.Item label="相似度阈值">{snapshotParam(record.config, 'similarity_threshold')}</Descriptions.Item>
                    <Descriptions.Item label="Embedding">{snapshotParam(record.config, 'embedding_model')}</Descriptions.Item>
                    <Descriptions.Item label="维度">{snapshotParam(record.config, 'embedding_dimensions')}</Descriptions.Item>
                    <Descriptions.Item label="Chat">{snapshotParam(record.config, 'chat_model')}</Descriptions.Item>
                    <Descriptions.Item label="指标版本">{snapshotParam(record.config, 'metric_version')}</Descriptions.Item>
                    <Descriptions.Item label="生成评测">{snapshotParam(record.config, 'evaluate_generation')}</Descriptions.Item>
                    <Descriptions.Item label="有效题 / 总题">
                      {formatEvalCount(run?.supervised_count)} / {formatEvalCount(run?.case_count)}
                    </Descriptions.Item>
                    <Descriptions.Item label="无答案题">{formatEvalCount(run?.unanswerable_count)}</Descriptions.Item>
                    <Descriptions.Item label="最近运行">{run ? `#${run.id}` : '尚未运行'}</Descriptions.Item>
                    <Descriptions.Item label="失败原因">{run?.error_message || '-'}</Descriptions.Item>
                  </Descriptions>
                );
              },
            }}
            pagination={{
              current: page,
              pageSize,
              total: listQuery.data?.total ?? 0,
            }}
          />
        </ListTableArea>
        <ListTableArea>
          <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
            <span className="text-sm text-slate-600">运行记录</span>
            <Select
              allowClear
              placeholder="运行状态"
              style={{ width: 140 }}
              value={runsStatus}
              onChange={(value) => {
                setRunsStatus(value);
                setRunsPage(1);
              }}
              options={RUN_RECORD_STATUS_FILTERS.map((value) => ({
                value,
                label: knowledgeRunStatusLabel(value),
              }))}
            />
          </div>
          <AppTable
            rowKey="id"
            loading={runsQuery.isLoading}
            columns={runColumns}
            dataSource={runsQuery.data?.items ?? []}
            onChange={handleRunsTableChange}
            expandable={{
              expandedRowRender: (record) => {
                const snapshot = record.config_snapshot;
                const view = evalRunMetrics(record);
                return (
                  <Descriptions size="small" column={4} bordered>
                    <Descriptions.Item label="数据集">{datasetName(record.dataset_id)}</Descriptions.Item>
                    <Descriptions.Item label="数据集版本">{record.dataset_version}</Descriptions.Item>
                    <Descriptions.Item label="Vector Top-K">{snapshotParam(snapshot, 'vector_k')}</Descriptions.Item>
                    <Descriptions.Item label="Keyword Top-K">{snapshotParam(snapshot, 'keyword_k')}</Descriptions.Item>
                    <Descriptions.Item label="RRF k">{snapshotParam(snapshot, 'rrf_k')}</Descriptions.Item>
                    <Descriptions.Item label="候选召回">{snapshotParam(snapshot, 'candidate_k')}</Descriptions.Item>
                    <Descriptions.Item label="相似度阈值">{snapshotParam(snapshot, 'similarity_threshold')}</Descriptions.Item>
                    <Descriptions.Item label="Embedding">{snapshotParam(snapshot, 'embedding_model')}</Descriptions.Item>
                    <Descriptions.Item label="维度">{snapshotParam(snapshot, 'embedding_dimensions')}</Descriptions.Item>
                    <Descriptions.Item label="Rerank 模型">{snapshotParam(snapshot, 'rerank_model')}</Descriptions.Item>
                    <Descriptions.Item label="Chat">{snapshotParam(snapshot, 'chat_model')}</Descriptions.Item>
                    <Descriptions.Item label="指标版本">{snapshotParam(snapshot, 'metric_version')}</Descriptions.Item>
                    <Descriptions.Item label="生成评测">{snapshotParam(snapshot, 'evaluate_generation')}</Descriptions.Item>
                    <Descriptions.Item label="有效题 / 总题">
                      {formatEvalCount(view.supervised_count)} / {formatEvalCount(view.case_count)}
                    </Descriptions.Item>
                    <Descriptions.Item label="尝试次数">{record.attempt}</Descriptions.Item>
                    <Descriptions.Item label="中断原因">
                      {knowledgeEvalInterruptLabel(record.interrupt_reason) || record.error_message || '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label="进度">{evalRunProgressText(record) || '-'}</Descriptions.Item>
                    <Descriptions.Item label="Token 预算">{record.token_budget ?? '未限制'}</Descriptions.Item>
                    <Descriptions.Item label="已消耗 Token">
                      {(usageNumber(record.usage, 'prompt_tokens') ?? 0) +
                        (usageNumber(record.usage, 'completion_tokens') ?? 0)}
                      {record.usage?.token_estimated === true ? '（估算）' : ''}
                    </Descriptions.Item>
                    <Descriptions.Item label="已消耗费用">
                      {usageNumber(record.usage, 'estimated_cost_usd') == null
                        ? '无数据'
                        : `$${usageNumber(record.usage, 'estimated_cost_usd')}`}
                    </Descriptions.Item>
                  </Descriptions>
                );
              },
            }}
            pagination={{
              current: runsPage,
              pageSize: runsPageSize,
              total: runsQuery.data?.total ?? 0,
            }}
          />
        </ListTableArea>
      </div>
      <Drawer title="创建实验" open={creating} onClose={() => setCreating(false)} width={480}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            strategy: 'HYBRID',
            top_k: defaults?.default_top_k ?? 8,
            candidate_k: defaults?.default_candidate_k ?? 24,
            rrf_k: defaults?.rrf_k ?? 60,
            rerank: false,
            evaluate_generation: false,
          }}
          onFinish={(values) =>
            createMutation.mutate({
              dataset_id: values.dataset_id,
              name: values.name.trim(),
              description: values.description,
              config: {
                strategy: values.strategy,
                top_k: values.top_k,
                candidate_k: values.candidate_k,
                vector_k: values.vector_k,
                keyword_k: values.keyword_k,
                rrf_k: values.rrf_k,
                similarity_threshold: values.similarity_threshold,
                rerank: values.rerank,
                evaluate_generation: values.evaluate_generation,
                token_budget: values.token_budget,
                cost_budget_usd: values.cost_budget_usd,
              },
            })
          }
        >
          <Form.Item name="dataset_id" label="数据集" rules={[{ required: true }]}>
            <Select options={(datasetsQuery.data?.items ?? []).map((item) => ({ value: item.id, label: `${item.name}（可评测 ${item.ready_count}）` }))} />
          </Form.Item>
          <Form.Item name="name" label="实验名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="strategy" label="检索策略">
            <Select options={Object.values(KNOWLEDGE_RETRIEVAL_STRATEGY).map((value) => ({ value, label: knowledgeRetrievalStrategyLabel(value) }))} />
          </Form.Item>
          <Form.Item name="top_k" label={defaults ? <FormLabelHelp label="最终 Top-K">{topKHelp(defaults)}</FormLabelHelp> : '最终 Top-K'}>
            <InputNumber min={1} max={50} className="w-full" />
          </Form.Item>
          <Form.Item name="vector_k" label={defaults ? <FormLabelHelp label="Vector Top-K">{vectorTopKHelp(defaults)}</FormLabelHelp> : 'Vector Top-K'}>
            <InputNumber min={1} max={100} className="w-full" />
          </Form.Item>
          <Form.Item name="keyword_k" label={defaults ? <FormLabelHelp label="Keyword Top-K">{keywordTopKHelp(defaults)}</FormLabelHelp> : 'Keyword Top-K'}>
            <InputNumber min={1} max={100} className="w-full" />
          </Form.Item>
          <Form.Item name="rrf_k" label={defaults ? <FormLabelHelp label="RRF k">{rrfKHelp(defaults)}</FormLabelHelp> : 'RRF k'}>
            <InputNumber min={1} max={200} className="w-full" />
          </Form.Item>
          <Form.Item name="candidate_k" label={defaults ? <FormLabelHelp label="候选召回数">{candidateKHelp(defaults)}</FormLabelHelp> : '候选召回数'}>
            <InputNumber min={1} max={100} className="w-full" />
          </Form.Item>
          <Form.Item
            name="similarity_threshold"
            label={defaults ? <FormLabelHelp label="向量相似度阈值">{similarityThresholdHelp(defaults)}</FormLabelHelp> : '向量相似度阈值'}
          >
            <InputNumber min={0} max={1} step={0.05} className="w-full" />
          </Form.Item>
          <Form.Item name="rerank" label={defaults ? <FormLabelHelp label="Rerank">{rerankHelp(defaults)}</FormLabelHelp> : 'Rerank'} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="evaluate_generation" label="生成质量评测（产生模型费用）" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="token_budget" label="Token 预算（可在恢复前上调）">
            <InputNumber min={0} className="w-full" placeholder="空则使用服务默认值" />
          </Form.Item>
          <Form.Item name="cost_budget_usd" label="费用预算 USD（可选）">
            <InputNumber min={0} step={0.01} className="w-full" placeholder="空表示不限制" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
            保存参数方案
          </Button>
        </Form>
      </Drawer>
      <Drawer title={`运行 #${activeRun?.id ?? ''}`} open={activeRun != null} width={720} onClose={() => setActiveRun(null)}>
        {activeRun ? (
          <div className="space-y-4">
            <Space wrap>
              <Tag color={knowledgeRunStatusColor(activeRun.status)}>{knowledgeRunStatusLabel(activeRun.status)}</Tag>
              <Tag>数据集版本 {activeRun.dataset_version}</Tag>
              <Tag>{knowledgeRetrievalStrategyLabel(String(activeRun.config_snapshot.strategy ?? ''))}</Tag>
              {activeRun.dataset_snapshot_meta.comparable === false ? <Tag color="warning">含失效标注，非严格可比</Tag> : null}
              <Tag>最终 Top-K {snapshotParam(activeRun.config_snapshot, 'top_k')}</Tag>
              <Tag>Vector {snapshotParam(activeRun.config_snapshot, 'vector_k')}</Tag>
              <Tag>Keyword {snapshotParam(activeRun.config_snapshot, 'keyword_k')}</Tag>
              <Tag>RRF k {snapshotParam(activeRun.config_snapshot, 'rrf_k')}</Tag>
              <Tag>候选 {snapshotParam(activeRun.config_snapshot, 'candidate_k')}</Tag>
              <Tag>Rerank {snapshotParam(activeRun.config_snapshot, 'rerank')}</Tag>
            </Space>
            {evalRunProgressText(activeRun) ? <div className="text-sm text-slate-600">{evalRunProgressText(activeRun)}</div> : null}
            {activeRun.interrupt_reason || activeRun.error_message ? (
              <div className="text-sm text-amber-700">
                中断原因：{knowledgeEvalInterruptLabel(activeRun.interrupt_reason) || activeRun.error_message}
              </div>
            ) : null}
            <div className="text-xs text-slate-500">
              Token {(usageNumber(activeRun.usage, 'prompt_tokens') ?? 0) + (usageNumber(activeRun.usage, 'completion_tokens') ?? 0)}
              {activeRun.token_budget != null ? ` / ${activeRun.token_budget}` : ''}
              {activeRun.usage?.token_estimated === true ? '（估算）' : ''}
              {usageNumber(activeRun.usage, 'estimated_cost_usd') != null
                ? ` · 费用 $${usageNumber(activeRun.usage, 'estimated_cost_usd')}`
                : ''}
            </div>
            <MetricBars
              items={[
                { label: 'Hit Rate', value: metricNumber(activeRun.metrics, 'hit_rate') },
                { label: 'Recall', value: metricNumber(activeRun.metrics, 'recall') },
                { label: 'Precision', value: metricNumber(activeRun.metrics, 'precision') },
                { label: 'MRR', value: metricNumber(activeRun.metrics, 'mrr') },
                { label: 'nDCG', value: metricNumber(activeRun.metrics, 'ndcg') },
              ]}
            />
            <div className="text-xs text-slate-500">粒度：Chunk。LLM Judge 具有主观性与波动，失败时不会伪造分数。</div>
            <AppTable
              rowKey="id"
              fillHeight={false}
              columns={resultColumns}
              dataSource={resultsQuery.data ?? []}
              pagination={false}
            />
          </div>
        ) : null}
      </Drawer>
      <Drawer title="单题评测结果" open={activeResult != null} width={880} onClose={() => setActiveResult(null)}>
        {activeResult ? (
          <EvalCaseResultPanel
            view={{
              question: activeResult.question,
              expected_answer: activeResult.expected_answer,
              answer: activeResult.answer,
              is_unanswerable: activeResult.is_unanswerable,
              error_message: activeResult.error_message,
              judge_error: activeResult.judge_error,
              retrieval_metrics: activeResult.retrieval_metrics,
              generation_metrics: activeResult.generation_metrics,
              retrieved: activeResult.retrieved,
              latency_ms: activeResult.latency_ms,
              usage: activeResult.usage,
              stages: activeResult.stages,
              strategy: activeRun ? String(activeRun.config_snapshot.strategy ?? '') : null,
              raw: activeResult,
            }}
          />
        ) : null}
      </Drawer>
      <Modal
        title={`继续运行 #${resumeTarget?.id ?? ''}`}
        open={resumeTarget != null}
        onCancel={() => setResumeTarget(null)}
        onOk={() =>
          resumeForm.validateFields().then((values) => {
            if (!resumeTarget) {
              return;
            }
            return resumeEvalRun(resumeTarget.id, {
              token_budget: values.token_budget,
              cost_budget_usd: values.cost_budget_usd,
            })
              .then((run) => {
                message.success('已在同一 Run 继续');
                setResumeTarget(null);
                setActiveRun(run);
                invalidate();
              })
              .catch((error: Error) => message.error(error.message));
          })
        }
        okText="继续运行"
      >
        <p className="mb-3 text-sm text-slate-600">
          将保留已完成题目和阶段结果，不会新建实验。检索配置与数据集快照不可改，仅允许调整本次运行预算。
        </p>
        <Form form={resumeForm} layout="vertical">
          <Form.Item name="token_budget" label="Token 预算">
            <InputNumber min={0} className="w-full" />
          </Form.Item>
          <Form.Item name="cost_budget_usd" label="费用预算 USD">
            <InputNumber min={0} step={0.01} className="w-full" />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageContainer>
  );
}
