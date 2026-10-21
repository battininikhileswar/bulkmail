import React, { useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/input';
import { StatusBadge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Modal } from '@/components/ui/modal';
import { FileText, Send, Sparkles, X, Save, AlertTriangle, CheckCircle2 } from 'lucide-react';

export function DraftsPage({
  draftFilter = 'all',
  onFilterChange,
  drafts = [],
  selectedDraftId,
  onSelectDraft,
  draftBodyEdit,
  onDraftBodyEditChange,
  savingDraft = false,
  onRegenerateDraft,
  onRejectDraft,
  onSaveDraft,
  onApproveAndSendDraft,
  settings,
  loading = false,
}) {
  const prefersReduced = useReducedMotion();
  const [showSendConfirmModal, setShowSendConfirmModal] = useState(false);

  const filterTabs = [
    { id: 'all', label: 'All Drafts' },
    { id: 'pending_approval', label: 'Pending Approval' },
    { id: 'needs_review', label: 'Needs Review' },
    { id: 'rejected', label: 'Rejected' },
  ];

  const sel = drafts.find((d) => d.id === selectedDraftId);

  const isNeedsReviewUnedited =
    sel &&
    sel.status === 'needs_review' &&
    (!draftBodyEdit.trim() || draftBodyEdit.trim() === (sel.original_body || sel.body || '').trim());

  const disableSend = savingDraft || !draftBodyEdit.trim() || isNeedsReviewUnedited;

  const handleSendClick = () => {
    setShowSendConfirmModal(true);
  };

  return (
    <div className="space-y-4">
      {/* Filter Tabs / Pills */}
      <div className="flex items-center gap-2 flex-wrap mb-4">
        {filterTabs.map((f) => {
          const isActive = draftFilter === f.id;
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => onFilterChange(f.id)}
              className={`inline-flex items-center justify-center rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors cursor-pointer border ${
                isActive
                  ? 'bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] text-[#0A0A0A] font-semibold border-[#D4AF37] shadow-[0_0_12px_rgba(212,175,55,0.3)]'
                  : 'bg-[#121212] text-[#A59F8F] border-[rgba(212,175,55,0.22)] hover:bg-[#1A1A1A] hover:text-[#F5F1E6]'
              }`}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      {/* 2-Column: List on Left, Editor on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 h-[calc(100vh-180px)] min-h-[550px]">
        {/* Drafts List */}
        <div className="lg:col-span-5 glass flex flex-col overflow-hidden h-full">
          <div className="p-3.5 px-4 border-b border-[rgba(212,175,55,0.18)] bg-[#1A1A1A]/40 flex items-center justify-between flex-shrink-0">
            <span className="text-xs font-semibold text-[#F2D675]">
              Draft Responses ({drafts.length})
            </span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-[rgba(212,175,55,0.1)]">
            {loading ? (
              <div className="space-y-3 p-4">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-md" />
                ))}
              </div>
            ) : drafts.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={FileText}
                  title="No drafts available"
                  description="AI-generated drafts waiting for approval will appear here."
                />
              </div>
            ) : (
              <AnimatePresence>
                {drafts.map((d) => {
                  const isSelected = selectedDraftId === d.id;
                  const needsReview = d.status === 'needs_review';

                  return (
                    <motion.div
                      key={d.id}
                      layout={!prefersReduced}
                      initial={prefersReduced ? {} : { opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={prefersReduced ? {} : { opacity: 0, scale: 0.95 }}
                      transition={{ duration: 0.18, ease: 'easeOut' }}
                      onClick={() => onSelectDraft(d)}
                      className={`p-4 cursor-pointer transition-colors text-xs select-none ${
                        isSelected
                          ? 'bg-[#1A1A1A] border-l-4 border-l-[#D4AF37]'
                          : needsReview
                          ? 'bg-[#FF9F43]/5 border-l-4 border-l-[#FF9F43] hover:bg-[#1A1A1A]/60'
                          : 'bg-[#121212] hover:bg-[#1A1A1A]/50 border-l-4 border-l-transparent'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-semibold text-[#F5F1E6] truncate max-w-[220px]">
                          {d.contact_name || d.contact_email}
                        </span>
                        <span className="text-[11px] text-[#A59F8F] font-mono flex-shrink-0">
                          {new Date(d.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>

                      <div className="text-[#F2D675] font-medium truncate mb-1.5 text-xs">
                        {d.reply_subject || 'Inquiry'}
                      </div>

                      <div className="text-[#A59F8F] line-clamp-2 text-xs leading-relaxed mb-2.5">
                        {d.body || '(No body text)'}
                      </div>

                      {needsReview && d.reason && (
                        <div className="text-[11px] text-[#FF9F43] bg-[#FF9F43]/10 border border-[#FF9F43]/30 rounded px-2.5 py-1 mb-2.5 font-medium leading-snug">
                          Needs Review: {d.reason}
                        </div>
                      )}

                      <div className="flex items-center gap-1.5 flex-wrap">
                        <StatusBadge status={d.status} />
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            )}
          </div>
        </div>

        {/* Editor Pane */}
        <div className="lg:col-span-7 glass flex flex-col overflow-hidden h-full">
          {selectedDraftId && sel ? (
            <>
              {/* Header */}
              <div className="p-3.5 px-5 border-b border-[rgba(212,175,55,0.18)] flex items-center justify-between bg-[#1A1A1A]/40 flex-shrink-0">
                <div className="flex items-center gap-2.5 truncate">
                  <h4 className="text-xs font-semibold text-[#F2D675] truncate">
                    {sel.reply_subject || 'Draft Reply'}
                  </h4>
                  <StatusBadge status={sel.status} />
                </div>
                <Button variant="ghost" size="sm" onClick={() => onSelectDraft({ id: null, body: '' })}>
                  Close
                </Button>
              </div>

              {/* Scrollable Body */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4">
                {/* Attendee's Message */}
                <div className="rounded-xl border border-[rgba(212,175,55,0.18)] bg-[#1A1A1A]/60 p-4 text-xs space-y-2">
                  <div className="flex items-center justify-between text-[#A59F8F] text-[11px]">
                    <span className="font-semibold text-[#F2D675]">
                      Attendee: {sel.contact_name || sel.contact_email}
                    </span>
                    <span>
                      {sel.reply_received_at ? new Date(sel.reply_received_at).toLocaleTimeString() : ''}
                    </span>
                  </div>
                  <div className="text-[#F5F1E6] whitespace-pre-wrap leading-relaxed font-sans text-xs">
                    {sel.reply_body || '(No incoming message body)'}
                  </div>
                </div>

                {/* Flag Reason Banner */}
                {sel.status === 'needs_review' && sel.reason && (
                  <div className="flex items-start gap-3 p-3.5 rounded-xl bg-[#FF9F43]/10 border border-[#FF9F43]/30 text-xs text-[#FF9F43]">
                    <AlertTriangle className="w-4 h-4 text-[#FF9F43] flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-[#F5F1E6]">Needs Human Review: {sel.reason}</div>
                      <div className="text-[11px] text-[#A59F8F] mt-0.5">
                        Please edit the response text below before approving.
                      </div>
                    </div>
                  </div>
                )}

                {/* Editable Draft Textarea */}
                <div>
                  <label className="block text-xs font-medium text-[#A59F8F] mb-1.5">
                    Suggested Response (editable):
                  </label>
                  <Textarea
                    rows={8}
                    value={draftBodyEdit}
                    onChange={(e) => onDraftBodyEditChange(e.target.value)}
                    placeholder="Draft response body..."
                    className="font-sans leading-relaxed text-xs border border-[rgba(212,175,55,0.22)] bg-[#1A1A1A] text-[#F5F1E6] rounded-xl p-3 focus:border-[#D4AF37]"
                  />
                </div>
              </div>

              {/* Footer Actions */}
              <div className="p-3.5 px-5 border-t border-[rgba(212,175,55,0.18)] flex flex-wrap items-center justify-end gap-2 bg-[#1A1A1A]/40 flex-shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onRegenerateDraft}
                  disabled={savingDraft || sel.status === 'sent'}
                >
                  <Sparkles className="w-3.5 h-3.5 mr-1" />
                  Regenerate
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onRejectDraft}
                  disabled={savingDraft || sel.status === 'sent' || sel.status === 'rejected'}
                  className="text-[#FF5C5C] hover:text-[#FF5C5C] hover:bg-[#FF5C5C]/10 border-[#FF5C5C]/30"
                >
                  <X className="w-3.5 h-3.5 mr-1" />
                  Reject
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onSaveDraft}
                  disabled={savingDraft || sel.status === 'sent'}
                >
                  <Save className="w-3.5 h-3.5 mr-1" />
                  {savingDraft ? 'Saving...' : 'Save Edit'}
                </Button>

                {sel.status !== 'sent' && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleSendClick}
                    disabled={disableSend}
                    title={isNeedsReviewUnedited ? 'Draft flagged for review must be edited before sending' : ''}
                  >
                    <Send className="w-3.5 h-3.5 mr-1" />
                    {savingDraft ? 'Sending...' : 'Approve & Send'}
                  </Button>
                )}
              </div>
            </>
          ) : (
            <div className="m-auto p-8">
              <EmptyState
                icon={FileText}
                title="Select a draft"
                description="Click on any draft in the list to review the incoming message, edit the generated response, and approve for sending."
              />
            </div>
          )}
        </div>
      </div>

      {/* Approve & Send Confirm Box */}
      <Modal
        isOpen={showSendConfirmModal && Boolean(sel)}
        onClose={() => setShowSendConfirmModal(false)}
        title="Approve & Send Email Response"
        maxWidth="max-w-lg"
      >
        {sel && (
          <div className="space-y-4 text-xs text-[#F5F1E6]">
            {/* Recipient */}
            <div className="p-2.5 rounded-lg bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)]">
              <span className="text-[#A59F8F] font-medium">Recipient: </span>
              <strong className="text-[#F2D675] font-semibold">
                {sel.contact_name ? `${sel.contact_name} <${sel.contact_email}>` : sel.contact_email}
              </strong>
            </div>

            {/* Delivery unknown warning for uncertain items */}
            {sel.reason && sel.reason.includes('Delivery unknown') && (
              <div className="p-3 rounded-lg bg-[#FF9F43]/15 border border-[#FF9F43]/40 text-[#FF9F43] flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-[#FF9F43] flex-shrink-0 mt-0.5" />
                <div>
                  <strong className="block font-semibold">WARNING: Delivery Status Unknown</strong>
                  <span className="text-[11px] text-[#F5F1E6]">Delivery status for this message is unknown. Check your Gmail Sent folder before sending again to avoid duplicate emails.</span>
                </div>
              </div>
            )}

            {/* Final Email Text with Mandatory Footer */}
            <div>
              <label className="block text-[#A59F8F] font-medium mb-1.5">
                Final Email Content (with mandatory footer):
              </label>
              <div className="rounded-xl border border-[rgba(212,175,55,0.22)] bg-[#1A1A1A] p-3.5 space-y-3 font-sans leading-relaxed text-[#F5F1E6] max-h-56 overflow-y-auto">
                <div className="whitespace-pre-wrap">{draftBodyEdit}</div>
                <div className="pt-2 border-t border-[rgba(212,175,55,0.15)] text-[#A59F8F] text-[11px] whitespace-pre-wrap">
                  {settings?.footer_preview || `--\n${settings?.sender_name || 'Event Coordinator'}\n${settings?.unsubscribe_line || "To unsubscribe, reply with 'unsubscribe'."}`}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-2 border-t border-[rgba(212,175,55,0.18)]">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowSendConfirmModal(false)}
                disabled={savingDraft}
              >
                Cancel
              </Button>
              <Button
                variant={sel.reason && sel.reason.includes('Delivery unknown') ? 'danger' : 'primary'}
                size="sm"
                disabled={savingDraft}
                onClick={async () => {
                  setShowSendConfirmModal(false);
                  await onApproveAndSendDraft();
                }}
              >
                <Send className="w-3.5 h-3.5 mr-1" />
                {savingDraft
                  ? 'Sending...'
                  : sel.reason && sel.reason.includes('Delivery unknown')
                  ? 'Confirm & Send Again'
                  : 'Confirm & Send'}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
