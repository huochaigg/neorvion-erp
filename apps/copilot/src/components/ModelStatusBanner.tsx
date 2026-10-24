import { Alert } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { modelStatus } from '@/api/workflows';

export function ModelStatusBanner(){const q=useQuery({queryKey:['model-status'],queryFn:({signal})=>modelStatus(signal),refetchInterval:30000});const x=q.data;
  if(!x||x.state==='available')return null;
  const text=x.state==='mock'?'当前为 Mock 测试模式，回答不是真实模型':x.state==='unconfigured'?'真实模型未配置':`模型服务异常：${x.detail??'探测失败'}`;
  return <Alert banner showIcon type={x.state==='mock'?'warning':'error'} message={text}/>;
}
