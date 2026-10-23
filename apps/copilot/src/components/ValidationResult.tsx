import { Alert } from 'antd';
import type { ProposalValidation } from '@/types';

export function ValidationResult({ value }: { value: ProposalValidation | null }) {
  if (!value) return <Alert type="info" showIcon message="尚未预检" description="保存完整字段后可执行 ERP 无副作用预检。" />;
  const problems = [...value.errors, ...value.warnings];
  return (
    <div className="space-y-2">
      <Alert
        showIcon
        type={value.status === 'VALID' ? 'success' : value.status === 'UNAVAILABLE' ? 'warning' : 'error'}
        message={value.status === 'VALID' ? '草稿预检通过' : value.status === 'UNAVAILABLE' ? 'ERP 预检暂时不可用' : '草稿预检未通过'}
        description={value.status === 'VALID' ? '结果仅代表预检时点，未创建任何 ERP 单据。' : undefined}
      />
      {value.missing_fields.length ? <div className="text-sm text-amber-700">待补充：{value.missing_fields.join('、')}</div> : null}
      {problems.map((item, index) => (
        <div key={`${item.code}-${index}`} className="rounded-lg bg-[#F8FAFC] px-3 py-2 text-sm text-[#475569]">
          {item.message}{item.field ? `（${item.field}）` : ''}
        </div>
      ))}
    </div>
  );
}
