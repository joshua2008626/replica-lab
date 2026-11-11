import React, { useState, useEffect } from 'react';
import {
  SearchCode,
  ShieldCheck,
  Database,
  Lock,
  Layers,
  FileCheck,
  FolderGit2,
  Terminal,
  Copy,
  Check,
  Search,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { EmptyState } from '../components/common/EmptyState';
import type { Project, EvidenceRecordResponse } from '../types';
import { fetchProjectJobs, fetchJobDetails } from '../services/jobService';

interface EvidencePageProps {
  projects: Project[];
  onNavigateProjects: () => void;
}

export const EvidencePage: React.FC<EvidencePageProps> = ({ projects, onNavigateProjects }) => {
  const [evidenceList, setEvidenceList] = useState<Array<EvidenceRecordResponse & { projectName: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const evidencePrinciples = [
    {
      title: 'Cryptographic Provenance',
      icon: <Lock className="w-4 h-4 text-emerald-400" />,
      description: 'Every uploaded file is hashed in 64 KiB chunks with SHA-256 upon arrival to ensure immutability.',
    },
    {
      title: 'Immutable Evidence Records',
      icon: <Database className="w-4 h-4 text-indigo-400" />,
      description: 'Findings from REA MCP tools are stored in dedicated SQLite evidence records without lossy truncation.',
    },
    {
      title: 'Compiler & Binary Signatures',
      icon: <FileCheck className="w-4 h-4 text-cyan-400" />,
      description: 'Identifies Go build info, Rust cargo-auditable markers, and PE security load configurations.',
    },
  ];

  useEffect(() => {
    let active = true;

    async function loadAllEvidence() {
      if (projects.length === 0) {
        if (active) setEvidenceList([]);
        return;
      }
      try {
        if (active) setLoading(true);
        const allRecords: Array<EvidenceRecordResponse & { projectName: string }> = [];

        for (const proj of projects) {
          try {
            const jobs = await fetchProjectJobs(proj.id);
            for (const job of jobs) {
              if (job.status === 'completed' || job.status === 'partial') {
                const details = await fetchJobDetails(job.id);
                if (details.evidence_records) {
                  for (const er of details.evidence_records) {
                    allRecords.push({ ...er, projectName: proj.name });
                  }
                }
              }
            }
          } catch {
            // Ignore offline or fetch errors per project
          }
        }
        if (active) setEvidenceList(allRecords);
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadAllEvidence();

    return () => {
      active = false;
    };
  }, [projects]);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const filteredEvidence = evidenceList.filter((e) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      e.tool_name.toLowerCase().includes(q) ||
      e.category.toLowerCase().includes(q) ||
      e.projectName.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="rounded-xl bg-[#0f1422] border border-[#1e2638] p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-950/60 text-indigo-300 border border-indigo-800/40 mb-2">
              <ShieldCheck className="w-3 h-3" /> IMMUTABLE AUDIT TRAIL
            </div>
            <h3 className="text-base font-semibold text-slate-100 mb-1">
              Evidence Explorer & Technical Findings
            </h3>
            <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
              When reverse engineering tasks complete, REPLICA LAB captures raw tool responses, parsed facts,
              and security indicators into an immutable SQLite ledger.
            </p>
          </div>
          <Badge variant="indigo" size="md">
            <span>Captured Records: {evidenceList.length}</span>
          </Badge>
        </div>
      </div>

      {/* Principles */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {evidencePrinciples.map((p) => (
          <Card key={p.title} className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-7 h-7 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center">
                {p.icon}
              </div>
              <h4 className="text-xs font-semibold text-slate-200">{p.title}</h4>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">{p.description}</p>
          </Card>
        ))}
      </div>

      {/* Evidence Ledger Section */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-indigo-400" /> Recorded Evidence Records ({filteredEvidence.length})
          </h4>

          {evidenceList.length > 0 && (
            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter by tool or category..."
                className="w-full pl-8 pr-3 py-1 text-xs bg-[#0f1422] border border-[#222c40] rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 font-mono"
              />
            </div>
          )}
        </div>

        {loading && evidenceList.length === 0 ? (
          <div className="py-12 flex flex-col items-center justify-center text-slate-500 text-xs">
            <span className="w-5 h-5 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mb-2" />
            <span>Scanning project ledgers for captured evidence...</span>
          </div>
        ) : evidenceList.length === 0 ? (
          <EmptyState
            icon={<SearchCode className="w-6 h-6" />}
            title="No Evidence Records Found"
            description="Evidence records are captured automatically as REA tools inspect quarantined artifacts. Start an analysis job in a project workspace to generate evidence."
            actionLabel="View Projects"
            actionIcon={<FolderGit2 className="w-4 h-4" />}
            onAction={onNavigateProjects}
          />
        ) : (
          <div className="space-y-3">
            {filteredEvidence.map((er) => {
              const jsonText = JSON.stringify(er.raw_evidence, null, 2);
              const isCopied = copiedId === er.id;
              return (
                <div key={er.id} className="rounded-xl bg-[#0f1422] border border-[#1e2638] overflow-hidden text-xs">
                  <div className="p-3 bg-slate-900/90 border-b border-[#1e2638] flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5 font-mono">
                      <Terminal className="w-4 h-4 text-indigo-400" />
                      <span className="font-semibold text-slate-200">{er.tool_name}</span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">
                        {er.category}
                      </span>
                      <span className="text-[11px] text-slate-500">Workspace: {er.projectName}</span>
                    </div>

                    <button
                      onClick={() => handleCopy(jsonText, er.id)}
                      className="px-2.5 py-1 rounded text-[11px] font-mono text-slate-400 hover:text-slate-200 hover:bg-slate-800 flex items-center gap-1.5 transition-colors border border-slate-800"
                    >
                      {isCopied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{isCopied ? 'Copied' : 'Copy Evidence JSON'}</span>
                    </button>
                  </div>
                  <pre className="p-3.5 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-56 bg-[#090d16]">
                    {jsonText}
                  </pre>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
