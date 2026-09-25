import { SHELL_ROUTES } from '@neorvion/shared';
import { App, Button, Card, Form, Input, Typography } from 'antd';
import { Link, useNavigate } from 'react-router-dom';
import { registerAccount } from '@/api/auth';
import { AuthLayout } from '@/layouts/AuthLayout';

interface RegisterFormValues {
  email: string;
  display_name: string;
  password: string;
  confirm: string;
}

export function RegisterPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();

  const onFinish = async (values: RegisterFormValues) => {
    try {
      await registerAccount({
        email: values.email,
        password: values.password,
        display_name: values.display_name,
      });
      message.success('注册成功，请登录');
      navigate(SHELL_ROUTES.login, { replace: true });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '注册失败');
    }
  };

  return (
    <AuthLayout title="创建 Neorvion 账号" description="先完成个人身份注册。租户与权限将在后续版本接入。">
      <Card className="w-full max-w-md shadow-sm" title="注册">
        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            label="邮箱"
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input size="large" autoComplete="email" />
          </Form.Item>
          <Form.Item
            label="显示名称"
            name="display_name"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input size="large" autoComplete="nickname" maxLength={64} />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少 8 位' },
              {
                pattern: /^(?=.*[A-Za-z])(?=.*\d).{8,72}$/,
                message: '密码需 8-72 位，且同时包含字母和数字',
              },
            ]}
          >
            <Input.Password size="large" autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            label="确认密码"
            name="confirm"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator(_, value: string) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password size="large" autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block>
            注册
          </Button>
        </Form>
        <Typography.Paragraph className="!mb-0 mt-4 text-center text-slate-500">
          已有账号？ <Link to={SHELL_ROUTES.login}>返回登录</Link>
        </Typography.Paragraph>
      </Card>
    </AuthLayout>
  );
}
