import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button, Modal, Tag, message } from 'antd';
import { Ban, FilePenLine, History, Play, ShieldCheck } from 'lucide-react';
import { cancelProposal, getCurrentIdentity, updateProposal, validateProposal } from '@/api/proposals';
import { confirmExecution, createConfirmation } from '@/api/executions';
import { ConfirmationDialog } from './ConfirmationDialog';
import { ExecutionDetail } from './ExecutionDetail';
import { ExecutionStatus } from './ExecutionStatus';
import { ProposalDetail } from './ProposalDetail';
import { ValidationResult } from './ValidationResult';
import type { ActionExecution, ActionProposal } from '@/types';
import { useCopilotStore } from '@/store';

const LABELS = { PURCHASE_ORDER_CREATE:'采购草稿', SALES_ORDER_CREATE:'销售订单草稿', INVENTORY_TRANSFER_CREATE:'库存调拨草稿' } as const;
const COLORS:Record<string,string> = {READY:'green',NEEDS_INPUT:'orange',STALE:'gold',CANCELLED:'default',EXPIRED:'default',DRAFT:'blue'};
const PERMISSIONS = {PURCHASE_ORDER_CREATE:'purchase:create',SALES_ORDER_CREATE:'order:create',INVENTORY_TRANSFER_CREATE:'stock_transfer:create'} as const;

export function ProposalCard({ value, initialExecution, onChanged }: {value:ActionProposal;initialExecution?:ActionExecution;onChanged:(value:ActionProposal)=>void}) {
  const [detail, setDetail] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [execution, setExecution] = useState<ActionExecution|null>(null);
  const [executionOpen, setExecutionOpen] = useState(false);
  const [renderedAt] = useState(() => Date.now());
  const tenantId = useCopilotStore((state) => state.tenantId);
  const identity = useQuery({queryKey:['tenant',tenantId,'copilot-current-identity'],queryFn:({signal})=>getCurrentIdentity(signal),enabled:tenantId!=null});
  const allowed = identity.data?.permissions.includes(PERMISSIONS[value.action_type]) ?? false;
  const immutable = value.status === 'CANCELLED' || value.status === 'EXPIRED' || !allowed;
  const previewFresh = value.status==='READY' && value.validation?.status==='VALID' && new Date(value.validation.expires_at).getTime()>renderedAt;
  const visibleExecution = execution ?? initialExecution ?? null;
  const executionInProgress = visibleExecution !== null && !['FAILED','REJECTED','CANCELLED','EXPIRED'].includes(visibleExecution.status);
  const run = async (work:()=>Promise<ActionProposal>, success:string) => {
    setBusy(true);
    try { const next = await work(); onChanged(next); message.success(success); }
    catch (error) { message.error(error instanceof Error ? error.message : '操作失败'); }
    finally { setBusy(false); }
  };
  const confirm = async () => { setBusy(true); try { const ticket=await createConfirmation(value); const result=await confirmExecution(ticket); setExecution(result); setConfirmOpen(false); message.success(result.status==='WAITING_APPROVAL'?'已提交审批':'已提交受控执行'); } catch(error) { message.error(error instanceof Error?error.message:'确认失败'); } finally {setBusy(false);} };
  return <div className="rounded-2xl border border-[#C7D2FE] bg-white p-4 shadow-[0_8px_24px_rgba(79,70,229,0.08)]">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><div className="font-semibold text-[#0F172A]">{LABELS[value.action_type]}</div><div className="text-xs text-[#94A3B8]">草稿 #{value.id} · 版本 {value.current_revision}</div></div>
      <Tag color={COLORS[value.status]}>{value.status}</Tag>
    </div>
    <div className="mt-3"><ValidationResult value={value.validation} /></div>
    <div className="mt-3 flex flex-wrap gap-2">
      <Button icon={<FilePenLine size={14}/>} onClick={()=>setDetail(true)} disabled={immutable}>编辑</Button>
      <Button icon={<ShieldCheck size={14}/>} loading={busy} onClick={()=>void run(()=>validateProposal(value),'预检已更新')} disabled={immutable || value.status==='NEEDS_INPUT'}>重新预检</Button>
      <Button icon={<History size={14}/>} onClick={()=>setDetail(true)}>详情与历史</Button>
      <Button type="primary" danger icon={<Play size={14}/>} disabled={immutable||!previewFresh||executionInProgress} onClick={()=>setConfirmOpen(true)}>确认执行</Button>
      {visibleExecution&&<Button onClick={()=>setExecutionOpen(true)}><ExecutionStatus value={visibleExecution.status}/></Button>}
      <Button danger icon={<Ban size={14}/>} disabled={immutable} onClick={()=>Modal.confirm({title:'取消这个业务草稿？',content:'取消后不能继续编辑或预检。',onOk:()=>run(()=>cancelProposal(value),'草稿已取消')})}>取消</Button>
    </div>
    <div className="mt-3 text-xs text-[#64748B]">{!allowed ? '当前权限不允许操作此草稿。' : 'V6 只有显式确认、必要审批和执行前复核全部通过后，才会在 ERP 创建草稿单据。'}</div>
    <ProposalDetail open={detail} proposal={value} busy={busy} onClose={()=>setDetail(false)} onSave={async(payload)=>{await run(()=>updateProposal(value,payload),'草稿已保存');setDetail(false);}} />
    <ConfirmationDialog open={confirmOpen} proposal={value} busy={busy} onCancel={()=>setConfirmOpen(false)} onConfirm={()=>void confirm()}/>
    {visibleExecution&&<ExecutionDetail id={visibleExecution.id} open={executionOpen} onClose={()=>setExecutionOpen(false)}/>}
  </div>;
}
