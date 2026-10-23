import { Button, Form, Input, InputNumber, Space } from 'antd';
import type { ActionProposal } from '@/types';
import { RemoteErpSelect } from './RemoteErpSelect';

const ID_LABELS: Record<string, string> = {
  supplier_id: '供应商 ID', customer_id: '客户 ID', warehouse_id: '仓库 ID',
  source_warehouse_id: '调出仓库 ID', target_warehouse_id: '调入仓库 ID',
};
const ID_KINDS = {
  supplier_id:'supplier',customer_id:'customer',warehouse_id:'warehouse',
  source_warehouse_id:'warehouse',target_warehouse_id:'warehouse',
} as const;

export function ProposalEditor({ proposal, disabled, onSave }: {proposal:ActionProposal;disabled:boolean;onSave:(payload:Record<string,unknown>)=>Promise<void>}) {
  const [form] = Form.useForm();
  const initial = { ...proposal.payload };
  const topFields = proposal.editable_fields.filter((field) => field !== 'items' && field !== 'remark' && field !== 'expected_arrival_date');
  return (
    <Form form={form} layout="vertical" initialValues={initial} onFinish={async (values) => {
      await onSave(values);
    }}>
      <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
        {topFields.map((field) => ID_LABELS[field] ? (
          <Form.Item key={field} name={field} label={ID_LABELS[field]}><RemoteErpSelect kind={ID_KINDS[field as keyof typeof ID_KINDS]} placeholder={`请选择${ID_LABELS[field]}`} /></Form.Item>
        ) : (
          <Form.Item key={field} name={field} label={field}><Input maxLength={255} /></Form.Item>
        ))}
        {proposal.editable_fields.includes('expected_arrival_date') ? <Form.Item name="expected_arrival_date" label="预计到货日期"><Input type="date" /></Form.Item> : null}
      </div>
      <Form.List name="items">
        {(fields, { add, remove }) => <div className="space-y-2">
          <div className="text-sm font-medium text-[#334155]">明细</div>
          {fields.map(({ key, name }) => <Space key={key} align="baseline" wrap>
            <Form.Item name={[name, 'sku_id']} rules={[{ required: true, message: '请选择 SKU' }]}><RemoteErpSelect kind="sku" placeholder="搜索 SKU" /></Form.Item>
            <Form.Item name={[name, 'quantity']} rules={[{ required: true, message: '请填写数量' }]}><InputNumber min={1} placeholder="数量" /></Form.Item>
            {proposal.action_type !== 'INVENTORY_TRANSFER_CREATE' ? <Form.Item name={[name, 'unit_price']}><InputNumber min={0} precision={2} placeholder="单价（可选）" /></Form.Item> : null}
            <Button danger type="text" onClick={() => remove(name)}>删除</Button>
          </Space>)}
          <Button type="dashed" onClick={() => add({})}>添加明细</Button>
        </div>}
      </Form.List>
      <Form.Item name="remark" label="备注" className="mt-3"><Input.TextArea maxLength={255} /></Form.Item>
      <Button htmlType="submit" type="primary" disabled={disabled}>保存修改</Button>
    </Form>
  );
}
