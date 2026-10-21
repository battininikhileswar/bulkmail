import React from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { cn } from '@/lib/utils';

export const Button = React.forwardRef(({
  className,
  variant = 'primary',
  size = 'sm',
  disabled = false,
  children,
  onClick,
  type = 'button',
  ...props
}, ref) => {
  const prefersReduced = useReducedMotion();

  const variantStyles = {
    primary:
      'bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] text-[#0A0A0A] font-semibold hover:shadow-[0_0_16px_rgba(212,175,55,0.45)] hover:brightness-105 active:brightness-95 disabled:opacity-40 disabled:shadow-none',
    outline:
      'border border-[rgba(212,175,55,0.3)] bg-[#121212] text-[#F2D675] hover:bg-[#1A1A1A] hover:border-[rgba(212,175,55,0.65)] hover:text-[#F5F1E6] active:bg-[#222] disabled:opacity-40',
    secondary:
      'border border-[rgba(212,175,55,0.22)] bg-[#1A1A1A] text-[#F5F1E6] hover:bg-[rgba(212,175,55,0.12)] hover:border-[rgba(212,175,55,0.45)] active:bg-[#222] disabled:opacity-40',
    danger:
      'bg-[#FF5C5C] text-[#0A0A0A] font-semibold hover:bg-[#ff7070] hover:shadow-[0_0_12px_rgba(255,92,92,0.35)] disabled:opacity-40',
    ghost:
      'text-[#A59F8F] hover:text-[#F2D675] hover:bg-[#1A1A1A] disabled:opacity-40',
  };

  const sizeStyles = {
    xs: 'text-[11px] px-2 py-1 rounded-md gap-1',
    sm: 'text-xs px-3 py-1.5 rounded-md gap-1.5',
    md: 'text-sm px-4 py-2 rounded-md gap-2',
    lg: 'text-base px-6 py-2.5 rounded-lg gap-2.5',
  };

  return (
    <motion.button
      ref={ref}
      type={type}
      disabled={disabled}
      onClick={onClick}
      whileHover={!disabled && !prefersReduced ? { scale: 1.02 } : undefined}
      whileTap={!disabled && !prefersReduced ? { scale: 0.98 } : undefined}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      className={cn(
        'inline-flex items-center justify-center font-medium transition-all cursor-pointer select-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D4AF37] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0A0A0A]',
        'disabled:cursor-not-allowed disabled:pointer-events-none',
        variantStyles[variant] || variantStyles.primary,
        sizeStyles[size] || sizeStyles.sm,
        className
      )}
      {...props}
    >
      {children}
    </motion.button>
  );
});

Button.displayName = 'Button';
