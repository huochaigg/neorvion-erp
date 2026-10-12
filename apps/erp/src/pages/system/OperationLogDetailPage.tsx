import { OPERATION_RESULT_LABEL, operationLogQueryKey } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Descriptions, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchOperationLog } from '@/api/operation-logs';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function OperationLogDetailPage(_props: PageProps) {
  const { logId = '' } = useParams();
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const id = Number(logId);
  const query = useQuery({
    queryKey: operationLogQueryKey(tenantId, Number.isFinite(id) ? id : null),
    queryFn: ({ signal }) => fetchOperationLog(id, signal),
    enabled: tenantId != null && Number.isFinite(id),
  });
  const log = query.data;

  return (
    <FormPageContainer>
      <PageHeader
        title="操作日志详情"
        extra={<Button onClick={() => navigate('/system/operation-logs')}>返回列表</Button>}
      />
      {log ? (
        <>
          <Descriptions bordered size="small" column={2} className="mb-4">
            <Descriptions.Item label="时间">{formatDateTime(log.occurred_at)}</Descriptions.Item>
            <Descriptions.Item label="操作人">{log.operator_user_id ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="模块">{log.module}</Descriptions.Item>
            <Descriptions.Item label="动作">{log.action}</Descriptions.Item>
            <Descriptions.Item label="资源">
              {log.resource_name || `${log.resource_type ?? '-'}${log.resource_id ? `#${log.resource_id}` : ''}`}
            </Descriptions.Item>
            <Descriptions.Item label="结果">
              <Tag color={log.result === 'SUCCESS' ? 'green' : 'red'}>
                {OPERATION_RESULT_LABEL[log.result] ?? log.result}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="请求 ID">{log.request_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="请求">
              {log.request_method ? `${log.request_method} ${log.request_path ?? ''}` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="描述" span={2}>
              {log.description || '-'}
            </Descriptions.Item>
          </Descriptions>
          <pre className="overflow-auto rounded bg-neutral-50 p-3 text-xs">
            {JSON.stringify(log.metadata ?? {}, null, 2)}
          </pre>
        </>
      ) : null}
    </FormPageContainer>
  );
}
