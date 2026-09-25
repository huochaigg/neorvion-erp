import { SHELL_ROUTES } from '@neorvion/shared';
import { App, Button, Card, Form, Input, Typography } from 'antd';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { loginAccount } from '@/api/auth';
import { AuthLayout } from '@/layouts/AuthLayout';
import { useAuthStore } from '@/stores/auth-store';

interface LoginFormValues {
  email: string;
  password: string;
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const { message } = App.useApp();
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const fromState = (location.state as { from?: { pathname: string; search: string } } | null)?.from;
  const fromQuery = params.get('from');
  const redirectTo = fromState ? `${fromState.pathname}${fromState.search}` : (fromQuery ?? SHELL_ROUTES.home);

  const onFinish = async (values: LoginFormValues) => {
    try {
      const tokens = await loginAccount({
        email: values.email,
        password: values.password,
      });
      setAccessToken(tokens.access_token);
      navigate(redirectTo, { replace: true });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登录失败');
    }
  };

  return (
    <AuthLayout title="欢迎回到 Neorvion" description="使用企业账号登录跨境电商 ERP，统一管理商品、库存与订单。">
      <Card className="w-full max-w-md shadow-sm" title="登录">
        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            label="邮箱"
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input size="large" autoComplete="email" placeholder="you@company.com" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password size="large" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block>
            登录
          </Button>
        </Form>
        <Typography.Paragraph className="!mb-0 mt-4 text-center text-slate-500">
          还没有账号？ <Link to={SHELL_ROUTES.register}>立即注册</Link>
        </Typography.Paragraph>
      </Card>
    </AuthLayout>
  );
}
