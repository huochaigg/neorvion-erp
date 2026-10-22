import {
  DEFAULT_PAGE_SIZE,
  knowledgeAnnotationStatusColor,
  knowledgeAnnotationStatusLabel,
  knowledgeEvalVersionsQueryKey,
  knowledgeQuestionTypeLabel,
  PERMISSION_CODE,
  type KnowledgeEvalSnapshotCase,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Drawer, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  compareEvalVersions,
  deleteEvalVersion,
  fetchEvalVersion,
  fetchEvalVersions,
} from '@/api/evaluation';
import { Can } from '@/components/Can';
import { formatDateTime } from '@/lib/datetime';
import { usePermissions } from '@/hooks/usePermissions';

const CHANGE_LABEL: Record<string, string> = {
  ADDED: '新增',
  REMOVED: '删除',
  MODIFIED: '修改',
};

const FIELD_LABEL: Record<string, string> = {
  question: '问题',
  expected_answer: '标准答案',
  question_type: '类型',
  difficulty: '难度',
  tags: '标签',
  is_unanswerable: '无答案',
  annotation_status: '标注状态',
  judgments: 'Ground Truth',
};

function judgmentText(row: KnowledgeEvalSnapshotCase | null): string {
  if (!row?.judgments.length) return '无标注';
  return row.judgments
    .map((item) => `#${item.chunk_id} 相关性 ${item.relevance}${item.stale ? '（失效）' : ''}`)
    .join('；');
}

