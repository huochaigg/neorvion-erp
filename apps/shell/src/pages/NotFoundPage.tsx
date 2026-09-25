import { Button, Result } from 'antd';
import { useNavigate } from 'react-router-dom';
import { SHELL_ROUTES } from '@neorvion/shared';

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="flex h-full items-center justify-center p-8">
      <Result
        status="404"
        title="页面不存在"
        subTitle="请检查地址，或返回工作台。"
        extra={
          <Button type="primary" onClick={() => navigate(SHELL_ROUTES.home)}>
            返回工作台
          </Button>
        }
      />
    </div>
  );
}
