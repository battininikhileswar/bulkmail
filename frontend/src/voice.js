/**
 * Voice notifications helper using browser Web Speech API (speechSynthesis)
 * and SpeechRecognition API for voice briefings and answers.
 */

const STORAGE_KEY_ENABLED = 'ai_email_voice_enabled';
const STORAGE_KEY_MUTED = 'ai_email_voice_muted';
const STORAGE_KEY_VOICE_ANSWERS = 'ai_email_voice_answers';

// Module-level Set to retain active SpeechSynthesisUtterance objects in memory
// preventing early Chromium garbage collection drops before speech completion
const activeUtterances = new Set();

let isSpeakingState = false;
const speechListeners = new Set();

function setSpeakingState(speaking) {
  isSpeakingState = speaking;
  speechListeners.forEach((listener) => {
    try { listener(speaking); } catch { /* ignore */ }
  });
}

export function subscribeSpeechState(listener) {
  speechListeners.add(listener);
  listener(isSpeakingState);
  return () => speechListeners.delete(listener);
}

export function isVoiceSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
}

export function isSpeechRecognitionSupported() {
  return typeof window !== 'undefined' && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export function isVoiceEnabled() {
  if (typeof window === 'undefined') return false;
  return localStorage.getItem(STORAGE_KEY_ENABLED) === 'true';
}

export function enableVoice() {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY_ENABLED, 'true');
  // If not explicitly set, default muted to false once enabled
  if (localStorage.getItem(STORAGE_KEY_MUTED) === null) {
    localStorage.setItem(STORAGE_KEY_MUTED, 'false');
  }

  // Ask for desktop notification permission once on user gesture
  if ('Notification' in window && Notification.permission === 'default') {
    try {
      Notification.requestPermission();
    } catch {
      // ignore
    }
  }

  // Preload voices
  if ('speechSynthesis' in window) {
    try {
      window.speechSynthesis.getVoices();
    } catch {
      // ignore
    }
  }
}

export function isMuted() {
  if (typeof window === 'undefined') return true;
  return localStorage.getItem(STORAGE_KEY_MUTED) === 'true';
}

export function setMuted(muted) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY_MUTED, String(muted));
}

export function isVoiceAnswersEnabled() {
  if (typeof window === 'undefined') return false;
  // OFF by default
  return localStorage.getItem(STORAGE_KEY_VOICE_ANSWERS) === 'true';
}

export function setVoiceAnswersEnabled(enabled) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY_VOICE_ANSWERS, String(enabled));
}

export async function requestMicrophonePermission() {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    // Stop all audio tracks immediately after permission check
    stream.getTracks().forEach((track) => track.stop());
    return true;
  } catch (err) {
    console.warn('Microphone permission check failed:', err);
    return false;
  }
}

/**
 * Sanitize contact name before speaking:
 * - Keep only letters, spaces, apostrophes, hyphens, and periods.
 * - Trim to 40 characters.
 * - Fall back to "someone" if empty.
 */
