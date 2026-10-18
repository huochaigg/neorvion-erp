import { IAM_BASENAME } from '@neorvion/shared';
import { Card, Col, Row, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import type { PageProps } from '@/router/types';

const { Paragraph } = Typography;

export function DashboardPage(_props: PageProps) {
  return (
    <FormPageContainer>
      <PageHeader title="权限工作台" description="统一管理用户、租户成员、角色、应用注册与审计。菜单隐藏不是安全边界。" />
      <Paragraph className="text-slate-500">
        功能 RBAC 由 IAM 判定；订单归属、文档共享等资源 ACL 仍由各业务服务二次校验。
      </Paragraph>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card title="成员与角色">
            <Link to="/system/members">进入成员管理</Link>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card title="应用注册">
            <Link to="/applications">注册 Copilot 等新应用</Link>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card title="审计">
            <Link to="/audit">查看权限变更</Link>
          </Card>
        </Col>
      </Row>
      <Paragraph className="mt-4 text-slate-400">宿主路径前缀 {IAM_BASENAME}，子应用内部使用上表路径。</Paragraph>
    </FormPageContainer>
  );
}
