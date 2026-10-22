import { describe,expect,it } from 'vitest'; import { SafeMarkdown } from './SafeMarkdown';
describe('SafeMarkdown',()=>{it('不使用 HTML 注入',()=>{const element=SafeMarkdown({text:'<img src=x onerror=alert(1)>'});expect(element.props.dangerouslySetInnerHTML).toBeUndefined();expect(JSON.stringify(element.props.children)).toContain('<img src=x')})});
