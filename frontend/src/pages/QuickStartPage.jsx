import React, { useState, useEffect } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Input, Textarea } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { useToast } from '@/components/ui/toast';
import {
  Zap,
  Upload,
  Database,
  Sparkles,
  Eye,
  Send,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  Users,
  Check,
} from 'lucide-react';

export function QuickStartPage({ API, onNavigate, onCampaignCreated }) {
  const toast = useToast();
  const prefersReduced = useReducedMotion();

  // Wizard Step (1 to 4)
  const [step, setStep] = useState(1);

  // Step 1: CSV / Contacts
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStats, setUploadStats] = useState(null);
  const [discoveredPlaceholders, setDiscoveredPlaceholders] = useState(['name']);

  // Step 2: Goal & Instructions
  const [goal, setGoal] = useState('Announce / invite');
  const [instructions, setInstructions] = useState('We are hosting an exclusive product launch on Friday with live demos.');
  const [campName, setCampName] = useState('Quick Launch Campaign');

  // Step 3: AI Copywriter & Editable Template
  const [subject, setSubject] = useState('Invitation: Exclusive Event Launch');
  const [template, setTemplate] = useState('Hi {name},\n\nWe are hosting an exclusive product launch on Friday with live demos. We would love for you to join us!\n\nBest regards,');
  const [generating, setGenerating] = useState(false);
  const [aiFallbackUsed, setAiFallbackUsed] = useState(false);

  // Step 4: Preview & Test Send
  const [sampleContacts, setSampleContacts] = useState([]);
  const [testEmail, setTestEmail] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [sendingTest, setSendingTest] = useState(false);
  const [creatingCamp, setCreatingCamp] = useState(false);

  // Load available placeholders & top 3 contacts for preview
  const refreshPlaceholdersAndContacts = () => {
    fetch(`${API}/contacts/placeholders`)
      .then((r) => r.ok && r.json())
      .then((d) => setDiscoveredPlaceholders(d.placeholders || ['name']))
      .catch(() => {});

    fetch(`${API}/contacts`)
      .then((r) => r.ok && r.json())
      .then((list) => {
        if (Array.isArray(list)) {
          setSampleContacts(list.slice(0, 3));
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    refreshPlaceholdersAndContacts();
  }, []);

  // Step 1: Handle CSV Upload
  const handleUpload = async (e) => {
    e?.preventDefault();
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`${API}/contacts/upload`, { method: 'POST', body: fd });
      const data = await res.json();
      if (res.ok) {
        setUploadStats(data);
        toast.success(`Uploaded: Added ${data.added}, ${data.duplicates} duplicates, ${data.invalid} invalid.`);
        refreshPlaceholdersAndContacts();
      } else {
        toast.error(data.detail || 'Upload failed');
      }
    } catch {
      toast.error('Network error uploading file');
    } finally {
      setUploading(false);
    }
  };

  // Step 1: Load 5 Fake Sample Contacts
  const handleLoadSampleData = async () => {
    setUploading(true);
    try {
      const fakeCSV = `name,email,company,role\nAlice Morgan,alice@example.com,Acme Corp,Designer\nBob Chen,bob@example.com,Initech,Lead Engineer\nClara Vance,clara@example.com,Vance Refrigeration,Operations\nDavid Patel,david@example.com,Globex,Product Lead\nElena Rostova,elena@example.com,Soylent,Founder`;
      const blob = new Blob([fakeCSV], { type: 'text/csv' });
      const fd = new FormData();
      fd.append('file', blob, 'sample_attendees.csv');

      const res = await fetch(`${API}/contacts/upload`, { method: 'POST', body: fd });
      const data = await res.json();
      if (res.ok) {
        setUploadStats(data);
        toast.success(`Loaded 5 sample contacts (example.com) into your workspace.`);
        refreshPlaceholdersAndContacts();
      } else {
        toast.error(data.detail || 'Failed to load sample data');
      }
    } catch {
      toast.error('Network error loading sample data');
    } finally {
      setUploading(false);
    }
  };

  // Step 3: Call AI Copywriter
  const handleWriteForMe = async () => {
    setGenerating(true);
    setAiFallbackUsed(false);
    try {
      const res = await fetch(`${API}/ai/generate-campaign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal,
          instructions,
          placeholders: discoveredPlaceholders,
        }),
      });
      const data = await res.json();
      if (res.ok && data.subject && data.template) {
        setSubject(data.subject);
        setTemplate(data.template);
        if (data.fallback_used) {
          setAiFallbackUsed(true);
        }
        toast.success('Generated email subject and body!');
      } else {
        toast.error(data.detail || 'Failed to generate copy');
      }
    } catch {
      toast.error('Network error requesting AI copywriter');
    } finally {
      setGenerating(false);
    }
  };

  // Step 4: Quick Test Send
  const handleQuickTestSend = async () => {
    if (!testEmail) {
      toast.error('Please enter a test recipient email');
      return;
    }
    setSendingTest(true);
    setTestResult(null);
    try {
      const createRes = await fetch(`${API}/campaigns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: `${campName} (Test)`,
          subject,
          mode: 'same',
          template,
          provider: 'gmail',
        }),
      });
      const camp = await createRes.json();
      if (createRes.ok && camp.id) {
        const testRes = await fetch(`${API}/campaigns/${camp.id}/test-send`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ test_email: testEmail }),
        });
        const td = await testRes.json();
        if (testRes.ok && td.success) {
          toast.success(`Dispatched sample preview to ${testEmail}`);
          setTestResult(`Sent sample to ${testEmail}`);
        } else {
          const errMsg = td.detail || td.message || td.samples?.[0]?.error || 'Test send failed';
          toast.error(errMsg);
          setTestResult(errMsg);
        }
      }
    } catch {
      toast.error('Network error during test send');
    } finally {
      setSendingTest(false);
    }
  };

  // Step 4: Final Create Campaign
  const handleCreateCampaign = async () => {
    setCreatingCamp(true);
    try {
      const res = await fetch(`${API}/campaigns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: campName,
          subject,
          mode: 'same',
          template,
          provider: 'gmail',
        }),
      });
      const data = await res.json();
      if (res.ok && data.id) {
        toast.success(`Campaign "${data.name}" created in draft status!`);
        if (onCampaignCreated) onCampaignCreated(data.id);
        onNavigate('Campaign');
      } else {
        toast.error('Failed to create campaign');
      }
    } catch {
      toast.error('Network error creating campaign');
    } finally {
      setCreatingCamp(false);
    }
  };

  const renderSamplePreview = (contact) => {
    let text = template.replace('{name}', contact.name || 'there');
    if (contact.extra_data) {
      try {
        const extra = JSON.parse(contact.extra_data);
        Object.entries(extra).forEach(([k, v]) => {
          text = text.replace(new RegExp(`{${k}}`, 'g'), v);
        });
      } catch {}
    }
    return text;
  };

  const stepsMeta = [
    { num: 1, label: 'Upload CSV' },
    { num: 2, label: 'Goal & Prompt' },
    { num: 3, label: 'AI Copywriter' },
    { num: 4, label: 'Preview & Launch' },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="glass p-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] flex items-center justify-center text-[#0A0A0A] shadow-[0_0_15px_rgba(212,175,55,0.35)]">
            <Zap className="w-5 h-5 font-bold" />
          </div>
          <div>
            <h2 className="text-base font-bold text-[#F2D675] leading-tight">Quick Start Campaign</h2>
            <p className="text-xs text-[#A59F8F]">Go from CSV to a verified, ready-to-launch campaign in about 60 seconds.</p>
          </div>
        </div>
        <Badge variant="gold" className="text-[11px] font-semibold">
          Step {step} of 4
        </Badge>
      </div>

      {/* Step Indicators */}
      <div className="grid grid-cols-4 gap-2">
        {stepsMeta.map((s) => (
          <button
            key={s.num}
            type="button"
            onClick={() => setStep(s.num)}
            className={`p-3 rounded-xl border text-left transition-colors cursor-pointer ${
              step === s.num
                ? 'bg-[#1A1A1A] border-[#D4AF37] text-[#F2D675] shadow-[0_0_15px_rgba(212,175,55,0.15)]'
                : step > s.num
                ? 'bg-[#121212] border-[rgba(212,175,55,0.25)] text-[#F5F1E6]'
                : 'bg-[#121212]/50 border-[rgba(212,175,55,0.12)] text-[#A59F8F]/60'
            }`}
          >
            <div className="text-[10px] font-bold uppercase tracking-wider mb-0.5 flex items-center gap-1.5">
              {step > s.num ? (
                <Check className="w-3 h-3 text-[#3DDC97]" />
              ) : (
                <span>Step {s.num}</span>
              )}
            </div>
            <div className="text-xs font-semibold truncate">{s.label}</div>
          </button>
        ))}
      </div>

      {/* Step 1: Upload CSV / Sample Contacts */}
      {step === 1 && (
        <motion.div
          initial={prefersReduced ? {} : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass p-6 space-y-5"
        >
          <div>
            <h3 className="text-sm font-semibold text-[#F2D675] mb-1">Step 1: Provide Your Contact List</h3>
            <p className="text-xs text-[#A59F8F]">
              Upload your CSV file containing <code className="text-[#F2D675] bg-[#1A1A1A] border border-[rgba(212,175,55,0.2)] px-1.5 py-0.5 rounded font-mono">name</code>, <code className="text-[#F2D675] bg-[#1A1A1A] border border-[rgba(212,175,55,0.2)] px-1.5 py-0.5 rounded font-mono">email</code>, or load 5 sample contacts with example.com addresses to test.
            </p>
          </div>

          <div className="p-5 rounded-xl border border-dashed border-[rgba(212,175,55,0.3)] bg-[#1A1A1A]/40 flex flex-col items-center justify-center space-y-3">
            <Upload className="w-8 h-8 text-[#D4AF37]" />
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="text-xs text-[#A59F8F] file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border file:border-[rgba(212,175,55,0.25)] file:text-xs file:font-medium file:bg-[#1A1A1A] file:text-[#F5F1E6] hover:file:bg-[#222222] cursor-pointer"
            />
            <div className="flex gap-2.5 pt-1">
              <Button
                variant="primary"
                size="sm"
                disabled={!file || uploading}
                onClick={handleUpload}
              >
                <Upload className="w-3.5 h-3.5 mr-1" />
                {uploading ? 'Uploading...' : 'Upload CSV'}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleLoadSampleData}
                disabled={uploading}
              >
                <Database className="w-3.5 h-3.5 mr-1 text-[#D4AF37]" />
                Load Sample Data (example.com)
              </Button>
            </div>
          </div>

          {uploadStats && (
            <div className="p-3.5 rounded-xl bg-[#3DDC97]/10 border border-[#3DDC97]/30 text-xs text-[#3DDC97] space-y-1">
              <div className="font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-[#3DDC97]" />
                Contacts Ready
              </div>
              <div className="text-[11px] text-[#F5F1E6]">
                Added: <strong className="text-[#3DDC97]">{uploadStats.added}</strong> • Duplicates: <strong className="text-[#FF9F43]">{uploadStats.duplicates}</strong> • Invalid: <strong className="text-[#FF5C5C]">{uploadStats.invalid}</strong>
              </div>
            </div>
          )}

          <div className="flex justify-end pt-3 border-t border-[rgba(212,175,55,0.18)]">
            <Button variant="primary" size="sm" onClick={() => setStep(2)}>
              Next: Define Goal <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </div>
        </motion.div>
      )}

      {/* Step 2: Goal & What to Say */}
      {step === 2 && (
        <motion.div
          initial={prefersReduced ? {} : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass p-6 space-y-5"
        >
          <div>
            <h3 className="text-sm font-semibold text-[#F2D675] mb-1">Step 2: Choose Goal & Enter Details</h3>
            <p className="text-xs text-[#A59F8F]">Pick the intent of the message and enter 1-2 lines detailing what you want to communicate.</p>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1.5">Campaign Name</label>
            <Input
              value={campName}
              onChange={(e) => setCampName(e.target.value)}
              placeholder="e.g. October Product Launch"
              className="text-xs bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1.5">Email Goal</label>
            <div className="grid grid-cols-3 gap-3">
              {['Announce / invite', 'Reminder', 'Follow-up'].map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => setGoal(g)}
                  className={`p-3 rounded-xl border text-xs font-medium text-left transition-colors cursor-pointer ${
                    goal === g
                      ? 'border-[#D4AF37] bg-[#1A1A1A] text-[#F2D675] font-semibold shadow-[0_0_12px_rgba(212,175,55,0.2)]'
                      : 'border-[rgba(212,175,55,0.18)] bg-[#141414] hover:bg-[#1A1A1A] text-[#A59F8F]'
                  }`}
                >
                  {g}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">
              What should the email say? (1-2 lines)
            </label>
            <Textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="e.g. Announce our upcoming event on Friday. Mention that registration includes free entry and coffee."
              className="text-xs font-sans leading-relaxed bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
            />
            <p className="text-[11px] text-[#A59F8F]/70 mt-1">
              Safety rule: The AI copywriter will strictly use only the facts you type here and will never hallucinate unmentioned dates, prices, or links.
            </p>
          </div>

          <div className="flex justify-between pt-3 border-t border-[rgba(212,175,55,0.18)]">
            <Button variant="outline" size="sm" onClick={() => setStep(1)}>
              <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back
            </Button>
            <Button variant="primary" size="sm" onClick={() => setStep(3)}>
              Next: Generate Copy <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </div>
        </motion.div>
      )}

      {/* Step 3: AI Copywriter & Editable Template */}
      {step === 3 && (
        <motion.div
          initial={prefersReduced ? {} : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass p-6 space-y-5"
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-[#F2D675] mb-1">Step 3: Review & Edit Email Copy</h3>
              <p className="text-xs text-[#A59F8F]">
                Click "Write it for me" to draft the copy using your configured AI provider, or freely tweak the text below.
              </p>
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={handleWriteForMe}
              disabled={generating}
              className="text-xs"
            >
              <Sparkles className={`w-3.5 h-3.5 mr-1.5 ${generating ? 'animate-spin' : ''}`} />
              {generating ? 'Drafting copy...' : 'Write it for me'}
            </Button>
          </div>

          {aiFallbackUsed && (
            <div className="p-3 rounded-xl bg-[#FF9F43]/10 border border-[#FF9F43]/30 text-xs text-[#FF9F43]">
              Note: Clean default template applied (AI API key not configured or temporarily busy).
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">Subject Line</label>
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="text-xs bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A59F8F] mb-1">
              Email Body (Editable Template)
            </label>
            <Textarea
              rows={7}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              className="text-xs font-sans leading-relaxed bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              required
            />
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-[#A59F8F] mr-1">Insert variables:</span>
              {discoveredPlaceholders.map((ph) => (
                <button
                  key={ph}
                  type="button"
                  onClick={() => setTemplate((prev) => prev + `{${ph}}`)}
                  className="px-2 py-0.5 rounded text-[11px] font-mono bg-[#1A1A1A] text-[#F2D675] border border-[rgba(212,175,55,0.25)] hover:bg-[#222222] cursor-pointer"
                >
                  +{`{${ph}}`}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-between pt-3 border-t border-[rgba(212,175,55,0.18)]">
            <Button variant="outline" size="sm" onClick={() => setStep(2)}>
              <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back
            </Button>
            <Button variant="primary" size="sm" onClick={() => setStep(4)}>
              Next: Preview & Launch <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </div>
        </motion.div>
      )}

      {/* Step 4: Preview First 3, Test Send, & Create Draft Campaign */}
      {step === 4 && (
        <motion.div
          initial={prefersReduced ? {} : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass p-6 space-y-5"
        >
          <div>
            <h3 className="text-sm font-semibold text-[#F2D675] mb-1">Step 4: Preview Mails & Launch</h3>
            <p className="text-xs text-[#A59F8F]">
              Verify how the email renders for real sample recipients, send a test email to your inbox, then save as a ready campaign draft.
            </p>
          </div>

          {/* Rendered Preview of First 3 Contacts */}
          <div>
            <h4 className="text-xs font-semibold text-[#F2D675] mb-2 flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5 text-[#D4AF37]" />
              Preview First 3 Contacts
            </h4>
            {sampleContacts.length === 0 ? (
              <EmptyState
                icon={Users}
                title="No sample contacts found"
                description="Upload contacts in Step 1 or load sample data to preview rendering."
              />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {sampleContacts.map((c, idx) => (
                  <div
                    key={c.id || idx}
                    className="glass p-3.5 text-xs space-y-1.5"
                  >
                    <div className="font-semibold text-[#F2D675] truncate">
                      To: {c.name} &lt;{c.email}&gt;
                    </div>
                    <div className="text-[11px] font-medium text-[#D4AF37] truncate">
                      Subject: {subject}
                    </div>
                    <div className="text-[#F5F1E6] whitespace-pre-wrap leading-relaxed text-[11px] pt-1 border-t border-[rgba(212,175,55,0.12)] max-h-36 overflow-y-auto">
                      {renderSamplePreview(c)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Send Test Email Box */}
          <div className="glass p-4 space-y-2">
            <h4 className="text-xs font-semibold text-[#F2D675]">Send Test Email</h4>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="test@example.com"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                className="text-xs max-w-sm bg-[#121212] border-[rgba(212,175,55,0.22)] text-[#F5F1E6]"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={handleQuickTestSend}
                disabled={sendingTest}
              >
                <Send className="w-3 h-3 mr-1" />
                {sendingTest ? 'Sending...' : 'Send Test Mail'}
              </Button>
            </div>
            {testResult && (
              <div className="text-[11px] text-[#F2D675] font-mono bg-[#121212] p-2 rounded-lg border border-[rgba(212,175,55,0.2)]">
                {testResult}
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex justify-between items-center pt-3 border-t border-[rgba(212,175,55,0.18)]">
            <Button variant="outline" size="sm" onClick={() => setStep(3)}>
              <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleCreateCampaign}
              disabled={creatingCamp}
            >
              <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
              {creatingCamp ? 'Creating Campaign...' : 'Create Campaign (Draft)'}
            </Button>
          </div>
        </motion.div>
      )}
    </div>
  );
}
