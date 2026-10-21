import React, { useEffect } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  maxWidth = 'max-w-md',
}) {
  const prefersReduced = useReducedMotion();

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            className="fixed inset-0 bg-[#0A0A0A]/85 backdrop-blur-sm"
          />

          {/* Modal Content */}
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={prefersReduced ? { opacity: 0 } : { opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={prefersReduced ? { opacity: 0 } : { opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className={cn(
              'relative w-full glass-strong z-10 overflow-hidden text-[#F5F1E6]',
              maxWidth
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-[rgba(212,175,55,0.18)]">
              <h3 className="text-sm font-semibold text-[#F2D675]">{title}</h3>
              <button
                type="button"
                onClick={onClose}
                className="text-[#A59F8F] hover:text-[#F5F1E6] rounded-md p-1 hover:bg-[#1A1A1A] transition-colors"
                aria-label="Close modal"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="p-5 max-h-[80vh] overflow-y-auto">
              {children}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

export function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title = 'Confirm Action',
  description = 'Are you sure you want to proceed?',
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'primary',
  loading = false,
  children,
}) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title}>
      <div className="space-y-4">
        <p className="text-xs text-[#A59F8F] leading-relaxed">{description}</p>
        {children}
        <div className="flex justify-end gap-2.5 pt-2 border-t border-[rgba(212,175,55,0.15)]">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={loading}>
            {cancelText}
          </Button>
          <Button variant={variant} size="sm" onClick={onConfirm} disabled={loading}>
            {loading ? 'Processing...' : confirmText}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export const ConfirmDialog = ConfirmModal;

