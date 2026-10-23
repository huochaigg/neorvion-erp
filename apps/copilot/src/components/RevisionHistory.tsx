import { useQuery } from '@tanstack/react-query';
import { Timeline } from 'antd';
import { listProposalRevisions } from '@/api/proposals';

export function RevisionHistory({ proposalId }: { proposalId: number }) {
  const query = useQuery({ queryKey: ['proposal-revisions', proposalId], queryFn: ({signal}) => listProposalRevisions(proposalId, signal) });
  return <Timeline pending={query.isPending ? '加载中' : undefined} items={(query.data?.items ?? []).map((item) => ({
    children: <div><div className="font-medium">版本 {item.revision}</div><div className="text-xs text-[#94A3B8]">{new Date(item.created_at).toLocaleString()}</div></div>,
  }))} />;
}
