import {
  currentUserQueryKey,
  ERP_BASENAME,
  ERP_DEFAULT_PATH,
  healthQueryKey,
  listUsableTenants,
  myTenantsQueryKey,
  tenantMembersQueryKey,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Col, Row, Space, Spin, Table, Tag, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { fetchCurrentUser } from '@/api/auth';
import { fetchHealth } from '@/api/health';
import { fetchMyTenants, fetchTenantMembers } from '@/api/tenants';
import { useAuthStore } from '@/stores/auth-store';
import { useTenantStore } from '@/stores/tenant-store';

const { Title, Paragraph, Text } = Typography;

function statusColor(status: string) {
  return status === 'ok' ? 'success' : 'error';
}

export function HomePage() {
  const tenantId = useTenantStore((state) => state.currentTenantId);
  const accessToken = useAuthStore((state) => state.accessToken);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: healthQueryKey(tenantId),
    queryFn: ({ signal }) => fetchHealth(signal),
    retry: false,
  });
  const { data: currentUser } = useQuery({
    queryKey: currentUserQueryKey(),
    queryFn: fetchCurrentUser,
    enabled: Boolean(accessToken),
  });
  const { data: tenants } = useQuery({
    queryKey: myTenantsQueryKey(),
    queryFn: ({ signal }) => fetchMyTenants(signal),
    enabled: Boolean(accessToken),
  });
  const { data: members, isLoading: membersLoading } = useQuery({
    queryKey: tenantMembersQueryKey(tenantId),
    queryFn: ({ signal }) => fetchTenantMembers(tenantId as number, signal),
    enabled: tenantId != null,
  });

  const currentTenant = listUsableTenants(tenants ?? []).find((item) => item.id === tenantId);

  return (
    <div className="p-6">
      <Title level={3} className="!mb-2">
        主应用工作台
      </Title>
      <Paragraph className="text-slate-500">
        当前用户：{currentUser?.display_name ?? '加载中'}（{currentUser?.email ?? '-'}）。当前企业：
        {currentTenant ? `${currentTenant.name}（${currentTenant.code}）` : tenantId}。ERP
        业务请从左侧进入；切换企业不会重新登录。
      </Paragraph>
      <Space className="mb-4" wrap>
        <Link to={`${ERP_BASENAME}${ERP_DEFAULT_PATH}`}>
          <Button type="primary">打开 ERP 工作台</Button>
        </Link>
        <Link to={`${ERP_BASENAME}/orders`}>
          <Button>打开 ERP 订单</Button>
        </Link>
      </Space>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="后端健康检查" extra={<Text type="secondary">GET /api/v1/health</Text>}>
            {isLoading ? <Spin /> : null}
            {isError ? (
              <Alert
                type="warning"
                showIcon
                title="暂时无法连接 FastAPI"
                description={error instanceof Error ? error.message : '请先启动 backend（端口 8011）'}
              />
            ) : null}
            {data ? (
              <div className="flex flex-wrap gap-2">
                <Tag color={statusColor(data.app)}>App {data.app}</Tag>
                <Tag color={statusColor(data.mysql)}>MySQL {data.mysql}</Tag>
                <Tag color={statusColor(data.redis)}>Redis {data.redis}</Tag>
                <Tag>{data.milestone}</Tag>
              </div>
            ) : null}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="当前企业成员">
            <Table
              rowKey="id"
              size="small"
              loading={membersLoading}
              pagination={false}
              dataSource={members}
              columns={[
                { title: '姓名', dataIndex: 'display_name' },
                { title: '邮箱', dataIndex: 'email' },
                { title: '角色', dataIndex: 'role' },
                { title: '状态', dataIndex: 'status' },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
