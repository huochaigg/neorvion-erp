export function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <span
      className="inline-flex items-center justify-center rounded-[14px] bg-gradient-to-br from-[#4F8CFF] to-[#8B5CF6] text-white shadow-[0_8px_20px_rgba(99,102,241,0.28)]"
      style={{ width: size, height: size }}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" width={Math.round(size * 0.52)} height={Math.round(size * 0.52)} fill="none">
        <path
          d="M12 3.5 13.7 8.4l5.3.4-4.1 3.4 1.3 5.1L12 14.8 7.8 17.3l1.3-5.1L5 8.8l5.3-.4L12 3.5Z"
          fill="currentColor"
        />
      </svg>
    </span>
  );
}
