import type { ReactNode } from 'react';

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match = pattern.exec(text);
  let key = 0;
  while (match) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    nodes.push(
      token.startsWith('**') ? (
        <strong key={key} className="font-semibold text-[#0F172A]">
          {token.slice(2, -2)}
        </strong>
      ) : (
        <code key={key} className="rounded-md bg-[#F1F5F9] px-1.5 py-0.5 font-mono text-[12px] text-[#334155]">
          {token.slice(1, -1)}
        </code>
      ),
    );
    key += 1;
    last = match.index + token.length;
    match = pattern.exec(text);
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'quote'; text: string }
  | { type: 'code'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'paragraph'; text: string };

function splitRow(row: string) {
  return row
    .split('|')
    .slice(1, -1)
    .map((cell) => cell.trim());
}

function parseBlocks(text: string): Block[] {
  const lines = text.split('\n');
  const blocks: Block[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? '';
    if (line.startsWith('```')) {
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? '').startsWith('```')) {
        body.push(lines[index] ?? '');
        index += 1;
      }
      blocks.push({ type: 'code', text: body.join('\n') });
      index += 1;
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }
    if (line.startsWith('> ')) {
      const body: string[] = [];
      while (index < lines.length && (lines[index] ?? '').startsWith('> ')) {
        body.push((lines[index] ?? '').slice(2));
        index += 1;
      }
      blocks.push({ type: 'quote', text: body.join('\n') });
      continue;
    }
    const divider = index + 1 < lines.length ? (lines[index + 1] ?? '') : '';
    if (/^\|.+\|$/.test(line) && /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/.test(divider)) {
      const headers = splitRow(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && /^\|.+\|$/.test(lines[index] ?? '')) {
        rows.push(splitRow(lines[index] ?? ''));
        index += 1;
      }
      blocks.push({ type: 'table', headers, rows });
      continue;
    }
    const ordered = /^\d+\.\s+/.test(line);
    const bullet = /^[-*]\s+/.test(line);
    if (ordered || bullet) {
      const items: string[] = [];
      const pattern = ordered ? /^\d+\.\s+/ : /^[-*]\s+/;
      while (index < lines.length && pattern.test(lines[index] ?? '')) {
        items.push((lines[index] ?? '').replace(pattern, ''));
        index += 1;
      }
      blocks.push({ type: 'list', ordered, items });
      continue;
    }
    if (!line.trim()) {
      index += 1;
      continue;
    }
    const body: string[] = [];
    while (index < lines.length) {
      const current = lines[index] ?? '';
      if (
        !current.trim() ||
        current.startsWith('```') ||
        /^#{1,3}\s+/.test(current) ||
        current.startsWith('> ') ||
        /^[-*]\s+/.test(current) ||
        /^\d+\.\s+/.test(current)
      ) {
        break;
      }
      body.push(current);
      index += 1;
    }
    blocks.push({ type: 'paragraph', text: body.join('\n') });
  }
  return blocks;
}

/** 仅构造 React 文本节点的轻量 Markdown，不解析 HTML、链接或可执行内容。 */
export function SafeMarkdown({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  return (
    <div className="space-y-3 text-[15px] leading-7 text-[#0F172A]">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const Tag = block.level === 1 ? 'h3' : block.level === 2 ? 'h4' : 'h5';
          return (
            <Tag key={index} className="font-semibold tracking-tight text-[#0F172A]">
              {renderInline(block.text)}
            </Tag>
          );
        }
        if (block.type === 'quote') {
          return (
            <blockquote
              key={index}
              className="border-l-[3px] border-[#C7D2FE] bg-[#F8FAFC] px-4 py-2 text-[#475569]"
            >
              {renderInline(block.text)}
            </blockquote>
          );
        }
        if (block.type === 'code') {
          return (
            <pre
              key={index}
              className="overflow-x-auto rounded-xl bg-[#0F172A] px-4 py-3 font-mono text-[12px] leading-6 text-slate-100"
            >
              {block.text}
            </pre>
          );
        }
        if (block.type === 'list') {
          const ListTag = block.ordered ? 'ol' : 'ul';
          return (
            <ListTag
              key={index}
              className={`space-y-1 pl-5 ${block.ordered ? 'list-decimal' : 'list-disc'} text-[#334155]`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ListTag>
          );
        }
        if (block.type === 'table') {
          return (
            <div key={index} className="overflow-x-auto rounded-xl border border-[#E2E8F0]">
              <table className="min-w-full text-left text-[13px]">
                <thead className="bg-[#F8FAFC] text-[#64748B]">
                  <tr>
                    {block.headers.map((header, headerIndex) => (
                      <th key={headerIndex} className="px-3 py-2 font-medium">
                        {renderInline(header)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className="border-t border-[#E2E8F0]">
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex} className="px-3 py-2 text-[#334155]">
                          {renderInline(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={index} className="whitespace-pre-wrap break-words">
            {renderInline(block.text)}
          </p>
        );
      })}
    </div>
  );
}
