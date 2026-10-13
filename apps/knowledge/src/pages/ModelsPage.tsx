import { knowledgeModelsQueryKey, PERMISSION_CODE, type KnowledgeModelProfile } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { fetchModels, testModel } from '@/api/rag';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

const KIND_LABEL: Record<string, string> = {
  CHAT: '对话',
  EMBEDDING: '向量',
  RERANK: '重排序',
};

export function ModelsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const query = useQuery({
    queryKey: knowledgeModelsQueryKey(tenantId),
    queryFn: ({ signal }) => fetchModels(signal),
    enabled: tenantId != null,
  });

  const testMutation = useMutation({
    mutationFn: testModel,
    onSuccess: (row) => {
      message.success(row.last_test_ok ? `${row.kind} 连通正常` : '测试完成');
      void queryClient.invalidateQueries({ queryKey: knowledgeModelsQueryKey(tenantId) });
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeModelProfile> = [
    { title: '类型', dataIndex: 'kind', width: 90, render: (value: string) => KIND_LABEL[value] ?? value },
    { title: '名称', dataIndex: 'name' },
    { title: '供应商', dataIndex: 'provider', width: 140 },
    { title: '模型', dataIndex: 'model_name' },
    { title: '维度', dataIndex: 'dimensions', width: 80, render: (value: number | null) => value ?? '-' },
    { title: '密钥环境变量', dataIndex: 'api_key_env', width: 180 },
    {
      title: '已配置密钥',
      dataIndex: 'has_api_key',
      width: 110,
      render: (value: boolean) => <Tag color={value ? 'success' : 'default'}>{value ? '是' : '否'}</Tag>,
    },
    {
      title: '最近测试',
      dataIndex: 'last_tested_at',
      width: 180,
      render: (value: string | null, row) =>
        value ? `${formatDateTime(value)} ${row.last_test_ok ? '成功' : '失败'}` : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      render: (_, row) => (
        <Can permission={PERMISSION_CODE.knowledgeUpdate}>
          <Button type="link" size="small" loading={testMutation.isPending} onClick={() => testMutation.mutate(row.kind)}>
            连通测试
          </Button>
        </Can>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PageHeader
        title="模型配置"
        description="平台级 Chat / Embedding / Rerank 来自服务端环境变量。密钥不会返回前端，租户管理员不能覆盖全局密钥。"
      />
      <Card size="small" className="min-h-0 flex-1 overflow-hidden">
        <Table
          rowKey={(row) => `${row.kind}-${row.id ?? 'env'}`}
          size="small"
          loading={query.isLoading}
          pagination={false}
          columns={columns}
          dataSource={query.data ?? []}
        />
      </Card>
    </div>
  );
}
