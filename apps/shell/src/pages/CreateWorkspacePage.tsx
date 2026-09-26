import { myTenantsQueryKey, SHELL_ROUTES, type Tenant } from '@neorvion/shared';
import { useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Form, Input, Typography } from 'antd';
import { Link, useNavigate } from 'react-router-dom';
import { createTenant } from '@/api/tenants';
import { switchTenant } from '@/lib/switch-tenant';

const { Title, Paragraph } = Typography;

interface CreateWorkspaceValues {
  name: string;
  code?: string;
}

export function CreateWorkspacePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  const onFinish = async (values: CreateWorkspaceValues) => {
    try {
      const tenant = await createTenant({
        name: values.name,
        code: values.code?.trim() ? values.code.trim() : undefined,
      });
      queryClient.setQueryData<Tenant[]>(myTenantsQueryKey(), (list = []) =>
        list.some((item) => item.id === tenant.id) ? list : [...list, tenant],
      );
      await queryClient.invalidateQueries({ queryKey: myTenantsQueryKey() });
      await queryClient.refetchQueries({ queryKey: myTenantsQueryKey() });
      switchTenant(queryClient, tenant.id);
      message.success('企业已创建');
      navigate(`${SHELL_ROUTES.erp}/dashboard`, { replace: true });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建失败');
    }
  };

  return (
    <div className="p-6">
      <Title level={3} className="!mb-2">
        创建企业
      </Title>
      <Paragraph className="text-slate-500">
        创建后会自动把你写成该企业的 OWNER，并进入 ERP 工作台。本接口不要求事先选中租户。
      </Paragraph>
      <Card className="max-w-xl">
        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            label="企业名称"
            name="name"
            rules={[
              { required: true, message: '请输入企业名称' },
              { max: 64, message: '名称不能超过 64 个字符' },
            ]}
          >
            <Input size="large" placeholder="例如：南半球货代" />
          </Form.Item>
          <Form.Item
            label="企业标识（可选）"
            name="code"
            extra="不填则由服务端生成。如填写：以小写字母开头，只能包含小写字母、数字和连字符。"
            rules={[
              { max: 32, message: '标识不能超过 32 个字符' },
              {
                pattern: /^(?:[a-z][a-z0-9-]{1,31})?$/,
                message: '标识需以小写字母开头，只能包含小写字母、数字和连字符',
              },
            ]}
          >
            <Input size="large" placeholder="acme-logistics" />
          </Form.Item>
          <SpaceActions />
        </Form>
      </Card>
    </div>
  );
}

function SpaceActions() {
  return (
    <div className="flex gap-3">
      <Button type="primary" htmlType="submit" size="large">
        创建并进入
      </Button>
      <Link to={SHELL_ROUTES.workspaces}>
        <Button size="large">返回选择</Button>
      </Link>
    </div>
  );
}
