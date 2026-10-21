import React, { useState, useEffect } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { RefreshCw, AlertCircle } from 'lucide-react';

export function LoadingScreen({
  step = 0,
  statusText = 'Checking your session...',
  onRetry,
  timeoutError = false,
}) {
  const prefersReduced = useReducedMotion();
  const [progress, setProgress] = useState(20);

  useEffect(() => {
    // Smoothly increment progress according to step
    const target = Math.min(95, Math.max(20, (step + 1) * 25));
    setProgress(target);
  }, [step]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#0A0A0A] text-[#F5F1E6] select-none p-4"
      style={{
        backgroundImage: 'radial-gradient(circle at 50% 45%, rgba(212,175,55,0.08) 0%, transparent 60%)',
      }}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-col items-center max-w-sm w-full space-y-6">
        {/* Animated Gold Envelope Logo */}
        <div className="relative w-20 h-20 flex items-center justify-center">
          {/* Subtle Outer Glow */}
          <div className="absolute inset-0 rounded-full bg-[#D4AF37]/10 blur-xl animate-pulse" />

          <svg
            className="w-16 h-16 relative"
            viewBox="0 0 64 64"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Envelope Outline Body */}
            <motion.rect
              x="6"
              y="16"
              width="52"
              height="36"
              rx="6"
              stroke="#D4AF37"
              strokeWidth="2.5"
              fill="#121212"
              initial={prefersReduced ? { pathLength: 1 } : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1.2, ease: 'easeInOut' }}
            />
            {/* Top Flap Path */}
            <motion.path
              d="M8 18L32 36L56 18"
              stroke="#F2D675"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={prefersReduced ? { pathLength: 1 } : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1.4, delay: 0.3, ease: 'easeInOut' }}
            />
            {/* Bottom Inner Creases */}
            <motion.path
              d="M8 50L24 34M56 50L40 34"
              stroke="rgba(212,175,55,0.4)"
              strokeWidth="2"
              strokeLinecap="round"
              initial={prefersReduced ? { opacity: 1 } : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8, delay: 0.6 }}
            />
          </svg>
        </div>

        {/* Brand App Name */}
        <div className="text-center space-y-1">
          <h2 className="text-base font-bold tracking-tight text-[#F2D675] uppercase tracking-wider text-xs">
            Mail Assistant
          </h2>
          <p className="text-[11px] text-[#A59F8F]">Smart Dispatcher</p>
        </div>

        {/* Thin Gold Progress Bar */}
        {!timeoutError && (
          <div className="w-56 bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] rounded-full h-1.5 overflow-hidden">
            <motion.div
              className="h-full bg-[linear-gradient(90deg,#D4AF37,#F2D675)] shadow-[0_0_10px_rgba(212,175,55,0.6)] rounded-full"
              initial={{ width: '15%' }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: prefersReduced ? 0 : 0.4, ease: 'easeOut' }}
            />
          </div>
        )}

        {/* Real-time Status Text or Timeout Error */}
        <div className="text-center min-h-12 flex flex-col items-center justify-center">
          {timeoutError ? (
            <div className="space-y-3">
              <div className="flex items-center gap-1.5 text-xs text-[#FF9F43] justify-center font-medium">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>Taking longer than usual to connect.</span>
              </div>
              <Button
                variant="primary"
                size="sm"
                onClick={onRetry}
                className="text-xs"
              >
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                Retry Connection
              </Button>
            </div>
          ) : (
            <motion.p
              key={statusText}
              initial={prefersReduced ? { opacity: 1 } : { opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-xs text-[#D4AF37] font-mono tracking-tight"
            >
              {statusText}
            </motion.p>
          )}
        </div>
      </div>
    </div>
  );
}
