import React from 'react';

export type BadgeVariant = 'neutral' | 'success' | 'warning' | 'error' | 'cyan' | 'indigo';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: 'sm' | 'md';
  className?: string;
  dot?: boolean;
}

const variantStyles: Record<BadgeVariant, { bg: string; text: string; border: string; dot: string }> = {
  neutral: {
    bg: 'bg-slate-800/60',
    text: 'text-slate-300',
    border: 'border-slate-700/60',
    dot: 'bg-slate-400',
  },
  success: {
    bg: 'bg-emerald-950/40',
    text: 'text-emerald-400',
    border: 'border-emerald-800/50',
    dot: 'bg-emerald-400',
  },
  warning: {
    bg: 'bg-amber-950/40',
    text: 'text-amber-400',
    border: 'border-amber-800/50',
    dot: 'bg-amber-400',
  },
  error: {
    bg: 'bg-rose-950/40',
    text: 'text-rose-400',
    border: 'border-rose-800/50',
    dot: 'bg-rose-400',
  },
  cyan: {
    bg: 'bg-cyan-950/40',
    text: 'text-cyan-400',
    border: 'border-cyan-800/50',
    dot: 'bg-cyan-400',
  },
  indigo: {
    bg: 'bg-indigo-950/40',
    text: 'text-indigo-400',
    border: 'border-indigo-800/50',
    dot: 'bg-indigo-400',
  },
};

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  size = 'md',
  className = '',
  dot = false,
}) => {
  const styles = variantStyles[variant];
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-md border ${styles.bg} ${styles.text} ${styles.border} ${sizeClasses} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${styles.dot}`} />}
      {children}
    </span>
  );
};
