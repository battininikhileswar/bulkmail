import { useState, useRef, useEffect, useCallback } from 'react';
import {
  isVoiceEnabled,
  isMuted as checkIsMuted,
  setMuted as saveMutedPreference,
  isVoiceAnswersEnabled,
  setVoiceAnswersEnabled,
  isSpeechRecognitionSupported,
  requestMicrophonePermission,
  listenForVoiceAnswer,
  sanitizeMessageForSpeech,
  describeIntent,
  cleanContactName,
  formatBriefingQuestion,
  speak,
  pauseSpeech,
  resumeSpeech,
  stopSpeech,
  getSeenReplyIds,
  saveSeenReplyIds,
  getReadAloudReplyIds,
  saveReadAloudReplyIds,
} from '@/voice';

export function useVoiceBriefing({
  currentUser,
  replies = [],
  drafts = [],
  voiceEnabled,
  voiceMuted,
  onMuteChange,
  toast,
}) {
  const [briefing, setBriefing] = useState({
    status: 'idle', // 'idle' | 'prompting' | 'listening' | 'reading' | 'completed'
    realCount: 0,
    extraText: '',
    repliesToRead: [],
    currentIndex: 0,
    hasSuggestedDraft: false,
    draftText: '',
    isPaused: false,
    draftsWaitingCount: 0,
  });

  const [voiceAnswersOn, setVoiceAnswersOn] = useState(isVoiceAnswersEnabled);

  const pendingBatchRef = useRef([]);
  const batchTimerRef = useRef(null);
  const stopListeningRef = useRef(null);
  const readingCancelledRef = useRef(false);
  const isReadingRef = useRef(false);

  // Sync voice answers toggle from storage
  useEffect(() => {
    setVoiceAnswersOn(isVoiceAnswersEnabled());
  }, []);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (batchTimerRef.current) {
        clearTimeout(batchTimerRef.current);
      }
      if (stopListeningRef.current) {
        stopListeningRef.current();
      }
      stopSpeech();
    };
  }, []);

  // Toggle voice answers with mic permission check
  const handleToggleVoiceAnswers = async () => {
    if (!voiceAnswersOn) {
      if (!isSpeechRecognitionSupported()) {
        toast.error('Voice answers require browser SpeechRecognition support (Chrome, Edge, Safari).');
        return;
      }
      toast.info('Requesting microphone permission for voice answers...');
      const granted = await requestMicrophonePermission();
      if (!granted) {
        toast.error('Microphone permission denied. Voice answers will remain off.');
        return;
      }
      setVoiceAnswersEnabled(true);
      setVoiceAnswersOn(true);
      toast.success('Voice answers enabled. Browser will listen for "Yes" or "Not now".');
    } else {
      setVoiceAnswersEnabled(false);
      setVoiceAnswersOn(false);
      if (stopListeningRef.current) {
        stopListeningRef.current();
        stopListeningRef.current = null;
      }
      toast.info('Voice answers disabled.');
    }
  };

  // Start reading an array of replies sequentially
  const startReading = useCallback(
    async (repliesList) => {
      if (!repliesList || repliesList.length === 0) {
        setBriefing((prev) => ({ ...prev, status: 'idle' }));
        return;
      }

      if (stopListeningRef.current) {
        stopListeningRef.current();
        stopListeningRef.current = null;
      }

      readingCancelledRef.current = false;
      isReadingRef.current = true;

      const total = repliesList.length;
      const readAloudSet = getReadAloudReplyIds(currentUser?.id);

      for (let i = 0; i < total; i++) {
        if (readingCancelledRef.current) break;

        const reply = repliesList[i];
        const name = cleanContactName(reply.contact_name || reply.contact_email);
        const intentText = describeIntent(reply.intent);
        const bodyText = sanitizeMessageForSpeech(reply.body_text || '');

        // Check for matching draft
        const matchedDraft = drafts.find(
          (d) => d.reply_id === reply.id || (reply.thread_id && d.thread_id === reply.thread_id)
        );

        setBriefing({
          status: 'reading',
          realCount: total,
          extraText: '',
          repliesToRead: repliesList,
          currentIndex: i,
          hasSuggestedDraft: Boolean(matchedDraft),
          draftText: matchedDraft ? matchedDraft.body : '',
          isPaused: false,
          draftsWaitingCount: drafts.filter(
            (d) => d.status === 'needs_review' || d.status === 'pending_approval'
          ).length,
        });

        // 1. Speak the reply: "Reply 1 of 2, from <name>. <intent>. <message>"
        const replyUtterance = `Reply ${i + 1} of ${total}, from ${name}. ${intentText}. ${bodyText}`;
        await speak(replyUtterance);

        if (readingCancelledRef.current) break;

        // Mark this reply as read aloud
        readAloudSet.add(reply.id);
        saveReadAloudReplyIds(currentUser?.id, readAloudSet);

        // 2. If suggested draft exists, notify user without auto-reading
        if (matchedDraft) {
          const draftNotice = 'I have a suggested answer ready. Open the Drafts page to review it.';
          await speak(draftNotice);
          if (readingCancelledRef.current) break;
          // Brief pause so admin has a moment to click "Read the draft" if desired
          await new Promise((r) => setTimeout(r, 2000));
          if (readingCancelledRef.current) break;
        }

        // Short breather between replies
        if (i < total - 1 && !readingCancelledRef.current) {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }

      if (!readingCancelledRef.current) {
        // Conclude briefing
        const pendingDraftsCount = drafts.filter(
          (d) => d.status === 'needs_review' || d.status === 'pending_approval'
        ).length;
        const draftWord = pendingDraftsCount === 1 ? '1 draft is' : `${pendingDraftsCount} drafts are`;
        const conclusionText = `That's all. ${draftWord} waiting for your review.`;

        setBriefing({
          status: 'completed',
          realCount: total,
          extraText: '',
          repliesToRead: repliesList,
          currentIndex: total - 1,
          hasSuggestedDraft: false,
          draftText: '',
          isPaused: false,
          draftsWaitingCount: pendingDraftsCount,
        });

        await speak(conclusionText);
      }

      isReadingRef.current = false;
    },
    [currentUser?.id, drafts]
  );

  // Present the question to the admin: "You have N new replies. Shall I read them?"
  const presentQuestion = useCallback(
    async (realReplies, extraCounts) => {
      const realCount = realReplies.length;
      if (realCount === 0) return;

      const extraParts = [];
      if (extraCounts.unsubscribe_request > 0) {
        const n = extraCounts.unsubscribe_request;
        extraParts.push(`${n} ${n === 1 ? 'unsubscribe request' : 'unsubscribe requests'}`);
      }
      if (extraCounts.bounce > 0) {
        const n = extraCounts.bounce;
        extraParts.push(`${n} ${n === 1 ? 'bounce' : 'bounces'}`);
      }
      if (extraCounts.auto_reply > 0) {
        const n = extraCounts.auto_reply;
        extraParts.push(`${n} ${n === 1 ? 'automatic reply' : 'automatic replies'}`);
      }
      const extraText = extraParts.join(', ');

      const questionPrompt = formatBriefingQuestion(realCount, extraCounts);

      setBriefing({
        status: 'prompting',
        realCount,
        extraText,
        repliesToRead: realReplies,
        currentIndex: 0,
        hasSuggestedDraft: false,
        draftText: '',
        isPaused: false,
        draftsWaitingCount: drafts.filter(
          (d) => d.status === 'needs_review' || d.status === 'pending_approval'
        ).length,
      });

      // Speak question if voice active
      if (voiceEnabled && !voiceMuted) {
        await speak(questionPrompt);

        // If voice answers toggle is ON, listen for spoken response for 6s
        if (voiceAnswersOn && isSpeechRecognitionSupported()) {
          setBriefing((prev) => (prev.status === 'prompting' ? { ...prev, status: 'listening' } : prev));

          stopListeningRef.current = listenForVoiceAnswer({
            timeoutMs: 6000,
            onAnswer: (answer) => {
              stopListeningRef.current = null;
              if (answer === 'yes') {
                startReading(realReplies);
              } else if (answer === 'no') {
                setBriefing((prev) => ({ ...prev, status: 'idle' }));
              } else {
                // Unrecognized word: return to prompting so buttons remain usable
                setBriefing((prev) => ({ ...prev, status: 'prompting' }));
              }
            },
            onTimeout: () => {
              stopListeningRef.current = null;
              // Timeout: leave buttons on screen
              setBriefing((prev) => (prev.status === 'listening' ? { ...prev, status: 'prompting' } : prev));
            },
            onError: () => {
              stopListeningRef.current = null;
              setBriefing((prev) => (prev.status === 'listening' ? { ...prev, status: 'prompting' } : prev));
            },
          });
        }
      }
    },
    [voiceEnabled, voiceMuted, voiceAnswersOn, drafts, startReading]
  );

  // Flush pending batch after 10-second window
  const flushBatch = useCallback(() => {
    const batch = [...pendingBatchRef.current];
    pendingBatchRef.current = [];
    batchTimerRef.current = null;

    if (batch.length === 0) return;

    // Filter real replies vs non-real
    const realReplies = batch.filter((r) => r.category === 'reply');
    const extraCounts = {
      unsubscribe_request: batch.filter((r) => r.category === 'unsubscribe_request').length,
      bounce: batch.filter((r) => r.category === 'bounce').length,
      auto_reply: batch.filter((r) => r.category === 'auto_reply').length,
    };

    if (realReplies.length > 0) {
      presentQuestion(realReplies, extraCounts);
    } else if (extraCounts.unsubscribe_request > 0 || extraCounts.bounce > 0) {
      // Short notification if non-real items arrived without real replies
      const msgs = [];
      if (extraCounts.unsubscribe_request > 0) msgs.push(`${extraCounts.unsubscribe_request} unsubscribe`);
      if (extraCounts.bounce > 0) msgs.push(`${extraCounts.bounce} bounce`);
      toast.info(`Received ${msgs.join(', ')}.`);
    }
  }, [presentQuestion, toast]);

  // Public method called by App when fresh replies arrive
  const queueIncomingReplies = useCallback(
    (freshReplies) => {
      if (!freshReplies || freshReplies.length === 0) return;

      // Add to pending batch
      pendingBatchRef.current.push(...freshReplies);

      // Start 10-second batch timer if not already active
      if (!batchTimerRef.current) {
        batchTimerRef.current = setTimeout(() => {
          flushBatch();
        }, 10000);
      }
    },
    [flushBatch]
  );

  // Manual trigger from top bar "Read my replies"
  const triggerManualBriefing = useCallback(() => {
    if (!replies || replies.length === 0) {
      toast.info('No replies found.');
      return;
    }

    const readAloudIds = getReadAloudReplyIds(currentUser?.id);
    // Prefer unread real replies, fall back to recent real replies
    let target = replies.filter((r) => r.category === 'reply' && !readAloudIds.has(r.id));
    if (target.length === 0) {
      target = replies.filter((r) => r.category === 'reply').slice(0, 5);
    }

    if (target.length === 0) {
      toast.info('No real email replies available to read.');
      return;
    }

    startReading(target);
  }, [replies, currentUser?.id, startReading, toast]);

  // Action handlers for banner controls
  const handleAccept = () => {
    if (stopListeningRef.current) {
      stopListeningRef.current();
      stopListeningRef.current = null;
    }
    startReading(briefing.repliesToRead);
  };

  const handleDecline = () => {
    if (stopListeningRef.current) {
      stopListeningRef.current();
      stopListeningRef.current = null;
    }
    setBriefing((prev) => ({ ...prev, status: 'idle' }));
  };

  const handleMute = () => {
    if (stopListeningRef.current) {
      stopListeningRef.current();
      stopListeningRef.current = null;
    }
    stopSpeech();
    saveMutedPreference(true);
    if (onMuteChange) onMuteChange(true);
    setBriefing((prev) => ({ ...prev, status: 'idle' }));
    toast.info('Voice notifications muted.');
  };

  const handlePauseToggle = () => {
    if (briefing.isPaused) {
      resumeSpeech();
      setBriefing((prev) => ({ ...prev, isPaused: false }));
    } else {
      pauseSpeech();
      setBriefing((prev) => ({ ...prev, isPaused: true }));
    }
  };

  const handleSkip = () => {
    stopSpeech();
    // Advance to next index
    const nextIdx = briefing.currentIndex + 1;
    if (nextIdx < briefing.repliesToRead.length) {
      startReading(briefing.repliesToRead.slice(nextIdx));
    } else {
      readingCancelledRef.current = true;
      setBriefing((prev) => ({ ...prev, status: 'idle' }));
    }
  };

  const handleStop = () => {
    readingCancelledRef.current = true;
    stopSpeech();
    setBriefing((prev) => ({ ...prev, status: 'idle' }));
  };

  const handleReadDraft = async () => {
    if (briefing.draftText) {
      await speak(`Suggested draft: ${sanitizeMessageForSpeech(briefing.draftText)}`);
    }
  };

  const handleClose = () => {
    setBriefing((prev) => ({ ...prev, status: 'idle' }));
  };

  return {
    briefing,
    voiceAnswersOn,
    handleToggleVoiceAnswers,
    queueIncomingReplies,
    triggerManualBriefing,
    handleAccept,
    handleDecline,
    handleMute,
    handlePauseToggle,
    handleSkip,
    handleStop,
    handleReadDraft,
    handleClose,
  };
}
