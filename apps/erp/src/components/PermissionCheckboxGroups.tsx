import {
  groupPermissionsByModule,
  permissionModuleLabel,
  toggleModulePermissionIds,
  type PermissionInfo,
} from '@neorvion/shared';
import { Checkbox } from 'antd';

interface PermissionCheckboxGroupsProps {
  value?: number[];
  onChange?: (ids: number[]) => void;
  items: PermissionInfo[];
  disabled?: boolean;
}

export function PermissionCheckboxGroups({
  value = [],
  onChange,
  items,
  disabled,
}: PermissionCheckboxGroupsProps) {
  const grouped = groupPermissionsByModule(items);
  const selected = new Set(value);

  return (
    <div className="flex flex-col gap-4">
      {grouped.map(([module, moduleItems]) => {
        const ids = moduleItems.map((item) => item.id);
        const checkedCount = ids.filter((id) => selected.has(id)).length;
        const allChecked = ids.length > 0 && checkedCount === ids.length;
        const indeterminate = checkedCount > 0 && !allChecked;
        return (
          <div key={module} className="rounded-md border border-slate-200 p-3">
            <Checkbox
              className="mb-2 font-medium"
              checked={allChecked}
              indeterminate={indeterminate}
              disabled={disabled}
              onChange={(event) => onChange?.(toggleModulePermissionIds(value, ids, event.target.checked))}
            >
              {permissionModuleLabel(module)}
            </Checkbox>
            <div className="flex flex-wrap gap-x-4 gap-y-2 pl-6">
              {moduleItems.map((item) => (
                <Checkbox
                  key={item.id}
                  checked={selected.has(item.id)}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange?.(toggleModulePermissionIds(value, [item.id], event.target.checked))
                  }
                >
                  {item.name}
                </Checkbox>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
