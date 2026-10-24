import { Timeline } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { listExecutionAudit } from '@/api/executions';
export function ExecutionAuditTimeline({executionId}:{executionId:number}) {
  const query=useQuery({queryKey:['execution-audit',executionId],queryFn:({signal})=>listExecutionAudit(executionId,signal)});
  return <Timeline items={(query.data?.items??[]).map(x=>({children:<div><b>{x.event_type}</b> · {x.outcome}<div className="text-xs text-[#94A3B8]">{new Date(x.created_at).toLocaleString()}</div></div>}))}/>;
}
