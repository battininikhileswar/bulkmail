import React from 'react';
import { cn } from '@/lib/utils';
import { Inbox } from 'lucide-react';

export function EmptyState({
  icon: Icon = Inbox,
  title = 'No items found',
  description,
  className,
  action,
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center py-10 px-4 text-center rounded-lg border border-dashed border-[rgba(212,175,55,0.2)] bg-[#121212]/50',
        className
      )}
    >
      <div className="w-9 h-9 rounded-full bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] flex items-center justify-center text-[#F2D675] mb-2.5 shadow-xs">
        <Icon className="w-5 h-5" />
      </div>
      <p className="text-xs font-semibold text-[#F5F1E6]">{title}</p>
      {description && (
        <p className="text-[11px] text-[#A59F8F] mt-0.5 max-w-sm leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
