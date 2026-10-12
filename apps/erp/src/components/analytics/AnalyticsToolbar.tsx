import { warehousesQueryKey, WAREHOUSE_STATUS } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Select, Space } from 'antd';
import type { Dayjs } from 'dayjs';
import type { ReactNode } from 'react';
import { fetchWarehouses } from '@/api/warehouses';
import { AppRangePicker } from '@/components/AppDatePicker';
import { analyticsRangePresets } from '@/lib/analytics-range';
import { usePermissions } from '@/hooks/usePermissions';

interface AnalyticsToolbarProps {
  range: [Dayjs, Dayjs];
  onRangeChange: (range: [Dayjs, Dayjs]) => void;
  warehouseId?: number;
  onWarehouseChange?: (warehouseId: number | undefined) => void;
  extra?: ReactNode;
  onRefresh?: () => void;
  showWarehouse?: boolean;
}

export function AnalyticsToolbar({
  range,
  onRangeChange,
  warehouseId,
  onWarehouseChange,
  extra,
  onRefresh,
  showWarehouse = true,
}: AnalyticsToolbarProps) {
  const { tenantId } = usePermissions();
  const warehouses = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: showWarehouse && tenantId != null,
  });

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <AppRangePicker
        value={range}
        allowClear={false}
        presets={analyticsRangePresets()}
        onChange={(dates) => {
          if (dates?.[0] && dates[1]) {
            onRangeChange([dates[0], dates[1]]);
          }
        }}
      />
      {showWarehouse ? (
        <Select
          allowClear
          placeholder="全部仓库"
          className="min-w-40"
          value={warehouseId}
          onChange={(value) => onWarehouseChange?.(value)}
          options={(warehouses.data?.items ?? []).map((item) => ({
            value: item.id,
            label: item.name,
          }))}
        />
      ) : null}
      <Space>
        {extra}
        {onRefresh ? (
          <Button onClick={onRefresh}>刷新</Button>
        ) : null}
      </Space>
    </div>
  );
}
