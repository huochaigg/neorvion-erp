import { QuestionCircleOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';
import type { ReactNode } from 'react';

export function FormLabelHelp({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1">
      {label}
      <Tooltip title={<div className="max-w-xs text-xs leading-5">{children}</div>}>
        <QuestionCircleOutlined className="cursor-help text-slate-400" />
      </Tooltip>
    </span>
  );
}
