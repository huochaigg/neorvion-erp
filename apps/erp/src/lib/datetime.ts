import dayjs, { type Dayjs } from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';

dayjs.extend(customParseFormat);

export const DATE_FORMAT = 'YYYY-MM-DD';
export const DATETIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';

type DateRangeValue = [Dayjs | null | undefined, Dayjs | null | undefined] | null | undefined;

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format(DATE_FORMAT) : value;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format(DATETIME_FORMAT) : value;
}

export function toDateParam(value: Dayjs | string | null | undefined): string | null {
  if (value == null || value === '') {
    return null;
  }
  const parsed = typeof value === 'string' ? dayjs(value) : value;
  return parsed.isValid() ? parsed.format(DATE_FORMAT) : null;
}

export function fromDateParam(value: string | null | undefined): Dayjs | null {
  if (!value) {
    return null;
  }
  const parsed = dayjs(value, DATE_FORMAT, true);
  if (parsed.isValid()) {
    return parsed;
  }
  const fallback = dayjs(value);
  return fallback.isValid() ? fallback : null;
}

export function rangeToDateTimes(
  dates: DateRangeValue,
): { from: string | undefined; to: string | undefined } {
  if (!dates?.[0] || !dates[1]) {
    return { from: undefined, to: undefined };
  }
  return {
    from: `${dates[0].format(DATE_FORMAT)}T00:00:00`,
    to: `${dates[1].format(DATE_FORMAT)}T23:59:59`,
  };
}

export function rangeToDates(
  dates: DateRangeValue,
): { from: string | undefined; to: string | undefined } {
  if (!dates?.[0] || !dates[1]) {
    return { from: undefined, to: undefined };
  }
  return {
    from: dates[0].format(DATE_FORMAT),
    to: dates[1].format(DATE_FORMAT),
  };
}
