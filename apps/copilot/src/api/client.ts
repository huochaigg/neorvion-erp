import axios from 'axios'; import { ApiError,TENANT_HEADER,type ApiResponse } from '@neorvion/shared'; import { shellProps } from '@/runtime'; import { useCopilotStore } from '@/store';
export const api=axios.create({baseURL:import.meta.env.VITE_API_BASE_URL||'http://localhost:8013',timeout:Number(import.meta.env.VITE_API_TIMEOUT_MS||8000)});
api.interceptors.request.use(c=>{const token=shellProps().token;const tenant=useCopilotStore.getState().tenantId;if(token)c.headers.Authorization=`Bearer ${token}`;if(tenant)c.headers[TENANT_HEADER]=String(tenant);return c});
api.interceptors.response.use(r=>r,e=>Promise.reject(new ApiError(e.code==='ECONNABORTED'?'请求超时，请检查会话数据库或身份服务':e.response?.data?.message||'网络异常',{status:e.response?.status??0,code:e.response?.data?.code??0})));
export async function unwrap<T>(p:Promise<{data:ApiResponse<T>}>){const {data}=await p;if(data.code!==0)throw new ApiError(data.message,{code:data.code});return data.data}
