import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { WorkflowStatus } from './WorkflowStatus';

describe('WorkflowStatus', () => {
  it.each(['WAITING_INPUT', 'WAITING_APPROVAL', 'RECONCILING', 'NEEDS_MANUAL_INTERVENTION'])(
    '展示真实工作流状态 %s',
    (status) => {
      expect(renderToStaticMarkup(<WorkflowStatus value={status} />)).toContain(status);
    },
  );
});
