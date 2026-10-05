import { Table, Tooltip } from 'antd';
import type { TableProps } from 'antd';
import type { ReactNode } from 'react';
import { useTableScrollY } from '@/hooks/useTableScrollY';
import styles from './AppTable.module.scss';

type AppTableProps<RecordType> = TableProps<RecordType> & {
  fillHeight?: boolean;
};

export function AppTable<RecordType extends object>({
  fillHeight = true,
  className,
  scroll,
  pagination,
  size = 'middle',
  ...rest
}: AppTableProps<RecordType>) {
  const hasPagination = pagination !== false;
  const { containerRef, scrollY } = useTableScrollY(hasPagination);
  const mergedScroll = fillHeight
    ? { x: 'max-content' as const, y: scrollY, ...scroll }
    : { x: 'max-content' as const, ...scroll };

  return (
    <div ref={fillHeight ? containerRef : undefined} className={fillHeight ? styles.tableFill : undefined}>
      <Table<RecordType>
        size={size}
        className={[styles.table, className].filter(Boolean).join(' ')}
        scroll={mergedScroll}
        pagination={
          pagination === false
            ? false
            : {
                showSizeChanger: true,
                ...pagination,
              }
        }
        {...rest}
      />
    </div>
  );
}

export function EllipsisCell({ value }: { value: ReactNode }) {
  const text = value == null || value === '' ? '-' : String(value);
  return (
    <Tooltip title={text === '-' ? undefined : text}>
      <span className={styles.nowrap}>{text}</span>
    </Tooltip>
  );
}

export function CodeCell({ value }: { value: string | null | undefined }) {
  const text = value?.trim() ? value : '-';
  return (
    <Tooltip title={text === '-' ? undefined : text}>
      <code className={styles.code}>{text}</code>
    </Tooltip>
  );
}

export function ActionCell({ children }: { children: ReactNode }) {
  return <div className={styles.actions}>{children}</div>;
}
