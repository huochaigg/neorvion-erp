import { Button, Empty, List, Skeleton, message } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createWorkflow, listWorkflows } from '@/api/workflows';
import { WorkflowInputForm } from '@/components/WorkflowInputForm';
import { WorkflowStatus } from '@/components/WorkflowStatus';
import { useCopilotStore } from '@/store';
import type { WorkflowType } from '@/types';
export function WorkflowListPage(){const tenant=useCopilotStore(s=>s.tenantId);const q=useQuery({queryKey:['tenant',tenant,'workflows'],queryFn:({signal})=>listWorkflows(signal),refetchInterval:5000});const qc=useQueryClient();const nav=useNavigate();const [open,setOpen]=useState(false);
 const create=async(type:WorkflowType,input:Record<string,unknown>,conversation?:number)=>{try{const x=await createWorkflow(type,input,conversation);await qc.invalidateQueries({queryKey:['tenant',tenant,'workflows']});nav(`/workflows/${x.id}`);}catch(e){message.error(e instanceof Error?e.message:'创建失败');throw e;}};
 return <div className="copilot-scroll h-full overflow-auto p-6"><div className="mx-auto max-w-[960px]"><div className="mb-5 flex items-center justify-between"><div><h1 className="text-xl font-semibold">业务工作流</h1><p className="text-sm text-[#64748B]">确定性步骤、人工等待和 V6 受控执行。</p></div><Button type="primary" onClick={()=>setOpen(true)}>创建工作流</Button></div>{q.isPending?<Skeleton active/>:q.data?.items.length?<List dataSource={q.data.items} renderItem={x=><List.Item actions={[<Button key="view" onClick={()=>nav(`/workflows/${x.id}`)}>查看</Button>]}><List.Item.Meta title={<>{x.workflow_type} <WorkflowStatus value={x.status}/></>} description={`#${x.id} · 当前步骤 ${x.current_step}`}/></List.Item>}/>:<Empty description="暂无工作流"/>}<WorkflowInputForm open={open} onClose={()=>setOpen(false)} onSubmit={create}/></div></div>}
