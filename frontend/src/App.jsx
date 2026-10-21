import React, { useState, useEffect, useRef } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
} from 'react-router-dom';
import {
  isVoiceSupported,
  isVoiceEnabled,
  enableVoice,
  isMuted as checkIsMuted,
  setMuted as saveMutedPreference,
  cleanContactName,
  cleanContactFirstName,
  speak,
  getSeenReplyIds,
  saveSeenReplyIds,
} from './voice';
import { useVoiceBriefing } from './useVoiceBriefing';
import { VoiceBriefingBanner } from '@/components/VoiceBriefingBanner';
import { ToastProvider, useToast } from '@/components/ui/toast';
import { VoiceSpeakingIndicator } from '@/components/ui/voice-indicator';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { LoadingScreen } from '@/components/LoadingScreen';
import { CommandPalette } from '@/components/CommandPalette';

// Pages
import { LandingPage } from '@/pages/LandingPage';
import { LoginPage } from '@/pages/LoginPage';
import { QuickStartPage } from '@/pages/QuickStartPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { ContactsPage } from '@/pages/ContactsPage';
import { CampaignPage } from '@/pages/CampaignPage';
import { AutopilotPage } from '@/pages/AutopilotPage';
import { RepliesPage } from '@/pages/RepliesPage';
import { DraftsPage } from '@/pages/DraftsPage';
import { ActivityPage } from '@/pages/ActivityPage';
import { SettingsPage } from '@/pages/SettingsPage';

import {
  Zap,
  LayoutDashboard,
  Users,
  Megaphone,
  Compass,
  MessageSquare,
  FileText,
  History,
  Settings as SettingsIcon,
  Pause,
  Play,
  Volume2,
  VolumeX,
  Mic,
  AlertTriangle,
  LogOut,
  Search,
  Bell,
  ChevronLeft,
  ChevronRight,
  User,
  ShieldCheck,
  CheckCircle2,
} from 'lucide-react';

import { getApiBaseUrl } from '@/lib/api';

const API = getApiBaseUrl();

