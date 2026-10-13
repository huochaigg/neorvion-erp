import {
  ApiError,
  KNOWLEDGE_BASE_STATUS,
  knowledgeBaseQueryKey,
  knowledgeBaseStatusLabel,
  PERMISSION_CODE,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Empty, Result, Space, Spin, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchKnowledgeBase } from '@/api/knowledge-bases';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

export function KnowledgeBaseDetailPage() {
  const { id } = useParams();
  const knowledgeBaseId = Number(id);
  const navigate = useNavigate();
  const { tenantId } = usePermissions();
  const detailQuery = useQuery({
    queryKey: knowledgeBaseQueryKey(tenantId, Number.isFinite(knowledgeBaseId) ? knowledgeBaseId : null),
    queryFn: ({ signal }) => fetchKnowledgeBase(knowledgeBaseId, signal),
    enabled: tenantId != null && Number.isFinite(knowledgeBaseId),
  });

  if (!Number.isFinite(knowledgeBaseId)) {
    return <Result status="404" title="知识库不存在" extra={<Button onClick={() => navigate('/bases')}>返回列表</Button>} />;
  }

  if (detailQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spin />
      </div>
    );
  }

  if (detailQuery.isError) {
    const error = detailQuery.error;
    const forbidden = error instanceof ApiError && error.status === 403;
    const missing = error instanceof ApiError && error.status === 404;
    return (
      <Result
        status={forbidden ? '403' : missing ? '404' : 'error'}
        title={forbidden ? '无权限' : missing ? '知识库不存在或不可访问' : '加载失败'}
        subTitle={error instanceof ApiError ? error.message : '请稍后重试'}
        extra={<Button onClick={() => navigate('/bases')}>返回列表</Button>}
      />
    );
  }

  const item = detailQuery.data;
  if (!item) {
    return <Empty description="暂无数据" />;
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageHeader
        title={item.name}
        description="知识库基础资料。文档上传与解析属于 V2，当前不会出现假的上传成功。"
        extra={
          <Space>
            <Button onClick={() => navigate('/bases')}>返回列表</Button>
            <Can permission={PERMISSION_CODE.knowledgeUpdate}>
              <Button type="primary" onClick={() => navigate('/bases')}>
                去列表编辑
              </Button>
            </Can>
          </Space>
        }
      />
      <Card>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="名称">{item.name}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={item.status === KNOWLEDGE_BASE_STATUS.active ? 'success' : 'default'}>
              {knowledgeBaseStatusLabel(item.status)}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>
            {item.description || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="文档数量">{item.document_count}</Descriptions.Item>
          <Descriptions.Item label="所属企业 ID">{item.tenant_id}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDateTime(item.created_at)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{formatDateTime(item.updated_at)}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card className="mt-4" title="文档">
        <Alert
          type="info"
          showIcon
          title="文档功能将在 V2 提供"
          description="当前版本只展示文档数量，不提供上传、解析或检索。禁用状态的知识库也不会进入未来的普通检索。"
        />
        {item.document_count === 0 ? <Empty className="mt-6" description="暂无文档" /> : null}
      </Card>
    </div>
  );
}
