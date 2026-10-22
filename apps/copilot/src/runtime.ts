import type { ShellToErpProps } from '@neorvion/shared';
export const shellProps=():ShellToErpProps=>typeof window==='undefined'?{token:null,tenantId:null,user:null}:(window.$wujie?.props??{token:null,tenantId:null,user:null});
