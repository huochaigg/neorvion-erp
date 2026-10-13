import type { ReactNode } from 'react';

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[\d+\])/g;
  let last = 0;
  let match = pattern.exec(text);
  let key = 0;
  while (match) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    const token = match[0];
    if (token.startsWith('**')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('`')) {
      nodes.push(
        <code key={key} className="rounded bg-slate-100 px-1 text-[12px]">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(
        <sup key={key} className="mx-0.5 text-[#1890ff]">
          {token}
        </sup>,
      );
    }
    key += 1;
    last = match.index + token.length;
    match = pattern.exec(text);
  }
  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return nodes;
}

interface ChatMarkdownProps {
  text: string;
}

/** 轻量 Markdown：转义 HTML，支持粗体、行内代码、引用编号。 */
export function ChatMarkdown({ text }: ChatMarkdownProps) {
  const safe = escapeHtml(text);
  const blocks = safe.split('\n');
  return (
    <div className="whitespace-pre-wrap break-words text-[14px] leading-6 text-slate-800">
      {blocks.map((line, index) => (
        <span key={index}>
          {renderInline(line)}
          {index < blocks.length - 1 ? '\n' : null}
        </span>
      ))}
    </div>
  );
}
