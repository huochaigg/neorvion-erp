interface MetricBarItem {
  label: string;
  value: number | null | undefined;
  percent?: boolean;
}

export function MetricBars({ items }: { items: MetricBarItem[] }) {
  return (
    <div className="space-y-2">
      {items.map((item) => {
        const value = typeof item.value === 'number' ? item.value : 0;
        const width = item.percent === false ? Math.min(100, value) : Math.min(100, Math.max(0, value * 100));
        const text =
          item.value == null
            ? '-'
            : item.percent === false
              ? String(Math.round(value * 100) / 100)
              : `${(value * 100).toFixed(1)}%`;
        return (
          <div key={item.label}>
            <div className="mb-1 flex justify-between text-xs text-slate-600">
              <span>{item.label}</span>
              <span>{text}</span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-slate-100">
              <div className="h-2 rounded bg-sky-500" style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function GroupedMetricBars({
  series,
}: {
  series: { name: string; color: string; values: { label: string; value: number | null }[] }[];
}) {
  const labels = series[0]?.values.map((item) => item.label) ?? [];
  return (
    <div className="space-y-3">
      {labels.map((label, index) => (
        <div key={label}>
          <div className="mb-1 text-xs text-slate-600">{label}</div>
          <div className="space-y-1">
            {series.map((item) => {
              const value = item.values[index]?.value;
              const width = value == null ? 0 : Math.min(100, Math.max(0, value * 100));
              return (
                <div key={item.name} className="flex items-center gap-2">
                  <span className="w-24 truncate text-[11px] text-slate-500">{item.name}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded bg-slate-100">
                    <div className="h-2 rounded" style={{ width: `${width}%`, background: item.color }} />
                  </div>
                  <span className="w-14 text-right text-[11px] text-slate-500">
                    {value == null ? '-' : `${(value * 100).toFixed(1)}%`}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
