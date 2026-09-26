import { currentUserQueryKey, ERP_BASENAME, ERP_DEFAULT_PATH, healthQueryKey } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Col, Row, Space, Spin, Tag, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { fetchCurrentUser } from '@/api/auth';
import { fetchHealth } from '@/api/health';
import { useAuthStore } from '@/stores/auth-store';
import { useShellStore } from '@/stores/shell-store';

const { Title, Paragraph, Text } = Typography;

function statusColor(status: string) {
  return status === 'ok' ? 'success' : 'error';
}

export function HomePage() {
  const tenantId = useShellStore((state) => state.currentTenantId);
  const accessToken = useAuthStore((state) => state.accessToken);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: healthQueryKey(tenantId),
    queryFn: fetchHealth,
    retry: false,
  });
  const { data: currentUser } = useQuery({
    queryKey: currentUserQueryKey(),
    queryFn: fetchCurrentUser,
    enabled: Boolean(accessToken),
  });

  return (
    <div className="p-6">
      <Title level={3} className="!mb-2">
        主应用工作台
      </Title>
      <Paragraph className="text-slate-500">
        当前用户：{currentUser?.display_name ?? '加载中'}（{currentUser?.email ?? '-'}）。这是
        Shell 主应用首页，ERP 业务请从左侧「ERP 业务」进入（恢复上次页面）。指定页面可从下方打开。
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
          <Card title="本阶段能力">
            <ul className="m-0 list-disc space-y-1 pl-5 text-sm text-slate-600">
              <li>注册、登录、Refresh Cookie、退出登录</li>
              <li>Access Token 仅保存在内存，刷新页面后自动恢复</li>
              <li>首页 / 只显示主应用工作台，不会打开 ERP</li>
              <li>未登录访问 /erp 会跳转登录并在成功后回到原页面</li>
              <li>ERP 子应用通过 Wujie props 接收 token，不单独做登录页</li>
            </ul>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
