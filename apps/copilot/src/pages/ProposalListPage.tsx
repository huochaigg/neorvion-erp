import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Empty, Skeleton } from 'antd';
import { listProposals } from '@/api/proposals';
import { listExecutions } from '@/api/executions';
import { ProposalCard } from '@/components/ProposalCard';
import { useCopilotStore } from '@/store';

export function ProposalListPage() {
  const tenantId = useCopilotStore((s) => s.tenantId);
  const client = useQueryClient();
  const query = useQuery({ queryKey:['tenant',tenantId,'action-proposals'], queryFn:({signal})=>listProposals(signal), enabled:tenantId!=null });
  const executions = useQuery({ queryKey:['tenant',tenantId,'action-executions'], queryFn:({signal})=>listExecutions(signal), enabled:tenantId!=null });
  return <div className="copilot-scroll h-full overflow-auto p-6"><div className="mx-auto max-w-[900px]">
    <h1 className="text-xl font-semibold text-[#0F172A]">业务草稿</h1>
    <p className="mb-5 mt-1 text-sm text-[#64748B]">草稿本身不会写入 ERP；只有人工确认、必要审批和最终复核通过后才创建 ERP 草稿单据。</p>
    {query.isPending ? <Skeleton active /> : query.data?.items.length ? <div className="space-y-4">{query.data.items.map((item)=><ProposalCard key={item.id} value={item} initialExecution={executions.data?.items.find((entry)=>entry.proposal_id===item.id && entry.proposal_revision===item.current_revision)} onChanged={()=>void Promise.all([client.invalidateQueries({queryKey:['tenant',tenantId,'action-proposals']}),client.invalidateQueries({queryKey:['tenant',tenantId,'action-executions']})])}/>)}</div> : <Empty description="暂无业务草稿" />}
  </div></div>;
}
