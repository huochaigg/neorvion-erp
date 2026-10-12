import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useTabsStore } from '@/stores/tabs-store';

/** 详情页加载到业务编号后可更新当前 Tab 标题；不调用也不影响 Tab 创建。 */
export function useTabTitle(title: string | undefined) {
  const pathname = useLocation().pathname;
  const setTitle = useTabsStore((state) => state.setTitle);

  useEffect(() => {
    if (!title) {
      return;
    }
    setTitle(pathname, title);
  }, [pathname, setTitle, title]);
}
