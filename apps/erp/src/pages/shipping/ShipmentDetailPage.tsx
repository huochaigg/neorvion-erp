import {
  ApiError,
  CARRIER_STATUS,
  PERMISSION_CODE,
  TRACKING_EVENT_STATUS_OPTIONS,
  canAddTrackingEvent,
  canCancelShipment,
  canConfirmShipment,
  canDeliverShipment,
  canEditShipment,
  carriersQueryKey,
  outboundOrderQueryKey,
  outboundOrdersQueryKey,
  salesOrderQueryKey,
  salesOrdersQueryKey,
  shipmentQueryKey,
  shipmentStatusLabel,
  shipmentsQueryKey,
  trackingEventStatusLabel,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, DatePicker, Descriptions, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Timeline } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchCarriers } from '@/api/carriers';
import {
  addShipmentTrackingEvent,
  cancelShipment,
  confirmShipment,
  deliverShipment,
  fetchShipment,
  updateShipment,
} from '@/api/shipments';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { DATETIME_FORMAT, formatDateTime, toDateTimeParam } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function ShipmentDetailPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const shipmentId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const [trackingOpen, setTrackingOpen] = useState(false);
  const [deliverOpen, setDeliverOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const query = useQuery({
    queryKey: shipmentQueryKey(tenantId, shipmentId),
    queryFn: ({ signal }) => fetchShipment(shipmentId, signal),
    enabled: tenantId != null && shipmentId > 0,
  });
  const shipment = query.data;
  const carriersQuery = useQuery({
    queryKey: carriersQueryKey(tenantId, { status: CARRIER_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchCarriers({ status: CARRIER_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null && editOpen,
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: shipmentQueryKey(tenantId, shipmentId) });
    await queryClient.invalidateQueries({ queryKey: shipmentsQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'shipment-tracking'] });
    await queryClient.invalidateQueries({
      queryKey: salesOrderQueryKey(tenantId, shipment?.sales_order_id ?? null),
    });
    await queryClient.invalidateQueries({ queryKey: salesOrdersQueryKey(tenantId) });
    await queryClient.invalidateQueries({
      queryKey: outboundOrderQueryKey(tenantId, shipment?.outbound_order_id ?? null),
    });
    await queryClient.invalidateQueries({ queryKey: outboundOrdersQueryKey(tenantId) });
  }

  const confirmMutation = useMutation({
    mutationFn: () => confirmShipment(shipmentId),
    onSuccess: async () => {
      message.success('已发货。库存不会再变化，因为出库时已经扣过。');
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '确认失败');
    },
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelShipment(shipmentId),
    onSuccess: async () => {
      message.success('已取消物流草稿');
      await refresh();
    },
  });
  const trackingMutation = useMutation({
    mutationFn: (values: { status: string; description: string; location?: string; occurred_at: string }) =>
      addShipmentTrackingEvent(shipmentId, values),
    onSuccess: async () => {
      message.success('已追加轨迹');
      setTrackingOpen(false);
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '添加失败');
    },
  });
  const updateMutation = useMutation({
    mutationFn: (values: { carrier_id: number; tracking_no?: string; remark?: string }) =>
      updateShipment(shipmentId, {
        carrier_id: values.carrier_id,
        tracking_no: values.tracking_no?.trim() || null,
        remark: values.remark?.trim() || null,
      }),
    onSuccess: async () => {
      message.success('草稿已更新');
      setEditOpen(false);
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });
  const deliverMutation = useMutation({
    mutationFn: (values: { delivered_at?: string; remark?: string }) => deliverShipment(shipmentId, values),
    onSuccess: async () => {
      message.success('已签收。如果订单全部签收，销售订单会进入已完成。');
      setDeliverOpen(false);
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '签收失败');
    },
  });

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? shipment?.shipment_no ?? '物流单'}
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/shipments')}>返回列表</Button>
            {shipment && canEditShipment(shipment.status) ? (
              <Can permission={PERMISSION_CODE.shipmentUpdate}>
                <Button onClick={() => setEditOpen(true)}>编辑</Button>
              </Can>
            ) : null}
            {shipment && canConfirmShipment(shipment.status) ? (
              <Can permission={PERMISSION_CODE.shipmentConfirm}>
                <Popconfirm
                  title="确认后物流单将进入已发货状态，无法直接修改商品数量，是否继续？"
                  onConfirm={() => {
                    if (!shipment.tracking_no) {
                      message.warning('确认发货前必须填写运单号');
                      return;
                    }
                    confirmMutation.mutate();
                  }}
                >
                  <Button type="primary" loading={confirmMutation.isPending}>
                    确认发货
                  </Button>
                </Popconfirm>
              </Can>
            ) : null}
            {shipment && canAddTrackingEvent(shipment.status) ? (
              <Can permission={PERMISSION_CODE.shipmentTrackingUpdate}>
                <Button onClick={() => setTrackingOpen(true)}>新增轨迹</Button>
              </Can>
            ) : null}
            {shipment && canDeliverShipment(shipment.status) ? (
              <Can permission={PERMISSION_CODE.shipmentDeliver}>
                <Button type="primary" onClick={() => setDeliverOpen(true)}>
                  确认签收
                </Button>
              </Can>
            ) : null}
            {shipment && canCancelShipment(shipment.status) ? (
              <Can permission={PERMISSION_CODE.shipmentCancel}>
                <Button danger loading={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
                  取消
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {shipment ? (
        <>
          <Descriptions column={3}>
            <Descriptions.Item label="状态">
              <Tag>{shipmentStatusLabel(shipment.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="销售订单">{shipment.sales_order_no}</Descriptions.Item>
            <Descriptions.Item label="出库单">{shipment.outbound_no}</Descriptions.Item>
            <Descriptions.Item label="客户">{shipment.customer_name}</Descriptions.Item>
            <Descriptions.Item label="收件人">{shipment.recipient_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="地址">{shipment.address || '-'}</Descriptions.Item>
            <Descriptions.Item label="物流商">{shipment.carrier_name}</Descriptions.Item>
            <Descriptions.Item label="运单号">{shipment.tracking_no || '-'}</Descriptions.Item>
            <Descriptions.Item label="发货人">{shipment.shipped_by_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="发货时间">{formatDateTime(shipment.shipped_at)}</Descriptions.Item>
            <Descriptions.Item label="签收时间">{formatDateTime(shipment.delivered_at)}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatDateTime(shipment.created_at)}</Descriptions.Item>
            <Descriptions.Item label="备注" span={3}>
              {shipment.remark || '-'}
            </Descriptions.Item>
          </Descriptions>
          <Table
            className="mt-4!"
            rowKey="id"
            pagination={false}
            dataSource={shipment.items}
            columns={[
              { title: 'SKU', dataIndex: 'sku_code' },
              { title: '商品', dataIndex: 'product_name' },
              { title: '出库数量', dataIndex: 'outbound_quantity' },
              { title: '此前已发', dataIndex: 'shipped_before' },
              { title: '本次发货', dataIndex: 'quantity' },
            ]}
          />
          <div className="mt-6">
            <h3 className="mb-3 text-base font-medium">物流轨迹</h3>
            <Timeline
              items={
                shipment.tracking_events.length
                  ? shipment.tracking_events.map((event) => ({
                      children: (
                        <div>
                          <div>
                            {formatDateTime(event.occurred_at)} · {trackingEventStatusLabel(event.status)}
                          </div>
                          <div>{event.location || '地点未填'}</div>
                          <div>{event.description}</div>
                        </div>
                      ),
                    }))
                  : [{ children: '还没有轨迹' }]
              }
            />
          </div>
        </>
      ) : null}
      <Modal
        title="编辑物流草稿"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        footer={null}
        destroyOnHidden
      >
        {shipment ? (
          <Form
            layout="vertical"
            initialValues={{
              carrier_id: shipment.carrier_id,
              tracking_no: shipment.tracking_no ?? '',
              remark: shipment.remark ?? '',
            }}
            onFinish={(values: { carrier_id: number; tracking_no?: string; remark?: string }) =>
              updateMutation.mutate(values)
            }
          >
            <Form.Item name="carrier_id" label="物流商" rules={[{ required: true, message: '请选择物流商' }]}>
              <Select
                options={(carriersQuery.data?.items ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name} (${item.code})`,
                }))}
              />
            </Form.Item>
            <Form.Item name="tracking_no" label="运单号">
              <Input maxLength={64} />
            </Form.Item>
            <Form.Item name="remark" label="备注">
              <Input.TextArea rows={2} maxLength={255} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
              保存
            </Button>
          </Form>
        ) : null}
      </Modal>
      <Modal
        title="新增轨迹"
        open={trackingOpen}
        onCancel={() => setTrackingOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Form
          layout="vertical"
          onFinish={(values: { status: string; description: string; location?: string; occurred_at: dayjs.Dayjs }) =>
            trackingMutation.mutate({
              status: values.status,
              description: values.description,
              location: values.location?.trim() || undefined,
              occurred_at: toDateTimeParam(values.occurred_at)!,
            })
          }
        >
          <Form.Item name="status" label="轨迹类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select options={TRACKING_EVENT_STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="occurred_at" label="时间" rules={[{ required: true, message: '请选择时间' }]}>
            <DatePicker showTime format={DATETIME_FORMAT} className="w-full" />
          </Form.Item>
          <Form.Item name="location" label="地点">
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="description" label="说明" rules={[{ required: true, message: '请填写说明' }]}>
            <Input.TextArea rows={3} maxLength={255} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={trackingMutation.isPending}>
            保存
          </Button>
        </Form>
      </Modal>
      <Modal
        title="确认签收"
        open={deliverOpen}
        onCancel={() => setDeliverOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Form
          layout="vertical"
          initialValues={{ delivered_at: dayjs() }}
          onFinish={(values: { delivered_at?: dayjs.Dayjs; remark?: string }) =>
            deliverMutation.mutate({
              delivered_at: toDateTimeParam(values.delivered_at) ?? undefined,
              remark: values.remark?.trim() || undefined,
            })
          }
        >
          <Form.Item name="delivered_at" label="签收时间">
            <DatePicker showTime format={DATETIME_FORMAT} className="w-full" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} maxLength={255} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={deliverMutation.isPending}>
            确认签收
          </Button>
        </Form>
      </Modal>
    </FormPageContainer>
  );
}
