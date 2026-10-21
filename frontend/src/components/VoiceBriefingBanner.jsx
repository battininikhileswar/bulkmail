import React from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Volume2,
  VolumeX,
  Mic,
  Play,
  Pause,
  SkipForward,
  Square,
  FileText,
  MessageSquare,
} from 'lucide-react';
import { cleanContactName, describeIntent } from '@/voice';

export function VoiceBriefingBanner({
  briefing,
  onAccept,
  onDecline,
  onMute,
  onPauseToggle,
  onSkip,
  onStop,
  onReadDraft,
  onClose,
}) {
  const prefersReduced = useReducedMotion();

  if (!briefing || briefing.status === 'idle') {
    return null;
  }

  const {
    status,
    realCount = 0,
    extraText = '',
    repliesToRead = [],
    currentIndex = 0,
    hasSuggestedDraft = false,
    isPaused = false,
    draftsWaitingCount = 0,
  } = briefing;

  const currentReply = repliesToRead[currentIndex];
  const senderName = currentReply
    ? cleanContactName(currentReply.contact_name || currentReply.contact_email)
    : 'contact';

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: prefersReduced ? 0 : 0.2 }}
        className="mb-5 glass text-[#F5F1E6] p-4"
        role="region"
        aria-label="Voice briefing"
      >
        {/* 1. Prompting & Listening State */}
        {(status === 'prompting' || status === 'listening') && (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start gap-3 min-w-0">
              <div className="w-8 h-8 rounded-full bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] text-[#0A0A0A] flex items-center justify-center flex-shrink-0 shadow-[0_0_10px_rgba(212,175,55,0.4)]">
                {status === 'listening' ? (
                  <Mic className="w-4 h-4 animate-pulse text-[#0A0A0A]" />
                ) : (
                  <Volume2 className="w-4 h-4 text-[#0A0A0A]" />
                )}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[#F2D675] leading-snug">
                  You have {realCount} new {realCount === 1 ? 'reply' : 'replies'}
                  {extraText ? `, and ${extraText}` : ''}. Shall I read them?
                </div>
                <div className="text-[11px] text-[#A59F8F] mt-0.5 flex items-center gap-2">
                  {status === 'listening' ? (
                    <span className="inline-flex items-center gap-1.5 text-[#F2D675] font-medium">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#D4AF37] animate-ping" />
                      Listening for "Yes" or "Not now" (6s)...
                    </span>
                  ) : (
                    <span>Voice works only while this page is open.</span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap flex-shrink-0 self-end sm:self-center">
              <Button
                variant="primary"
                size="sm"
                onClick={onAccept}
                className="text-xs font-semibold"
              >
                Yes, read them
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={onDecline}
                className="text-xs"
              >
                Not now
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onMute}
                className="text-xs text-[#A59F8F] hover:text-[#F2D675]"
                title="Mute voice announcements"
              >
                <VolumeX className="w-3.5 h-3.5 mr-1" />
                Mute
              </Button>
            </div>
          </div>
        )}

        {/* 2. Reading Aloud State */}
        {status === 'reading' && (
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[rgba(212,175,55,0.18)] pb-2.5">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] text-[#0A0A0A] flex items-center justify-center flex-shrink-0">
                  <Volume2 className="w-3.5 h-3.5" />
                </div>
                <div>
                  <div className="text-xs font-bold text-[#F5F1E6]">
                    Reply {currentIndex + 1} of {repliesToRead.length}
                    <span className="font-normal text-[#A59F8F] ml-1.5">from</span>{' '}
                    <strong className="text-[#F2D675]">{senderName}</strong>
                  </div>
                  <div className="text-[10px] text-[#A59F8F]">
                    Voice works only while this page is open.
                  </div>
                </div>
              </div>

              {/* Reading Controls */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onPauseToggle}
                  className="text-xs h-7 px-2.5"
                  title={isPaused ? 'Resume reading' : 'Pause reading'}
                >
                  {isPaused ? (
                    <>
                      <Play className="w-3 h-3 mr-1 text-[#3DDC97]" />
                      Resume
                    </>
                  ) : (
                    <>
                      <Pause className="w-3 h-3 mr-1 text-[#F2D675]" />
                      Pause
                    </>
                  )}
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={onSkip}
                  className="text-xs h-7 px-2.5"
                  title="Skip to next reply"
                >
                  <SkipForward className="w-3 h-3 mr-1" />
                  Skip
                </Button>

                <Button
                  variant="danger"
                  size="sm"
                  onClick={onStop}
                  className="text-xs h-7 px-2.5"
                  title="Stop reading replies"
                >
                  <Square className="w-3 h-3 mr-1 fill-current" />
                  Stop
                </Button>
              </div>
            </div>

            {/* Current Reply Context */}
            {currentReply && (
              <div className="bg-[#1A1A1A] rounded-md border border-[rgba(212,175,55,0.18)] p-3 text-xs space-y-1.5">
                <div className="flex items-center gap-2">
                  <Badge variant="gold" className="text-[10px] font-medium py-0">
                    {describeIntent(currentReply.intent)}
                  </Badge>
                  <span className="text-[11px] text-[#A59F8F] font-mono truncate">
                    {currentReply.contact_email}
                  </span>
                </div>
                <div className="text-[#F5F1E6] font-sans text-xs line-clamp-3 leading-relaxed">
                  "{currentReply.body_text || 'No text content'}"
                </div>
              </div>
            )}

            {/* Suggested Draft Prompt */}
            {hasSuggestedDraft && (
              <div className="flex items-center justify-between gap-3 bg-[#FF9F43]/10 border border-[#FF9F43]/30 rounded-md p-2.5 text-xs text-[#FF9F43]">
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="w-4 h-4 text-[#FF9F43] flex-shrink-0" />
                  <span className="truncate font-medium text-[#F5F1E6]">
                    Suggested response ready in Drafts. Open Drafts to review or approve.
                  </span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onReadDraft}
                  className="text-xs h-7 px-2.5 flex-shrink-0 border-[#FF9F43]/40 text-[#FF9F43] hover:bg-[#FF9F43]/10"
                >
                  Read the draft
                </Button>
              </div>
            )}
          </div>
        )}

        {/* 3. Completed State */}
        {status === 'completed' && (
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-full bg-[#3DDC97]/20 border border-[#3DDC97]/40 text-[#3DDC97] flex items-center justify-center flex-shrink-0">
                <MessageSquare className="w-3.5 h-3.5" />
              </div>
              <div>
                <div className="text-xs font-semibold text-[#F2D675]">
                  That's all. {draftsWaitingCount === 1 ? '1 draft is' : `${draftsWaitingCount} drafts are`} waiting for your review.
                </div>
                <div className="text-[11px] text-[#A59F8F]">
                  You can open Drafts to approve or edit any suggested replies.
                </div>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={onClose}
              className="text-xs"
            >
              Done
            </Button>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
