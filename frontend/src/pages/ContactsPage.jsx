import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { StatusBadge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { TableSkeleton } from '@/components/ui/skeleton';
import { Upload, Download, RefreshCw, Users, Search } from 'lucide-react';

export function ContactsPage({
  contacts = [],
  search = '',
  onSearchChange,
  file,
  onFileChange,
  onUpload,
  uploading = false,
  onRefresh,
  API,
  loading = false,
}) {
  const filtered = contacts.filter((c) =>
    (c.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (c.email || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-5">
      {/* Upload Box */}
      <div className="glass p-5">
        <h3 className="text-sm font-semibold text-[#F2D675] mb-2 flex items-center gap-2">
          <Upload className="w-4 h-4 text-[#D4AF37]" />
          Upload Contacts
        </h3>
        <p className="text-xs text-[#A59F8F] mb-4">
          Upload a CSV file containing columns like{' '}
          <code className="text-[#F2D675] bg-[#1A1A1A] border border-[rgba(212,175,55,0.2)] px-1.5 py-0.5 rounded font-mono">name</code>,{' '}
          <code className="text-[#F2D675] bg-[#1A1A1A] border border-[rgba(212,175,55,0.2)] px-1.5 py-0.5 rounded font-mono">email</code>, and optional custom variables.
        </p>
        <form onSubmit={onUpload} className="flex flex-wrap items-center gap-3">
          <input
            id="csvIn"
            type="file"
            accept=".csv"
            onChange={(e) => onFileChange(e.target.files?.[0] || null)}
            className="text-xs text-[#A59F8F] file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border file:border-[rgba(212,175,55,0.25)] file:text-xs file:font-medium file:bg-[#1A1A1A] file:text-[#F5F1E6] hover:file:bg-[#222222] cursor-pointer"
          />
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={!file || uploading}
          >
            <Upload className="w-3.5 h-3.5 mr-1" />
            {uploading ? 'Uploading...' : 'Upload CSV'}
          </Button>
        </form>
      </div>

      {/* Contacts List Card */}
      <div className="glass overflow-hidden">
        {/* Header / Actions */}
        <div className="p-4 border-b border-[rgba(212,175,55,0.18)] flex flex-wrap items-center justify-between gap-3 bg-[#1A1A1A]/40">
          <div className="relative w-full max-w-xs">
            <Search className="w-3.5 h-3.5 text-[#A59F8F] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <Input
              type="text"
              placeholder="Search contacts..."
              className="pl-8 text-xs h-8 bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6] focus:border-[#D4AF37]"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <a
              href={`${API}/contacts/export`}
              download
              className="inline-flex items-center justify-center font-medium transition-colors cursor-pointer text-xs px-2.5 py-1.5 rounded-md gap-1.5 border border-[rgba(212,175,55,0.25)] bg-[#1A1A1A] text-[#F5F1E6] hover:bg-[#222222] hover:border-[#D4AF37]"
            >
              <Download className="w-3.5 h-3.5 text-[#D4AF37]" />
              Export CSV
            </a>
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Table / Loading / Empty */}
        {loading ? (
          <TableSkeleton rows={6} cols={4} />
        ) : filtered.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={Users}
              title={search ? 'No contacts match your search' : 'No contacts uploaded yet'}
              description={search ? 'Try clearing or modifying your search filter.' : 'Upload a CSV file above to populate contacts.'}
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#1A1A1A]/80 border-b border-[rgba(212,175,55,0.2)] text-[#A59F8F] uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="py-2.5 px-4 font-semibold text-[#D4AF37]">Name</th>
                  <th className="py-2.5 px-4 font-semibold text-[#D4AF37]">Email</th>
                  <th className="py-2.5 px-4 font-semibold text-[#D4AF37]">Group</th>
                  <th className="py-2.5 px-4 font-semibold text-[#D4AF37]">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(212,175,55,0.1)]">
                {filtered.map((c) => (
                  <tr key={c.id} className="hover:bg-[#1A1A1A]/50 transition-colors">
                    <td className="py-2.5 px-4 font-medium text-[#F5F1E6]">{c.name}</td>
                    <td className="py-2.5 px-4 text-[#A59F8F]">{c.email}</td>
                    <td className="py-2.5 px-4 text-[#A59F8F]">{c.group_tag || '—'}</td>
                    <td className="py-2.5 px-4">
                      <StatusBadge status={c.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
