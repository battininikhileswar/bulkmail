import React from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { cn } from '@/lib/utils';

export function AnimatedProgressBar({
  value = 0,
  max = 100,
  className,
  color = 'bg-[linear-gradient(90deg,#D4AF37,#F2D675)]',
}) {
  const prefersReduced = useReducedMotion();
  const percentage = max > 0 ? Math.min(100, Math.max(0, Math.round((value / max) * 100))) : 0;

  return (
    <div className={cn('w-full bg-[#1A1A1A] border border-[rgba(212,175,55,0.18)] rounded-full h-2 overflow-hidden', className)}>
      <motion.div
        className={cn('h-full rounded-full shadow-[0_0_8px_rgba(212,175,55,0.5)]', color)}
        initial={{ width: 0 }}
        animate={{ width: `${percentage}%` }}
        transition={
          prefersReduced
            ? { duration: 0 }
            : { duration: 0.35, ease: 'easeOut' }
        }
      />
    </div>
  );
}
