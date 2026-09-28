import {
  ApiError,
  brandOptionsQueryKey,
  PERMISSION_CODE,
  PRODUCT_STATUS,
  productCategoriesQueryKey,
  productQueryKey,
  SKU_STATUS,
  specEntriesFromRecord,
  specRecordFromEntries,
  type ProductCategory,
  type ProductSku,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Form, Input, Select, Space, Spin, TreeSelect } from 'antd';
import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchBrandOptions, fetchProductCategories } from '@/api/catalog';
import {
  addProductSku,
  createProduct,
  deleteProductSku,
  fetchProduct,
  updateProduct,
  updateProductSku,
} from '@/api/products';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

interface SpecForm {
  key?: string;
  value?: string;
}

interface SkuForm {
  id?: number;
  sku_code: string;
  name: string;
  barcode?: string;
  status?: string;
  specs?: SpecForm[];
}

interface ProductFormValues {
  name: string;
  code: string;
  category_id: number;
  brand_id?: number | null;
  description?: string;
  status: string;
  skus: SkuForm[];
}

interface CategoryTreeNode {
  value: number;
  title: string;
  disabled?: boolean;
  children?: CategoryTreeNode[];
}

function toTreeData(nodes: ProductCategory[]): CategoryTreeNode[] {
  return nodes.map((node) => ({
    value: node.id,
    title: node.name,
    disabled: node.status !== 'ACTIVE',
    children: node.children.length ? toTreeData(node.children) : undefined,
  }));
}

function skuToForm(sku: ProductSku): SkuForm {
  return {
    id: sku.id,
    sku_code: sku.sku_code,
    name: sku.name,
    barcode: sku.barcode ?? '',
    status: sku.status,
    specs: specEntriesFromRecord(sku.spec_values),
  };
}

async function syncSkus(productId: number, original: ProductSku[], next: SkuForm[]) {
  const keptIds = new Set(next.filter((item) => item.id != null).map((item) => item.id as number));
  for (const item of next) {
    const payload = {
      sku_code: item.sku_code,
      name: item.name,
      barcode: item.barcode || null,
      spec_values: specRecordFromEntries(item.specs),
      status: item.status || SKU_STATUS.active,
    };
    if (item.id == null) {
      await addProductSku(productId, payload);
      continue;
    }
    await updateProductSku(productId, item.id, {
      name: payload.name,
      barcode: payload.barcode,
      spec_values: payload.spec_values,
      status: payload.status,
    });
  }
  for (const sku of original) {
    if (!keptIds.has(sku.id)) {
      await deleteProductSku(productId, sku.id);
    }
  }
}

