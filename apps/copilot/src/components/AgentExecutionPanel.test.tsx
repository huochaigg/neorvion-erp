import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AgentExecutionPanel } from './AgentExecutionPanel';

describe('AgentExecutionPanel', () => {
  it('renders parallel agent statuses from real trace data', () => {
    const html = renderToStaticMarkup(<AgentExecutionPanel runs={[{
      id: 1, graph_type: 'MULTI_AGENT', status: 'DEGRADED', route_reason: '跨领域', total_duration_ms: 10,
      tasks: [
        {agent_name:'sales_agent',task_id:'sales-1',status:'SUCCEEDED',duration_ms:4,model_calls:1,tool_calls:2,evidence_count:1,error_code:null},
        {agent_name:'inventory_agent',task_id:'inventory-1',status:'FAILED',duration_ms:5,model_calls:1,tool_calls:1,evidence_count:0,error_code:50288},
      ],
    }]} />);
    expect(html).toContain('Sales Agent');
    expect(html).toContain('Inventory Agent');
    expect(html).toContain('多 Agent 协作');
    expect(html).toContain('部分任务未完成');
    expect(html).not.toContain('MULTI_AGENT');
    expect(html).not.toContain('DEGRADED');
  });

  it('未完成路由的 PENDING 空 Run 不展示 Agent 协作区域', () => {
    const html = renderToStaticMarkup(<AgentExecutionPanel runs={[{
      id: 53, graph_type: 'PENDING', status: 'INTERRUPTED', route_reason: null, total_duration_ms: null, tasks: [],
    }]} />);
    expect(html).toBe('');
    expect(html).not.toContain('PENDING');
    expect(html).not.toContain('INTERRUPTED');
    expect(html).not.toContain('Agent 协作');
  });
});
