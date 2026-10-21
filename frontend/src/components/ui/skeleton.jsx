import React from 'react';
import { cn } from '@/lib/utils';

export function Skeleton({ className, ...props }) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-md bg-[#1A1A1A] border border-[rgba(212,175,55,0.08)] relative overflow-hidden',
        'after:absolute after:inset-0 after:-translate-x-full after:animate-[shimmer_2s_infinite]',
        'after:bg-gradient-to-r after:from-transparent after:via-[rgba(212,175,55,0.06)] after:to-transparent',
        className
      )}
      {...props}
    />
  );
}

export function TableSkeleton({ rows = 5, cols = 4 }) {
  return (
    <div className="space-y-3 p-4 bg-[#121212] rounded-lg border border-[rgba(212,175,55,0.18)]">
      <div className="flex gap-4 border-b border-[rgba(212,175,55,0.1)] pb-2">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-5 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 pt-2">
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton key={j} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}
