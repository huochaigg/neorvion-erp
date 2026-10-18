import {
  ApiError,
  PERMISSION_CODE,
  productSkuOptionsQueryKey,
  STOCKTAKE_SCOPE,
  STOCKTAKE_SCOPE_LABEL,
  stocktakesQueryKey,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type SkuOption,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Select, Space } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchSkuOptions } from '@/api/inventory';
import { createStocktake } from '@/api/stocktakes';
import { fetchWarehouses } from '@/api/warehouses';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

interface FormValues {
  warehouse_id: number;
  scope: string;
  sku_ids?: number[];
  remark?: string;
}

export function StocktakeFormPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId, hasPermission } = usePermissions();
  const [form] = Form.useForm<FormValues>();
  const [skuSearch, setSkuSearch] = useState('');
  const [skuKeyword, setSkuKeyword] = useState('');
  const scope = Form.useWatch('scope', form);

  useEffect(() => {
    const timer = window.setTimeout(() => setSkuKeyword(skuSearch.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [skuSearch]);

  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });
  const skuOptionsQuery = useQuery({
    queryKey: productSkuOptionsQueryKey(tenantId, { q: skuKeyword, page: 1, pageSize: 20 }),
    queryFn: ({ signal }) => fetchSkuOptions({ q: skuKeyword || undefined, page: 1, pageSize: 20 }, signal),
    enabled: tenantId != null && hasPermission(PERMISSION_CODE.productRead) && scope === STOCKTAKE_SCOPE.selectedSku,
  });

  const createMutation = useMutation({
    mutationFn: (values: FormValues) =>
      createStocktake({
        warehouse_id: values.warehouse_id,
        scope: values.scope,
        sku_ids: values.scope === STOCKTAKE_SCOPE.selectedSku ? values.sku_ids ?? [] : [],
        remark: values.remark?.trim() || null,
      }),
    onSuccess: (data) => {
      message.success('盘点任务已创建，已保存当时账面快照');
      void queryClient.invalidateQueries({ queryKey: stocktakesQueryKey(tenantId) });
      navigate(`/stocktakes/${data.id}`);
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  return (
    <FormPageContainer>
      <PageHeader title={props.title ?? '新建盘点'} description={props.description} />
      <Form
        form={form}
        layout="vertical"
        className="max-w-xl"
        initialValues={{ scope: STOCKTAKE_SCOPE.all }}
        onFinish={(values) => createMutation.mutate(values)}
      >
        <Form.Item name="warehouse_id" label="仓库" rules={[{ required: true, message: '请选择仓库' }]}>
          <Select
            showSearch
            optionFilterProp="label"
            options={(warehouseQuery.data?.items ?? []).map((item) => ({
              value: item.id,
              label: `${item.name}（${item.code}）`,
            }))}
          />
        </Form.Item>
        <Form.Item name="scope" label="盘点范围" rules={[{ required: true }]}>
          <Select
            options={Object.entries(STOCKTAKE_SCOPE_LABEL).map(([value, label]) => ({ value, label }))}
          />
        </Form.Item>
        {scope === STOCKTAKE_SCOPE.selectedSku ? (
          <Form.Item name="sku_ids" label="SKU" rules={[{ required: true, message: '请选择至少一个 SKU' }]}>
            <Select
              mode="multiple"
              showSearch
              filterOption={false}
              onSearch={setSkuSearch}
              placeholder="远程搜索 SKU"
              options={(skuOptionsQuery.data?.items ?? []).map((item: SkuOption) => ({
                value: item.id,
                label: `${item.sku_code} ${item.product_name} ${item.name}`,
              }))}
            />
          </Form.Item>
        ) : null}
        <Form.Item name="remark" label="备注">
          <Input.TextArea rows={3} maxLength={255} />
        </Form.Item>
        <Space>
          <Button onClick={() => navigate('/stocktakes')}>返回</Button>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
            创建
          </Button>
        </Space>
      </Form>
    </FormPageContainer>
  );
}
