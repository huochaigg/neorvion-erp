import { useQuery } from '@tanstack/react-query';
import { Select } from 'antd';
import { useState } from 'react';
import { listErpOptions, type ErpOptionKind } from '@/api/erpOptions';
import { useCopilotStore } from '@/store';

export function RemoteErpSelect({kind,value,onChange,placeholder}:{kind:ErpOptionKind;value?:number;onChange?:(value:number)=>void;placeholder:string}) {
  const tenantId = useCopilotStore((state)=>state.tenantId);
  const [keyword,setKeyword] = useState('');
  const query = useQuery({
    queryKey:['tenant',tenantId,'erp-options',kind,keyword],
    queryFn:({signal})=>listErpOptions(kind,keyword,signal),
    enabled:tenantId!=null,
  });
  const options = [...(query.data ?? [])];
  if (value && !options.some((item)=>item.value===value)) options.unshift({value,label:`ID ${value}`});
  return <Select className="w-full" showSearch filterOption={false} value={value} onChange={onChange} onSearch={setKeyword} options={options} loading={query.isFetching} placeholder={placeholder} />;
}
