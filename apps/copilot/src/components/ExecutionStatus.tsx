import { Tag } from 'antd';
import type { ExecutionStatus as Status } from '@/types';
const colors:Record<Status,string>={PENDING_CONFIRMATION:'gold',WAITING_APPROVAL:'orange',APPROVED:'cyan',EXECUTING:'processing',SUCCEEDED:'green',FAILED:'red',UNKNOWN:'purple',RECONCILING:'processing',REJECTED:'red',CANCELLED:'default',EXPIRED:'default'};
const labels:Record<Status,string>={PENDING_CONFIRMATION:'待确认',WAITING_APPROVAL:'待审批',APPROVED:'已批准待执行',EXECUTING:'执行中',SUCCEEDED:'已成功',FAILED:'执行失败',UNKNOWN:'正在确认 ERP 实际结果',RECONCILING:'对账中',REJECTED:'已拒绝',CANCELLED:'已取消',EXPIRED:'已过期'};
export function ExecutionStatus({value}:{value:Status}) { return <Tag color={colors[value]}>{labels[value]}</Tag>; }
