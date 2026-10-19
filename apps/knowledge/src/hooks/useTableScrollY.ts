import { useEffect, useRef, useState } from 'react';

const FALLBACK_HEADER = 39;
const FALLBACK_PAGINATION = 64;
const GAP = 8;

function blockSize(el: HTMLElement | null, fallback: number): number {
  if (!el) {
    return fallback;
  }
  const style = window.getComputedStyle(el);
  return Math.ceil(
    el.getBoundingClientRect().height +
      (Number.parseFloat(style.marginTop) || 0) +
      (Number.parseFloat(style.marginBottom) || 0),
  );
}

export function measureTableScrollY(container: HTMLElement, hasPagination: boolean): number {
  const header =
    container.querySelector<HTMLElement>('.ant-table-header') ??
    container.querySelector<HTMLElement>('.ant-table-thead');
  const pagination = container.querySelector<HTMLElement>('.ant-table-pagination');
  const headerHeight = blockSize(header, FALLBACK_HEADER);
  const paginationHeight = hasPagination ? blockSize(pagination, FALLBACK_PAGINATION) : 0;
  return Math.max(
    0,
    Math.floor(container.clientHeight - headerHeight - paginationHeight - GAP),
  );
}

export function useTableScrollY(hasPagination = true) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollY, setScrollY] = useState(320);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) {
      return;
    }
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        setScrollY(measureTableScrollY(node, hasPagination));
      });
    };
    update();
    const resizeObserver = new ResizeObserver(update);
    resizeObserver.observe(node);
    const mutationObserver = new MutationObserver(update);
    mutationObserver.observe(node, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      mutationObserver.disconnect();
    };
  }, [hasPagination]);

  return { containerRef, scrollY };
}
