import React, { useState, useEffect } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Input, Textarea } from '@/components/ui/input';
import { Badge, StatusBadge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';
import { EmptyState } from '@/components/ui/empty-state';
import { TableSkeleton } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/toast';
import {
  Compass,
  Clock,
  PlusCircle,
  Eye,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Send,
  Power,
  RotateCw,
} from 'lucide-react';

export function AutopilotPage({ API, campaigns = [] }) {
  const toast = useToast();
  const prefersReduced = useReducedMotion();

  const [automations, setAutomations] = useState([]);
  const [loading, setLoading] = useState(true);

  // Create Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCampId, setNewCampId] = useState('');
  const [newType, setNewType] = useState('followup');
  const [newDelayDays, setNewDelayDays] = useState(3);
  const [newMaxFollowups, setNewMaxFollowups] = useState(1);
  const [newWindowStart, setNewWindowStart] = useState('09:00');
  const [newWindowEnd, setNewWindowEnd] = useState('18:00');
  const [newSubject, setNewSubject] = useState('');
  const [newTemplate, setNewTemplate] = useState('Hi {name},\n\nI wanted to gently follow up on our previous note. Let us know if you have any questions!\n\nBest regards,');
  const [newScheduledAt, setNewScheduledAt] = useState('');
  const [createConsent, setCreateConsent] = useState(false);
  const [creating, setCreating] = useState(false);

  // Enable Consent Modal State
  const [enableTargetId, setEnableTargetId] = useState(null);
  const [enableConsent, setEnableConsent] = useState(false);

  // Preview Modal State
  const [previewData, setPreviewData] = useState(null);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const fetchAutomations = () => {
    setLoading(true);
    fetch(`${API}/automations`)
      .then((r) => r.ok && r.json())
      .then((data) => setAutomations(data || []))
      .catch(() => toast.error('Failed to load automations'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAutomations();
    if (campaigns.length > 0 && !newCampId) {
      setNewCampId(campaigns[0].id);
    }
  }, [campaigns]);

  // Create Automation
  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newCampId) {
      toast.error('Select a campaign first');
      return;
    }
    setCreating(true);
    try {
      const res = await fetch(`${API}/automations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          campaign_id: Number(newCampId),
          type: newType,
          delay_days: Number(newDelayDays),
          max_followups: Number(newMaxFollowups),
          send_window_start: newWindowStart,
          send_window_end: newWindowEnd,
          subject: newSubject,
          template: newTemplate,
          scheduled_at: newType === 'event_reminder' ? newScheduledAt : null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Created ${newType} automation rule (disabled by default)`);
        setShowCreateModal(false);
        fetchAutomations();
      } else {
        toast.error(data.detail || 'Failed to create automation');
      }
    } catch {
      toast.error('Network error creating automation');
    } finally {
      setCreating(false);
    }
  };

  // Toggle Enable / Disable
  const handleToggle = (auto) => {
    if (auto.enabled === 1) {
      fetch(`${API}/automations/${auto.id}/disable`, { method: 'POST' })
        .then((r) => r.ok && r.json())
        .then(() => {
          toast.info(`Automation #${auto.id} disabled`);
          fetchAutomations();
        })
        .catch(() => toast.error('Failed to disable automation'));
    } else {
      setEnableTargetId(auto.id);
      setEnableConsent(false);
    }
  };

  // Confirm Enable with Consent
  const handleConfirmEnable = () => {
    if (!enableTargetId || !enableConsent) return;
    fetch(`${API}/automations/${enableTargetId}/enable`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ consent: true }),
    })
      .then((r) => r.ok && r.json())
      .then(() => {
        toast.success(`Automation #${enableTargetId} enabled!`);
        setEnableTargetId(null);
        fetchAutomations();
      })
      .catch(() => toast.error('Failed to enable automation'));
  };

  // Open Preview Modal
  const handleOpenPreview = (autoId) => {
    setLoadingPreview(true);
    setShowPreviewModal(true);
    fetch(`${API}/automations/${autoId}/preview`)
      .then((r) => r.ok && r.json())
      .then((data) => setPreviewData(data))
      .catch(() => toast.error('Failed to load preview'))
      .finally(() => setLoadingPreview(false));
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass p-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] flex items-center justify-center text-[#0A0A0A] shadow-[0_0_15px_rgba(212,175,55,0.35)]">
            <Compass className="w-5 h-5 font-bold" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-[#F2D675] leading-tight">Autopilot Engine</h2>
              <Badge variant="neutral" className="text-[10px]">OFF by default</Badge>
            </div>
            <p className="text-xs text-[#A59F8F] mt-0.5 font-medium">
              Autopilot runs only while the app is running.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchAutomations}>
            <RotateCw className="w-3.5 h-3.5 mr-1" />
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setCreateConsent(false);
              setShowCreateModal(true);
            }}
          >
            <PlusCircle className="w-3.5 h-3.5 mr-1.5" />
            New Automation
          </Button>
        </div>
      </div>

      {/* Safety Notice */}
      <div className="p-4 rounded-xl glass text-xs text-[#F5F1E6] space-y-1">
        <div className="font-semibold flex items-center gap-1.5 text-[#F2D675]">
          <Clock className="w-4 h-4 text-[#D4AF37]" />
          Autonomous Dispatch Guardrails
        </div>
        <p className="text-[11px] text-[#A59F8F] leading-relaxed">
          Autopilot strictly stops for contacts who reply, unsubscribe, or bounce. Follow-ups send only within your defined send window (quiet hours) and never exceed the daily send cap or the hard ceiling of 2 follow-ups.
        </p>
      </div>

      {/* Automations List */}
      <div className="space-y-4">
        {loading ? (
          <TableSkeleton rows={4} cols={4} />
        ) : automations.length === 0 ? (
          <EmptyState
            icon={Compass}
            title="No automations configured yet"
            description="Create an automatic follow-up or scheduled reminder for your campaigns."
            action={
              <Button variant="primary" size="sm" onClick={() => setShowCreateModal(true)}>
                <PlusCircle className="w-3.5 h-3.5 mr-1" /> Create Automation
              </Button>
            }
          />
        ) : (
          automations.map((a) => {
            const isEnabled = a.enabled === 1;
            return (
              <motion.div
                key={a.id}
                whileHover={!prefersReduced ? { y: -1 } : undefined}
                className={`glass p-5 transition-shadow space-y-4 ${
                  isEnabled ? 'border-[#D4AF37] shadow-[0_0_15px_rgba(212,175,55,0.15)]' : ''
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-[#F5F1E6]">
                        {a.campaign_name || `Campaign #${a.campaign_id}`}
                      </span>
                      <Badge variant={a.type === 'followup' ? 'gold' : 'warning'} className="capitalize text-[10px]">
                        {a.type === 'followup' ? 'Follow-up' : 'Event Reminder'}
                      </Badge>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                          isEnabled
                            ? 'bg-[#3DDC97]/15 text-[#3DDC97] border-[#3DDC97]/30'
                            : 'bg-[#1A1A1A] text-[#A59F8F] border-[rgba(212,175,55,0.2)]'
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${isEnabled ? 'bg-[#3DDC97] animate-pulse' : 'bg-[#A59F8F]'}`} />
                        {isEnabled ? 'Active' : 'Disabled'}
                      </span>
                    </div>
                    <div className="text-xs text-[#A59F8F] flex flex-wrap gap-4 pt-0.5">
                      {a.type === 'followup' && (
                        <span>Delay: <strong className="text-[#F2D675]">{a.delay_days} day(s)</strong></span>
                      )}
                      {a.type === 'followup' && (
                        <span>Max Follow-ups: <strong className="text-[#F2D675]">{a.max_followups}</strong></span>
                      )}
                      <span>
                        Send Window: <strong className="text-[#F2D675]">{a.send_window_start} – {a.send_window_end}</strong>
                      </span>
                      {a.type === 'event_reminder' && a.scheduled_at && (
                        <span>Scheduled: <strong className="text-[#F2D675]">{new Date(a.scheduled_at).toLocaleString()}</strong></span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleOpenPreview(a.id)}
                      className="text-xs"
                    >
                      <Eye className="w-3.5 h-3.5 mr-1" />
                      Who will get this?
                    </Button>
                    <Button
                      variant={isEnabled ? 'danger' : 'primary'}
                      size="sm"
                      onClick={() => handleToggle(a)}
                      className="text-xs"
                    >
                      <Power className="w-3.5 h-3.5 mr-1" />
                      {isEnabled ? 'Turn OFF' : 'Turn ON'}
                    </Button>
                  </div>
                </div>

                {/* Template Preview */}
                <div className="p-3 rounded-lg bg-[#1A1A1A] border border-[rgba(212,175,55,0.18)] text-xs text-[#F5F1E6] space-y-1">
                  <div className="text-[11px] font-semibold text-[#F2D675]">
                    Template: {a.subject ? `[Subject: ${a.subject}]` : '(Re: Campaign Subject)'}
                  </div>
                  <div className="whitespace-pre-wrap font-sans text-[11px] text-[#A59F8F] line-clamp-3">
                    {a.template}
                  </div>
                </div>
              </motion.div>
            );
          })
        )}
      </div>

      {/* Create Automation Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create New Automation Rule"
        maxWidth="max-w-lg"
      >
        <form onSubmit={handleCreate} className="space-y-4 text-xs text-[#F5F1E6]">
          <div>
            <label className="block font-medium text-[#A59F8F] mb-1">Target Campaign</label>
            <select
              className="w-full px-3 py-1.5 text-xs bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] rounded-lg text-[#F5F1E6] focus:outline-none focus:border-[#D4AF37]"
              value={newCampId}
              onChange={(e) => setNewCampId(e.target.value)}
              required
            >
              <option value="">-- Select Campaign --</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.id} - {c.name} ({c.status})
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-medium text-[#A59F8F] mb-1">Type</label>
              <select
                className="w-full px-3 py-1.5 text-xs bg-[#1A1A1A] border border-[rgba(212,175,55,0.22)] rounded-lg text-[#F5F1E6] focus:outline-none focus:border-[#D4AF37]"
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
              >
                <option value="followup">Follow-up (no reply)</option>
                <option value="event_reminder">Event Reminder</option>
              </select>
            </div>
            {newType === 'followup' ? (
              <div>
                <label className="block font-medium text-[#A59F8F] mb-1">Delay Days</label>
                <Input
                  type="number"
                  min="0"
                  max="30"
                  value={newDelayDays}
                  onChange={(e) => setNewDelayDays(Number(e.target.value))}
                  className="text-xs bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
                  required
                />
              </div>
            ) : (
              <div>
                <label className="block font-medium text-[#A59F8F] mb-1">Scheduled Date & Time</label>
                <Input
                  type="datetime-local"
                  value={newScheduledAt}
                  onChange={(e) => setNewScheduledAt(e.target.value)}
                  className="text-xs bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
                  required
                />
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-medium text-[#A59F8F] mb-1">Send Window Start (Local)</label>
              <Input
                type="time"
                value={newWindowStart}
                onChange={(e) => setNewWindowStart(e.target.value)}
                className="text-xs bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
                required
              />
            </div>
            <div>
              <label className="block font-medium text-[#A59F8F] mb-1">Send Window End (Local)</label>
              <Input
                type="time"
                value={newWindowEnd}
                onChange={(e) => setNewWindowEnd(e.target.value)}
                className="text-xs bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
                required
              />
            </div>
          </div>

          <div>
            <label className="block font-medium text-[#A59F8F] mb-1">Custom Subject (optional)</label>
            <Input
              value={newSubject}
              onChange={(e) => setNewSubject(e.target.value)}
              placeholder="e.g. Re: Welcome to our event"
              className="text-xs bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
            />
          </div>

          <div>
            <label className="block font-medium text-[#A59F8F] mb-1">Approved Template Message</label>
            <Textarea
              rows={5}
              value={newTemplate}
              onChange={(e) => setNewTemplate(e.target.value)}
              className="text-xs font-sans leading-relaxed bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t border-[rgba(212,175,55,0.18)]">
            <Button variant="outline" size="sm" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" type="submit" disabled={creating}>
              {creating ? 'Saving...' : 'Save Automation Rule'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Enable Consent Confirmation Modal */}
      <Modal
        isOpen={Boolean(enableTargetId)}
        onClose={() => setEnableTargetId(null)}
        title="Confirm Autopilot Activation"
        maxWidth="max-w-md"
      >
        <div className="space-y-4 text-xs text-[#F5F1E6]">
          <p className="leading-relaxed">
            You are about to activate automated sending for this campaign. The background scheduler will check every 60 seconds and dispatch messages inside the send window.
          </p>
          <label className="flex items-start gap-2.5 p-3 rounded-xl border border-[rgba(212,175,55,0.22)] bg-[#1A1A1A] cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5 rounded accent-[#D4AF37] focus:ring-[#D4AF37]"
              checked={enableConsent}
              onChange={(e) => setEnableConsent(e.target.checked)}
            />
            <span className="font-medium text-[#F5F1E6]">
              I confirm that these contacts consented to receive communications and that follow-ups adhere to applicable sending policies.
            </span>
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-4 mt-4 border-t border-[rgba(212,175,55,0.18)]">
          <Button variant="outline" size="sm" onClick={() => setEnableTargetId(null)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!enableConsent}
            onClick={handleConfirmEnable}
          >
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
            Confirm & Activate
          </Button>
        </div>
      </Modal>

      {/* "Who will get this?" Preview Modal */}
      <Modal
        isOpen={showPreviewModal}
        onClose={() => setShowPreviewModal(false)}
        title="Autopilot Recipient Preview"
        maxWidth="max-w-2xl"
      >
        <div className="space-y-4 text-xs text-[#F5F1E6]">
          {loadingPreview ? (
            <TableSkeleton rows={4} cols={3} />
          ) : !previewData ? (
            <EmptyState title="No preview data available" />
          ) : (
            <>
              <div className="flex gap-4 p-3 rounded-xl glass">
                <div>
                  <span className="text-[#A59F8F] font-medium">Qualifying Now: </span>
                  <strong className="text-[#3DDC97] font-bold">{previewData.total_eligible} contact(s)</strong>
                </div>
                <div>
                  <span className="text-[#A59F8F] font-medium">Skipped: </span>
                  <strong className="text-[#F2D675] font-bold">{previewData.total_skipped} contact(s)</strong>
                </div>
              </div>

              {/* Qualifying Table */}
              <div>
                <h4 className="font-semibold text-[#F2D675] mb-2 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-[#3DDC97]" />
                  Eligible to receive message now ({previewData.total_eligible})
                </h4>
                {previewData.eligible.length === 0 ? (
                  <div className="p-3 bg-[#1A1A1A] rounded-lg text-[#A59F8F] text-[11px] italic">
                    No contacts currently meet all send conditions.
                  </div>
                ) : (
                  <div className="max-h-48 overflow-y-auto border border-[rgba(212,175,55,0.2)] rounded-lg">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-[#1A1A1A] border-b border-[rgba(212,175,55,0.18)] text-[#A59F8F] text-[10px] uppercase font-semibold">
                        <tr>
                          <th className="py-2 px-3 text-[#D4AF37]">Name</th>
                          <th className="py-2 px-3 text-[#D4AF37]">Email</th>
                          <th className="py-2 px-3 text-[#D4AF37]">Follow-ups Sent</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[rgba(212,175,55,0.1)]">
                        {previewData.eligible.map((e) => (
                          <tr key={e.recipient_id}>
                            <td className="py-2 px-3 font-medium text-[#F5F1E6]">{e.name}</td>
                            <td className="py-2 px-3 text-[#A59F8F]">{e.email}</td>
                            <td className="py-2 px-3 font-mono text-[11px] text-[#F2D675]">{e.followup_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Skipped Table */}
              <div>
                <h4 className="font-semibold text-[#F2D675] mb-2 flex items-center gap-1.5">
                  <XCircle className="w-3.5 h-3.5 text-[#FF5C5C]" />
                  Skipped Contacts ({previewData.total_skipped})
                </h4>
                {previewData.skipped.length === 0 ? (
                  <div className="p-3 bg-[#1A1A1A] rounded-lg text-[#A59F8F] text-[11px] italic">
                    No skipped contacts.
                  </div>
                ) : (
                  <div className="max-h-48 overflow-y-auto border border-[rgba(212,175,55,0.2)] rounded-lg">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-[#1A1A1A] border-b border-[rgba(212,175,55,0.18)] text-[#A59F8F] text-[10px] uppercase font-semibold">
                        <tr>
                          <th className="py-2 px-3 text-[#D4AF37]">Email</th>
                          <th className="py-2 px-3 text-[#D4AF37]">Reason Skipped</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[rgba(212,175,55,0.1)]">
                        {previewData.skipped.map((s, idx) => (
                          <tr key={idx} className="hover:bg-[#1A1A1A]/50">
                            <td className="py-2 px-3 font-medium text-[#F5F1E6]">{s.email}</td>
                            <td className="py-2 px-3 text-[#A59F8F] text-[11px]">{s.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}

          <div className="flex justify-end pt-3 border-t border-[rgba(212,175,55,0.18)]">
            <Button variant="outline" size="sm" onClick={() => setShowPreviewModal(false)}>
              Close
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
