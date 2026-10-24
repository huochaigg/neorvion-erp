import { Button, Input, Modal, message } from 'antd';
import { useState } from 'react';
import { decideApproval } from '@/api/executions';
import type { ActionApproval } from '@/types';

export function ApprovalDetail({value,open,onClose,onChanged}:{value:ActionApproval;open:boolean;onClose:()=>void;onChanged:()=>void}) {
  const [reason,setReason]=useState(''); const [busy,setBusy]=useState(false);
  const decide=async(approve:boolean)=>{setBusy(true);try{await decideApproval(value.id,approve,reason);message.success(approve?'已批准，等待申请人执行':'已拒绝');onChanged();onClose();}catch(e){message.error(e instanceof Error?e.message:'审批失败');}finally{setBusy(false);}};
  return <Modal open={open} title={`审批 #${value.id}`} onCancel={onClose} okText="批准" cancelText="关闭" confirmLoading={busy} onOk={()=>void decide(true)}
    footer={(_, {OkBtn,CancelBtn})=><><CancelBtn/><Button danger loading={busy} onClick={()=>void decide(false)}>拒绝</Button><OkBtn/></>}>
    <div className="mb-3 text-sm">申请人：{value.applicant_user_id} · Proposal #{value.proposal_id} · revision {value.proposal_revision}</div>
    <Input.TextArea value={reason} onChange={e=>setReason(e.target.value)} maxLength={500} placeholder="审批意见（拒绝时建议填写）" rows={4}/>
  </Modal>;
}
