import { Card } from 'antd';
import type { WorkflowStep } from '@/types';
import { WorkflowStatus } from './WorkflowStatus';
export function WorkflowStepCard({value}:{value:WorkflowStep}){return <Card size="small" title={<span>{value.step_key} <WorkflowStatus value={value.status}/></span>}><div className="text-xs text-[#64748B]">{value.step_type} · 尝试 {value.attempt_count}</div>{value.error_code&&<div className="mt-2 text-sm text-red-600">错误：{value.error_code}</div>}</Card>}
