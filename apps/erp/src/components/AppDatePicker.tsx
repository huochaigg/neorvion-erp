import { DatePicker } from 'antd';
import type { ComponentProps } from 'react';
import { DATE_FORMAT } from '@/lib/datetime';

type DatePickerProps = ComponentProps<typeof DatePicker>;
type RangePickerProps = ComponentProps<typeof DatePicker.RangePicker>;

export function AppDatePicker(props: DatePickerProps) {
  return <DatePicker format={DATE_FORMAT} allowClear {...props} />;
}

export function AppRangePicker(props: RangePickerProps) {
  return <DatePicker.RangePicker format={DATE_FORMAT} allowClear separator="~" {...props} />;
}
