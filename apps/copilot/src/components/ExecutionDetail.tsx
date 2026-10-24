import { Button, Descriptions, Modal, message } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { executeApproved, getExecution, reconcileExecution } from '@/api/executions';
import { ExecutionAuditTimeline } from './ExecutionAuditTimeline';
import { ExecutionStatus } from './ExecutionStatus';
export function ExecutionDetail({id,open,onClose}:{id:number;open:boolean;onClose:()=>void}) {
  const [busy,setBusy]=useState(false);
  const query=useQuery({queryKey:['execution',id],queryFn:({signal})=>getExecution(id,signal),enabled:open,refetchInterval:(q)=>['PENDING_CONFIRMATION','WAITING_APPROVAL','APPROVED','EXECUTING','UNKNOWN','RECONCILING'].includes(q.state.data?.status??'')?3000:false});
  const run=async(work:()=>Promise<unknown>,success:string)=>{setBusy(true);try{await work();await query.refetch();message.success(success);}catch(error){message.error(error instanceof Error?error.message:'操作失败');}finally{setBusy(false);}};
  const x=query.data; return <Modal width={720} open={open} onCancel={onClose} footer={null} title={`执行 #${id}`} destroyOnHidden>
    {x&&<><Descriptions column={1} bordered size="small" items={[{key:'status',label:'状态',children:<ExecutionStatus value={x.status}/>},{key:'revision',label:'Proposal 版本',children:x.proposal_revision},{key:'resource',label:'ERP 单据',children:x.erp_resource_no??x.erp_resource_id??'尚未确定'}]}/>
    {x.status==='APPROVED'&&<Button type="primary" danger className="mt-3" loading={busy} onClick={()=>void run(()=>executeApproved(x),'已提交 ERP 执行')}>执行已批准动作</Button>}
    {x.status==='UNKNOWN'&&<Button className="mt-3" loading={busy} onClick={()=>void run(()=>reconcileExecution(id),'对账已完成')}>立即对账</Button>}<div className="mt-5"><ExecutionAuditTimeline executionId={id}/></div></>}
  </Modal>;
}
