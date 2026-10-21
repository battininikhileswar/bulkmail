import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Search, Zap, LayoutDashboard, Users, Megaphone, Compass, MessageSquare, FileText, History, Settings, Volume2, X } from 'lucide-react';

export function CommandPalette({
  isOpen,
  onClose,
  onNavigate,
  contacts = [],
  onTriggerVoiceBriefing,
}) {
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery('');
    }
  }, [isOpen]);

  // Keyboard shortcut Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
        else onClose(false); // toggle handled by parent
      } else if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const navPages = [
    { id: 'Quick Start', label: 'Quick Start', icon: Zap },
    { id: 'Dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'Contacts', label: 'Contacts', icon: Users },
    { id: 'Campaign', label: 'Campaign', icon: Megaphone },
    { id: 'Autopilot', label: 'Autopilot', icon: Compass },
    { id: 'Replies', label: 'Replies', icon: MessageSquare },
    { id: 'Drafts', label: 'Drafts', icon: FileText },
    { id: 'Activity', label: 'Activity Log', icon: History },
    { id: 'Settings', label: 'Settings', icon: Settings },
  ];

  const filteredPages = navPages.filter((p) =>
    p.label.toLowerCase().includes(query.toLowerCase().trim())
  );

  const filteredContacts = query.trim()
    ? contacts
        .filter(
          (c) =>
            c.name?.toLowerCase().includes(query.toLowerCase()) ||
            c.email?.toLowerCase().includes(query.toLowerCase())
        )
        .slice(0, 5)
    : [];

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 bg-[#0A0A0A]/85 backdrop-blur-sm">
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: -10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -10 }}
          transition={{ duration: 0.15 }}
          className="w-full max-w-lg glass-strong overflow-hidden text-[#F5F1E6]"
        >
          {/* Search Header */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-[rgba(212,175,55,0.18)]">
            <Search className="w-4 h-4 text-[#D4AF37] flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search pages, contacts, or quick actions..."
              className="w-full bg-transparent border-none text-xs sm:text-sm text-[#F5F1E6] placeholder:text-[#A59F8F] focus:outline-none caret-[#D4AF37]"
            />
            <span className="text-[10px] text-[#A59F8F] border border-[rgba(212,175,55,0.22)] px-1.5 py-0.5 rounded font-mono">
              ESC
            </span>
          </div>

          {/* Results List */}
          <div className="p-2 max-h-80 overflow-y-auto space-y-3 text-xs">
            {/* Quick Actions */}
            <div>
              <div className="px-2.5 py-1 text-[10px] font-bold text-[#A59F8F] uppercase tracking-wider">
                Quick Actions
              </div>
              <button
                type="button"
                onClick={() => {
                  onTriggerVoiceBriefing?.();
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left text-[#F5F1E6] hover:bg-[#1A1A1A] hover:text-[#F2D675] cursor-pointer"
              >
                <Volume2 className="w-4 h-4 text-[#D4AF37]" />
                <span>Read my replies aloud</span>
              </button>
            </div>

            {/* Navigation Pages */}
            <div>
              <div className="px-2.5 py-1 text-[10px] font-bold text-[#A59F8F] uppercase tracking-wider">
                Pages
              </div>
              {filteredPages.map((page) => {
                const Icon = page.icon;
                return (
                  <button
                    key={page.id}
                    type="button"
                    onClick={() => {
                      onNavigate(page.id);
                      onClose();
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left text-[#F5F1E6] hover:bg-[#1A1A1A] hover:text-[#F2D675] cursor-pointer"
                  >
                    <Icon className="w-4 h-4 text-[#A59F8F]" />
                    <span>{page.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Contacts Matches */}
            {filteredContacts.length > 0 && (
              <div>
                <div className="px-2.5 py-1 text-[10px] font-bold text-[#A59F8F] uppercase tracking-wider">
                  Contacts
                </div>
                {filteredContacts.map((contact) => (
                  <button
                    key={contact.id}
                    type="button"
                    onClick={() => {
                      onNavigate('Contacts');
                      onClose();
                    }}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-left hover:bg-[#1A1A1A] cursor-pointer"
                  >
                    <div className="truncate">
                      <span className="font-semibold text-[#F5F1E6]">{contact.name}</span>
                      <span className="text-[11px] text-[#A59F8F] ml-2 font-mono">{contact.email}</span>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1A1A1A] text-[#D4AF37] border border-[rgba(212,175,55,0.2)]">
                      {contact.status}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
