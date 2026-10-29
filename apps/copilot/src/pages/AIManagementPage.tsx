import { KNOWLEDGE_BASENAME } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Result, Space, Tabs, Typography } from 'antd';
import { DatabaseZap, Route, ShieldCheck } from 'lucide-react';
import { lazy, Suspense } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getCurrentIdentity } from '@/api/proposals';
import { useCopilotStore } from '@/store';

const EvaluationCenterPage = lazy(() => import('@/pages/EvaluationCenterPage'));
const GovernanceCenterPage = lazy(() => import('@/pages/GovernanceCenterPage'));
const EcosystemManagementPage = lazy(() => import('@/pages/EcosystemManagementPage'));
const { Text, Title } = Typography;

export default function AIManagementPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'evaluation';
  const tenantId = useCopilotStore((s) => s.tenantId);
  const identity = useQuery({
    queryKey: ['tenant', tenantId, 'copilot-current-identity'],
    queryFn: ({ signal }) => getCurrentIdentity(signal),
    enabled: tenantId != null,
  });
  if (identity.isPending) return <Card loading className="m-6" />;
  const evaluationAllowed = identity.data?.permissions.includes('copilot:evaluation:read');
  const governanceAllowed = identity.data?.permissions.includes('copilot:governance:read');
  const ecosystemAllowed = identity.data?.permissions.some((code) =>
    ['copilot:mcp:read', 'copilot:skill:read'].includes(code),
  );
  if (!evaluationAllowed && !governanceAllowed && !ecosystemAllowed)
    return (
      <Result
        status="403"
        title="无权访问 AI 管理中心"
        subTitle="需要 Agent 评测、AI 治理、MCP 或 Skill 读取权限"
      />
    );
  const knowledgeAllowed = Boolean(identity.data?.permissions.includes('knowledge:read'));
  const items = [
    ...(ecosystemAllowed ? [{
      key: 'ecosystem',
      label: 'MCP 与 Skills',
      children: <Suspense fallback={<Card loading />}><EcosystemManagementPage
        canMcpRead={Boolean(identity.data?.permissions.includes('copilot:mcp:read'))}
        canMcpManage={Boolean(identity.data?.permissions.includes('copilot:mcp:manage'))}
        canSkillRead={Boolean(identity.data?.permissions.includes('copilot:skill:read'))}
        canSkillManage={Boolean(identity.data?.permissions.includes('copilot:skill:manage'))}
      /></Suspense>,
    }] : []),
    ...(governanceAllowed ? [{
      key: 'governance',
      label: '企业 AI 治理',
      children: <Suspense fallback={<Card loading />}><GovernanceCenterPage canManage={Boolean(identity.data?.permissions.includes('copilot:governance:manage'))} /></Suspense>,
    }] : []),
    ...(evaluationAllowed ? [
    {
      key: 'evaluation',
      label: 'Agent 任务评测',
      children: (
        <Suspense fallback={<Card loading />}>
          <EvaluationCenterPage />
        </Suspense>
      ),
    },
    ] : []),
    ...(knowledgeAllowed
      ? [
          {
            key: 'knowledge',
            label: '知识检索评测',
            children: (
              <Card>
                <Space direction="vertical" size="middle">
                  <DatabaseZap size={28} className="text-indigo-600" />
                  <Title level={4} className="!mb-0">
                    Knowledge 检索评测
                  </Title>
                  <Text type="secondary">
                    通过 Shell 已注册的 Knowledge 微前端打开，继续使用 Knowledge
                    自身权限和租户上下文。
                  </Text>
                  <Button type="primary" href={`${KNOWLEDGE_BASENAME}/datasets`} target="_top">
                    进入知识检索评测
                  </Button>
                </Space>
              </Card>
            ),
          },
        ]
      : []),
    {
      key: 'trace',
      label: '运行追踪',
      children: (
        <Card>
          <Space direction="vertical">
            <Route size={28} className="text-indigo-600" />
            <Title level={4} className="!mb-0">
              Agent 运行追踪
            </Title>
            <Text type="secondary">
              Trace Viewer 位于 Agent 任务评测的 Trace 页签，展示 AgentRun、ModelCall、ToolRun 与
              Evidence，不展示隐藏思维过程。
            </Text>
            <Button disabled={!evaluationAllowed} onClick={() => setParams({ tab: 'evaluation' })}>打开 Agent 评测</Button>
          </Space>
        </Card>
      ),
    },
    {
      key: 'security',
      label: '安全说明',
      children: (
        <Card>
          <Space direction="vertical">
            <ShieldCheck size={28} className="text-emerald-600" />
            <Text>所有管理接口继续由服务端 IAM 权限和租户隔离保护；隐藏菜单不是授权边界。</Text>
          </Space>
        </Card>
      ),
    },
  ];
  return (
    <div className="copilot-scroll h-full overflow-y-auto p-4 md:p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-4">
          <Title level={3} className="!mb-1">
            AI 管理中心
          </Title>
          <Text type="secondary">面向授权管理员和开发测试人员的评测、运行追踪与安全治理入口。</Text>
        </div>
        <Alert
          className="mb-4"
          type="info"
          showIcon
          message="两套评测保持独立"
          description="Agent 评测关注任务、工具、证据与安全；Knowledge 评测关注检索、重排与 Recall/MRR/nDCG。这里只统一入口，不合并数据库或 Runner。"
        />
        <Tabs
          activeKey={items.some((item) => item.key === tab) ? tab : (ecosystemAllowed ? 'ecosystem' : governanceAllowed ? 'governance' : 'evaluation')}
          onChange={(value) => setParams({ tab: value })}
          items={items}
        />
      </div>
    </div>
  );
}
