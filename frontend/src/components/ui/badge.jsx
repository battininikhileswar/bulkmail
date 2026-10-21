import React from 'react';
import { cn } from '@/lib/utils';
import { AlertTriangle, CheckCircle2, Clock, XCircle, UserX } from 'lucide-react';

export function StatusBadge({ status, className }) {
  const norm = (status || '').toLowerCase().trim();

  let style = 'bg-[#1A1A1A] text-[#A59F8F] border-[rgba(212,175,55,0.22)]';
  let Icon = null;
  let label = status || 'unknown';

  if (norm === 'sent' || norm === 'completed') {
    style = 'bg-[#3DDC97]/15 text-[#3DDC97] border-[#3DDC97]/40';
    Icon = CheckCircle2;
  } else if (norm === 'pending' || norm === 'pending_approval' || norm === 'draft') {
    style = 'bg-[#6EA8FF]/15 text-[#6EA8FF] border-[#6EA8FF]/40';
    Icon = Clock;
    if (norm === 'pending_approval') label = 'Pending Approval';
  } else if (norm === 'needs_review' || norm === 'manual_review') {
    style = 'bg-[#FF9F43]/15 text-[#FF9F43] border-[#FF9F43]/40';
    Icon = AlertTriangle;
    label = norm === 'manual_review' ? 'Manual Review' : 'Needs Review';
  } else if (norm === 'uncertain') {
    style = 'bg-[#FF9F43]/25 text-[#FF9F43] border-[#FF9F43]/60 font-semibold';
    Icon = AlertTriangle;
    label = 'Uncertain Delivery';
  } else if (norm === 'failed') {
    style = 'bg-[#FF5C5C]/15 text-[#FF5C5C] border-[#FF5C5C]/40';
    Icon = XCircle;
  } else if (norm === 'unsubscribed') {
    style = 'bg-[#1A1A1A] text-[#A59F8F] border-[rgba(212,175,55,0.2)] line-through';
    Icon = UserX;
  } else if (norm === 'running') {
    style = 'bg-[#D4AF37]/15 text-[#F2D675] border-[#D4AF37]/50';
    Icon = Clock;
  } else if (norm === 'paused') {
    style = 'bg-[#FF9F43]/15 text-[#FF9F43] border-[#FF9F43]/40';
    Icon = AlertTriangle;
  } else if (norm === 'stopped') {
    style = 'bg-[#1A1A1A] text-[#A59F8F] border-[rgba(212,175,55,0.2)]';
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border select-none capitalize',
        style,
        className
      )}
    >
      {Icon && <Icon className="w-3 h-3 flex-shrink-0" />}
      {label}
    </span>
  );
}

export function Badge({ children, variant = 'info', className }) {
  const variantStyles = {
    info: 'bg-[#6EA8FF]/15 text-[#6EA8FF] border-[#6EA8FF]/40',
    success: 'bg-[#3DDC97]/15 text-[#3DDC97] border-[#3DDC97]/40',
    warning: 'bg-[#FF9F43]/15 text-[#FF9F43] border-[#FF9F43]/40',
    danger: 'bg-[#FF5C5C]/15 text-[#FF5C5C] border-[#FF5C5C]/40',
    gold: 'bg-[#D4AF37]/20 text-[#F2D675] border-[#D4AF37]/50 font-semibold',
    neutral: 'bg-[#1A1A1A] text-[#A59F8F] border-[rgba(212,175,55,0.22)]',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium border select-none',
        variantStyles[variant] || variantStyles.neutral,
        className
      )}
    >
      {children}
    </span>
  );
}