export function EvaluationDatasetVersionsPanel({
  datasetId,
  focusVersion,
}: {
  datasetId: number;
  focusVersion?: number | null;
}) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [openVersion, setOpenVersion] = useState<number | null>(focusVersion ?? null);
  const [detailPage, setDetailPage] = useState(1);
  const [compareOpen, setCompareOpen] = useState(false);
  const [leftVersion, setLeftVersion] = useState<number | null>(null);
  const [rightVersion, setRightVersion] = useState<number | null>(null);
  const [diffPage, setDiffPage] = useState(1);

  useEffect(() => {
    setPage(1);
    setOpenVersion(focusVersion ?? null);
  }, [tenantId, datasetId, focusVersion]);

  const versionsQuery = useQuery({
    queryKey: knowledgeEvalVersionsQueryKey(tenantId, datasetId, { page, pageSize }),
    queryFn: ({ signal }) => fetchEvalVersions(datasetId, { page, pageSize }, signal),
    enabled: tenantId != null && Number.isFinite(datasetId),
  });

  const pickerQuery = useQuery({
    queryKey: knowledgeEvalVersionsQueryKey(tenantId, datasetId, { page: 1, pageSize: 100 }),
    queryFn: ({ signal }) => fetchEvalVersions(datasetId, { page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null && Number.isFinite(datasetId) && compareOpen,
  });

  const detailQuery = useQuery({
    queryKey: ['tenant', tenantId, 'knowledge-eval-version', datasetId, openVersion, detailPage],
    queryFn: ({ signal }) => fetchEvalVersion(datasetId, openVersion as number, { page: detailPage, pageSize: 20 }, signal),
    enabled: tenantId != null && openVersion != null,
  });

  const diffQuery = useQuery({
    queryKey: ['tenant', tenantId, 'knowledge-eval-version-diff', datasetId, leftVersion, rightVersion, diffPage],
    queryFn: ({ signal }) =>
      compareEvalVersions(
        datasetId,
        { left: leftVersion as number, right: rightVersion as number, page: diffPage, pageSize: 20 },
        signal,
      ),
    enabled: tenantId != null && compareOpen && leftVersion != null && rightVersion != null,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-versions'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-eval-dataset'] });
  };

  const columns: ColumnsType<NonNullable<typeof versionsQuery.data>['items'][number]> = [
    { title: '版本', dataIndex: 'version', width: 80, render: (value: number) => `v${value}` },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    { title: '题目数', dataIndex: 'case_count', width: 90 },
    { title: 'READY', dataIndex: 'ready_count', width: 90 },
    { title: '无答案', dataIndex: 'unanswerable_count', width: 90 },
    { title: '失效标注', dataIndex: 'stale_judgment_count', width: 100 },
    { title: '引用 Run', dataIndex: 'run_count', width: 100 },
    {
      title: '最新',
      dataIndex: 'is_current',
      width: 90,
      render: (value: boolean) => (value ? <Tag color="blue">当前版本</Tag> : '历史'),
    },
    {
      title: '操作',
      width: 160,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setDetailPage(1);
              setOpenVersion(record.version);
            }}
          >
            查看
          </Button>
          <Can permission={PERMISSION_CODE.knowledgeDelete}>
            {record.deletable ? (
              <Popconfirm
                title={`删除冻结快照 v${record.version}？`}
                description="该版本没有评测运行引用。删除后当前最新版本号不会回退。"
                onConfirm={() =>
                  deleteEvalVersion(datasetId, record.version)
                    .then(() => {
                      message.success(`已删除 v${record.version}`);
                      if (openVersion === record.version) setOpenVersion(null);
                      refresh();
                    })
                    .catch((error: Error) => message.error(error.message))
                }
              >
                <Button type="link" size="small" danger>
                  删除
                </Button>
              </Popconfirm>
            ) : (
              <Tooltip title={record.is_current ? '当前最新版本不能删除' : '已有评测运行引用，不能删除'}>
                <Button type="link" size="small" danger disabled>
                  删除
                </Button>
              </Tooltip>
            )}
          </Can>
        </Space>
      ),
    },
  ];

  const detail = detailQuery.data;
  const diff = diffQuery.data;

  return (
    <div className="space-y-3">
      <Alert
        type="info"
        showIcon
        message="这里是历史冻结快照，全部只读。正式评测和断点续跑读取快照，不读取你后来对工作稿的修改。冻结不会锁定工作稿。"
      />
      <div className="flex justify-end mt-3!">
        <Button onClick={() => setCompareOpen(true)}>比较两个版本</Button>
      </div>
      <Table
        rowKey="id"
        size="small"
        loading={versionsQuery.isLoading}
        columns={columns}
        dataSource={versionsQuery.data?.items ?? []}
        pagination={{
          current: page,
          pageSize,
          total: versionsQuery.data?.total ?? 0,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage);
            setPageSize(nextSize);
          },
        }}
      />
      <Drawer
        title={openVersion == null ? '冻结快照' : `冻结快照 v${openVersion}`}
        open={openVersion != null}
        width={860}
        onClose={() => setOpenVersion(null)}
      >
        {detail ? (
          <div className="space-y-3">
            <Alert type="warning" showIcon title={detail.note} />
            <Space wrap className="mt-3!">
              {detail.version.is_current ? <Tag color="blue">当前最新版本</Tag> : <Tag>历史版本</Tag>}
              <Tag>题目 {detail.version.case_count}</Tag>
              <Tag>READY {detail.version.ready_count}</Tag>
              <Tag>引用 Run {detail.version.run_count}</Tag>
              <Tag>知识库 {detail.knowledge_base_ids.join(', ') || '无'}</Tag>
            </Space>
            <Table
              rowKey="id"
              size="small"
              loading={detailQuery.isLoading}
              dataSource={detail.items}
              pagination={{
                current: detailPage,
                pageSize: 20,
                total: detail.total,
                onChange: setDetailPage,
              }}
              expandable={{
                expandedRowRender: (record) => (
                  <div className="text-sm">
                    <div>标准答案：{record.expected_answer || '无'}</div>
                    <div className="mt-1">标注：{judgmentText(record)}</div>
                    {record.judgments.some((item) => item.snippet) ? (
                      <div className="mt-1 text-slate-500">
                        {record.judgments.map((item) => (
                          <div key={item.chunk_id}>
                            #{item.chunk_id} {item.filename || ''} {item.snippet || ''}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ),
              }}
              columns={[
                { title: 'ID', dataIndex: 'id', width: 70 },
                { title: '问题', dataIndex: 'question', ellipsis: true },
                {
                  title: '类型',
                  width: 110,
                  render: (_, record) => knowledgeQuestionTypeLabel(record.question_type || ''),
                },
                {
                  title: '状态',
                  width: 90,
                  render: (_, record) => (
                    <Tag color={knowledgeAnnotationStatusColor(record.annotation_status || '')}>
                      {knowledgeAnnotationStatusLabel(record.annotation_status || '')}
                    </Tag>
                  ),
                },
                {
                  title: '无答案',
                  width: 80,
                  render: (_, record) => (record.is_unanswerable ? '是' : '否'),
                },
                { title: '标注数', width: 80, render: (_, record) => record.judgments.length },
              ]}
            />
          </div>
        ) : null}
      </Drawer>
      <Modal title="比较冻结版本" open={compareOpen} onCancel={() => setCompareOpen(false)} footer={null} width={880}>
        <Space className="mb-3" wrap>
          <Select
            placeholder="左版本"
            style={{ width: 140 }}
            value={leftVersion}
            onChange={(value) => {
              setLeftVersion(value);
              setDiffPage(1);
            }}
            options={(pickerQuery.data?.items ?? []).map((item) => ({ value: item.version, label: `v${item.version}` }))}
          />
          <Select
            placeholder="右版本"
            style={{ width: 140 }}
            value={rightVersion}
            onChange={(value) => {
              setRightVersion(value);
              setDiffPage(1);
            }}
            options={(pickerQuery.data?.items ?? []).map((item) => ({ value: item.version, label: `v${item.version}` }))}
          />
        </Space>
        {diff ? (
          <div className="space-y-3">
            <div className="text-sm">
              相对 v{diff.left_version}，v{diff.right_version} 新增 {diff.added_count}，删除 {diff.removed_count}，修改 {diff.modified_count}，未变化 {diff.unchanged_count}。
            </div>
            <div className="text-xs text-slate-500">{diff.note}</div>
            <Table
              rowKey={(row) => `${row.change}-${row.case_id}`}
              size="small"
              dataSource={diff.items}
              pagination={{ current: diffPage, pageSize: 20, total: diff.total, onChange: setDiffPage }}
              columns={[
                { title: '变化', width: 80, render: (_, row) => CHANGE_LABEL[row.change] || row.change },
                { title: '题目', dataIndex: 'case_id', width: 80 },
                {
                  title: '问题',
                  ellipsis: true,
                  render: (_, row) => row.after?.question || row.before?.question || '-',
                },
                {
                  title: '差异字段',
                  render: (_, row) => (row.fields.length ? row.fields.map((item) => FIELD_LABEL[item] || item).join('、') : '-'),
                },
              ]}
              expandable={{
                expandedRowRender: (row) => (
                  <div className="grid gap-2 text-sm md:grid-cols-2">
                    <div>
                      <div className="font-medium">v{diff.left_version}</div>
                      <div>{row.before?.question || '此版本没有该题'}</div>
                      <div>答案：{row.before?.expected_answer || '无'}</div>
                      <div>标注：{judgmentText(row.before)}</div>
                    </div>
                    <div>
                      <div className="font-medium">v{diff.right_version}</div>
                      <div>{row.after?.question || '此版本没有该题'}</div>
                      <div>答案：{row.after?.expected_answer || '无'}</div>
                      <div>标注：{judgmentText(row.after)}</div>
                    </div>
                  </div>
                ),
              }}
            />
          </div>
        ) : (
          <div className="text-sm text-slate-500">选择左右两个版本后显示题目和标注差异。</div>
        )}
      </Modal>
    </div>
  );
}
