import { useQuery } from '@tanstack/react-query';
import { Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { fetchMenus, type IamMenu } from '@/api/catalog';
import { AppTable } from '@/components/AppTable';
import { ListPageContainer, ListTableArea } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import type { PageProps } from '@/router/types';

export function MenusPage(_props: PageProps) {
  const query = useQuery({
    queryKey: ['iam', 'menus'],
    queryFn: ({ signal }) => fetchMenus(signal),
  });
  const columns: ColumnsType<IamMenu> = [
    { title: 'Key', dataIndex: 'menu_key', width: 220 },
    { title: '标题', dataIndex: 'title' },
    { title: '类型', dataIndex: 'menu_type', width: 100 },
    { title: '路径', dataIndex: 'path' },
    { title: '权限编码', dataIndex: 'permission_code', width: 220 },
    {
      title: '可见',
      dataIndex: 'visible',
      width: 80,
      render: (value: boolean) => (value ? <Tag color="success">是</Tag> : <Tag>否</Tag>),
    },
    {
      title: '锁定',
      dataIndex: 'locked',
      width: 80,
      render: (value: boolean) => (value ? '已锁定' : '未锁定'),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title="菜单管理" description="业务服务启动时不得覆盖管理员已锁定的菜单配置。" />
      <ListTableArea>
        <AppTable rowKey="id" loading={query.isLoading} columns={columns} dataSource={query.data ?? []} />
      </ListTableArea>
    </ListPageContainer>
  );
}