export function cleanContactName(rawName) {
  if (!rawName || typeof rawName !== 'string') return 'someone';
  const cleaned = rawName.replace(/[^a-zA-Z\s'.-]/g, '').trim();
  const trimmed = cleaned.slice(0, 40).trim();
  return trimmed || 'someone';
}

/**
 * Convenience helper to extract first name from sanitized contact name.
 */
export function cleanContactFirstName(rawName) {
  const cleaned = cleanContactName(rawName);
  if (cleaned === 'someone') return 'someone';
  const first = cleaned.split(/\s+/)[0];
  return first || 'someone';
}

/**
 * Sanitize email reply body for speech synthesis:
 * - Plain text only (strip HTML tags)
 * - Replace URLs with "link"
 * - Replace email addresses with "email address"
 * - Replace long digit strings (5+ digits) with "number"
 * - Trim to about 400 characters (say "message shortened" if cut)
 */
export function sanitizeMessageForSpeech(rawText) {
  if (!rawText || typeof rawText !== 'string') return '';

  // 1. Strip HTML tags
  let cleaned = rawText.replace(/<[^>]*>/g, ' ');

  // 2. Replace URLs with the word "link"
  cleaned = cleaned.replace(/(?:https?:\/\/|www\.)[^\s<>"'()]+/gi, ' link ');

  // 3. Replace email addresses with "email address"
  cleaned = cleaned.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, ' email address ');

  // 4. Replace long digit sequences (5 or more digits like phone numbers/IDs) with "number"
  cleaned = cleaned.replace(/\b\d{5,}\b/g, ' number ');

  // 5. Normalize whitespace
  cleaned = cleaned.replace(/\s+/g, ' ').trim();

  // 6. Trim to ~400 characters
  if (cleaned.length > 400) {
    cleaned = cleaned.slice(0, 400).trim() + ', message shortened';
  }

  return cleaned;
}

/**
 * Convert raw reply intent into conversational English.
 */
export function describeIntent(intent) {
  if (!intent || typeof intent !== 'string') return 'They sent a message';
  const norm = intent.toLowerCase().trim();
  switch (norm) {
    case 'question':
      return 'They have a question';
    case 'pricing':
      return 'They are asking about pricing';
    case 'scheduling':
      return 'They want to schedule a time';
    case 'objection':
      return 'They have an objection';
    case 'positive_feedback':
      return 'They sent positive feedback';
    case 'unsubscribe':
      return 'They want to unsubscribe';
    case 'demo':
    case 'meeting':
      return 'They are requesting a meeting';
    default:
      return 'They sent an inquiry';
  }
}

/**
 * Format the voice briefing prompt question.
 */
export function formatBriefingQuestion(realCount, extraCounts = {}) {
  const parts = [];
  const replyWord = realCount === 1 ? '1 new reply' : `${realCount} new replies`;

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

  let prompt = `You have ${replyWord}`;
  if (extraParts.length > 0) {
    prompt += `, and ${extraParts.join(', ')}`;
  }
  prompt += '. Shall I read them?';
  return prompt;
}

/**
 * Per-user seen replies tracking in localStorage to prevent duplicate announcements.
 */
export function getSeenReplyIds(userId) {
  if (typeof window === 'undefined' || !userId) return new Set();
  try {
    const raw = localStorage.getItem(`ai_email_seen_reply_ids_${userId}`);
    if (raw) return new Set(JSON.parse(raw));
  } catch {}
  return new Set();
}

export function saveSeenReplyIds(userId, idsSet) {
  if (typeof window === 'undefined' || !userId) return;
  try {
    const arr = Array.from(idsSet).slice(-1000);
    localStorage.setItem(`ai_email_seen_reply_ids_${userId}`, JSON.stringify(arr));
  } catch {}
}

export function getReadAloudReplyIds(userId) {
  if (typeof window === 'undefined' || !userId) return new Set();
  try {
    const raw = localStorage.getItem(`ai_email_read_aloud_ids_${userId}`);
    if (raw) return new Set(JSON.parse(raw));
  } catch {}
  return new Set();
}

export function saveReadAloudReplyIds(userId, idsSet) {
  if (typeof window === 'undefined' || !userId) return;
  try {
    const arr = Array.from(idsSet).slice(-1000);
    localStorage.setItem(`ai_email_read_aloud_ids_${userId}`, JSON.stringify(arr));
  } catch {}
}

/**
 * Show desktop notification if permitted.
 */
export function showDesktopNotification(text) {
  if (typeof window === 'undefined' || !('Notification' in window)) return;
  if (Notification.permission === 'granted') {
    try {
      new Notification('Email Assistant', { body: text });
    } catch {
      // ignore
    }
  }
}

/**
 * Speak text aloud.
 * Dynamic safety timeout based on text length to prevent cutting off 400-char replies.
 */
export function speak(text, { timeoutMs, onEnd } = {}) {
  if (!text || typeof text !== 'string') {
    if (onEnd) onEnd();
    return Promise.resolve();
  }

  const supported = isVoiceSupported();
  const enabled = isVoiceEnabled();
  const muted = isMuted();

  // If muted or off, show desktop notification if permitted, and resolve immediately
  if (!supported || !enabled || muted) {
    showDesktopNotification(text);
    if (onEnd) onEnd();
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    let finished = false;
    let currentUtterance = null;

    const finish = () => {
      if (!finished) {
        finished = true;
        clearTimeout(timer);
        setSpeakingState(false);
        if (currentUtterance) {
          activeUtterances.delete(currentUtterance);
        }
        if (onEnd) onEnd();
        resolve();
      }
    };

    // ~12 characters per second + 6s buffer; min 6s
    const maxDuration = timeoutMs || Math.max(6000, Math.ceil(text.length / 12) * 1000 + 6000);
    const timer = setTimeout(finish, maxDuration);

    try {
      window.speechSynthesis.cancel();
      currentUtterance = new SpeechSynthesisUtterance(text);
      activeUtterances.add(currentUtterance);
      setSpeakingState(true);

      const voices = window.speechSynthesis.getVoices();
      if (voices && voices.length > 0) {
        const enVoice = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith('en'));
        if (enVoice) {
          currentUtterance.voice = enVoice;
        }
      }

      currentUtterance.onend = finish;
      currentUtterance.onerror = finish;
      window.speechSynthesis.speak(currentUtterance);
    } catch {
      finish();
    }
  });
}

export function pauseSpeech() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try {
      window.speechSynthesis.pause();
    } catch {}
  }
}

