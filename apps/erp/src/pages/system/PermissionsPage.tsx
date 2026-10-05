import { ApiError, permissionModuleLabel, tenantPermissionsQueryKey, type PermissionInfo } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { fetchPermissions } from '@/api/roles';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { ListPageContainer, ListTableArea } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

export function PermissionsPage(props: PageProps) {
  const { tenantId } = usePermissions();
  const query = useQuery({
    queryKey: tenantPermissionsQueryKey(tenantId),
    queryFn: ({ signal }) => fetchPermissions(signal),
    enabled: tenantId != null,
  });

  const columns: ColumnsType<PermissionInfo> = [
    {
      title: '权限名称',
      dataIndex: 'name',
      width: 160,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '权限编码',
      dataIndex: 'code',
      width: 280,
      render: (value: string) => <CodeCell value={value} />,
    },
    {
      title: '所属模块',
      dataIndex: 'module',
      width: 120,
      render: (value: string) => <Tag>{permissionModuleLabel(value)}</Tag>,
    },
    {
      title: '说明',
      dataIndex: 'description',
      width: 260,
      render: (value: string | null) => <EllipsisCell value={value} />,
    },
    {
      title: '状态',
      dataIndex: 'deprecated',
      width: 90,
      render: (value: boolean | undefined) =>
        value ? <Tag color="warning">已废弃</Tag> : <Tag>有效</Tag>,
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '权限目录'}
        description={
          props.description ?? '只读查看系统当前支持的权限。新增业务权限由代码与 seed 同步，不能在此增删。'
        }
      />
      {query.isError ? (
        <p className="mb-3 shrink-0 text-sm text-red-600">
          {query.error instanceof ApiError ? query.error.message : '无法加载权限目录'}
        </p>
      ) : null}
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data}
          pagination={false}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}
