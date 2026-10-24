import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Empty, List, Result, Skeleton, Tag } from 'antd';
import { useState } from 'react';
import { listApprovals } from '@/api/executions';
import { getCurrentIdentity } from '@/api/proposals';
import { ApprovalDetail } from '@/components/ApprovalDetail';
import type { ActionApproval } from '@/types';
import { useCopilotStore } from '@/store';

export function ApprovalListPage(){const tenantId=useCopilotStore(s=>s.tenantId);const qc=useQueryClient();const [selected,setSelected]=useState<ActionApproval|null>(null);
  const identity=useQuery({queryKey:['tenant',tenantId,'copilot-current-identity'],queryFn:({signal})=>getCurrentIdentity(signal)});
  const allowed=identity.data?.permissions.includes('copilot:approve')??false;
  const query=useQuery({queryKey:['tenant',tenantId,'action-approvals'],queryFn:({signal})=>listApprovals(signal),enabled:allowed,refetchInterval:5000});
  if(identity.isPending)return <div className="p-6"><Skeleton active/></div>; if(!allowed)return <Result status="403" title="无审批权限" subTitle="需要 copilot:approve 权限"/>;
  return <div className="copilot-scroll h-full overflow-auto p-6"><div className="mx-auto max-w-[900px]"><h1 className="text-xl font-semibold">执行审批</h1><p className="mb-5 text-sm text-[#64748B]">申请人与审批人必须分离；批准后仍需申请人以当前权限执行。</p>
  {query.data?.items.length?<List dataSource={query.data.items} renderItem={x=><List.Item actions={[<Button key="view" onClick={()=>setSelected(x)}>查看并决策</Button>]}><List.Item.Meta title={<>Proposal #{x.proposal_id} <Tag>{x.status}</Tag></>} description={`申请人 ${x.applicant_user_id} · revision ${x.proposal_revision}`}/></List.Item>}/>:<Empty description="暂无审批任务"/>}
  {selected&&<ApprovalDetail value={selected} open onClose={()=>setSelected(null)} onChanged={()=>void qc.invalidateQueries({queryKey:['tenant',tenantId,'action-approvals']})}/>}</div></div>}
