import { Collapse, Tag } from 'antd';
import type { AgentRun, ToolRun } from '@/types';
import {
  agentGraphLabel,
  agentRunStatusLabel,
  agentTaskStatusLabel,
  hasVisibleAgentTrace,
} from '@/lib/runConnection';

const LABELS: Record<string, string> = {
  single_agent: '单一 Agent',
  supervisor_agent: 'Supervisor',
  sales_agent: 'Sales Agent',
  inventory_agent: 'Inventory Agent',
  procurement_agent: 'Procurement Agent',
  knowledge_agent: 'Knowledge Agent',
};

function taskColor(status: string) {
  if (status === 'FAILED' || status === 'INTERRUPTED' || status === 'TIMED_OUT') return 'red';
  if (status === 'RUNNING') return 'blue';
  if (status === 'CANCELLED') return 'default';
  return 'green';
}

export function AgentExecutionPanel({ runs, toolRuns = [] }: { runs: AgentRun[]; toolRuns?: ToolRun[] }) {
  const visible = runs.filter(hasVisibleAgentTrace);
  if (!visible.length) return null;
  return (
    <Collapse
      className="mb-3!"
      size="small"
      defaultActiveKey={visible.map((run) => String(run.id))}
      items={visible.map((run) => {
        const title = agentGraphLabel(run.graph_type) || 'Agent 执行';
        const statusText = agentRunStatusLabel(run.status);
        return {
          key: String(run.id),
          label: (
            <span>
              {title}
              {statusText ? <Tag className="ml-2">{statusText}</Tag> : null}
            </span>
          ),
          children: (
            <div className="space-y-2">
              {run.route_reason ? <div className="text-xs text-slate-500">{run.route_reason}</div> : null}
              {run.total_duration_ms != null ? (
                <div className="text-xs text-slate-500">耗时 {run.total_duration_ms} ms</div>
              ) : null}
              {run.tasks.length ? (
                run.tasks.map((task) => {
                  const tools = toolRuns.filter((item) => item.agent_task_id === task.task_id);
                  return (
                    <div key={task.task_id} className="rounded-lg border border-slate-100 p-2 text-xs">
                      <div className="flex items-center justify-between">
                        <b>{LABELS[task.agent_name] ?? task.agent_name}</b>
                        <Tag color={taskColor(task.status)}>{agentTaskStatusLabel(task.status) || task.status}</Tag>
                      </div>
                      <div className="mt-1 text-slate-500">
                        工具 {task.tool_calls} · 证据 {task.evidence_count} · 模型 {task.model_calls} ·{' '}
                        {task.duration_ms ?? '-'} ms
                      </div>
                      {tools.length ? (
                        <div className="mt-1 text-slate-500">{tools.map((item) => item.tool_name).join('、')}</div>
                      ) : null}
                      {task.error_code ? <div className="mt-1 text-red-600">错误码：{task.error_code}</div> : null}
                    </div>
                  );
                })
              ) : (
                <div className="text-xs text-slate-500">暂无已完成的 Agent 子任务。</div>
              )}
            </div>
          ),
        };
      })}
    />
  );
}
