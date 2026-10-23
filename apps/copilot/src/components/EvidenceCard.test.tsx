import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { EvidenceCard } from './EvidenceCard';

describe('EvidenceCard', () => {
  it('区分 ERP 与 Knowledge 来源并显示服务端引用编号', () => {
    const html = renderToStaticMarkup(
      <EvidenceCard items={[
        {
          citation_id: 'E1', source_type: 'ERP', resource_type: 'get_inventory',
          resource_id: 'SKU-1', knowledge_base_id: null, document_id: null, chunk_id: null,
          title: 'ERP 库存', excerpt: '可用库存 7', source_version: null, metadata: {},
          observed_at: '2026-10-23T00:00:00Z', access_status: 'ACTIVE',
        },
        {
          citation_id: 'K2', source_type: 'KNOWLEDGE', resource_type: 'knowledge_chunk',
          resource_id: '31', knowledge_base_id: 11, document_id: 21, chunk_id: 31,
          title: '退货制度.md', excerpt: null, source_version: 4, metadata: {},
          observed_at: '2026-10-23T00:00:00Z', access_status: 'FORBIDDEN',
        },
      ]} />,
    );
    expect(html).toContain('[E1]');
    expect(html).toContain('[K2]');
    expect(html).toContain('ERP 库存');
    expect(html).toContain('退货制度.md');
    expect(html).not.toContain('可用库存 7');
  });
});