export function resumeSpeech() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try {
      window.speechSynthesis.resume();
    } catch {}
  }
}

export function stopSpeech() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try {
      window.speechSynthesis.cancel();
      activeUtterances.clear();
      setSpeakingState(false);
    } catch {}
  }
}

/**
 * Listen for a spoken answer to "Shall I read them?" using Web SpeechRecognition.
 * Listens for up to timeoutMs (default 6 seconds), then stops automatically.
 */
export function listenForVoiceAnswer({ onAnswer, onTimeout, onError, timeoutMs = 6000 } = {}) {
  const SpeechRec = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
  if (!SpeechRec) {
    if (onError) onError('SpeechRecognition not supported in browser');
    return () => {};
  }

  let recognition = null;
  let settled = false;
  let timer = null;

  const cleanup = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (recognition) {
      try {
        recognition.abort();
      } catch {}
      recognition = null;
    }
  };

  try {
    recognition = new SpeechRec();
    recognition.lang = 'en-US';
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 3;

    timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        cleanup();
        if (onTimeout) onTimeout();
      }
    }, timeoutMs);

    recognition.onresult = (event) => {
      if (settled) return;
      settled = true;
      cleanup();

      const transcripts = [];
      for (let i = 0; i < event.results.length; i++) {
        for (let j = 0; j < event.results[i].length; j++) {
          transcripts.push(event.results[i][j].transcript.toLowerCase().trim());
        }
      }
      const combined = transcripts.join(' ');

      const positiveMatch = /\b(yes|read\s+them|read|go\s+ahead|sure|ok|okay|yeah|yep)\b/i.test(combined);
      const negativeMatch = /\b(no|not\s+now|later|stop|cancel|never)\b/i.test(combined);

      if (positiveMatch) {
        if (onAnswer) onAnswer('yes', combined);
      } else if (negativeMatch) {
        if (onAnswer) onAnswer('no', combined);
      } else {
        if (onAnswer) onAnswer('unrecognized', combined);
      }
    };

    recognition.onerror = (err) => {
      if (settled) return;
      settled = true;
      cleanup();
      if (onError) onError(err);
    };

    recognition.onend = () => {
      if (!settled) {
        settled = true;
        cleanup();
        if (onTimeout) onTimeout();
      }
    };

    recognition.start();
  } catch (err) {
    settled = true;
    cleanup();
    if (onError) onError(err);
  }

  return cleanup;
}
