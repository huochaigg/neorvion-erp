import { Sparkles } from 'lucide-react';

export function BrandMark({ size = 36 }: { size?: number }) {
  const icon = Math.max(14, Math.round(size * 0.52));
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center"
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.32),
        color: '#fff',
        background: 'linear-gradient(135deg, #4F8CFF 0%, #8B5CF6 100%)',
        boxShadow: '0 8px 20px rgba(99, 102, 241, 0.28)',
      }}
    >
      <Sparkles size={icon} strokeWidth={2.2} color="#fff" fill="none" />
    </span>
  );
}
