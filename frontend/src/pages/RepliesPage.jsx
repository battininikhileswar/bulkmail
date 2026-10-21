import React from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { StatusBadge, Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { MessageSquare, RefreshCw, CheckCircle2, Clock, Eye, AlertTriangle } from 'lucide-react';

export function RepliesPage({
  watcher = { running: false, last_check_time: null },
  onToggleWatcher,
  replyFilter = 'all',
  onFilterChange,
  replies = [],
  selectedReplyId,
  onSelectReply,
  thread,
  onReclassify,
  rechecking = false,
  onMarkHandled,
  loading = false,
}) {
  const prefersReduced = useReducedMotion();

  const filterTabs = [
    { id: 'all', label: 'All Replies' },
    { id: 'unhandled', label: 'Unhandled' },
    { id: 'unsubscribe_request', label: 'Unsubscribes' },
    { id: 'auto_reply', label: 'Auto-replies' },
    { id: 'bounce', label: 'Bounces' },
  ];

  return (
    <div className="space-y-4">
      {/* Watcher Status Bar */}
      <div className="glass p-3.5 px-4 flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs text-[#F5F1E6]">
          <div className="flex items-center gap-1.5 font-medium">
            <span
              className={`w-2 h-2 rounded-full ${
                watcher.running ? 'bg-[#3DDC97] animate-pulse' : 'bg-[#A59F8F]/40'
              }`}
            />
            <span className="text-[#F2D675]">Watcher: {watcher.running ? 'Running' : 'Stopped'}</span>
          </div>
          <span className="text-[rgba(212,175,55,0.3)]">|</span>
          <span className="text-[#A59F8F]">
            Last checked: {watcher.last_check_time ? new Date(watcher.last_check_time).toLocaleTimeString() : 'Never'}
          </span>
        </div>
        <Button
          variant={watcher.running ? 'danger' : 'primary'}
          size="sm"
          onClick={onToggleWatcher}
        >
          {watcher.running ? 'Stop Watcher' : 'Start Watcher'}
        </Button>
      </div>

      {/* Filter Tabs / Pills */}
      <div className="flex items-center gap-2 flex-wrap mb-4">
        {filterTabs.map((f) => {
          const isActive = replyFilter === f.id;
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

      {/* 2-Column: List on Left, Thread on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 h-[calc(100vh-230px)] min-h-[500px]">
        {/* Replies List */}
        <div className="lg:col-span-5 glass flex flex-col overflow-hidden h-full">
          <div className="p-3.5 px-4 border-b border-[rgba(212,175,55,0.18)] bg-[#1A1A1A]/40 flex items-center justify-between flex-shrink-0">
            <span className="text-xs font-semibold text-[#F2D675]">
              Inbox ({replies.length})
            </span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-[rgba(212,175,55,0.1)]">
            {loading ? (
              <div className="space-y-3 p-4">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-md" />
                ))}
              </div>
            ) : replies.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={MessageSquare}
                  title="No replies found"
                  description="Incoming replies detected by the inbox watcher will appear here."
                />
              </div>
            ) : (
              <AnimatePresence>
                {replies.map((m) => {
                  const isSelected = selectedReplyId === m.id;
                  const isUnhandled = m.processed === 0;

                  return (
                    <motion.div
                      key={m.id}
                      layout={!prefersReduced}
                      initial={prefersReduced ? {} : { opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={prefersReduced ? {} : { opacity: 0, scale: 0.95 }}
                      transition={{ duration: 0.18, ease: 'easeOut' }}
                      onClick={() => onSelectReply(m.id)}
                      className={`p-4 cursor-pointer transition-colors text-xs select-none ${
                        isSelected
                          ? 'bg-[#1A1A1A] border-l-4 border-l-[#D4AF37]'
                          : isUnhandled
                          ? 'bg-[#FF9F43]/5 border-l-4 border-l-[#FF9F43] hover:bg-[#1A1A1A]/60'
                          : 'bg-[#121212] hover:bg-[#1A1A1A]/50 border-l-4 border-l-transparent'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-semibold text-[#F5F1E6] truncate max-w-[220px]">
                          {m.contact_name || m.contact_email}
                        </span>
                        <span className="text-[11px] text-[#A59F8F] font-mono flex-shrink-0">
                          {new Date(m.received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>

                      <div className="text-[#F2D675] font-medium truncate mb-1.5 text-xs">
                        {m.subject || '(No Subject)'}
                      </div>

                      <div className="text-[#A59F8F] line-clamp-2 text-xs leading-relaxed mb-2.5">
                        {m.body_text || '(No body text)'}
                      </div>

                      {m.summary && (
                        <div className="text-[11px] text-[#F5F1E6] bg-[#1A1A1A] border border-[rgba(212,175,55,0.2)] rounded px-2.5 py-1 mb-2.5 italic">
                          AI Summary: {m.summary}
                        </div>
                      )}

                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#1A1A1A] text-[#A59F8F] border border-[rgba(212,175,55,0.2)] font-medium">
                          {m.category}
                        </span>
                        {m.intent && (
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
                              m.intent === 'interested'
                                ? 'bg-[#3DDC97]/15 text-[#3DDC97] border-[#3DDC97]/30'
                                : m.intent === 'unsubscribe'
                                ? 'bg-[#FF5C5C]/15 text-[#FF5C5C] border-[#FF5C5C]/30'
                                : m.intent === 'question'
                                ? 'bg-[#6EA8FF]/15 text-[#6EA8FF] border-[#6EA8FF]/30'
                                : 'bg-[#FF9F43]/15 text-[#FF9F43] border-[#FF9F43]/30'
                            }`}
                          >
                            {m.intent}
                          </span>
                        )}
                        {m.flagged_reason && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FF9F43]/15 text-[#FF9F43] border border-[#FF9F43]/30 font-medium">
                            {m.flagged_reason}
                          </span>
                        )}
                        {isUnhandled ? (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FF9F43]/15 text-[#FF9F43] border border-[#FF9F43]/30 font-medium">
                            Unhandled
                          </span>
                        ) : (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#3DDC97]/15 text-[#3DDC97] border border-[#3DDC97]/30 font-medium">
                            Handled
                          </span>
                        )}
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            )}
          </div>
        </div>

        {/* Conversation Thread Pane */}
        <div className="lg:col-span-7 glass flex flex-col overflow-hidden h-full">
          {selectedReplyId && thread ? (
            <>
              {/* Header */}
              <div className="p-3.5 px-5 border-b border-[rgba(212,175,55,0.18)] flex items-center justify-between bg-[#1A1A1A]/40 flex-shrink-0">
                <div className="flex items-center gap-2.5 truncate">
                  <h4 className="text-xs font-semibold text-[#F2D675] truncate">
                    {thread.reply?.subject || 'Reply Conversation'}
                  </h4>
                  {thread.reply?.intent && (
                    <Badge variant={thread.reply.intent === 'interested' ? 'success' : 'neutral'}>
                      {thread.reply.intent}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onReclassify(thread.reply?.id)}
                    disabled={rechecking}
                  >
                    <RefreshCw className={`w-3 h-3 mr-1 ${rechecking ? 'animate-spin' : ''}`} />
                    {rechecking ? 'Checking...' : 'Re-check AI'}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => onSelectReply(null)}>
                    Close
                  </Button>
                </div>
              </div>

              {/* Message Bubbles */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#0A0A0A]/40">
                {thread.original_sent_mail && (
                  <div className="ml-auto max-w-[85%] bg-[#1A1A1A] border border-[rgba(212,175,55,0.25)] rounded-xl p-3 text-xs space-y-1 shadow-[0_2px_10px_rgba(0,0,0,0.3)]">
                    <div className="text-[11px] text-[#F2D675] font-medium">
                      Original Campaign Email • {new Date(thread.original_sent_mail.sent_at).toLocaleDateString()}
                    </div>
                    <div className="text-[#F5F1E6] whitespace-pre-wrap leading-relaxed font-sans">
                      {thread.original_sent_mail.rendered_body}
                    </div>
                  </div>
                )}

                {thread.thread_history?.map((msg) => {
                  const isOutgoing = msg.direction === 'outgoing';
                  return (
                    <div
                      key={msg.id}
                      className={`max-w-[85%] rounded-xl p-3 text-xs space-y-1 shadow-[0_2px_10px_rgba(0,0,0,0.3)] ${
                        isOutgoing
                          ? 'ml-auto bg-[#1A1A1A] border border-[rgba(212,175,55,0.3)] text-[#F5F1E6]'
                          : 'mr-auto bg-[#141414] border border-[rgba(255,255,255,0.08)] text-[#F5F1E6]'
                      }`}
                    >
                      <div className="text-[11px] text-[#A59F8F] font-medium">
                        {isOutgoing ? 'Sent by you' : msg.contact_name || msg.contact_email} •{' '}
                        {new Date(msg.received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                      <div className="whitespace-pre-wrap leading-relaxed font-sans text-[#F5F1E6]">
                        {msg.body_text}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Footer */}
              <div className="p-3.5 px-5 border-t border-[rgba(212,175,55,0.18)] flex items-center justify-end bg-[#1A1A1A]/40 flex-shrink-0">
                {thread.reply?.processed === 0 ? (
                  <Button variant="primary" size="sm" onClick={() => onMarkHandled(thread.reply.id)}>
                    <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                    Mark Handled
                  </Button>
                ) : (
                  <span className="text-xs text-[#3DDC97] font-medium flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-[#3DDC97]" />
                    Already Marked Handled
                  </span>
                )}
              </div>
            </>
          ) : (
            <div className="m-auto p-8">
              <EmptyState
                icon={Eye}
                title="Select a reply"
                description="Click on any incoming reply from the list to view the full conversation history and classification."
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
