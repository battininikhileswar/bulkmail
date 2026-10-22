import React from 'react';
import { Button } from '@/components/ui/button';
import { Input, Textarea } from '@/components/ui/input';
import { AnimatedProgressBar } from '@/components/ui/progress';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '@/components/ui/empty-state';
import { StatusBadge } from '@/components/ui/badge';
import { Send, Pause, Square, Eye, RotateCcw, Megaphone, Check, Calendar, AlertCircle } from 'lucide-react';

export function CampaignPage({
  campaigns = [],
  activeCampId,
  onSelectCamp,
  campName,
  onCampNameChange,
  subject,
  onSubjectChange,
  mode,
  onModeChange,
  provider,
  onProviderChange,
  groupTag,
  onGroupTagChange,
  groups = [],
  template,
  onTemplateChange,
  chips = [],
  insertChip,
  templateRef,
  onCreateCampaign,
  progress,
  campaignPlan,
  canUseSmtp = true,
  onStartDispatch,
  onPause,
  onStop,
  onRetryFailed,
  preview,
  showPreview,
  onClosePreview,
  onOpenPreview,
  showConfirm,
  onCloseConfirm,
  onOpenConfirm,
  confirmed,
  onConfirmedChange,
  testEmail,
  onTestEmailChange,
  onTestSend,
  testResult,
}) {
  const activeCamp = campaigns.find((c) => c.id === activeCampId);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Create Campaign Form */}
      <div className="glass p-5">
        <h3 className="text-sm font-semibold text-[#F2D675] mb-4 flex items-center gap-2">
          <Megaphone className="w-4 h-4 text-[#D4AF37]" />
          New Campaign
        </h3>

        <form onSubmit={onCreateCampaign} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">Campaign Name</label>
            <Input
              value={campName}
              onChange={(e) => onCampNameChange(e.target.value)}
              placeholder="e.g. Welcome Campaign"
              className="bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">Subject</label>
            <Input
              value={subject}
              onChange={(e) => onSubjectChange(e.target.value)}
              placeholder="e.g. Welcome to our event"
              className="bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1.5">Personalization Mode</label>
            <div className="space-y-2">
              {[
                { id: 'same', label: 'Same Template', desc: 'Replaces {name} placeholder with contact name.' },
                { id: 'fields', label: 'Custom Fields', desc: 'Replaces custom columns (e.g. {company}, {role}).' },
                { id: 'per_person', label: 'Per Person', desc: 'Uses unique message from CSV body column.' },
              ].map((m) => (
                <label
                  key={m.id}
                  className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-xs cursor-pointer transition-colors ${
                    mode === m.id
                      ? 'border-[#D4AF37] bg-[#1A1A1A] text-[#F2D675]'
                      : 'border-[rgba(212,175,55,0.18)] bg-[#141414] hover:bg-[#1A1A1A] text-[#A59F8F]'
                  }`}
                >
                  <input
                    type="radio"
                    name="mode"
                    className="mt-0.5 accent-[#D4AF37] focus:ring-[#D4AF37]"
                    checked={mode === m.id}
                    onChange={() => onModeChange(m.id)}
                  />
                  <div>
                    <div className="font-semibold text-[#F5F1E6]">{m.label}</div>
                    <div className="text-[11px] text-[#A59F8F]">{m.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-[#A59F8F] mb-1">Provider</label>
              <select
                className="w-full px-3 py-1.5 text-xs bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] rounded-lg text-[#F5F1E6] focus:outline-none focus:border-[#D4AF37]"
                value={provider}
                onChange={(e) => onProviderChange(e.target.value)}
              >
                <option value="gmail">Gmail</option>
                {canUseSmtp ? (
                  <option value="smtp">SMTP</option>
                ) : (
                  <option value="smtp" disabled>SMTP (Custom domain only)</option>
                )}
              </select>
              {!canUseSmtp && (
                <p className="mt-1 text-[11px] text-[#FF9F43]">
                  Gmail accounts must use Google sign-in to comply with Gmail sending policies.
                </p>
              )}
            </div>
            <div>
              <label className="block text-xs font-medium text-[#A59F8F] mb-1">Target Group</label>
              <select
                className="w-full px-3 py-1.5 text-xs bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] rounded-lg text-[#F5F1E6] focus:outline-none focus:border-[#D4AF37]"
                value={groupTag}
                onChange={(e) => onGroupTagChange(e.target.value)}
              >
                <option value="">All Contacts</option>
                {groups.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">Email Body Template</label>
            <Textarea
              ref={templateRef}
              rows={5}
              value={template}
              onChange={(e) => onTemplateChange(e.target.value)}
              placeholder="Hi {name},&#10;&#10;..."
              className="bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
            {mode === 'fields' && chips.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5 items-center">
                <span className="text-[11px] text-[#A59F8F] mr-1">Insert variables:</span>
                {chips.map((ph) => (
                  <button
                    key={ph}
                    type="button"
                    onClick={() => insertChip(ph)}
                    className="px-2 py-0.5 rounded text-[11px] font-mono bg-[#1A1A1A] hover:bg-[#222222] text-[#F2D675] border border-[rgba(212,175,55,0.25)] cursor-pointer transition-colors"
                  >
                    +{`{${ph}}`}
                  </button>
                ))}
              </div>
            )}
          </div>

          <Button type="submit" variant="primary" size="sm" className="w-full">
            Create Campaign
          </Button>
        </form>
      </div>

      {/* Active Campaign & Test Box */}
      <div className="space-y-5">
        <div className="glass p-5">
          <h3 className="text-sm font-semibold text-[#F2D675] mb-3">Active Campaign Dispatch</h3>

          {campaigns.length === 0 ? (
            <EmptyState
              icon={Megaphone}
              title="No campaigns yet"
              description="Create a campaign using the form on the left to begin sending."
            />
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-[#A59F8F] mb-1">Select Campaign</label>
                <select
                  className="w-full px-3 py-1.5 text-xs bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] rounded-lg text-[#F5F1E6] focus:outline-none focus:border-[#D4AF37]"
                  value={activeCampId || ''}
                  onChange={(e) => onSelectCamp(Number(e.target.value))}
                >
                  {campaigns.map((c) => (
                    <option key={c.id} value={c.id}>
                      #{c.id} - {c.name} ({c.status})
                    </option>
                  ))}
                </select>
              </div>

              {/* Multi-Day Planning Callout */}
              {campaignPlan && (
                <div className="p-3.5 rounded-xl bg-[#1A1A1A] border border-[rgba(212,175,55,0.3)] text-xs text-[#F5F1E6] flex items-start gap-2.5">
                  <Calendar className="w-4 h-4 text-[#D4AF37] flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block text-[#F2D675]">
                      {campaignPlan.is_multi_day ? 'Multi-Day Dispatch Plan' : 'Schedule Estimate'}
                    </span>
                    {campaignPlan.is_multi_day ? (
                      <p className="text-[11px] text-[#A59F8F] mt-0.5">
                        {campaignPlan.summary_text ? (
                          campaignPlan.summary_text
                        ) : (
                          <>
                            {campaignPlan.pending_count} contacts, {campaignPlan.limits_status?.campaign_cap || 360} per day: about{' '}
                            <strong className="text-[#F2D675]">{campaignPlan.days_needed} days</strong>, finishing around{' '}
                            <strong className="text-[#F2D675]">{campaignPlan.finish_date}</strong>.
                          </>
                        )}
                      </p>
                    ) : (
                      <p className="text-[11px] text-[#A59F8F] mt-0.5">
                        All {campaignPlan.pending_count} pending contacts can be dispatched today within your daily campaign cap ({campaignPlan.limits_status?.campaign_cap || 360}/day).
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Smooth Animated Progress Bar */}
              {progress && (
                <div className="space-y-2 p-3.5 rounded-xl bg-[#1A1A1A] border border-[rgba(212,175,55,0.18)]">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-[#F2D675]">
                      {campaignPlan?.is_multi_day
                        ? `Day ${progress.current_day || 1} of ${campaignPlan.days_needed} (${progress.sent}/${progress.total} sent)`
                        : 'Dispatch Progress'}
                    </span>
                    <span className="text-[#A59F8F] font-mono text-[11px]">
                      {progress.sent} / {progress.total} ({progress.total > 0 ? Math.round((progress.sent / progress.total) * 100) : 0}%)
                    </span>
                  </div>
                  <AnimatedProgressBar value={progress.sent} max={progress.total || 1} />
                  <div className="flex justify-between text-[11px] text-[#A59F8F] pt-1">
                    <span>Sent: <strong className="text-[#3DDC97]">{progress.sent}</strong></span>
                    <span>Pending: <strong className="text-[#FF9F43]">{progress.pending}</strong></span>
                    <span>Skipped: <strong className="text-[#A59F8F]">{progress.skipped}</strong></span>
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-wrap gap-2 pt-1">
                {progress?.campaign_status !== 'running' ? (
                  <Button variant="primary" size="sm" onClick={onOpenConfirm}>
                    <Send className="w-3.5 h-3.5 mr-1" />
                    Start Sending
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" onClick={onPause} className="text-[#FF9F43] border-[#FF9F43]/40 hover:bg-[#FF9F43]/10">
                    <Pause className="w-3.5 h-3.5 mr-1" />
                    Pause
                  </Button>
                )}
                <Button variant="danger" size="sm" onClick={onStop}>
                  <Square className="w-3.5 h-3.5 mr-1" />
                  Stop
                </Button>
                <Button variant="outline" size="sm" onClick={onOpenPreview}>
                  <Eye className="w-3.5 h-3.5 mr-1" />
                  Preview
                </Button>
                <Button variant="outline" size="sm" onClick={onRetryFailed}>
                  <RotateCcw className="w-3.5 h-3.5 mr-1" />
                  Retry Failed
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Test Send Box */}
        {activeCamp && (
          <div className="glass p-5">
            <h3 className="text-sm font-semibold text-[#F2D675] mb-2">Send Test Sample</h3>
            <p className="text-xs text-[#A59F8F] mb-3">
              Safely send a sample preview email to verify template variables and formatting.
            </p>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="test@example.com"
                value={testEmail}
                onChange={(e) => onTestEmailChange(e.target.value)}
                className="text-xs bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              />
              <Button variant="outline" size="sm" onClick={onTestSend} className="flex-shrink-0">
                Send Test
              </Button>
            </div>
            {testResult && (
              <div className="mt-2 text-xs text-[#F2D675] font-mono bg-[#1A1A1A] p-2 rounded-lg border border-[rgba(212,175,55,0.2)] break-words whitespace-pre-wrap">
                {testResult.includes('http') ? (
                  testResult.split(/(https?:\/\/[^\s]+)/g).map((part, idx) =>
                    part.startsWith('http') ? (
                      <a
                        key={idx}
                        href={part}
                        target="_blank"
                        rel="noreferrer"
                        className="underline text-[#F2D675] hover:text-[#FFF] font-semibold break-all"
                      >
                        {part}
                      </a>
                    ) : (
                      part
                    )
                  )
                ) : (
                  testResult
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Preview Modal */}
      <Modal
        isOpen={showPreview}
        onClose={onClosePreview}
        title={`Preview Emails (${preview?.total_contacts || 0} Contacts)`}
        maxWidth="max-w-xl"
      >
        <div className="max-h-[60vh] overflow-y-auto space-y-3 pr-1">
          {!preview || !preview.rendered || preview.rendered.length === 0 ? (
            <EmptyState
              icon={Eye}
              title="No preview available"
              description="Could not render contacts for this campaign."
            />
          ) : (
            preview.rendered.map((item, idx) => (
              <div
                key={idx}
                className="p-3.5 rounded-xl border border-[rgba(212,175,55,0.18)] bg-[#1A1A1A] text-xs space-y-1.5"
              >
                <div className="font-semibold text-[#F2D675]">
                  To: {item.name} &lt;{item.email}&gt;
                </div>
                <div className="text-[#F5F1E6] whitespace-pre-wrap leading-relaxed font-sans">
                  {item.body}
                </div>
              </div>
            ))
          )}
        </div>
        <div className="flex justify-end pt-4 mt-4 border-t border-[rgba(212,175,55,0.15)]">
          <Button variant="outline" size="sm" onClick={onClosePreview}>
            Close
          </Button>
        </div>
      </Modal>

      {/* Confirm Dispatch Modal */}
      <Modal
        isOpen={showConfirm}
        onClose={onCloseConfirm}
        title="Confirm Campaign Dispatch"
        maxWidth="max-w-md"
      >
        <div className="space-y-4 text-xs text-[#F5F1E6]">
          <p className="leading-relaxed">
            You are about to dispatch <strong className="text-[#F2D675]">{progress?.total || activeCamp?.total_recipients || 0}</strong> emails via <strong className="text-[#F2D675]">{(activeCamp?.provider || 'gmail').toUpperCase()}</strong>.
          </p>
          {campaignPlan?.is_multi_day && (
            <div className="p-3 rounded-xl bg-[#1A1A1A] border border-[rgba(212,175,55,0.25)] text-[#F5F1E6] text-xs">
              <span className="font-semibold block text-[#F2D675] mb-1">Multi-day Dispatch Schedule:</span>
              <p className="text-[11px] text-[#A59F8F] leading-relaxed">
                {campaignPlan.summary_text}
              </p>
            </div>
          )}
          <label className="flex items-start gap-2.5 p-3 rounded-xl border border-[rgba(212,175,55,0.22)] bg-[#1A1A1A] cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5 rounded accent-[#D4AF37] focus:ring-[#D4AF37]"
              checked={confirmed}
              onChange={(e) => onConfirmedChange(e.target.checked)}
            />
            <span className="font-medium text-[#F5F1E6]">
              I confirm that these contacts consented to receive communications and that sending adheres to applicable regulations.
            </span>
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-4 mt-4 border-t border-[rgba(212,175,55,0.15)]">
          <Button variant="outline" size="sm" onClick={onCloseConfirm}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!confirmed}
            onClick={onStartDispatch}
          >
            <Check className="w-3.5 h-3.5 mr-1" />
            Confirm & Start
          </Button>
        </div>
      </Modal>
    </div>
  );
}
