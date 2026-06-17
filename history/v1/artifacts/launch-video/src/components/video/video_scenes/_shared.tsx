import type { ReactNode } from 'react';

export function CenterScrim({ intensity = 0.8 }: { intensity?: number }) {
  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{
        background: `radial-gradient(ellipse 62% 52% at 50% 50%, rgba(0,0,0,${intensity}) 0%, rgba(0,0,0,${intensity * 0.55}) 38%, transparent 76%)`,
      }}
    />
  );
}

export function EditorialLabel({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`font-body uppercase text-white/50 font-medium ${className}`}
      style={{ letterSpacing: '0.14em' }}
    >
      {children}
    </span>
  );
}
