import { listUsableTenants, myTenantsQueryKey, SHELL_ROUTES } from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Empty, Space, Table, Tag, Typography } from 'antd';
import { Link, useNavigate } from 'react-router-dom';
import { fetchMyTenants } from '@/api/tenants';
import { switchTenant } from '@/lib/switch-tenant';
import { useTenantStore } from '@/stores/tenant-store';

const { Title, Paragraph } = Typography;

export function WorkspacesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const currentTenantId = useTenantStore((state) => state.currentTenantId);
  const { data: tenants, isLoading } = useQuery({
    queryKey: myTenantsQueryKey(),
    queryFn: ({ signal }) => fetchMyTenants(signal),
  });

  const usable = listUsableTenants(tenants ?? []);
  const others = (tenants ?? []).filter((item) => !usable.some((active) => active.id === item.id));

  const enterWorkspace = (tenantId: number) => {
    try {
      switchTenant(queryClient, tenantId);
      navigate(SHELL_ROUTES.erp);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '无法进入该企业');
    }
  };

  return (
    <div className="p-6">
      <Title level={3} className="!mb-2">
        选择工作空间
      </Title>
      <Paragraph className="text-slate-500">
        当前登录身份可以加入多家企业。请选择要进入的企业；切换企业不会重新登录。
      </Paragraph>
      <Space className="mb-4">
        <Link to={SHELL_ROUTES.workspaceCreate}>
          <Button type="primary">创建企业</Button>
        </Link>
      </Space>
      <Card title="可进入的企业">
        {usable.length === 0 && !isLoading ? (
          <Empty description="还没有可进入的企业">
            <Link to={SHELL_ROUTES.workspaceCreate}>
              <Button type="primary">创建企业</Button>
            </Link>
          </Empty>
        ) : (
          <Table
            rowKey="id"
            loading={isLoading}
            pagination={false}
            dataSource={usable}
            columns={[
              { title: '企业名称', dataIndex: 'name' },
              { title: '标识', dataIndex: 'code' },
              {
                title: '身份',
                dataIndex: 'my_role',
                render: (role: string, record) => (
                  <Tag color={record.is_owner ? 'gold' : 'blue'}>{role}</Tag>
                ),
              },
              {
                title: '操作',
                render: (_, record) => (
                  <Button
                    type={record.id === currentTenantId ? 'default' : 'primary'}
                    onClick={() => enterWorkspace(record.id)}
                  >
                    {record.id === currentTenantId ? '进入 ERP' : '进入'}
                  </Button>
                ),
              },
            ]}
          />
        )}
      </Card>
      {others.length > 0 ? (
        <Card className="mt-4" title="当前不可用">
          <Table
            rowKey="id"
            pagination={false}
            dataSource={others}
            columns={[
              { title: '企业名称', dataIndex: 'name' },
              { title: '标识', dataIndex: 'code' },
              { title: '企业状态', dataIndex: 'status' },
              { title: '成员状态', dataIndex: 'my_status' },
            ]}
          />
        </Card>
      ) : null}
    </div>
  );
}
