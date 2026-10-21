import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Settings as SettingsIcon, Save, Database, Download, ShieldCheck } from 'lucide-react';

export function SettingsPage({
  settings = {},
  onSettingsChange,
  onSaveSettings,
  savingSettings = false,
  onBackupNow,
  backups = [],
  API,
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Settings Form */}
      <div className="lg:col-span-7 glass p-5">
        <h3 className="text-sm font-semibold text-[#F2D675] mb-4 flex items-center gap-2">
          <SettingsIcon className="w-4 h-4 text-[#D4AF37]" />
          System Settings
        </h3>

        <form onSubmit={onSaveSettings} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">Sender Name</label>
            <Input
              value={settings.sender_name || ''}
              onChange={(e) => onSettingsChange({ ...settings, sender_name: e.target.value })}
              placeholder="e.g. Event Coordinator"
              className="bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">Tone Description</label>
            <Input
              value={settings.tone || ''}
              onChange={(e) => onSettingsChange({ ...settings, tone: e.target.value })}
              placeholder="e.g. friendly and professional"
              className="bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">Test Address</label>
            <Input
              type="email"
              value={settings.test_email || ''}
              onChange={(e) => onSettingsChange({ ...settings, test_email: e.target.value })}
              placeholder="test@example.com"
              className="bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-medium text-[#A59F8F]">Daily Sending Cap</label>
                <span className="text-[10px] text-[#A59F8F]/70">Max: {settings.default_cap || 400}</span>
              </div>
              <Input
                type="number"
                min="1"
                max={settings.default_cap || 400}
                value={settings.daily_cap ?? 400}
                onChange={(e) => onSettingsChange({ ...settings, daily_cap: Number(e.target.value) })}
                className="bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
                required
              />
              <p className="mt-1 text-[11px] text-[#A59F8F]/80 leading-tight">
                Personal Gmail accounts are capped at 400/day. Google Workspace accounts can send up to 1,500/day.
              </p>
            </div>
            <div>
              <label className="block text-xs font-medium text-[#A59F8F] mb-1">Pause Between Sends (sec)</label>
              <Input
                type="number"
                min="0"
                value={settings.pause_seconds ?? 5}
                onChange={(e) => onSettingsChange({ ...settings, pause_seconds: Number(e.target.value) })}
                className="bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
                required
              />
              <p className="mt-1 text-[11px] text-[#A59F8F]/80 leading-tight">
                Safety delay between individual recipient dispatches.
              </p>
            </div>
          </div>

          {/* Warm-Up Toggle */}
          <div className="pt-1">
            <label className="flex items-start gap-2.5 p-3 rounded-xl border border-[rgba(212,175,55,0.22)] bg-[#1A1A1A]/50 cursor-pointer hover:bg-[#1A1A1A]">
              <input
                type="checkbox"
                className="mt-0.5 rounded accent-[#D4AF37] focus:ring-[#D4AF37]"
                checked={Boolean(settings.warmup_enabled)}
                onChange={(e) => onSettingsChange({ ...settings, warmup_enabled: e.target.checked })}
              />
              <div className="text-xs text-[#A59F8F]">
                <span className="font-semibold block text-[#F5F1E6]">Gradual Warm-Up Ramp</span>
                <span>
                  Protects sender reputation by gradually scaling daily limits: Day 1 (50) → Day 2 (100) → Day 3 (200) → Full Daily Cap ({settings.daily_cap || 400}).
                </span>
                {settings.warmup_enabled && (
                  <span className="block mt-1 font-semibold text-[#F2D675] text-[11px]">
                    Active: Warm-up Day {settings.warmup_day || 1} (Limit is {settings.effective_cap || 50} today)
                  </span>
                )}
              </div>
            </label>
          </div>

          <div className="pt-1">
            <label className="flex items-start gap-2.5 p-3 rounded-xl border border-[rgba(212,175,55,0.22)] bg-[#1A1A1A]/50 cursor-pointer hover:bg-[#1A1A1A]">
              <input
                type="checkbox"
                className="mt-0.5 rounded accent-[#D4AF37] focus:ring-[#D4AF37]"
                checked={Boolean(settings.test_mode)}
                onChange={(e) => onSettingsChange({ ...settings, test_mode: e.target.checked })}
              />
              <div className="text-xs text-[#A59F8F]">
                <span className="font-semibold block text-[#F5F1E6]">Enable Test Mode</span>
                Safely diverts outgoing reply and campaign sends to the configured test address with [TEST] prefix.
              </div>
            </label>
          </div>

          <Button type="submit" variant="primary" size="sm" disabled={savingSettings}>
            <Save className="w-3.5 h-3.5 mr-1" />
            {savingSettings ? 'Saving...' : 'Save Settings'}
          </Button>
        </form>
      </div>

      {/* Side Info Cards */}
      <div className="lg:col-span-5 space-y-5">
        {/* Account Identity Card */}
        <div className="glass p-5 space-y-2">
          <h3 className="text-sm font-semibold text-[#F2D675]">Sending Identity</h3>
          <div className="text-xs space-y-1.5">
            <div className="flex justify-between items-center py-1 border-b border-[rgba(212,175,55,0.12)]">
              <span className="text-[#A59F8F]">Connected Account:</span>
              <strong className="text-[#F5F1E6] font-mono text-[11px]">{settings.sending_as || 'Not signed in'}</strong>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-[rgba(212,175,55,0.12)]">
              <span className="text-[#A59F8F]">SMTP Capability:</span>
              <span className={`font-semibold text-[11px] ${settings.can_use_smtp ? 'text-[#3DDC97]' : 'text-[#A59F8F]'}`}>
                {settings.can_use_smtp ? 'Allowed (custom domain)' : 'Restricted (Personal Gmail)'}
              </span>
            </div>
            <p className="text-[11px] text-[#A59F8F] pt-1">
              All campaign emails and reply drafts are sent directly from your connected Google identity.
            </p>
          </div>
        </div>

        {/* AI Provider Card */}
        <div className="glass p-5 space-y-2">
          <h3 className="text-sm font-semibold text-[#F2D675]">AI Provider</h3>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#A59F8F]">Configured Engine:</span>
            <Badge variant="gold" className="uppercase tracking-wide font-semibold text-[10px]">
              {settings.ai_provider || 'anthropic'}
            </Badge>
          </div>
          <p className="text-[11px] text-[#A59F8F]/70 italic leading-relaxed">
            Free AI tiers may have daily limits and different data-use terms.
          </p>
        </div>

        {/* Backups & Data Export */}
        <div className="glass p-5 space-y-3">
          <h3 className="text-sm font-semibold text-[#F2D675]">Backups & Data Export</h3>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" size="sm" onClick={onBackupNow}>
              <Database className="w-3.5 h-3.5 mr-1" />
              Backup Now
            </Button>
            <a
              href={`${API}/contacts/export`}
              download
              className="inline-flex items-center justify-center font-medium transition-colors cursor-pointer text-xs px-2.5 py-1.5 rounded-md gap-1.5 border border-[rgba(212,175,55,0.25)] bg-[#1A1A1A] text-[#F5F1E6] hover:bg-[#222222] hover:border-[#D4AF37]"
            >
              <Download className="w-3.5 h-3.5 text-[#D4AF37]" />
              Export Contacts
            </a>
          </div>
          {backups.length > 0 && (
            <div className="text-[11px] text-[#A59F8F] font-mono bg-[#1A1A1A] p-2 rounded-lg border border-[rgba(212,175,55,0.18)]">
              Latest: <strong className="text-[#F2D675]">{backups[0].filename}</strong> ({Math.round(backups[0].size_bytes / 1024)} KB)
            </div>
          )}
        </div>

        {/* Footer Preview */}
        <div className="glass p-5 space-y-2">
          <h3 className="text-sm font-semibold text-[#F2D675]">Outgoing Mail Footer Preview</h3>
          <div className="text-xs text-[#A59F8F]">
            Unsubscribe line: <em className="text-[#F5F1E6]">"{settings.unsubscribe_line}"</em>
          </div>
          <div className="bg-[#1A1A1A] border border-[rgba(212,175,55,0.18)] rounded-lg p-3 text-xs text-[#A59F8F] whitespace-pre-wrap font-sans leading-relaxed">
            {settings.footer_preview || 'Preview unavailable'}
          </div>
        </div>
      </div>
    </div>
  );
}
