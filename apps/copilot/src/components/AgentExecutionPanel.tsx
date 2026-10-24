import { Collapse, Tag } from 'antd';
import type { AgentRun, ToolRun } from '@/types';

const LABELS: Record<string, string> = {
  single_agent: 'Single Agent',
  supervisor_agent: 'Supervisor',
  sales_agent: 'Sales Agent',
  inventory_agent: 'Inventory Agent',
  procurement_agent: 'Procurement Agent',
  knowledge_agent: 'Knowledge Agent',
};

export function AgentExecutionPanel({ runs, toolRuns = [] }: { runs: AgentRun[]; toolRuns?: ToolRun[] }) {
  if (!runs.length) return null;
  return (
    <Collapse
      className="mb-3"
      size="small"
      defaultActiveKey={runs.map((run) => String(run.id))}
      items={runs.map((run) => ({
        key: String(run.id),
        label: (
          <span>
            Agent 协作 · {run.graph_type} <Tag className="ml-2">{run.status}</Tag>
          </span>
        ),
        children: (
          <div className="space-y-2">
            {run.tasks.map((task) => {
              const tools = toolRuns.filter((item) => item.agent_task_id === task.task_id);
              return <div key={task.task_id} className="rounded-lg border border-slate-100 p-2 text-xs">
                <div className="flex items-center justify-between">
                  <b>{LABELS[task.agent_name] ?? task.agent_name}</b>
                  <Tag
                    color={
                      task.status === 'FAILED'
                        ? 'red'
                        : task.status === 'RUNNING'
                          ? 'blue'
                          : 'green'
                    }
                  >
                    {task.status}
                  </Tag>
                </div>
                <div className="mt-1 text-slate-500">
                  工具 {task.tool_calls} · 证据 {task.evidence_count} · 模型 {task.model_calls} ·{' '}
                  {task.duration_ms ?? '-'} ms
                </div>
                {tools.length ? (
                  <div className="mt-1 text-slate-500">
                    {tools.map((item) => item.tool_name).join('、')}
                  </div>
                ) : null}
                {task.error_code ? (
                  <div className="mt-1 text-red-600">错误码：{task.error_code}</div>
                ) : null}
              </div>;
            })}
          </div>
        ),
      }))}
    />
  );
}