function Workspace({ currentUser, setCurrentUser, onLogout }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [tab, setTab] = useState('Dashboard');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);

  // Voice State
  const [voiceEnabled, setVoiceEnabled] = useState(isVoiceEnabled);
  const [voiceMuted, setVoiceMuted] = useState(checkIsMuted);

  // Polling / Live connection status
  const [isOnline, setIsOnline] = useState(true);

  // Core Data
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState({
    total: 0,
    pending: 0,
    sent: 0,
    failed: 0,
    unsubscribed: 0,
    unhandled_replies: 0,
    pending_drafts: 0,
    stranded: 0,
  });
  const [strandedItems, setStrandedItems] = useState({
    stranded_recipients: [],
    stranded_drafts: [],
    total_stranded: 0,
  });
  const [contacts, setContacts] = useState([]);
  const [search, setSearch] = useState('');
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  // Replies State
  const [replies, setReplies] = useState([]);
  const [replyFilter, setReplyFilter] = useState('all');
  const [selectedReplyId, setSelectedReplyId] = useState(null);
  const [thread, setThread] = useState(null);

  // Drafts State
  const [drafts, setDrafts] = useState([]);
  const [draftFilter, setDraftFilter] = useState('all');
  const [selectedDraftId, setSelectedDraftId] = useState(null);
  const [draftBodyEdit, setDraftBodyEdit] = useState('');
  const [savingDraft, setSavingDraft] = useState(false);
  const [globalPaused, setGlobalPaused] = useState(false);

  // Voice Briefing Hook
  const {
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
  } = useVoiceBriefing({
    currentUser,
    replies,
    drafts,
    voiceEnabled,
    voiceMuted,
    onMuteChange: (nextMuted) => setVoiceMuted(nextMuted),
    toast,
  });

  // Campaign State
  const [campaigns, setCampaigns] = useState([]);
  const [activeCampId, setActiveCampId] = useState(null);
  const [chips, setChips] = useState(['name']);
  const [groups, setGroups] = useState([]);
  const [campName, setCampName] = useState('Welcome Campaign');
  const [subject, setSubject] = useState('Welcome to our event');
  const [mode, setMode] = useState('same');
  const [provider, setProvider] = useState('gmail');
  const [groupTag, setGroupTag] = useState('');
  const [template, setTemplate] = useState('Hi {name},\n\nThank you for registering! We look forward to seeing you.');
  const [progress, setProgress] = useState(null);
  const [campaignPlan, setCampaignPlan] = useState(null);
  const [preview, setPreview] = useState(null);
  const [showPreview, setShowPreview] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [testEmail, setTestEmail] = useState('test@example.com');
  const [testResult, setTestResult] = useState(null);

  // Watcher & AI Usage
  const [watcher, setWatcher] = useState({ running: false, last_check_time: null, messages_seen: 0 });
  const [aiUsage, setAiUsage] = useState({ total_calls: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0 });
  const [rechecking, setRechecking] = useState(false);

  // Activity State
  const [activity, setActivity] = useState([]);
  const [activityFilter, setActivityFilter] = useState('');

  // Settings State
  const [settings, setSettings] = useState({
    sender_name: 'Event Coordinator',
    tone: 'friendly and professional',
    test_mode: true,
    test_email: 'test@example.com',
    daily_cap: 400,
    pause_seconds: 5,
    unsubscribe_line: '',
    footer_preview: '',
    ai_provider: 'anthropic',
  });
  const [savingSettings, setSavingSettings] = useState(false);
  const [backups, setBackups] = useState([]);

  const seenReplyIdsRef = useRef(new Set());
  const initialRepliesLoadedRef = useRef(false);
  const seenReviewDraftIdsRef = useRef(new Set());
  const initialDraftsLoadedRef = useRef(false);
  const templateRef = useRef(null);
  const notificationsRef = useRef(null);
  const userMenuRef = useRef(null);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (notificationsRef.current && !notificationsRef.current.contains(e.target)) {
        setNotificationsOpen(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  // Voice toggle helpers
  const handleEnableVoice = () => {
    enableVoice();
    setVoiceEnabled(true);
    setVoiceMuted(checkIsMuted());
    toast.info('Voice notifications enabled.');
  };

  const handleToggleVoiceMute = () => {
    const next = !voiceMuted;
    saveMutedPreference(next);
    setVoiceMuted(next);
    toast.info(next ? 'Voice notifications muted.' : 'Voice notifications active.');
  };

  // API Call Helpers
  const fetchHealth = () =>
    fetch(`${API}/health`)
      .then((r) => r.ok && r.json())
      .then((h) => {
        setIsOnline(true);
        setHealth(h);
        if (h && typeof h.global_sending_paused === 'boolean') {
          setGlobalPaused(h.global_sending_paused);
        }
      })
      .catch(() => {
        setIsOnline(false);
        setHealth(null);
      });

  const toggleGlobalSending = async () => {
    const action = globalPaused ? 'resume' : 'pause';
    try {
      const res = await fetch(`${API}/sending/${action}`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setGlobalPaused(data.paused);
        toast.info(data.paused ? 'Global sending paused.' : 'Global sending resumed.');
      }
    } catch {
      toast.error('Failed to change sending status.');
    }
  };

  const fetchActivity = (email = activityFilter) => {
    let url = `${API}/activity?limit=200`;
    if (email && email.trim()) url += `&contact_email=${encodeURIComponent(email.trim())}`;
    fetch(url).then((r) => r.ok && r.json()).then((d) => setActivity(d || [])).catch(() => {});
  };

  const fetchSettings = () => {
    fetch(`${API}/settings`).then((r) => r.ok && r.json()).then((d) => d && setSettings(d)).catch(() => {});
    fetch(`${API}/backups`).then((r) => r.ok && r.json()).then((b) => b && setBackups(b || [])).catch(() => {});
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setSavingSettings(true);
    try {
      const res = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      const data = await res.json();
      if (res.ok) {
        setSettings(data);
        toast.success('Settings updated successfully.');
        fetchHealth();
      } else {
        toast.error('Failed to update settings.');
      }
    } catch {
      toast.error('Network error saving settings.');
    } finally {
      setSavingSettings(false);
    }
  };

  const handleBackupNow = async () => {
    try {
      const res = await fetch(`${API}/backups/create`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Backup created: ${data.filename}`);
        fetchSettings();
      } else {
        toast.error(data.detail || 'Backup failed.');
      }
    } catch {
      toast.error('Network error creating backup.');
    }
  };

  const handleRetryFailed = async () => {
    if (!activeCampId) return;
    try {
      const res = await fetch(`${API}/campaigns/${activeCampId}/retry-failed`, { method: 'POST' });
      const data = await res.json();
      toast.success(`Re-queued ${data.requeued_count || 0} failed contact(s).`);
      fetchProgress(activeCampId);
      fetchCampaigns();
      fetchStats();
    } catch {
      toast.error('Failed to re-queue failed contacts.');
    }
  };

  const fetchStats = () => fetch(`${API}/stats`).then((r) => r.ok && r.json()).then(setStats).catch(() => {});
  const fetchStranded = () => fetch(`${API}/stranded`).then((r) => r.ok && r.json()).then((d) => d && setStrandedItems(d)).catch(() => {});
  const fetchContacts = () => fetch(`${API}/contacts`).then((r) => r.ok && r.json()).then(setContacts).catch(() => {});
  const fetchChips = () => fetch(`${API}/contacts/placeholders`).then((r) => r.ok && r.json()).then((d) => { setChips(d.placeholders || ['name']); setGroups(d.groups || []); }).catch(() => {});
  const fetchCampaigns = () => fetch(`${API}/campaigns`).then((r) => r.ok && r.json()).then((d) => { setCampaigns(d); if (d.length && !activeCampId) setActiveCampId(d[0].id); }).catch(() => {});
  const fetchProgress = (id) => id && fetch(`${API}/campaigns/${id}/progress`).then((r) => r.ok && r.json()).then(setProgress).catch(() => {});
  const fetchCampaignPlan = (id) => id && fetch(`${API}/campaigns/${id}/plan`).then((r) => r.ok && r.json()).then(setCampaignPlan).catch(() => setCampaignPlan(null));
  const fetchWatcher = () => fetch(`${API}/watcher/status`).then((r) => r.ok && r.json()).then(setWatcher).catch(() => {});
  const fetchAiUsage = () => fetch(`${API}/ai/usage`).then((r) => r.ok && r.json()).then(setAiUsage).catch(() => {});

  const fetchDrafts = (filter = draftFilter) => {
    let url = `${API}/drafts`;
    if (filter !== 'all') url += `?status=${filter}`;
    fetch(url).then((r) => r.ok && r.json()).then((data) => {
      const list = data || [];
      setDrafts(list);
      if (selectedDraftId) {
        const found = list.find((d) => d.id === selectedDraftId);
        if (found) setDraftBodyEdit(found.body || '');
      }

      const reviewDrafts = list.filter((d) => d.status === 'needs_review');
      if (!initialDraftsLoadedRef.current) {
        initialDraftsLoadedRef.current = true;
        reviewDrafts.forEach((d) => seenReviewDraftIdsRef.current.add(d.id));
      } else {
        const freshReview = reviewDrafts.filter((d) => !seenReviewDraftIdsRef.current.has(d.id));
        if (freshReview.length > 0) {
          freshReview.forEach((d) => seenReviewDraftIdsRef.current.add(d.id));
          if (freshReview.length === 1) {
            speak('A draft needs your review');
          } else {
            speak(`${freshReview.length} drafts need review`);
          }
        }
      }
    }).catch(() => {});
  };

  const handleSelectDraft = (d) => {
    setSelectedDraftId(d.id);
    setDraftBodyEdit(d.body || '');
  };

  const handleSaveDraft = async () => {
    if (!selectedDraftId) return;
    setSavingDraft(true);
    try {
      const res = await fetch(`${API}/drafts/${selectedDraftId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: draftBodyEdit }),
      });
      if (res.ok) {
        toast.success('Draft updated successfully.');
        fetchDrafts();
        fetchStats();
      } else {
        toast.error('Failed to update draft.');
      }
    } catch {
      toast.error('Network error saving draft.');
    } finally {
      setSavingDraft(false);
    }
  };

  const handleRejectDraft = async () => {
    if (!selectedDraftId) return;
    setSavingDraft(true);
    try {
      const res = await fetch(`${API}/drafts/${selectedDraftId}/reject`, { method: 'POST' });
      if (res.ok) {
        toast.info('Draft rejected.');
        fetchDrafts();
        fetchStats();
      } else {
        toast.error('Failed to reject draft.');
      }
    } catch {
      toast.error('Network error rejecting draft.');
    } finally {
      setSavingDraft(false);
    }
  };

  const handleRegenerateDraft = async () => {
    if (!selectedDraftId) return;
    setSavingDraft(true);
    try {
      const res = await fetch(`${API}/drafts/${selectedDraftId}/regenerate`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Generated new draft (${data.status}).`);
        setSelectedDraftId(data.id);
        setDraftBodyEdit(data.body || '');
        fetchDrafts();
        fetchStats();
        fetchAiUsage();
      } else {
        toast.error(data.detail || 'Regeneration failed.');
      }
    } catch {
      toast.error('Network error regenerating draft.');
    } finally {
      setSavingDraft(false);
    }
  };

  const handleApproveAndSendDraft = async () => {
    if (!selectedDraftId) return;
    setSavingDraft(true);
    try {
      const sel = drafts.find((d) => d.id === selectedDraftId);
      const rawName = sel ? (sel.contact_name || '') : '';
      const firstName = cleanContactFirstName(rawName);
      if (firstName) {
        await speak(`Replying to ${firstName}`);
      } else {
        await speak('Replying');
      }

      await fetch(`${API}/drafts/${selectedDraftId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: draftBodyEdit }),
      });

      const res = await fetch(`${API}/drafts/${selectedDraftId}/send`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        toast.success('Draft approved and dispatched!');
        fetchDrafts();
        fetchStats();
        fetchReplies();
      } else {
        toast.error(data.detail || 'Failed to dispatch email.');
      }
    } catch {
      toast.error('Network error sending draft.');
    } finally {
      setSavingDraft(false);
    }
  };

  const fetchReplies = (filter = replyFilter) => {
    let url = `${API}/replies`;
    if (filter === 'unhandled') url += '?unprocessed_only=true';
    else if (filter !== 'all') url += `?category=${filter}`;
    fetch(url)
      .then((r) => r.ok && r.json())
      .then((data) => {
        const list = data || [];
        setReplies(list);

        if (!currentUser) return;
        if (!initialRepliesLoadedRef.current) {
          initialRepliesLoadedRef.current = true;
          const seen = getSeenReplyIds(currentUser.id);
          list.forEach((r) => seen.add(r.id));
          saveSeenReplyIds(currentUser.id, seen);
          seenReplyIdsRef.current = seen;
        } else {
          const seen = seenReplyIdsRef.current;
          const fresh = list.filter((r) => !seen.has(r.id));
          if (fresh.length > 0) {
            fresh.forEach((r) => seen.add(r.id));
            saveSeenReplyIds(currentUser.id, seen);
            queueIncomingReplies(fresh);
          }
        }
      })
      .catch(() => {});
  };

  const fetchThread = (id) => {
    if (!id) return setThread(null);
    fetch(`${API}/replies/${id}`).then((r) => r.ok && r.json()).then(setThread).catch(() => {});
  };

  const handleReclassify = async (id) => {
    if (!id) return;
    setRechecking(true);
    try {
      const res = await fetch(`${API}/replies/${id}/classify`, { method: 'POST' });
      if (res.ok) {
        toast.success('Reply reclassified successfully.');
        fetchReplies();
        fetchThread(id);
        fetchAiUsage();
        fetchDrafts();
        fetchStats();
      } else {
        toast.error('Failed to reclassify reply.');
      }
    } catch {
      toast.error('Failed to reclassify reply.');
    } finally {
      setRechecking(false);
    }
  };

  useEffect(() => {
    if (!currentUser) return;
    fetchHealth();
    fetchStats();
    fetchStranded();
    fetchContacts();
    fetchChips();
    fetchCampaigns();
    fetchWatcher();
    fetchReplies();
    fetchAiUsage();
    fetchDrafts();
    fetchActivity();
    fetchSettings();
  }, [currentUser?.id]);

  useEffect(() => {
    if (activeCampId) {
      fetchCampaignPlan(activeCampId);
    }
  }, [activeCampId]);

  // Polling
  useEffect(() => {
    if (!currentUser) return;
    const t = setInterval(() => {
      fetchHealth();
      fetchWatcher();
      fetchReplies();
      fetchStats();
      fetchStranded();
      fetchAiUsage();
      fetchDrafts();
      if (progress?.campaign_status === 'running' || progress?.campaign_status === 'paused') {
        fetchProgress(activeCampId);
        fetchCampaignPlan(activeCampId);
      }
      fetch(`${API}/auth/me`)
        .then((r) => r.ok && r.json())
        .then((u) => {
          if (u) setCurrentUser((prev) => (prev ? { ...prev, ...u } : u));
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(t);
  }, [currentUser?.id, activeCampId, progress?.campaign_status, replyFilter, draftFilter]);

  useEffect(() => {
    fetchThread(selectedReplyId);
  }, [selectedReplyId]);

  // Upload
  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`${API}/contacts/upload`, { method: 'POST', body: fd });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Uploaded: Added ${data.added}, ${data.duplicates} duplicates, ${data.invalid} invalid.`);
        setFile(null);
        const fileInput = document.getElementById('csvIn');
        if (fileInput) fileInput.value = '';
        fetchStats();
        fetchContacts();
        fetchChips();
      } else {
        toast.error(data.detail || 'Upload failed');
      }
    } catch {
      toast.error('Network error during upload');
    } finally {
      setUploading(false);
    }
  };

  const insertChip = (ph) => {
    const el = templateRef.current;
    if (el) {
      const s = el.selectionStart;
      const val = `{${ph}}`;
      setTemplate(template.substring(0, s) + val + template.substring(el.selectionEnd));
    } else {
      setTemplate((prev) => prev + `{${ph}}`);
    }
  };

  const handleCreateCampaign = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API}/campaigns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: campName, subject, mode, template, provider, group_tag: groupTag || null }),
      });
      if (res.ok) {
        const c = await res.json();
        toast.success(`Created campaign: ${c.name}`);
        fetchCampaigns();
        setActiveCampId(c.id);
        fetchProgress(c.id);
      } else {
        toast.error('Error creating campaign');
      }
    } catch {
      toast.error('Error creating campaign');
    }
  };

  const handlePreview = () => {
    if (!activeCampId) return;
    fetch(`${API}/campaigns/${activeCampId}/preview?limit=5`, { method: 'POST' })
      .then((r) => r.ok && r.json())
      .then((d) => { setPreview(d); setShowPreview(true); })
      .catch(() => toast.error('Failed to generate preview'));
  };

  const handleTestSend = async () => {
    if (!activeCampId || !testEmail) return;
    setTestResult(null);
    try {
      const res = await fetch(`${API}/campaigns/${activeCampId}/test-send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_email: testEmail }),
      });
      const d = await res.json();
      if (d.success) {
        toast.success(`Dispatched ${d.sent_count} sample(s) to ${testEmail}`);
        setTestResult(`Dispatched ${d.sent_count} sample(s) to ${testEmail}`);
      } else {
        toast.error(d.message || 'Test send failed');
        setTestResult(d.message || 'Error');
      }
    } catch {
      toast.error('Network error during test send');
    }
  };

  const startDispatch = () => {
    setShowConfirm(false);
    fetch(`${API}/campaigns/${activeCampId}/start`, { method: 'POST' })
      .then(() => {
        toast.info('Campaign dispatch initiated');
        fetchProgress(activeCampId);
        fetchCampaigns();
      })
      .catch(() => toast.error('Failed to start campaign'));
  };

  const toggleWatcher = () => {
    const act = watcher.running ? 'stop' : 'start';
    fetch(`${API}/watcher/${act}`, { method: 'POST' })
      .then((r) => r.ok && r.json())
      .then((d) => {
        setWatcher(d.status);
        toast.info(`Watcher ${d.status.running ? 'started' : 'stopped'}`);
      })
      .catch(() => toast.error('Failed to toggle watcher'));
  };

  const markHandled = (id) => {
    fetch(`${API}/replies/${id}/mark-handled`, { method: 'POST' }).then(() => {
      toast.success('Marked reply as handled');
      fetchReplies();
      fetchStats();
      if (thread && thread.reply?.id === id) {
        setThread((p) => ({ ...p, reply: { ...p.reply, processed: 1 } }));
      }
    });
  };

  const reviewDraftsCount = drafts.filter((d) => d.status === 'needs_review').length;
  const totalPendingAttention = (stats.unhandled_replies || 0) + reviewDraftsCount;

  const navItems = [
    { id: 'Dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'Quick Start', label: 'Quick Start', icon: Zap },
    { id: 'Contacts', label: 'Contacts', icon: Users },
    { id: 'Campaign', label: 'Campaign', icon: Megaphone },
    { id: 'Autopilot', label: 'Autopilot', icon: Compass },
    { id: 'Replies', label: 'Replies', icon: MessageSquare, badge: stats.unhandled_replies },
    { id: 'Drafts', label: 'Drafts', icon: FileText, badge: reviewDraftsCount },
    { id: 'Activity', label: 'Activity', icon: History },
    { id: 'Settings', label: 'Settings', icon: SettingsIcon },
  ];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0A0A0A] font-sans text-[#F5F1E6] antialiased select-none">
      {/* Sidebar */}
      <aside
        className={`${
          isSidebarCollapsed ? 'w-16 min-w-16 max-w-16' : 'w-60 min-w-60 max-w-60'
        } glass rounded-none border-t-0 border-l-0 border-b-0 border-r border-[rgba(212,175,55,0.22)] flex flex-col justify-between p-3.5 flex-shrink-0 transition-all duration-200 h-screen`}
      >
        <div className="space-y-5">
          {/* Brand Header */}
          <div className="flex items-center justify-between px-1.5 pt-1">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-xl bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] flex items-center justify-center text-[#0A0A0A] font-bold text-sm shadow-[0_0_15px_rgba(212,175,55,0.35)] flex-shrink-0">
                M
              </div>
              {!isSidebarCollapsed && (
                <div className="min-w-0">
                  <div className="text-sm font-bold text-[#F2D675] leading-tight truncate">
                    Mail Assistant
                  </div>
                  <div className="text-[10px] text-[#A59F8F] font-medium truncate">
                    Smart Dispatcher
                  </div>
                </div>
              )}
            </div>

            {/* Collapse / Expand Toggle Button */}
            <button
              type="button"
              onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
              className="text-[#A59F8F] hover:text-[#F2D675] p-1 rounded-md hover:bg-[#1A1A1A] transition-colors"
              title={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {isSidebarCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
            </button>
          </div>

          {/* Navigation Items */}
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  title={isSidebarCollapsed ? item.label : undefined}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-colors cursor-pointer gap-2 ${
                    isActive
                      ? 'bg-[#1A1A1A] text-[#F2D675] font-semibold border-l-2 border-[#D4AF37] shadow-[0_0_12px_rgba(212,175,55,0.1)]'
                      : 'text-[#A59F8F] hover:bg-[#1A1A1A] hover:text-[#F5F1E6]'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-[#D4AF37]' : 'text-[#A59F8F]'}`} />
                    {!isSidebarCollapsed && <span className="truncate">{item.label}</span>}
                  </div>
                  {!isSidebarCollapsed && (
                    <div className="flex items-center gap-1.5 ml-auto flex-shrink-0">
                      {Boolean(item.badge) && item.badge > 0 && (
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-[#1A1A1A] text-[#F2D675] border border-[rgba(212,175,55,0.3)]">
                          {item.badge}
                        </span>
                      )}
                      {item.id === 'Dashboard' && stats.stranded > 0 && (
                        <span
                          className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-[#FF9F43] text-[#0A0A0A]"
                          title={`${stats.stranded} stranded items`}
                        >
                          !
                        </span>
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Sidebar Footer */}
        <div className="pt-3 border-t border-[rgba(212,175,55,0.18)] space-y-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleToggleVoiceMute}
            className={`w-full ${isSidebarCollapsed ? 'px-0 justify-center' : 'justify-start'} text-xs font-normal`}
            title={voiceMuted ? 'Voice Muted' : 'Voice Active'}
          >
            {voiceMuted ? (
              <>
                <VolumeX className="w-3.5 h-3.5 text-[#A59F8F] flex-shrink-0" />
                {!isSidebarCollapsed && <span className="ml-2">Voice Muted</span>}
              </>
            ) : (
              <>
                <Volume2 className="w-3.5 h-3.5 text-[#D4AF37] flex-shrink-0" />
                {!isSidebarCollapsed && <span className="ml-2">Voice Active</span>}
              </>
            )}
          </Button>
          {!isSidebarCollapsed && (
            <p className="text-[10px] text-[#A59F8F]/70 px-1 leading-snug">
              Voice works only while this page is open.
            </p>
          )}
        </div>
      </aside>

      {/* Main Container */}
      <div
        className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden bg-[#0A0A0A] relative"
        style={{ backgroundImage: 'radial-gradient(circle at 50% 0%, rgba(212,175,55,0.06) 0%, transparent 65%)' }}
      >
        {/* Gmail Reconnect Banner */}
        {(currentUser?.gmail_auth_expired || health?.gmail_auth_expired) && (
          <div className="bg-[#FF9F43]/10 border-b border-[#FF9F43]/30 text-[#FF9F43] px-6 py-2.5 text-xs font-medium flex items-center justify-between flex-shrink-0">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-[#FF9F43] flex-shrink-0" />
              <span className="text-[#F5F1E6]">Gmail connection expired. Stored authorization expired or was revoked.</span>
            </div>
            <a
              href={`${API}/auth/login`}
              className="px-3 py-1 rounded-lg bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] text-[#0A0A0A] font-semibold text-xs transition shadow-[0_0_10px_rgba(212,175,55,0.3)] inline-flex items-center gap-1"
            >
              Reconnect
            </a>
          </div>
        )}

        {/* Topbar */}
        <header className="min-h-14 py-2 glass rounded-none border-t-0 border-x-0 border-b border-[rgba(212,175,55,0.22)] px-6 flex items-center justify-between flex-wrap gap-2.5 flex-shrink-0">
          <div className="flex items-center gap-3">
            <h1 className="text-base font-semibold text-[#F2D675]">{tab}</h1>
            <span className="hidden sm:inline-flex items-center text-xs text-[#A59F8F]">
              Sending as <strong className="text-[#F5F1E6] ml-1 font-mono text-[11px]">{currentUser.email}</strong>
            </span>
          </div>

          <div className="flex items-center flex-wrap gap-2.5">
            {/* Command Palette Trigger */}
            <button
              type="button"
              onClick={() => setCommandPaletteOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs glass text-[#A59F8F] hover:text-[#F5F1E6] transition-colors"
            >
              <Search className="w-3.5 h-3.5 text-[#D4AF37]" />
              <span className="hidden md:inline">Search...</span>
              <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono bg-[#121212] border border-[rgba(212,175,55,0.25)] rounded text-[#F2D675]">
                Ctrl K
              </kbd>
            </button>

            {/* Live Status Chip */}
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)]">
              <span
                className={`w-2 h-2 rounded-full ${
                  isOnline ? 'bg-[#3DDC97] shadow-[0_0_8px_#3DDC97] animate-pulse' : 'bg-[#FF9F43]'
                }`}
              />
              <span className={isOnline ? 'text-[#3DDC97]' : 'text-[#FF9F43]'}>
                {isOnline ? 'Live' : 'Reconnecting...'}
              </span>
            </div>

            {/* Notification Bell Dropdown */}
            <div className="relative" ref={notificationsRef}>
              <button
                type="button"
                onClick={() => setNotificationsOpen(!notificationsOpen)}
                className="relative p-2 rounded-lg text-[#A59F8F] hover:text-[#F2D675] hover:bg-[#1A1A1A] transition-colors"
                title="Pending notifications"
              >
                <Bell className="w-4 h-4" />
                {totalPendingAttention > 0 && (
                  <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#D4AF37] shadow-[0_0_6px_rgba(212,175,55,0.8)]" />
                )}
              </button>

              {notificationsOpen && (
                <div className="absolute right-0 mt-2 w-72 glass-strong p-3 z-50 text-xs space-y-2">
                  <div className="font-semibold text-[#F2D675] border-b border-[rgba(212,175,55,0.18)] pb-1.5 flex justify-between">
                    <span>Attention Required</span>
                    <span className="text-[#A59F8F] text-[10px]">{totalPendingAttention} pending</span>
                  </div>
                  {totalPendingAttention === 0 ? (
                    <p className="text-[#A59F8F] text-[11px] py-2 text-center">
                      All caught up! No unhandled replies or pending review drafts.
                    </p>
                  ) : (
                    <div className="space-y-1.5">
                      {stats.unhandled_replies > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            setTab('Replies');
                            setNotificationsOpen(false);
                          }}
                          className="w-full text-left p-2 rounded-lg bg-[#1A1A1A] hover:bg-[#222222] transition-colors flex items-center justify-between"
                        >
                          <span className="text-[#F5F1E6]">Unhandled Replies</span>
                          <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-[#FF9F43]/20 text-[#FF9F43]">
                            {stats.unhandled_replies}
                          </span>
                        </button>
                      )}
                      {reviewDraftsCount > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            setTab('Drafts');
                            setNotificationsOpen(false);
                          }}
                          className="w-full text-left p-2 rounded-lg bg-[#1A1A1A] hover:bg-[#222222] transition-colors flex items-center justify-between"
                        >
                          <span className="text-[#F5F1E6]">Drafts Needing Review</span>
                          <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-[#D4AF37]/20 text-[#F2D675]">
                            {reviewDraftsCount}
                          </span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* AI Voice Speaking Pulse */}
            <VoiceSpeakingIndicator />

            {/* Usage Pill */}
            {currentUser?.limits && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-[#1A1A1A] text-[#A59F8F] border border-[rgba(212,175,55,0.22)]">
                Today: <strong className="text-[#F2D675]">{currentUser.limits.sent_today}</strong> of {currentUser.limits.effective_cap}
              </span>
            )}

            {/* Test / Live Mode Badge */}
            {health && (
              health.test_mode ? (
                <Badge variant="warning" className="font-semibold text-[10px] tracking-wide">
                  TEST MODE
                </Badge>
              ) : (
                <Badge variant="danger" className="font-bold text-[10px] tracking-wide">
                  LIVE MODE
                </Badge>
              )
            )}

            {/* Global Pause Sending Switch */}
            <Button
              variant={globalPaused ? 'primary' : 'outline'}
              size="sm"
              onClick={toggleGlobalSending}
              className="text-xs font-medium"
            >
              {globalPaused ? (
                <>
                  <Play className="w-3 h-3 mr-1.5" />
                  Resume Sending
                </>
              ) : (
                <>
                  <Pause className="w-3 h-3 mr-1.5" />
                  Pause Sending
                </>
              )}
            </Button>

            {/* Read My Replies Voice Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={triggerManualBriefing}
              className="text-xs font-medium"
              title="Read recent replies aloud"
            >
              <Volume2 className="w-3.5 h-3.5 mr-1.5 text-[#D4AF37]" />
              Read replies
            </Button>

            {/* Voice Answers Toggle */}
            <Button
              variant={voiceAnswersOn ? 'primary' : 'outline'}
              size="sm"
              onClick={handleToggleVoiceAnswers}
              className="text-xs"
              title="Voice answers (browser sends audio to speech service)"
            >
              <Mic className="w-3.5 h-3.5 mr-1.5" />
              Voice answers {voiceAnswersOn ? 'ON' : 'OFF'}
            </Button>

            {/* User Profile Avatar & Dropdown */}
            <div className="relative pl-1 border-l border-[rgba(212,175,55,0.22)]" ref={userMenuRef}>
              <button
                type="button"
                onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                className="flex items-center gap-2 p-1 rounded-full hover:ring-2 hover:ring-[#D4AF37]/50 transition"
              >
                {currentUser.picture_url ? (
                  <img
                    src={currentUser.picture_url}
                    alt={currentUser.name || currentUser.email}
                    className="w-7 h-7 rounded-full border border-[rgba(212,175,55,0.4)] object-cover"
                  />
                ) : (
                  <div
                    className="w-7 h-7 rounded-full bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] text-[#0A0A0A] font-bold text-xs flex items-center justify-center uppercase shadow-[0_0_8px_rgba(212,175,55,0.4)]"
                    title={currentUser.email}
                  >
                    {(currentUser.name || currentUser.email || 'U')[0]}
                  </div>
                )}
              </button>

              {userDropdownOpen && (
                <div className="absolute right-0 mt-2 w-56 glass-strong p-3 z-50 text-xs space-y-2.5">
                  <div className="border-b border-[rgba(212,175,55,0.18)] pb-2">
                    <p className="font-semibold text-[#F2D675] truncate">{currentUser.name || 'User'}</p>
                    <p className="text-[11px] text-[#A59F8F] font-mono truncate">{currentUser.email}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setTab('Settings');
                      setUserDropdownOpen(false);
                    }}
                    className="w-full text-left px-2 py-1.5 rounded-lg text-[#F5F1E6] hover:bg-[#1A1A1A] flex items-center gap-2 transition"
                  >
                    <SettingsIcon className="w-3.5 h-3.5 text-[#D4AF37]" />
                    <span>Account Settings</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setUserDropdownOpen(false);
                      onLogout();
                    }}
                    className="w-full text-left px-2 py-1.5 rounded-lg text-[#FF5C5C] hover:bg-[#FF5C5C]/10 flex items-center gap-2 transition"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span>Sign Out</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-6 overflow-y-auto min-w-0 bg-[#0A0A0A] relative">
          {/* Ambient Background Gold Glow Orbs for Glassmorphism (subtle, low opacity 0.08, pointer-events-none) */}
          <div
            className="absolute top-8 right-1/4 w-96 h-96 rounded-full bg-[radial-gradient(circle,rgba(212,175,55,0.07)_0%,transparent_70%)] blur-3xl pointer-events-none animate-drift-1"
            aria-hidden="true"
          />
          <div
            className="absolute bottom-20 left-1/3 w-80 h-80 rounded-full bg-[radial-gradient(circle,rgba(242,214,117,0.05)_0%,transparent_70%)] blur-3xl pointer-events-none animate-drift-2"
            aria-hidden="true"
          />

          <div className="relative z-10">
            {/* Voice Briefing Banner */}
            <VoiceBriefingBanner
              briefing={briefing}
              onAccept={handleAccept}
              onDecline={handleDecline}
              onMute={handleMute}
              onPauseToggle={handlePauseToggle}
              onSkip={handleSkip}
              onStop={handleStop}
              onReadDraft={handleReadDraft}
              onClose={handleClose}
            />

          {tab === 'Dashboard' && (
            <DashboardPage
              health={health}
              stats={stats}
              aiUsage={aiUsage}
              strandedItems={strandedItems}
              onNavigate={(nextTab) => setTab(nextTab)}
              currentUser={currentUser}
              replies={replies}
              activity={activity}
              watcher={watcher}
              API={API}
              onTriggerVoiceBriefing={triggerManualBriefing}
            />
          )}

          {tab === 'Quick Start' && (
            <QuickStartPage
              API={API}
              onNavigate={(nextTab) => setTab(nextTab)}
              onCampaignCreated={(campId) => {
                setActiveCampId(campId);
                fetchCampaigns();
                fetchProgress(campId);
                fetchCampaignPlan(campId);
              }}
            />
          )}

          {tab === 'Contacts' && (
            <ContactsPage
              contacts={contacts}
              search={search}
              onSearchChange={setSearch}
              file={file}
              onFileChange={setFile}
              onUpload={handleUpload}
              uploading={uploading}
              onRefresh={fetchContacts}
              API={API}
            />
          )}

          {tab === 'Campaign' && (
            <CampaignPage
              campaigns={campaigns}
              activeCampId={activeCampId}
              onSelectCamp={(id) => {
                setActiveCampId(id);
                fetchProgress(id);
                fetchCampaignPlan(id);
              }}
              campName={campName}
              onCampNameChange={setCampName}
              subject={subject}
              onSubjectChange={setSubject}
              mode={mode}
              onModeChange={setMode}
              provider={provider}
              onProviderChange={setProvider}
              groupTag={groupTag}
              onGroupTagChange={setGroupTag}
              groups={groups}
              template={template}
              onTemplateChange={setTemplate}
              chips={chips}
              insertChip={insertChip}
              templateRef={templateRef}
              onCreateCampaign={handleCreateCampaign}
              progress={progress}
              onStartDispatch={startDispatch}
              onPause={() => fetch(`${API}/campaigns/${activeCampId}/pause`, { method: 'POST' }).then(() => fetchProgress(activeCampId))}
              onStop={() => fetch(`${API}/campaigns/${activeCampId}/stop`, { method: 'POST' }).then(() => fetchProgress(activeCampId))}
              onRetryFailed={handleRetryFailed}
              preview={preview}
              showPreview={showPreview}
              onClosePreview={() => setShowPreview(false)}
              onOpenPreview={handlePreview}
              showConfirm={showConfirm}
              onCloseConfirm={() => setShowConfirm(false)}
              onOpenConfirm={() => {
                setConfirmed(false);
                setShowConfirm(true);
              }}
              confirmed={confirmed}
              onConfirmedChange={setConfirmed}
              testEmail={testEmail}
              onTestEmailChange={setTestEmail}
              onTestSend={handleTestSend}
              testResult={testResult}
              campaignPlan={campaignPlan}
              canUseSmtp={currentUser?.limits?.can_use_smtp ?? true}
            />
          )}

          {tab === 'Autopilot' && (
            <AutopilotPage
              API={API}
              campaigns={campaigns}
            />
          )}

          {tab === 'Replies' && (
            <RepliesPage
              watcher={watcher}
              onToggleWatcher={toggleWatcher}
              replyFilter={replyFilter}
              onFilterChange={(f) => {
                setReplyFilter(f);
                fetchReplies(f);
              }}
              replies={replies}
              selectedReplyId={selectedReplyId}
              onSelectReply={setSelectedReplyId}
              thread={thread}
              onReclassify={handleReclassify}
              rechecking={rechecking}
              onMarkHandled={markHandled}
            />
          )}

          {tab === 'Drafts' && (
            <DraftsPage
              draftFilter={draftFilter}
              onFilterChange={(f) => {
                setDraftFilter(f);
                fetchDrafts(f);
              }}
              drafts={drafts}
              selectedDraftId={selectedDraftId}
              onSelectDraft={handleSelectDraft}
              draftBodyEdit={draftBodyEdit}
              onDraftBodyEditChange={setDraftBodyEdit}
              savingDraft={savingDraft}
              onRegenerateDraft={handleRegenerateDraft}
              onRejectDraft={handleRejectDraft}
              onSaveDraft={handleSaveDraft}
              onApproveAndSendDraft={handleApproveAndSendDraft}
              settings={settings}
            />
          )}

          {tab === 'Activity' && (
            <ActivityPage
              activity={activity}
              filter={activityFilter}
              onFilterChange={(val) => {
                setActivityFilter(val);
                fetchActivity(val);
              }}
              onRefresh={() => fetchActivity(activityFilter)}
              API={API}
            />
          )}

          {tab === 'Settings' && (
            <SettingsPage
              settings={settings}
              onSettingsChange={setSettings}
              onSaveSettings={handleSaveSettings}
              savingSettings={savingSettings}
              onBackupNow={handleBackupNow}
              backups={backups}
              API={API}
            />
          )}
          </div>
        </main>
      </div>

      {/* Ctrl+K Command Palette */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onNavigate={(nextTab) => {
          setTab(nextTab);
          setCommandPaletteOpen(false);
        }}
        contacts={contacts}
        onTriggerVoiceBriefing={triggerManualBriefing}
      />
    </div>
  );
}

function MainRoutes() {
  const navigate = useNavigate();
  const location = useLocation();
  const [currentUser, setCurrentUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loadingStep, setLoadingStep] = useState(0);
  const [loadingStatusText, setLoadingStatusText] = useState('Checking credentials...');
  const [timeoutError, setTimeoutError] = useState(false);

  const statusMessages = [
    'Checking credentials...',
    'Verifying Gmail permissions...',
    'Syncing daily sending quota...',
    'Loading workspace...',
  ];

  const checkAuth = async () => {
    setAuthLoading(true);
    setTimeoutError(false);
    const start = Date.now();

    // Step animation interval
    let step = 0;
    const interval = setInterval(() => {
      step = (step + 1) % statusMessages.length;
      setLoadingStep(step);
      setLoadingStatusText(statusMessages[step]);
    }, 700);

    // 8-second timeout handler
    const timeoutTimer = setTimeout(() => {
      setTimeoutError(true);
    }, 8000);

    try {
      const res = await fetch(`${API}/auth/me`);
      if (res.ok) {
        const u = await res.json();
        setCurrentUser(u);
      } else {
        setCurrentUser(null);
      }
    } catch {
      setCurrentUser(null);
    } finally {
      clearInterval(interval);
      clearTimeout(timeoutTimer);
      const elapsed = Date.now() - start;
      const delay = Math.max(0, 600 - elapsed);
      setTimeout(() => {
        setAuthLoading(false);
      }, delay);
    }
  };

  useEffect(() => {
    checkAuth();

    const handleUnauthorized = () => {
      setCurrentUser(null);
      navigate('/login');
    };
    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, []);

  const handleLogout = async () => {
    try {
      await fetch(`${API}/auth/logout`, { method: 'POST' });
    } catch {}
    setCurrentUser(null);
    navigate('/login');
  };

  // Check URL params for auth error
  const urlParams = new URLSearchParams(location.search);
  const authError = urlParams.get('auth_error');

  return (
    <Routes>
      {/* Landing Page (/) */}
      <Route
        path="/"
        element={
          <LandingPage
            currentUser={currentUser}
            onNavigateToLogin={() => navigate('/login')}
            onNavigateToApp={() => navigate('/app')}
          />
        }
      />

      {/* Login Page (/login) */}
      <Route
        path="/login"
        element={
          currentUser ? (
            <Navigate to="/app" replace />
          ) : (
            <LoginPage
              API={API}
              error={authError}
              onBackToLanding={() => navigate('/')}
            />
          )
        }
      />

      {/* App Workspace (/app/*) */}
      <Route
        path="/app/*"
        element={
          authLoading ? (
            <LoadingScreen
              step={loadingStep}
              statusText={loadingStatusText}
              timeoutError={timeoutError}
              onRetry={checkAuth}
            />
          ) : !currentUser ? (
            <Navigate to="/login" replace />
          ) : (
            <Workspace
              currentUser={currentUser}
              setCurrentUser={setCurrentUser}
              onLogout={handleLogout}
            />
          )
        }
      />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <MainRoutes />
      </ToastProvider>
    </BrowserRouter>
  );
}
