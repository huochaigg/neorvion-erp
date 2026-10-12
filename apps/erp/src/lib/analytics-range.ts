import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { DATE_FORMAT, toDateParam } from '@/lib/datetime';

export type AnalyticsDateRange = [Dayjs, Dayjs];

export function defaultAnalyticsRange(): AnalyticsDateRange {
  const end = dayjs();
  return [end.subtract(29, 'day'), end];
}

export function analyticsRangePresets(): { label: string; value: AnalyticsDateRange }[] {
  const today = dayjs();
  return [
    { label: '今天', value: [today, today] },
    { label: '最近 7 天', value: [today.subtract(6, 'day'), today] },
    { label: '最近 30 天', value: [today.subtract(29, 'day'), today] },
    { label: '本月', value: [today.startOf('month'), today] },
    {
      label: '上月',
      value: [today.subtract(1, 'month').startOf('month'), today.subtract(1, 'month').endOf('month')],
    },
  ];
}

export function rangeToAnalyticsParams(range: AnalyticsDateRange | null | undefined): {
  startDate: string;
  endDate: string;
} {
  const fallback = defaultAnalyticsRange();
  const start = range?.[0] ?? fallback[0];
  const end = range?.[1] ?? fallback[1];
  return {
    startDate: toDateParam(start) ?? start.format(DATE_FORMAT),
    endDate: toDateParam(end) ?? end.format(DATE_FORMAT),
  };
}
