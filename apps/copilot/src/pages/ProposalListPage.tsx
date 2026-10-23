import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Empty, Skeleton } from 'antd';
import { listProposals } from '@/api/proposals';
import { ProposalCard } from '@/components/ProposalCard';
import { useCopilotStore } from '@/store';

export function ProposalListPage() {
  const tenantId = useCopilotStore((s) => s.tenantId);
  const client = useQueryClient();
  const query = useQuery({ queryKey:['tenant',tenantId,'action-proposals'], queryFn:({signal})=>listProposals(signal), enabled:tenantId!=null });
  return <div className="copilot-scroll h-full overflow-auto p-6"><div className="mx-auto max-w-[900px]">
    <h1 className="text-xl font-semibold text-[#0F172A]">业务草稿</h1>
    <p className="mb-5 mt-1 text-sm text-[#64748B]">这里的内容均未写入 ERP 正式业务表。</p>
    {query.isPending ? <Skeleton active /> : query.data?.items.length ? <div className="space-y-4">{query.data.items.map((item)=><ProposalCard key={item.id} value={item} onChanged={()=>void client.invalidateQueries({queryKey:['tenant',tenantId,'action-proposals']})}/>)}</div> : <Empty description="暂无业务草稿" />}
  </div></div>;
}
