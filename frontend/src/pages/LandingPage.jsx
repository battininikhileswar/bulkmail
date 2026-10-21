import React, { useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Badge, StatusBadge } from '@/components/ui/badge';
import {
  ShieldCheck,
  Mail,
  Users,
  Compass,
  Cpu,
  Volume2,
  ArrowRight,
  ChevronDown,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Lock,
  Calendar,
  Sparkles,
  Zap,
  Upload,
  Send,
  MessageSquare,
} from 'lucide-react';

export function LandingPage({ currentUser, onNavigateToLogin, onNavigateToApp }) {
  const prefersReduced = useReducedMotion();
  const [openFaq, setOpenFaq] = useState(null);
  const [legalModal, setLegalModal] = useState(null); // 'privacy' | 'terms' | null

  const toggleFaq = (index) => {
    setOpenFaq(openFaq === index ? null : index);
  };

  const scrollToSection = (id) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: prefersReduced ? 'auto' : 'smooth' });
    }
  };

  const faqs = [
    {
      q: 'Does the system send AI replies automatically?',
      a: 'No. The assistant generates response drafts strictly grounded in details you provide, but no email is ever dispatched until you manually click "Approve & Send". Auto-replies remain permanently disabled by design.',
    },
    {
      q: 'What happens when I hit my Gmail daily sending limit?',
      a: 'The dispatcher tracks daily sent counts and reserves 10% specifically for conversational replies. If your daily quota is reached, remaining campaign recipients are paused until your next authorized send window without failing.',
    },
    {
      q: 'Where are my Google credentials and tokens stored?',
      a: 'Your Google tokens are stored in an isolated, git-ignored local folder on the backend host with strict file-level separation. Each user\'s data is completely isolated; User A can never see or send from User B\'s data.',
    },
    {
      q: 'How does Test Mode safeguard my recipients?',
      a: 'When Test Mode is active, all outgoing campaign emails and test replies are diverted strictly to your configured test email address with a [TEST] subject prefix, without consuming live provider quota.',
    },
    {
      q: 'Can I use a custom domain or company email with SMTP?',
      a: 'Yes. Custom domains can utilize authenticated SMTP dispatch. Personal Gmail (@gmail.com) accounts are restricted to Google OAuth to ensure full SPF and DKIM compliance.',
    },
  ];

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E6] font-sans selection:bg-[#D4AF37] selection:text-[#0A0A0A]">
      {/* 1. Top Navigation */}
      <header className="sticky top-0 z-40 glass rounded-none border-t-0 border-x-0 border-b border-[rgba(212,175,55,0.22)] px-6 py-3.5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5 cursor-pointer" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <div className="w-8 h-8 rounded-lg bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] text-[#0A0A0A] font-bold text-sm flex items-center justify-center shadow-[0_0_12px_rgba(212,175,55,0.4)]">
              M
            </div>
            <div>
              <span className="font-bold text-sm tracking-tight text-[#F5F1E6]">Mail Assistant</span>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-6 text-xs font-medium text-[#A59F8F]">
            <button type="button" onClick={() => scrollToSection('features')} className="hover:text-[#F2D675] transition-colors">
              Features
            </button>
            <button type="button" onClick={() => scrollToSection('how-it-works')} className="hover:text-[#F2D675] transition-colors">
              How it works
            </button>
            <button type="button" onClick={() => scrollToSection('safety')} className="hover:text-[#F2D675] transition-colors">
              Safety
            </button>
            <button type="button" onClick={() => scrollToSection('faq')} className="hover:text-[#F2D675] transition-colors">
              FAQ
            </button>
          </nav>

          <div className="flex items-center gap-3">
            {currentUser ? (
              <Button variant="primary" size="sm" onClick={onNavigateToApp}>
                Go to Dashboard
                <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            ) : (
              <Button variant="primary" size="sm" onClick={onNavigateToLogin}>
                Sign In
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* 2. Hero Section */}
      <section className="relative pt-20 pb-16 px-6 overflow-hidden gold-glow-radial">
        {/* 3 Large Blurred Drifting Gold Glow Orbs */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[650px] h-[650px] rounded-full bg-[radial-gradient(circle,rgba(212,175,55,0.18)_0%,rgba(212,175,55,0)_70%)] blur-[90px] pointer-events-none animate-drift-1 -z-10" />
        <div className="absolute top-1/2 left-1/6 -translate-y-1/2 w-[520px] h-[520px] rounded-full bg-[radial-gradient(circle,rgba(242,214,117,0.14)_0%,rgba(212,175,55,0)_70%)] blur-[100px] pointer-events-none animate-drift-2 -z-10" />
        <div className="absolute top-3/5 right-1/6 w-[560px] h-[560px] rounded-full bg-[radial-gradient(circle,rgba(184,150,46,0.16)_0%,rgba(212,175,55,0)_70%)] blur-[110px] pointer-events-none animate-drift-3 -z-10" />

        <div className="max-w-4xl mx-auto text-center space-y-6 relative z-10">
          <motion.div
            initial={prefersReduced ? { opacity: 1 } : { opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[rgba(212,175,55,0.35)] bg-[#121212] text-[#F2D675] text-xs font-medium shadow-[0_0_15px_rgba(212,175,55,0.15)]"
          >
            <Sparkles className="w-3.5 h-3.5 text-[#D4AF37]" />
            Human-in-the-Loop Personalized Email Dispatch
          </motion.div>

          <motion.h1
            initial={prefersReduced ? { opacity: 1 } : { opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            style={{ textWrap: 'balance' }}
            className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight leading-[1.18] [text-wrap:balance] max-w-3xl mx-auto"
          >
            Send Personalized Email at Scale{' '}
            <span className="gold-gradient-text block mt-1">Within Your Daily Limit</span>
          </motion.h1>

          <motion.p
            initial={prefersReduced ? { opacity: 1 } : { opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="text-sm sm:text-base text-[#A59F8F] max-w-2xl mx-auto leading-relaxed"
          >
            Dispatch multi-day campaigns from your own Google account. Track incoming replies, listen to voice briefings, and approve AI drafts grounded strictly in your facts.
          </motion.p>

          <motion.div
            initial={prefersReduced ? { opacity: 1 } : { opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="flex items-center justify-center gap-3 pt-2"
          >
            <Button
              variant="primary"
              size="md"
              onClick={currentUser ? onNavigateToApp : onNavigateToLogin}
              className="text-xs sm:text-sm font-semibold px-6"
            >
              {currentUser ? 'Go to Dashboard' : 'Get Started'}
              <ArrowRight className="w-4 h-4 ml-1.5" />
            </Button>
            <Button
              variant="outline"
              size="md"
              onClick={() => scrollToSection('how-it-works')}
              className="text-xs sm:text-sm px-5"
            >
              See How It Works
            </Button>
          </motion.div>
        </div>

        {/* Numberless Workflow Strip */}
        <motion.div
          initial={prefersReduced ? { opacity: 1 } : { opacity: 0, y: 25 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.4 }}
          className="max-w-5xl mx-auto mt-14 glass overflow-hidden relative z-10"
        >
          {/* Top Bar */}
          <div className="bg-[#1A1A1A] border-b border-[rgba(212,175,55,0.22)] px-4 py-2.5 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[#FF5C5C]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#FF9F43]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#3DDC97]" />
              <span className="ml-2 font-semibold text-xs text-[#F2D675]">How it works</span>
            </div>
            <span className="text-[11px] text-[#A59F8F] font-mono">End-to-End Workflow</span>
          </div>

          {/* Workflow Strip: 5 Step Tiles Connected by a Thin Gold Line */}
          <div className="p-6 sm:p-8 relative">
            <div
              className="hidden sm:block absolute top-1/2 left-12 right-12 h-[1px] bg-[rgba(212,175,55,0.3)] -translate-y-5 z-0"
              aria-hidden="true"
            />

            <div className="grid grid-cols-1 sm:grid-cols-5 gap-3.5 relative z-10">
              {[
                { label: 'Upload CSV', icon: Upload },
                { label: 'Send within your daily limit', icon: Send },
                { label: 'Replies tracked', icon: MessageSquare },
                { label: 'AI drafts from your facts', icon: Sparkles },
                { label: 'You approve', icon: ShieldCheck },
              ].map((step, idx) => {
                const Icon = step.icon;
                return (
                  <div
                    key={idx}
                    className="flex flex-col items-center text-center p-4 rounded-xl bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] space-y-2.5 shadow-[0_4px_16px_rgba(0,0,0,0.35)]"
                  >
                    <div className="w-10 h-10 rounded-full bg-[#D4AF37]/15 border border-[#D4AF37]/40 flex items-center justify-center text-[#F2D675] shadow-[0_0_12px_rgba(212,175,55,0.15)] flex-shrink-0">
                      <Icon className="w-4 h-4 text-[#F2D675]" />
                    </div>
                    <span className="text-xs font-semibold text-[#F5F1E6] leading-snug">
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>
      </section>

      {/* 3. Features Grid (6 Real Features) */}
      <section id="features" className="py-20 px-6 max-w-6xl mx-auto border-t border-[rgba(212,175,55,0.15)]">
        <div className="text-center space-y-3 mb-14">
          <Badge variant="gold" className="text-xs">Product Capabilities</Badge>
          <h2 className="text-2xl sm:text-4xl font-bold text-[#F5F1E6]">
            Engineered for Precision, Safety & Daily Limits
          </h2>
          <p className="text-xs sm:text-sm text-[#A59F8F] max-w-xl mx-auto">
            Everything you need to run reliable email outreach without risking spam flags, rate-limits, or unverified AI outputs.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* 1 */}
          <div className="glass p-6 space-y-3 transition-all">
            <div className="w-10 h-10 rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/30 flex items-center justify-center text-[#F2D675]">
              <Lock className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#F2D675]">Google Sign-In & Send-As-You</h3>
            <p className="text-xs text-[#A59F8F] leading-relaxed">
              Authenticate with your Google account via secure OAuth with PKCE. All campaign emails and replies originate strictly from your authorized address.
            </p>
          </div>

          {/* 2 */}
          <div className="glass p-6 space-y-3 transition-all">
            <div className="w-10 h-10 rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/30 flex items-center justify-center text-[#F2D675]">
              <Users className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#F2D675]">CSV Upload & Validation</h3>
            <p className="text-xs text-[#A59F8F] leading-relaxed">
              Import contacts with automatic deduplication, email syntax verification, and dynamic column placeholder tags like {'{name}'} and custom fields.
            </p>
          </div>

          {/* 3 */}
          <div className="glass p-6 space-y-3 transition-all">
            <div className="w-10 h-10 rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/30 flex items-center justify-center text-[#F2D675]">
              <Calendar className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#F2D675]">Limit-Aware Multi-Day Sending</h3>
            <p className="text-xs text-[#A59F8F] leading-relaxed">
              Automatically split large contact lists over multiple days. Daily send caps are strictly respected with an automated 10% reserve for replies.
            </p>
          </div>

          {/* 4 */}
          <div className="glass p-6 space-y-3 transition-all">
            <div className="w-10 h-10 rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/30 flex items-center justify-center text-[#F2D675]">
              <Compass className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#F2D675]">Reply Tracking & Classification</h3>
            <p className="text-xs text-[#A59F8F] leading-relaxed">
              Background reply watcher monitors your Gmail threads, categorizes responses into questions, inquiries, or scheduling, and filters out-of-office notes.
            </p>
          </div>

          {/* 5 */}
          <div className="glass p-6 space-y-3 transition-all">
            <div className="w-10 h-10 rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/30 flex items-center justify-center text-[#F2D675]">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#F2D675]">Grounded AI Drafts</h3>
            <p className="text-xs text-[#A59F8F] leading-relaxed">
              The AI drafts proposed answers using only facts you entered in your campaign prompt. It never hallucinates unverified claims, links, or promises.
            </p>
          </div>

          {/* 6 */}
          <div className="glass p-6 space-y-3 transition-all">
            <div className="w-10 h-10 rounded-lg bg-[#D4AF37]/15 border border-[#D4AF37]/30 flex items-center justify-center text-[#F2D675]">
              <Volume2 className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-[#F2D675]">Interactive Voice Briefing</h3>
            <p className="text-xs text-[#A59F8F] leading-relaxed">
              The assistant speaks: "You have 2 new replies. Shall I read them?" with voice recognition answers ("Yes", "Not now") and playback controls.
            </p>
          </div>
        </div>
      </section>

      {/* 4. How It Works (4 Steps) */}
      <section id="how-it-works" className="py-20 px-6 max-w-5xl mx-auto border-t border-[rgba(212,175,55,0.15)]">
        <div className="text-center space-y-3 mb-14">
          <Badge variant="gold" className="text-xs">Streamlined Workflow</Badge>
          <h2 className="text-2xl sm:text-4xl font-bold text-[#F5F1E6]">
            From CSV to Dispatched Outreach in Minutes
          </h2>
          <p className="text-xs sm:text-sm text-[#A59F8F]">
            Four simple steps designed to keep you in complete command of every outgoing word.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="glass p-5 space-y-2 relative">
            <div className="text-2xl font-mono font-bold text-[#D4AF37]">01</div>
            <h4 className="text-xs font-bold text-[#F5F1E6]">Upload Contacts</h4>
            <p className="text-[11px] text-[#A59F8F] leading-relaxed">
              Drop your CSV file. The system checks email syntax, skips duplicates, and flags any invalid entries on upload.
            </p>
          </div>

          <div className="glass p-5 space-y-2 relative">
            <div className="text-2xl font-mono font-bold text-[#D4AF37]">02</div>
            <h4 className="text-xs font-bold text-[#F5F1E6]">Draft Template</h4>
            <p className="text-[11px] text-[#A59F8F] leading-relaxed">
              Choose an announcement, reminder, or follow-up goal. Click "Write it for me" or edit your personalized placeholders.
            </p>
          </div>

          <div className="glass p-5 space-y-2 relative">
            <div className="text-2xl font-mono font-bold text-[#D4AF37]">03</div>
            <h4 className="text-xs font-bold text-[#F5F1E6]">Send Within Limits</h4>
            <p className="text-[11px] text-[#A59F8F] leading-relaxed">
              Tick the consent confirmation and start. The queue respects pause delays and provider caps, resuming automatically next day.
            </p>
          </div>

          <div className="glass p-5 space-y-2 relative">
            <div className="text-2xl font-mono font-bold text-[#D4AF37]">04</div>
            <h4 className="text-xs font-bold text-[#F5F1E6]">Review AI Replies</h4>
            <p className="text-[11px] text-[#A59F8F] leading-relaxed">
              Hear incoming replies read aloud. Review grounded drafts and dispatch with one-click "Approve & Send".
            </p>
          </div>
        </div>
      </section>

      {/* 5. Safety and Control Section */}
      <section id="safety" className="py-20 px-6 max-w-5xl mx-auto border-t border-[rgba(212,175,55,0.15)]">
        <div className="glass p-8 sm:p-12 space-y-8">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-1.5 text-xs text-[#3DDC97] font-semibold">
              <ShieldCheck className="w-4 h-4" />
              Safety Architecture
            </div>
            <h3 className="text-2xl sm:text-3xl font-bold text-[#F2D675]">
              Human-in-the-Loop Safeguards
            </h3>
            <p className="text-xs sm:text-sm text-[#A59F8F] leading-relaxed max-w-2xl">
              We never bypass provider boundaries, disguise sending headers, or automate customer responses without your physical approval.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="flex items-start gap-2.5 p-3 rounded-xl bg-[#1A1A1A]/80 border border-[rgba(212,175,55,0.18)]">
              <CheckCircle2 className="w-4 h-4 text-[#3DDC97] flex-shrink-0 mt-0.5" />
              <div>
                <strong className="text-[#F5F1E6] block">You Approve Every Single Reply</strong>
                <span className="text-[#A59F8F]">AI drafts remain in a pending state until you review the text and click Approve & Send.</span>
              </div>
            </div>

            <div className="flex items-start gap-2.5 p-3 rounded-xl bg-[#1A1A1A]/80 border border-[rgba(212,175,55,0.18)]">
              <CheckCircle2 className="w-4 h-4 text-[#3DDC97] flex-shrink-0 mt-0.5" />
              <div>
                <strong className="text-[#F5F1E6] block">Unsubscribe Honored Promptly</strong>
                <span className="text-[#A59F8F]">Contacts requesting to stop are marked unsubscribed and excluded from all future sends.</span>
              </div>
            </div>

            <div className="flex items-start gap-2.5 p-3 rounded-xl bg-[#1A1A1A]/80 border border-[rgba(212,175,55,0.18)]">
              <CheckCircle2 className="w-4 h-4 text-[#3DDC97] flex-shrink-0 mt-0.5" />
              <div>
                <strong className="text-[#F5F1E6] block">Uncertain Sends Held For Review</strong>
                <span className="text-[#A59F8F]">Socket timeouts never re-send blindly. They are flagged for manual review to prevent double-sending.</span>
              </div>
            </div>

            <div className="flex items-start gap-2.5 p-3 rounded-xl bg-[#1A1A1A]/80 border border-[rgba(212,175,55,0.18)]">
              <CheckCircle2 className="w-4 h-4 text-[#3DDC97] flex-shrink-0 mt-0.5" />
              <div>
                <strong className="text-[#F5F1E6] block">Safe Isolated Test Mode</strong>
                <span className="text-[#A59F8F]">Switch on Test Mode at any time to verify rendering without emailing real recipients.</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 6. Honest Limits Callout */}
      <section className="py-6 px-6 max-w-5xl mx-auto">
        <div className="glass p-4 text-center text-xs text-[#A59F8F] space-y-1">
          <p className="font-semibold text-[#F2D675]">
            Works within your email provider's daily sending limits.
          </p>
          <p className="text-[11px] text-[#A59F8F]">
            Prototype: sign-in is limited to approved test users. Personal accounts cap at 400 emails/day; Workspace accounts at 1,500/day.
          </p>
        </div>
      </section>

      {/* 7. FAQ (Accordion) & Call to Action */}
      <section id="faq" className="py-20 px-6 max-w-4xl mx-auto border-t border-[rgba(212,175,55,0.15)]">
        <div className="text-center space-y-3 mb-12">
          <Badge variant="gold" className="text-xs">Common Questions</Badge>
          <h2 className="text-2xl sm:text-3xl font-bold text-[#F5F1E6]">Frequently Asked Questions</h2>
        </div>

        <div className="space-y-3">
          {faqs.map((faq, idx) => {
            const isOpen = openFaq === idx;
            return (
              <div
                key={idx}
                className="glass overflow-hidden transition-all"
              >
                <button
                  type="button"
                  onClick={() => toggleFaq(idx)}
                  className="w-full flex items-center justify-between p-4 text-left text-xs sm:text-sm font-semibold text-[#F5F1E6] hover:text-[#F2D675] cursor-pointer"
                >
                  <span>{faq.q}</span>
                  <ChevronDown className={`w-4 h-4 text-[#D4AF37] transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pt-1 text-xs text-[#A59F8F] leading-relaxed border-t border-[rgba(212,175,55,0.1)]">
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Final Call to Action */}
        <div className="mt-16 text-center space-y-5 glass p-8">
          <h3 className="text-xl sm:text-2xl font-bold text-[#F2D675]">Ready to dispatch your campaign safely?</h3>
          <p className="text-xs text-[#A59F8F] max-w-md mx-auto">
            Sign in with your authorized Google account and create a ready-to-dispatch campaign in under 60 seconds.
          </p>
          <Button
            variant="primary"
            size="md"
            onClick={currentUser ? onNavigateToApp : onNavigateToLogin}
            className="text-xs font-semibold px-6"
          >
            {currentUser ? 'Go to Dashboard' : 'Get Started with Google'}
            <ArrowRight className="w-4 h-4 ml-1.5" />
          </Button>
        </div>
      </section>

      {/* 8. Footer */}
      <footer className="border-t border-[rgba(212,175,55,0.18)] bg-[#0A0A0A] py-10 px-6 text-xs text-[#A59F8F]">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="space-y-1 text-center sm:text-left">
            <div className="font-bold text-[#F2D675]">Mail Assistant</div>
            <p className="text-[11px] text-[#A59F8F]">
              An intelligent email management tool operating strictly within authorized provider quotas.
            </p>
          </div>

          <div className="flex items-center gap-4 text-[11px]">
            <button type="button" onClick={() => setLegalModal('privacy')} className="hover:text-[#F2D675]">
              Privacy Policy
            </button>
            <span className="text-[rgba(212,175,55,0.3)]">•</span>
            <button type="button" onClick={() => setLegalModal('terms')} className="hover:text-[#F2D675]">
              Terms of Service
            </button>
          </div>
        </div>
      </footer>

      {/* Legal Modal Placeholder */}
      {legalModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0A0A0A]/85 backdrop-blur-sm">
          <div className="bg-[#121212] border border-[rgba(212,175,55,0.3)] rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-xs">
            <h3 className="text-sm font-bold text-[#F2D675] capitalize">
              {legalModal === 'privacy' ? 'Privacy Policy' : 'Terms of Service'}
            </h3>
            <div className="space-y-2 text-[#A59F8F] leading-relaxed max-h-60 overflow-y-auto pr-2">
              <p>
                This application acts as a client interface between you and your configured email provider. Your Google authorization tokens are saved securely on your local deployment and are used only to dispatch emails you approve and retrieve incoming replies for your threads.
              </p>
              <p>
                We do not sell, rent, or transfer your contact data or email content to third parties. AI calls transmit prompt details solely to your configured provider (e.g. Anthropic) for completion without retaining facts for public training.
              </p>
            </div>
            <div className="flex justify-end pt-2 border-t border-[rgba(212,175,55,0.15)]">
              <Button variant="outline" size="sm" onClick={() => setLegalModal(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
