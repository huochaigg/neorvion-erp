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
        <strong key={key}>{token.slice(2, -2)}</strong>
      ) : (
        <code key={key} className="rounded bg-slate-100 px-1 text-xs">
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

/** 仅构造 React 文本节点的轻量 Markdown，不解析 HTML、链接或可执行内容。 */
export function SafeMarkdown({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="whitespace-pre-wrap break-words text-sm leading-6">
      {lines.map((line, index) => (
        <span key={index}>
          {renderInline(line)}
          {index < lines.length - 1 ? '\n' : null}
        </span>
      ))}
    </div>
  );
}
