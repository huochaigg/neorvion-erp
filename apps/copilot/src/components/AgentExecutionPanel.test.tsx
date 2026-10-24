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
    expect(html).toContain('DEGRADED');
  });
});
