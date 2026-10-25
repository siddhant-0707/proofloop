import { useId } from "react";

/** Cascade's mark: three falling waves on a sky-to-teal tile. */
export default function Logo({ className = "size-9" }: { className?: string }) {
  const tile = useId();
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <defs>
        <linearGradient id={tile} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#0ea5e9" />
          <stop offset="100%" stopColor="#10b981" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#${tile})`} />
      <g fill="none" stroke="white" strokeLinecap="round" strokeWidth="2.6">
        <path d="M9 13c3.7-3 7.3 3 11 0s7.3 3 11 0" opacity="0.55" />
        <path d="M9 20c3.7-3 7.3 3 11 0s7.3 3 11 0" opacity="0.8" />
        <path d="M9 27c3.7-3 7.3 3 11 0s7.3 3 11 0" />
      </g>
    </svg>
  );
}
