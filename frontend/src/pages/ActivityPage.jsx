import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { TableSkeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { History, Download, RefreshCw, Search } from 'lucide-react';

export function ActivityPage({
  activity = [],
  filter = '',
  onFilterChange,
  onRefresh,
  API,
  loading = false,
}) {
  return (
    <div className="glass overflow-hidden">
      {/* Header / Filter Toolbar */}
      <div className="p-4 border-b border-[rgba(212,175,55,0.18)] flex flex-wrap items-center justify-between gap-3 bg-[#1A1A1A]/40">
        <div className="relative w-full max-w-xs">
          <Search className="w-3.5 h-3.5 text-[#A59F8F] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <Input
            type="text"
            placeholder="Filter by contact email..."
            className="pl-8 text-xs h-8 bg-[#1A1A1A] border-[rgba(212,175,55,0.22)] text-[#F5F1E6] focus:border-[#D4AF37]"
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-2">
          <a
            href={`${API}/activity/export${filter ? `?contact_email=${encodeURIComponent(filter)}` : ''}`}
            download
            className="inline-flex items-center justify-center font-medium transition-colors cursor-pointer text-xs px-2.5 py-1.5 rounded-md gap-1.5 border border-[rgba(212,175,55,0.25)] bg-[#1A1A1A] text-[#F5F1E6] hover:bg-[#222222] hover:border-[#D4AF37]"
          >
            <Download className="w-3.5 h-3.5 text-[#D4AF37]" />
            Download CSV
          </a>
          <Button variant="outline" size="sm" onClick={onRefresh}>
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Table / Skeleton / Empty */}
      {loading ? (
        <TableSkeleton rows={8} cols={4} />
      ) : activity.length === 0 ? (
        <div className="p-8">
          <EmptyState
            icon={History}
            title={filter ? 'No activity matching filter' : 'No activity logged yet'}
            description={filter ? 'Try clearing the contact email filter.' : 'Auditable log events like sends, replies, and edits will appear here.'}
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#1A1A1A]/80 border-b border-[rgba(212,175,55,0.2)] text-[#A59F8F] uppercase tracking-wider text-[10px]">
              <tr>
                <th className="py-2.5 px-4 font-semibold text-[#D4AF37] w-24">Time</th>
                <th className="py-2.5 px-4 font-semibold text-[#D4AF37] w-36">Action</th>
                <th className="py-2.5 px-4 font-semibold text-[#D4AF37] w-48">Contact</th>
                <th className="py-2.5 px-4 font-semibold text-[#D4AF37]">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgba(212,175,55,0.1)]">
              {activity.map((a) => (
                <tr key={a.id} className="hover:bg-[#1A1A1A]/50 transition-colors">
                  <td className="py-2.5 px-4 text-[#A59F8F] font-mono whitespace-nowrap text-[11px]">
                    {new Date(a.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </td>
                  <td className="py-2.5 px-4 font-medium text-[#F5F1E6]">
                    <span className="inline-block px-1.5 py-0.5 rounded bg-[#1A1A1A] text-[#F2D675] text-[11px] border border-[rgba(212,175,55,0.25)] font-mono">
                      {a.action}
                    </span>
                  </td>
                  <td className="py-2.5 px-4 text-[#F5F1E6] font-medium truncate max-w-[200px]">
                    {a.contact_email || '—'}
                  </td>
                  <td className="py-2.5 px-4 text-[#A59F8F] leading-relaxed max-w-md truncate">
                    {a.details}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
