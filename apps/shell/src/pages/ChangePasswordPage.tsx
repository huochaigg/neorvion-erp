import { currentUserQueryKey, SHELL_ROUTES } from '@neorvion/shared';
import { useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Form, Input } from 'antd';
import { useNavigate } from 'react-router-dom';
import { changePassword } from '@/api/auth';
import { AuthLayout } from '@/layouts/AuthLayout';

interface ChangePasswordForm {
  old_password: string;
  new_password: string;
  confirm_password: string;
}

export function ChangePasswordPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  const onFinish = async (values: ChangePasswordForm) => {
    try {
      const profile = await changePassword({
        oldPassword: values.old_password,
        newPassword: values.new_password,
      });
      queryClient.setQueryData(currentUserQueryKey(), profile);
      message.success('密码已更新');
      navigate(SHELL_ROUTES.home, { replace: true });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '修改失败');
    }
  };

  return (
    <AuthLayout title="修改密码" description="使用临时密码登录后必须立即设置自己的密码。">
      <Card className="w-full max-w-md shadow-sm" title="设置新密码">
        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            label="当前密码"
            name="old_password"
            rules={[{ required: true, message: '请输入当前密码' }]}
          >
            <Input.Password size="large" autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            label="新密码"
            name="new_password"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 8, message: '密码长度须为 8-72 位' },
              {
                pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/,
                message: '密码需同时包含字母和数字',
              },
            ]}
          >
            <Input.Password size="large" autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            label="确认新密码"
            name="confirm_password"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value: string) {
                  if (!value || getFieldValue('new_password') === value) {
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
            保存并继续
          </Button>
        </Form>
      </Card>
    </AuthLayout>
  );
}
