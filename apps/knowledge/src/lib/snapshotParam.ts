/** 从实验/运行保存的参数快照取值。缺 key 显示「未记录」，禁止用当前系统默认值冒充历史配置。 */
export function snapshotParam(config: Record<string, unknown> | null | undefined, key: string): string {
  if (!config || !(key in config) || config[key] === undefined) {
    return '未记录';
  }
  const value = config[key];
  if (value === null) {
    return '未指定';
  }
  if (typeof value === 'boolean') {
    return value ? '开' : '关';
  }
  if (Array.isArray(value)) {
    return value.length ? value.join(',') : '未指定';
  }
  return String(value);
}