export function ProductFormPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const params = useParams();
  const queryClient = useQueryClient();
  const { tenantId, hasPermission } = usePermissions();
  const productId = params.id ? Number(params.id) : null;
  const isEdit = productId != null && Number.isFinite(productId);
  const [form] = Form.useForm<ProductFormValues>();

  const categoriesQuery = useQuery({
    queryKey: productCategoriesQueryKey(tenantId),
    queryFn: ({ signal }) => fetchProductCategories(signal),
    enabled: tenantId != null,
  });
  const brandsQuery = useQuery({
    queryKey: brandOptionsQueryKey(tenantId),
    queryFn: ({ signal }) => fetchBrandOptions(signal),
    enabled: tenantId != null,
  });
  const productQuery = useQuery({
    queryKey: productQueryKey(tenantId, productId),
    queryFn: ({ signal }) => fetchProduct(productId as number, signal),
    enabled: isEdit && tenantId != null,
  });

  useEffect(() => {
    form.resetFields();
  }, [tenantId, form]);

  useEffect(() => {
    if (!productQuery.data) {
      return;
    }
    form.setFieldsValue({
      name: productQuery.data.name,
      code: productQuery.data.code,
      category_id: productQuery.data.category_id,
      brand_id: productQuery.data.brand_id,
      description: productQuery.data.description ?? '',
      status: productQuery.data.status,
      skus: productQuery.data.skus.map(skuToForm),
    });
  }, [productQuery.data, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: ProductFormValues) => {
      const skus = values.skus.map((item) => ({
        sku_code: item.sku_code,
        name: item.name,
        barcode: item.barcode || null,
        spec_values: specRecordFromEntries(item.specs),
        status: item.status || SKU_STATUS.active,
      }));
      if (isEdit && productId != null) {
        await updateProduct(productId, {
          name: values.name,
          category_id: values.category_id,
          brand_id: values.brand_id ?? null,
          description: values.description || null,
          status: values.status,
        });
        await syncSkus(productId, productQuery.data?.skus ?? [], values.skus);
        return productId;
      }
      const created = await createProduct({
        name: values.name,
        code: values.code,
        category_id: values.category_id,
        brand_id: values.brand_id ?? null,
        description: values.description || null,
        status: values.status,
        skus,
      });
      return created.id;
    },
    onSuccess: (id) => {
      message.success(isEdit ? '商品已更新' : '商品已创建');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'products'] });
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'product'] });
      navigate(`/products/${id}`);
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });

  const canSubmit = isEdit
    ? hasPermission(PERMISSION_CODE.productUpdate)
    : hasPermission(PERMISSION_CODE.productCreate);

  return (
    <div>
      <PageHeader
        title={props.title ?? (isEdit ? '编辑商品' : '新增商品')}
        description={
          props.description ??
          'SPU 保存公共信息。每个 SKU 是后续库存和订单的最小单位。规格用键值对，不生成笛卡尔积。'
        }
        extra={<Button onClick={() => navigate('/products/list')}>返回列表</Button>}
      />
      {isEdit && productQuery.isLoading ? <Spin /> : null}
      {isEdit && productQuery.isError ? (
        <Card>商品不存在，或不属于当前企业。</Card>
      ) : (
        <Form
          form={form}
          layout="vertical"
          disabled={!canSubmit}
          initialValues={{
            status: PRODUCT_STATUS.draft,
            skus: [
              {
                sku_code: '',
                name: '',
                barcode: '',
                status: SKU_STATUS.active,
                specs: [{ key: '', value: '' }],
              },
            ],
          }}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Card title="基础信息" className="mb-4">
            <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
              <Form.Item name="name" label="商品名称" rules={[{ required: true, message: '请输入名称' }]}>
                <Input maxLength={128} />
              </Form.Item>
              <Form.Item
                name="code"
                label="商品编码"
                extra="租户内唯一。大写字母、数字、下划线、中划线。"
                rules={[{ required: true, message: '请输入编码' }]}
              >
                <Input maxLength={64} disabled={isEdit} />
              </Form.Item>
              <Form.Item
                name="category_id"
                label="类目"
                rules={[{ required: true, message: '请选择类目' }]}
              >
                <TreeSelect
                  allowClear
                  placeholder="选择类目"
                  treeData={toTreeData(categoriesQuery.data ?? [])}
                />
              </Form.Item>
              <Form.Item name="brand_id" label="品牌">
                <Select
                  allowClear
                  placeholder="可选"
                  options={[
                    ...(productQuery.data?.brand_id &&
                    productQuery.data.brand_name &&
                    !(brandsQuery.data ?? []).some((item) => item.id === productQuery.data?.brand_id)
                      ? [
                          {
                            value: productQuery.data.brand_id,
                            label: `${productQuery.data.brand_name}（已停用）`,
                          },
                        ]
                      : []),
                    ...(brandsQuery.data ?? []).map((item) => ({
                      value: item.id,
                      label: item.name,
                    })),
                  ]}
                />
              </Form.Item>
              <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: PRODUCT_STATUS.draft, label: '草稿' },
                    { value: PRODUCT_STATUS.active, label: '启用' },
                    { value: PRODUCT_STATUS.inactive, label: '停用' },
                  ]}
                />
              </Form.Item>
            </div>
            <Form.Item name="description" label="描述">
              <Input.TextArea rows={3} />
            </Form.Item>
          </Card>

          <Card
            title="SKU"
            extra={<span className="text-sm text-slate-500">至少保留一个 SKU。已产生库存后将禁止物理删除。</span>}
          >
            <Form.List
              name="skus"
              rules={[
                {
                  validator: async (_, value: SkuForm[]) => {
                    if (!value?.length) {
                      throw new Error('至少添加一个 SKU');
                    }
                  },
                },
              ]}
            >
              {(fields, { add, remove }) => (
                <div className="flex flex-col gap-4">
                  {fields.map((field) => (
                    <div key={field.key} className="rounded border border-slate-200 p-4">
                      <div className="mb-2 flex items-center justify-between">
                        <strong>SKU {field.name + 1}</strong>
                        {fields.length > 1 ? (
                          <Button type="link" danger onClick={() => remove(field.name)}>
                            删除此行
                          </Button>
                        ) : null}
                      </div>
                      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
                        <Form.Item
                          name={[field.name, 'sku_code']}
                          label="SKU 编码"
                          rules={[{ required: true, message: '请输入 SKU 编码' }]}
                        >
                          <Input maxLength={64} disabled={isEdit && form.getFieldValue(['skus', field.name, 'id'])} />
                        </Form.Item>
                        <Form.Item
                          name={[field.name, 'name']}
                          label="名称"
                          rules={[{ required: true, message: '请输入名称' }]}
                        >
                          <Input maxLength={128} />
                        </Form.Item>
                        <Form.Item name={[field.name, 'barcode']} label="条码">
                          <Input maxLength={64} />
                        </Form.Item>
                        <Form.Item name={[field.name, 'status']} label="状态">
                          <Select
                            options={[
                              { value: SKU_STATUS.active, label: '启用' },
                              { value: SKU_STATUS.inactive, label: '停用' },
                            ]}
                          />
                        </Form.Item>
                      </div>
                      <Form.Item hidden name={[field.name, 'id']}>
                        <Input />
                      </Form.Item>
                      <Form.List name={[field.name, 'specs']}>
                        {(specFields, specOps) => (
                          <div>
                            <div className="mb-2 text-sm text-slate-600">规格（例如 颜色 / 黑色）</div>
                            {specFields.map((spec) => (
                              <Space key={spec.key} className="mb-2" align="start">
                                <Form.Item name={[spec.name, 'key']} className="mb-0">
                                  <Input placeholder="规格名" className="w-36" />
                                </Form.Item>
                                <Form.Item name={[spec.name, 'value']} className="mb-0">
                                  <Input placeholder="规格值" className="w-36" />
                                </Form.Item>
                                <Button type="link" onClick={() => specOps.remove(spec.name)}>
                                  移除
                                </Button>
                              </Space>
                            ))}
                            <Button type="dashed" onClick={() => specOps.add({ key: '', value: '' })}>
                              添加规格
                            </Button>
                          </div>
                        )}
                      </Form.List>
                    </div>
                  ))}
                  <Button
                    type="dashed"
                    onClick={() =>
                      add({
                        sku_code: '',
                        name: '',
                        barcode: '',
                        status: SKU_STATUS.active,
                        specs: [{ key: '', value: '' }],
                      })
                    }
                  >
                    新增 SKU
                  </Button>
                </div>
              )}
            </Form.List>
          </Card>

          <div className="mt-4">
            <Button type="primary" htmlType="submit" loading={saveMutation.isPending} disabled={!canSubmit}>
              保存
            </Button>
          </div>
        </Form>
      )}
    </div>
  );
}
