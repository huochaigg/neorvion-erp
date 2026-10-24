import { Alert, Descriptions, Modal } from 'antd';
import { useState } from 'react';
import type { ActionProposal } from '@/types';

export function ConfirmationDialog({ open, proposal, busy, onCancel, onConfirm }:{open:boolean;proposal:ActionProposal;busy:boolean;onCancel:()=>void;onConfirm:()=>void}) {
  const [renderedAt] = useState(() => Date.now());
  const previewOk = proposal.status === 'READY' && proposal.validation?.status === 'VALID' && new Date(proposal.validation.expires_at).getTime() > renderedAt;
  return <Modal open={open} title="确认创建真实 ERP 业务草稿" okText="我已核对，确认执行" cancelText="返回检查"
    confirmLoading={busy} okButtonProps={{danger:true,disabled:!previewOk}} onCancel={onCancel} onOk={onConfirm} destroyOnHidden>
    <Alert className="mb-4" type="warning" showIcon title="这是人工授权，不会自动提交审核、预占库存或出入库。" />
    <Descriptions size="small" column={1} bordered items={[
      {key:'action',label:'动作',children:proposal.action_type},
      {key:'revision',label:'草稿版本',children:proposal.current_revision},
      {key:'risk',label:'风险',children:proposal.action_type==='INVENTORY_TRANSFER_CREATE'?'高风险，需异人审批':'中风险，确认后执行'},
      {key:'effect',label:'业务影响',children:'在 ERP 创建一张草稿单据'},
      {key:'payload',label:'关键参数',children:<pre className="m-0 whitespace-pre-wrap text-xs">{JSON.stringify(proposal.payload,null,2)}</pre>},
    ]}/>
    {!previewOk && <Alert className="mt-3" type="error" title="预检无效或已过期，请先重新预检。" />}
  </Modal>;
}
