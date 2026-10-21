import React, { useState, useEffect } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { getApiBaseUrl } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge, StatusBadge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from 'recharts';
import {
  AlertTriangle,
  Mail,
  Send,
  CheckCircle2,
  XCircle,
  UserX,
  Sparkles,
  PlusCircle,
  MessageSquare,
  Upload,
  History,
  Settings as SettingsIcon,
  Zap,
  Volume2,
  Compass,
  Activity,
  ShieldCheck,
  Clock,
  ArrowUpRight,
  TrendingUp,
} from 'lucide-react';

const GOLD_PALETTE = ['#D4AF37', '#F2D675', '#B8962E', '#F5F1E6', '#6EA8FF', '#FF9F43'];

export function DashboardPage({
  health,
  stats = {},
  aiUsage = {},
  strandedItems = {},
  onNavigate,
  currentUser,
  loading = false,
  watcher = {},
  activity = [],
  replies = [],
  onTriggerVoiceBriefing,
  API,
}) {
  const apiBase = getApiBaseUrl(API);
  const prefersReduced = useReducedMotion();
  const [summaryData, setSummaryData] = useState(null);

  // Fetch 14-day trends & intent breakdown from read-only summary endpoint
  useEffect(() => {
    let active = true;
    const fetchSummary = async () => {
      try {
        const res = await fetch(`${apiBase}/dashboard/summary`);
        if (res.ok) {
          const data = await res.json();
          if (active) setSummaryData(data);
        }
      } catch {}
    };

    fetchSummary();
    const interval = setInterval(fetchSummary, 6000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [apiBase]);

  // Current formatted date
  const todayFormatted = new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date());

  const userName = currentUser?.name || currentUser?.email?.split('@')[0] || 'Admin';

  // KPI calculations
  const totalSent = stats.sent || 0;
  const incomingReplies = summaryData?.incoming_replies || stats.unhandled_replies || 0;
  const replyRate = summaryData?.reply_rate ?? (totalSent > 0 ? ((incomingReplies / totalSent) * 100).toFixed(1) : '0.0');
  const pendingReviewDrafts = stats.pending_drafts || 0;
  const aiCalls = aiUsage?.total_calls || 0;

  const effectiveCap = currentUser?.limits?.effective_cap || 400;
  const sentToday = currentUser?.limits?.sent_today || 0;
  const usagePercent = Math.min(100, Math.round((sentToday / Math.max(1, effectiveCap)) * 100));

  // Chart trend data from API
  const trendChartData = summaryData?.daily_trends?.length
    ? summaryData.daily_trends.map((item) => ({
        day: item.date.slice(5), // MM-DD
        sends: item.sends,
      }))
    : sentToday > 0
    ? [{ day: 'Today', sends: sentToday }]
    : [];

  // Intent breakdown data: calculated strictly from real incoming replies or API
  const intentData = React.useMemo(() => {
    if (summaryData?.intent_breakdown?.length) {
      return summaryData.intent_breakdown.map((item) => ({
        name: item.intent.replace('_', ' '),
        value: item.count,
      }));
    }
    if (!replies || replies.length === 0) return [];
    const counts = {};
    replies.forEach((r) => {
      const intentKey = (r.intent || r.category || 'other').replace('_', ' ');
      counts[intentKey] = (counts[intentKey] || 0) + 1;
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [summaryData, replies]);

  return (
    <div className="space-y-6 text-[#F5F1E6]">
      {/* 1. Header Greeting & Date */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-[rgba(212,175,55,0.18)]">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight">
            Welcome back, <span className="gold-gradient-text">{userName}</span>
          </h2>
          <p className="text-xs text-[#A59F8F] mt-0.5 flex items-center gap-1.5 font-medium">
            <Clock className="w-3.5 h-3.5 text-[#D4AF37]" />
            {todayFormatted}
          </p>
        </div>

        {/* Quick Action Pills */}
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={onTriggerVoiceBriefing}
            className="text-xs"
            title="Read recent replies aloud"
          >
            <Volume2 className="w-3.5 h-3.5 mr-1 text-[#F2D675]" />
            Read my replies
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onNavigate('Quick Start')}
            className="text-xs"
          >
            <Zap className="w-3.5 h-3.5 mr-1 text-[#0A0A0A]" />
            Quick Start
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onNavigate('Campaign')}
            className="text-xs"
          >
            <PlusCircle className="w-3.5 h-3.5 mr-1" />
            New Campaign
          </Button>
        </div>
      </div>

      {/* 2. Needs Attention Panel (Alerts, uncertain items, reconnect) */}
      {(health?.gmail_auth_expired || currentUser?.limits?.quota_exhausted || stats.stranded > 0 || (health?.test_mode && !health?.test_email_valid)) && (
        <div className="space-y-3">
          {health?.gmail_auth_expired && (
            <div className="flex items-center justify-between p-3.5 rounded-lg bg-[#FF9F43]/15 border border-[#FF9F43]/40 text-[#FF9F43] text-xs">
              <div className="flex items-center gap-2.5">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>
                  <strong>Gmail Connection Required:</strong> Your Google authorization token expired or was revoked. Reconnect in Top Bar to resume sending.
                </span>
              </div>
              <Button variant="outline" size="xs" onClick={() => (window.location.href = `${apiBase}/auth/login`)}>
                Reconnect
              </Button>
            </div>
          )}

          {health?.test_mode && !health?.test_email_valid && (
            <div className="flex items-center justify-between p-3.5 rounded-lg bg-[#FF5C5C]/15 border border-[#FF5C5C]/40 text-[#FF5C5C] text-xs">
              <div className="flex items-center gap-2.5">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>
                  <strong>Test Mode Alert:</strong> TEST_EMAIL is empty or invalid. Outgoing dispatches are blocked until configured in Settings.
                </span>
              </div>
              <Button variant="outline" size="xs" onClick={() => onNavigate('Settings')}>
                Configure
              </Button>
            </div>
          )}

          {currentUser?.limits?.quota_exhausted && (
            <div className="flex items-center gap-2.5 p-3.5 rounded-lg bg-[#FF9F43]/15 border border-[#FF9F43]/40 text-[#FF9F43] text-xs">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>
                <strong>Daily Limit Reached:</strong> Quota exhausted for today. Unsent queue items are safely paused and will resume at 00:00 Pacific.
              </span>
            </div>
          )}

          {stats.stranded > 0 && (
            <div className="glass p-4 space-y-3 border-[#FF9F43]/40">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-semibold text-[#FF9F43]">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>{stats.stranded} Uncertain & Interrupted Send(s) Awaiting Review</span>
                </div>
                <Button variant="outline" size="xs" onClick={() => onNavigate('Drafts')}>
                  Review Items
                </Button>
              </div>
              <p className="text-[11px] text-[#A59F8F]">
                Socket timeouts and crashed dispatches are never retried automatically to prevent duplicate sending. Review your Gmail Sent folder before approving.
              </p>
            </div>
          )}
        </div>
      )}

      {/* 3. KPI Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
        {/* KPI 1: Emails Sent */}
        <div className="glass p-4 relative overflow-hidden group transition-all">
          <div className="flex items-center justify-between text-[#A59F8F] mb-1.5">
            <span className="text-xs font-medium">Emails Sent</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-[#3DDC97]" />
          </div>
          <div className="text-2xl font-bold text-[#F2D675] tracking-tight">{totalSent}</div>
          <div className="text-[10px] text-[#A59F8F] mt-1 flex items-center gap-1">
            <TrendingUp className="w-3 h-3 text-[#3DDC97]" />
            <span>{sentToday} today</span>
          </div>
        </div>

        {/* KPI 2: Replies Received */}
        <div className="glass p-4 relative overflow-hidden group transition-all">
          <div className="flex items-center justify-between text-[#A59F8F] mb-1.5">
            <span className="text-xs font-medium">Replies</span>
            <MessageSquare className="w-3.5 h-3.5 text-[#6EA8FF]" />
          </div>
          <div className="text-2xl font-bold text-[#F5F1E6] tracking-tight">{incomingReplies}</div>
          <div className="text-[10px] text-[#A59F8F] mt-1">
            {stats.unhandled_replies || 0} unhandled
          </div>
        </div>

        {/* KPI 3: Reply Rate */}
        <div className="glass p-4 relative overflow-hidden group transition-all">
          <div className="flex items-center justify-between text-[#A59F8F] mb-1.5">
            <span className="text-xs font-medium">Reply Rate</span>
            <ArrowUpRight className="w-3.5 h-3.5 text-[#3DDC97]" />
          </div>
          <div className="text-2xl font-bold text-[#3DDC97] tracking-tight">{replyRate}%</div>
          <div className="text-[10px] text-[#A59F8F] mt-1">Grounded conversion</div>
        </div>

        {/* KPI 4: Drafts Awaiting Review */}
        <div className="glass p-4 relative overflow-hidden group transition-all cursor-pointer" onClick={() => onNavigate('Drafts')}>
          <div className="flex items-center justify-between text-[#A59F8F] mb-1.5">
            <span className="text-xs font-medium">Needs Review</span>
            <AlertTriangle className="w-3.5 h-3.5 text-[#FF9F43]" />
          </div>
          <div className="text-2xl font-bold text-[#FF9F43] tracking-tight">{pendingReviewDrafts}</div>
          <div className="text-[10px] text-[#A59F8F] mt-1">Requires approval</div>
        </div>

        {/* KPI 5: Sending Quota Meter */}
        <div className="glass p-4 relative overflow-hidden group transition-all">
          <div className="flex items-center justify-between text-[#A59F8F] mb-1.5">
            <span className="text-xs font-medium">Today's Cap</span>
            <Send className="w-3.5 h-3.5 text-[#D4AF37]" />
          </div>
          <div className="text-2xl font-bold text-[#F2D675] tracking-tight">
            {sentToday} <span className="text-xs font-normal text-[#A59F8F]">/ {effectiveCap}</span>
          </div>
          <div className="w-full bg-[#1A1A1A] rounded-full h-1 mt-2 overflow-hidden border border-[rgba(212,175,55,0.15)]">
            <div className="h-full bg-[linear-gradient(90deg,#D4AF37,#F2D675)]" style={{ width: `${usagePercent}%` }} />
          </div>
        </div>

        {/* KPI 6: AI Usage Calls */}
        <div className="glass p-4 relative overflow-hidden group transition-all">
          <div className="flex items-center justify-between text-[#A59F8F] mb-1.5">
            <span className="text-xs font-medium">AI Calls</span>
            <Sparkles className="w-3.5 h-3.5 text-[#D4AF37]" />
          </div>
          <div className="text-2xl font-bold text-[#F5F1E6] tracking-tight">{aiCalls}</div>
          <div className="text-[10px] text-[#A59F8F] mt-1 truncate">
            {health?.ai_provider || 'Anthropic'}
          </div>
        </div>
      </div>

      {/* 4. Real-Time Charts Section (Black & Gold Glass) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Chart 1: 14-Day Send Activity Trend */}
        <div className="lg:col-span-8 glass p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xs font-bold text-[#F2D675] uppercase tracking-wider">
                14-Day Dispatch Activity
              </h3>
              <p className="text-[11px] text-[#A59F8F] mt-0.5">
                Daily outgoing dispatches tracked against provider rate-limits.
              </p>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono text-[#F2D675] bg-[#1A1A1A] border border-[rgba(212,175,55,0.2)]">
              Daily Trends
            </span>
          </div>

          {trendChartData.length === 0 || trendChartData.every((d) => d.sends === 0) ? (
            <div className="h-56 w-full flex flex-col items-center justify-center text-center p-6 border border-dashed border-[rgba(212,175,55,0.2)] rounded-xl">
              <Send className="w-6 h-6 text-[#A59F8F] mb-2 opacity-50" />
              <span className="text-xs font-medium text-[#A59F8F]">No dispatch activity recorded yet</span>
              <span className="text-[11px] text-[#A59F8F]/70 mt-0.5">Send a campaign to view daily dispatch activity</span>
            </div>
          ) : (
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="goldGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#D4AF37" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#D4AF37" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="day"
                    stroke="#A59F8F"
                    fontSize={10}
                    tickLine={false}
                    axisLine={{ stroke: 'rgba(212,175,55,0.18)' }}
                  />
                  <YAxis
                    stroke="#A59F8F"
                    fontSize={10}
                    tickLine={false}
                    axisLine={{ stroke: 'rgba(212,175,55,0.18)' }}
                    allowDecimals={false}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: '#121212',
                      border: '1px solid rgba(212,175,55,0.4)',
                      borderRadius: '8px',
                      fontSize: '11px',
                      color: '#F5F1E6',
                    }}
                    itemStyle={{ color: '#F2D675' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="sends"
                    name="Emails Sent"
                    stroke="#D4AF37"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#goldGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Chart 2: Reply Intent Distribution */}
        <div className="lg:col-span-4 glass p-5 space-y-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-xs font-bold text-[#F2D675] uppercase tracking-wider">
                Reply Intent Breakdown
              </h3>
              <Badge variant="gold" className="text-[10px]">AI Classifier</Badge>
            </div>
            <p className="text-[11px] text-[#A59F8F]">
              Categorized incoming responses from verified threads.
            </p>
          </div>

          {intentData.length === 0 ? (
            <div className="h-44 w-full flex flex-col items-center justify-center text-center p-4 border border-dashed border-[rgba(212,175,55,0.2)] rounded-xl">
              <MessageSquare className="w-6 h-6 text-[#A59F8F] mb-2 opacity-50" />
              <span className="text-xs font-medium text-[#A59F8F]">No replies categorized yet</span>
              <span className="text-[11px] text-[#A59F8F]/70 mt-0.5">Incoming replies classified by AI will appear here</span>
            </div>
          ) : (
            <>
              <div className="h-44 w-full flex items-center justify-center">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={intentData}
                      cx="50%"
                      cy="50%"
                      innerRadius={36}
                      outerRadius={65}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {intentData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={GOLD_PALETTE[index % GOLD_PALETTE.length]} stroke="#121212" strokeWidth={2} />
                      ))}
                    </Pie>
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: '#121212',
                        border: '1px solid rgba(212,175,55,0.4)',
                        borderRadius: '8px',
                        fontSize: '11px',
                        color: '#F5F1E6',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Legend */}
              <div className="grid grid-cols-2 gap-1.5 pt-2 border-t border-[rgba(212,175,55,0.15)] text-[10px] text-[#A59F8F]">
                {intentData.slice(0, 4).map((entry, idx) => (
                  <div key={idx} className="flex items-center gap-1.5 truncate">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: GOLD_PALETTE[idx % GOLD_PALETTE.length] }} />
                    <span className="truncate capitalize">{entry.name}</span>
                    <span className="font-mono text-[#F5F1E6] ml-auto">{entry.value}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 5. Live Activity Feed (Latest 20 Events) */}
      <div className="glass p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#D4AF37]" />
            <h3 className="text-xs font-bold text-[#F2D675] uppercase tracking-wider">
              Live Audit & Activity Trail
            </h3>
          </div>
          <Button variant="ghost" size="xs" onClick={() => onNavigate('Activity')} className="text-xs text-[#A59F8F]">
            View Full Log
          </Button>
        </div>

        <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
          {activity.length === 0 ? (
            <p className="text-xs text-[#A59F8F] py-4 text-center">No activity recorded yet.</p>
          ) : (
            activity.slice(0, 20).map((act) => (
              <div
                key={act.id}
                className="flex items-start justify-between gap-3 p-2.5 rounded-xl bg-[#1A1A1A]/80 border border-[rgba(212,175,55,0.12)] text-xs hover:border-[rgba(212,175,55,0.3)] transition-colors"
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#D4AF37] flex-shrink-0 mt-1.5" />
                  <div className="min-w-0">
                    <span className="font-semibold text-[#F5F1E6] capitalize block truncate">
                      {act.action?.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[11px] text-[#A59F8F] truncate block">
                      {act.details || act.contact_email || 'System operation'}
                    </span>
                  </div>
                </div>
                <span className="text-[10px] font-mono text-[#A59F8F] flex-shrink-0 pt-0.5">
                  {act.timestamp?.slice(11, 16) || 'recent'}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 6. System Health Row */}
      <div className="glass p-4 text-xs">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center sm:text-left">
          <div>
            <span className="text-[10px] text-[#A59F8F] uppercase tracking-wider block">Reply Watcher</span>
            <strong className={`font-semibold ${watcher?.running ? 'text-[#3DDC97]' : 'text-[#A59F8F]'}`}>
              {watcher?.running ? '● Active Polling' : '○ Standby'}
            </strong>
          </div>
          <div>
            <span className="text-[10px] text-[#A59F8F] uppercase tracking-wider block">Global Sending</span>
            <strong className={`font-semibold ${health?.global_sending_paused ? 'text-[#FF9F43]' : 'text-[#3DDC97]'}`}>
              {health?.global_sending_paused ? 'Paused' : 'Active (Normal)'}
            </strong>
          </div>
          <div>
            <span className="text-[10px] text-[#A59F8F] uppercase tracking-wider block">AI Engine</span>
            <strong className="font-semibold text-[#F2D675] uppercase">
              {health?.ai_provider || 'Anthropic'}
            </strong>
          </div>
          <div>
            <span className="text-[10px] text-[#A59F8F] uppercase tracking-wider block">Dispatch Mode</span>
            <strong className={`font-semibold ${health?.test_mode ? 'text-[#FF9F43]' : 'text-[#FF5C5C]'}`}>
              {health?.test_mode ? 'Test Mode (Diverted)' : 'Live Mode'}
            </strong>
          </div>
        </div>
      </div>
    </div>
  );
}
