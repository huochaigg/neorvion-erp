import { healthQueryKey } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Col, Row, Spin, Tag, Typography } from 'antd';
import { fetchHealth } from '@/api/health';
import { useShellStore } from '@/stores/shell-store';

const { Title, Paragraph, Text } = Typography;

function statusColor(status: string) {
  return status === 'ok' ? 'success' : 'error';
}

export function HomePage() {
  const tenantId = useShellStore((state) => state.currentTenantId);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: healthQueryKey(tenantId),
    queryFn: fetchHealth,
    retry: false,
  });

  return (
    <div className="p-6">
      <Title level={3} className="!mb-2">
        Neorvion ERP 工作台
      </Title>
      <Paragraph className="text-slate-500">
        M1 完成主应用、ERP 微前端、FastAPI 与本地基础设施骨架。业务能力从 M2 开始接入。
      </Paragraph>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="后端健康检查" extra={<Text type="secondary">GET /api/v1/health</Text>}>
            {isLoading ? <Spin /> : null}
            {isError ? (
              <Alert
                type="warning"
                showIcon
                title="暂时无法连接 FastAPI"
                description={error instanceof Error ? error.message : '请先启动 backend（端口 8001）'}
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
              <li>主应用统一导航、登录占位、租户占位</li>
              <li>无界接入 ERP，支持 /erp 深链接与刷新</li>
              <li>ERP 子应用可独立运行于 5174 端口</li>
              <li>Tailwind + SCSS Modules 共存，Ant Design 走 Design Token</li>
            </ul>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
