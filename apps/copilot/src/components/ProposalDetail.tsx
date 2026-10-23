import { Modal, Tabs } from 'antd';
import { ProposalEditor } from './ProposalEditor';
import { RevisionHistory } from './RevisionHistory';
import { ValidationResult } from './ValidationResult';
import type { ActionProposal } from '@/types';

export function ProposalDetail({open,proposal,busy,onClose,onSave}:{open:boolean;proposal:ActionProposal;busy:boolean;onClose:()=>void;onSave:(payload:Record<string,unknown>)=>Promise<void>}) {
  const immutable = proposal.status === 'CANCELLED' || proposal.status === 'EXPIRED';
  return <Modal width={760} open={open} onCancel={onClose} footer={null} title={`业务草稿 #${proposal.id}`} destroyOnHidden>
    <Tabs items={[
      { key:'edit', label:'草稿内容', children:<ProposalEditor proposal={proposal} disabled={busy || immutable} onSave={onSave} /> },
      { key:'validation', label:'预检结果', children:<ValidationResult value={proposal.validation} /> },
      { key:'history', label:'版本历史', children:<RevisionHistory proposalId={proposal.id} /> },
    ]} />
  </Modal>;
}
