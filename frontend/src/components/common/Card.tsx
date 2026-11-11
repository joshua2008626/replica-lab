import React from 'react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  variant?: 'default' | 'elevated' | 'interactive';
  className?: string;
}

export const Card: React.FC<CardProps> = ({
  children,
  variant = 'default',
  className = '',
  ...props
}) => {
  const base = 'rounded-xl border p-5 transition-all duration-150';
  const variants = {
    default: 'bg-[#0f1422] border-[#1e2638] text-slate-200',
    elevated: 'bg-[#141b2e] border-[#253046] text-slate-100 shadow-md',
    interactive: 'bg-[#0f1422] border-[#1e2638] text-slate-200 hover:border-[#2f3d5c] hover:bg-[#12192a] cursor-pointer',
  };

  return (
    <div className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </div>
  );
};
