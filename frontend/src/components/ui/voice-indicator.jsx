import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { subscribeSpeechState } from '@/voice';
import { Volume2 } from 'lucide-react';

export function VoiceSpeakingIndicator() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const prefersReduced = useReducedMotion();

  useEffect(() => {
    return subscribeSpeechState(setIsSpeaking);
  }, []);

  return (
    <AnimatePresence>
      {isSpeaking && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.9 }}
          transition={{ duration: 0.15 }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#1A1A1A] border border-[#D4AF37]/50 text-[#F2D675] text-[11px] font-medium shadow-[0_0_10px_rgba(212,175,55,0.25)]"
          title="AI Voice is speaking..."
        >
          <Volume2 className="w-3.5 h-3.5 text-[#F2D675] animate-pulse" />
          <span>Speaking</span>
          {!prefersReduced && (
            <div className="flex items-center gap-0.5 h-2.5">
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  className="w-0.5 bg-[#F2D675] rounded-full"
                  animate={{ height: ['4px', '10px', '4px'] }}
                  transition={{
                    duration: 0.45,
                    repeat: Infinity,
                    delay: i * 0.15,
                    ease: 'easeInOut',
                  }}
                />
              ))}
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
