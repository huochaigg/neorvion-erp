import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import dayjs from 'dayjs';
import {
  DATE_FORMAT,
  DATETIME_FORMAT,
  formatDate,
  formatDateTime,
  fromDateParam,
  rangeToDateTimes,
  rangeToDates,
  toDateParam,
  toDateTimeParam,
} from './datetime';

describe('日期展示与 API 转换', () => {
  it('空值显示为 -，有效值统一为 YYYY-MM-DD / YYYY-MM-DD HH:mm:ss', () => {
    assert.equal(formatDate(null), '-');
    assert.equal(formatDate(''), '-');
    assert.equal(formatDate('2026-10-15'), '2026-10-15');
    assert.equal(formatDateTime('2026-10-15T08:09:10'), '2026-10-15 08:09:10');
    assert.equal(DATE_FORMAT, 'YYYY-MM-DD');
    assert.equal(DATETIME_FORMAT, 'YYYY-MM-DD HH:mm:ss');
  });

  it('DatePicker 的 dayjs 提交为 YYYY-MM-DD，不把 dayjs 对象传给 API', () => {
    assert.equal(toDateParam(dayjs('2026-10-15')), '2026-10-15');
    assert.equal(toDateParam(null), null);
    assert.equal(toDateParam('2026-10-15'), '2026-10-15');
    const back = fromDateParam('2026-10-15');
    assert.equal(back?.format(DATE_FORMAT), '2026-10-15');
    assert.equal(fromDateParam(null), null);
  });

  it('DateTimePicker 提交本地墙钟时间，不转 UTC', () => {
    assert.equal(toDateTimeParam(dayjs('2026-10-09 16:17:25')), '2026-10-09T16:17:25');
    assert.equal(toDateTimeParam(null), null);
    assert.equal(toDateTimeParam('2026-10-09 16:17:25'), '2026-10-09T16:17:25');
  });

  it('RangePicker 转查询参数：创建时间带时分秒，预计到货只到日期', () => {
    const range: [dayjs.Dayjs, dayjs.Dayjs] = [dayjs('2026-10-01'), dayjs('2026-10-05')];
    assert.deepEqual(rangeToDateTimes(range), {
      from: '2026-10-01T00:00:00',
      to: '2026-10-05T23:59:59',
    });
    assert.deepEqual(rangeToDates(range), {
      from: '2026-10-01',
      to: '2026-10-05',
    });
    assert.deepEqual(rangeToDates(null), { from: undefined, to: undefined });
  });
});
