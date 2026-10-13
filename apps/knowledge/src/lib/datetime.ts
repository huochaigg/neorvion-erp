import dayjs from 'dayjs';

export const DATETIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format(DATETIME_FORMAT) : value;
}
