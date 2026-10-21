import React, { createContext, useContext, useState, useCallback } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';
import { cn } from '@/lib/utils';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const prefersReduced = useReducedMotion();

  const addToast = useCallback((msg, type = 'info', duration = 3500) => {
    const id = Date.now() + Math.random().toString(36).substring(2, 6);
    setToasts((prev) => [...prev, { id, msg, type }]);

    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
    }
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = {
    success: (msg, duration) => addToast(msg, 'success', duration),
    error: (msg, duration) => addToast(msg, 'error', duration),
    warning: (msg, duration) => addToast(msg, 'warning', duration),
    info: (msg, duration) => addToast(msg, 'info', duration),
  };

  const icons = {
    success: <CheckCircle2 className="w-4 h-4 text-[#3DDC97] flex-shrink-0" />,
    error: <AlertCircle className="w-4 h-4 text-[#FF5C5C] flex-shrink-0" />,
    warning: <AlertTriangle className="w-4 h-4 text-[#FF9F43] flex-shrink-0" />,
    info: <Info className="w-4 h-4 text-[#6EA8FF] flex-shrink-0" />,
  };

  const borderStyles = {
    success: 'border-[#3DDC97]/40',
    error: 'border-[#FF5C5C]/40',
    warning: 'border-[#FF9F43]/40',
    info: 'border-[#6EA8FF]/40',
  };

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div
        className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none"
        aria-live="polite"
      >
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              initial={prefersReduced ? { opacity: 0 } : { opacity: 0, y: -10, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={prefersReduced ? { opacity: 0 } : { opacity: 0, y: -10, scale: 0.96 }}
              transition={{ duration: 0.2 }}
              className={cn(
                'pointer-events-auto flex items-start gap-2.5 p-3.5 glass-strong text-xs text-[#F5F1E6]',
                borderStyles[t.type] || 'border-[rgba(212,175,55,0.3)]'
              )}
            >
              {icons[t.type]}
              <div className="flex-1 min-w-0 pt-0.5 leading-snug">{t.msg}</div>
              <button
                type="button"
                onClick={() => removeToast(t.id)}
                className="text-[#A59F8F] hover:text-[#F5F1E6] rounded p-0.5"
                aria-label="Dismiss toast"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
