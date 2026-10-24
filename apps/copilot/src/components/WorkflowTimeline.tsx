import { Timeline } from 'antd';
import type { WorkflowEvent } from '@/types';
export function WorkflowTimeline({items}:{items:WorkflowEvent[]}){return <Timeline items={items.map(x=>({children:<div><div className="text-sm font-medium">{x.event_type}</div><div className="text-xs text-[#94A3B8]">{new Date(x.created_at).toLocaleString()}</div></div>}))}/>}
