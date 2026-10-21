import React from 'react';
import { cn } from '@/lib/utils';

export const Input = React.forwardRef(({
  className,
  type = 'text',
  ...props
}, ref) => {
  return (
    <input
      type={type}
      ref={ref}
      className={cn(
        'w-full px-3 py-1.5 text-sm bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] rounded-md text-[#F5F1E6]',
        'placeholder:text-[#A59F8F] transition-all duration-150',
        'hover:border-[rgba(212,175,55,0.45)]',
        'focus:outline-none focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/25 caret-[#D4AF37]',
        'disabled:cursor-not-allowed disabled:bg-[#121212] disabled:text-[#A59F8F]/50 disabled:border-[rgba(212,175,55,0.1)]',
        className
      )}
      {...props}
    />
  );
});

Input.displayName = 'Input';

export const Textarea = React.forwardRef(({
  className,
  ...props
}, ref) => {
  return (
    <textarea
      ref={ref}
      className={cn(
        'w-full p-3 text-sm bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] rounded-md text-[#F5F1E6]',
        'placeholder:text-[#A59F8F] transition-all duration-150',
        'hover:border-[rgba(212,175,55,0.45)]',
        'focus:outline-none focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/25 caret-[#D4AF37]',
        'disabled:cursor-not-allowed disabled:bg-[#121212] disabled:text-[#A59F8F]/50 disabled:border-[rgba(212,175,55,0.1)]',
        className
      )}
      {...props}
    />
  );
});

Textarea.displayName = 'Textarea';
