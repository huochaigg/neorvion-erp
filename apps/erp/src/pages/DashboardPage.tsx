import { healthQueryKey } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Col, Input, Row, Spin, Tag } from 'antd';
import { useState } from 'react';
import { fetchHealth } from '@/api/health';
import { PageHeader } from '@/components/PageHeader';
import { StatusTag } from '@/components/StatusTag';
import { getShellProps } from '@/lib/runtime';
import type { PageProps } from '@/router/types';

export function DashboardPage(props: PageProps) {
  const shellProps = getShellProps();
  const [aliveProbe, setAliveProbe] = useState('');
  const { data, isLoading, isError, error } = useQuery({
    queryKey: healthQueryKey(shellProps.tenantId),
    queryFn: fetchHealth,
    retry: false,
  });

  return (
    <div>
      <PageHeader
        title={props.title ?? '业务工作台'}
        description={props.description ?? 'ERP 子应用已接入。商品、库存、订单等业务页面从 M3 开始实现。'}
        extra={<StatusTag tone="ready">M1 骨架就绪</StatusTag>}
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card title="运行上下文">
            <p className="mb-2 text-sm text-slate-600">
              嵌入模式：{window.__POWERED_BY_WUJIE__ ? '无界子应用' : '独立启动'}
            </p>
            <p className="mb-0 text-sm text-slate-600">
              当前租户：{shellProps.tenantId ?? '尚未接入（M2）'}
            </p>
            <Input
              className="mt-3"
              value={aliveProbe}
              onChange={(event) => setAliveProbe(event.target.value)}
              placeholder="保活探测：输入后离开再回来应仍在"
            />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="API 连通性">
            {isLoading ? <Spin /> : null}
            {isError ? (
              <Alert
                type="warning"
                showIcon
                title="无法连接后端"
                description={error instanceof Error ? error.message : '请启动 FastAPI 8011 端口'}
              />
            ) : null}
            {data ? (
              <div className="flex flex-wrap gap-2">
                <Tag color={data.mysql === 'ok' ? 'success' : 'error'}>MySQL {data.mysql}</Tag>
                <Tag color={data.redis === 'ok' ? 'success' : 'error'}>Redis {data.redis}</Tag>
                <Tag>{data.milestone}</Tag>
              </div>
            ) : null}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
