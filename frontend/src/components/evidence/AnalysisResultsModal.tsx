import React, { useState } from 'react';
import {
  Binary,
  Layers,
  Database,
  Shield,
  FileCheck,
  Cpu,
  Copy,
  Check,
  AlertCircle,
  Terminal,
} from 'lucide-react';
import type { JobDetailResponse } from '../../types';
import { Modal } from '../common/Modal';
import { Badge } from '../common/Badge';

interface AnalysisResultsModalProps {
  isOpen: boolean;
  onClose: () => void;
  job: JobDetailResponse | null;
  artifactName?: string;
  artifactFormat?: string;
}

export const AnalysisResultsModal: React.FC<AnalysisResultsModalProps> = ({
  isOpen,
  onClose,
  job,
  artifactName = 'Software Artifact',
  artifactFormat,
}) => {
  const [activeTab, setActiveTab] = useState<'summary' | 'raw_evidence'>('summary');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (!job) return null;

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const summary = job.summary || {};
  const technologies = summary.technologies || [];
  const imports = summary.imports || [];
  const resources = summary.resources || [];
  const certificates = summary.certificates || [];
  const compilerInfo = summary.compiler_info || {};

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success" dot>Completed</Badge>;
      case 'partial':
        return <Badge variant="warning" dot>Partial Findings</Badge>;
      case 'running':
        return <Badge variant="indigo" dot>Analyzing ({job.progress_percent}%)</Badge>;
      case 'queued':
        return <Badge variant="neutral" dot>Queued</Badge>;
      case 'failed':
        return <Badge variant="error" dot>Failed</Badge>;
      case 'cancelled':
        return <Badge variant="neutral">Cancelled</Badge>;
      default:
        return <Badge variant="neutral">{status}</Badge>;
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Analysis Results: ${artifactName}`}
      description={`Job ID: ${job.id}`}
      maxWidth="xl"
    >
      <div className="space-y-4">
        {/* Top Header Card */}
        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-950/60 border border-indigo-800/50 flex items-center justify-center text-indigo-400">
              <Binary className="w-4 h-4" />
            </div>
            <div>
              <div className="font-semibold text-slate-100 flex items-center gap-2">
                <span>{artifactName}</span>
                {artifactFormat && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-950 text-indigo-300 border border-indigo-800/40 uppercase">
                    {artifactFormat}
                  </span>
                )}
              </div>
              <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                Current Step: {job.current_step}
              </div>
            </div>
          </div>
          <div>{getStatusBadge(job.status)}</div>
        </div>

        {/* Error Notice */}
        {job.error_message && (
          <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Notice: </span>
              {job.error_message}
            </div>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-[#1b2334] pb-1 text-xs">
          <button
            onClick={() => setActiveTab('summary')}
            className={`px-3 py-1.5 rounded-t-lg font-medium transition-colors flex items-center gap-1.5 ${
              activeTab === 'summary'
                ? 'text-indigo-400 border-b-2 border-indigo-500 bg-indigo-950/20'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-3.5 h-3.5" /> Normalized Findings
          </button>
          <button
            onClick={() => setActiveTab('raw_evidence')}
            className={`px-3 py-1.5 rounded-t-lg font-medium transition-colors flex items-center gap-1.5 ${
              activeTab === 'raw_evidence'
                ? 'text-indigo-400 border-b-2 border-indigo-500 bg-indigo-950/20'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Terminal className="w-3.5 h-3.5" /> Raw Evidence Records ({job.evidence_records.length})
          </button>
        </div>

        {/* Tab 1: Findings Summary */}
        {activeTab === 'summary' && (
          <div className="space-y-4 max-h-[460px] overflow-y-auto pr-1">
            {/* Technologies */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                <Cpu className="w-3 h-3 text-cyan-400" /> Detected Technologies
              </span>
              <div className="p-3 rounded-xl bg-[#0b101c] border border-[#1e2638] flex flex-wrap gap-1.5">
                {technologies.length > 0 ? (
                  technologies.map((t: string) => (
                    <span
                      key={t}
                      className="px-2 py-0.5 rounded-md text-xs font-mono bg-indigo-950/60 border border-indigo-800/50 text-indigo-300"
                    >
                      {t}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-500 italic">No specific framework indicators detected.</span>
                )}
              </div>
            </div>

            {/* Compiler & Tooling Info */}
            {Object.keys(compilerInfo).length > 0 && (
              <div className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  <FileCheck className="w-3 h-3 text-emerald-400" /> Compiler & Build Environment
                </span>
                <div className="p-3 rounded-xl bg-[#0b101c] border border-[#1e2638] font-mono text-xs text-slate-300 space-y-1">
                  {Object.entries(compilerInfo).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between">
                      <span className="text-slate-500">{k}:</span>
                      <span className="text-slate-200">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Dynamic Imports */}
            {imports.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  <Database className="w-3 h-3 text-indigo-400" /> Imported Dynamic Libraries ({imports.length})
                </span>
                <div className="rounded-xl border border-[#1e2638] overflow-hidden bg-[#0b101c]">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-slate-900/80 text-slate-400 border-b border-[#1e2638]">
                      <tr>
                        <th className="p-2.5">Library / DLL</th>
                        <th className="p-2.5">Functions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1b2334] text-slate-300">
                      {imports.slice(0, 10).map((imp: any, i: number) => (
                        <tr key={i} className="hover:bg-slate-900/40">
                          <td className="p-2.5 text-indigo-300 font-semibold">{imp.dll || imp.name || 'Unknown'}</td>
                          <td className="p-2.5 text-slate-400 text-[11px]">
                            {Array.isArray(imp.functions)
                              ? `${imp.functions.length} imported API(s)`
                              : 'Static import'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Embedded Resources */}
            {resources.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  <Layers className="w-3 h-3 text-amber-400" /> Embedded Resources ({resources.length})
                </span>
                <div className="p-3 rounded-xl bg-[#0b101c] border border-[#1e2638] text-xs font-mono space-y-1 text-slate-400">
                  {resources.slice(0, 5).map((r: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between">
                      <span className="text-slate-300">{r.type || r.name || `Resource #${idx + 1}`}</span>
                      <span>{r.size_bytes ? `${(r.size_bytes / 1024).toFixed(1)} KiB` : 'Embedded'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Authenticode Certificates */}
            {certificates.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  <Shield className="w-3 h-3 text-emerald-400" /> Digital Certificates
                </span>
                <div className="p-3 rounded-xl bg-[#0b101c] border border-[#1e2638] text-xs font-mono space-y-1.5">
                  {certificates.map((cert: any, i: number) => (
                    <div key={i} className="border-b border-slate-800 last:border-0 pb-1.5 last:pb-0">
                      <div className="text-slate-200 font-semibold">{cert.subject || 'Unknown Subject'}</div>
                      <div className="text-[11px] text-slate-400">Issuer: {cert.issuer || 'N/A'}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Raw Evidence Records */}
        {activeTab === 'raw_evidence' && (
          <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1">
            {job.evidence_records.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-500 font-mono">
                No raw evidence records generated for this job yet.
              </div>
            ) : (
              job.evidence_records.map((er) => {
                const jsonText = JSON.stringify(er.raw_evidence, null, 2);
                const isCopied = copiedId === er.id;
                return (
                  <div key={er.id} className="rounded-xl bg-[#0b101c] border border-[#1e2638] overflow-hidden text-xs">
                    <div className="p-2.5 bg-slate-900/80 border-b border-[#1e2638] flex items-center justify-between">
                      <div className="flex items-center gap-2 font-mono">
                        <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                        <span className="font-semibold text-slate-200">{er.tool_name}</span>
                        <span className="text-[10px] text-slate-500">({er.category})</span>
                      </div>
                      <button
                        onClick={() => handleCopy(jsonText, er.id)}
                        className="px-2 py-0.5 rounded text-[11px] font-mono text-slate-400 hover:text-slate-200 hover:bg-slate-800 flex items-center gap-1 transition-colors"
                      >
                        {isCopied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                        <span>{isCopied ? 'Copied' : 'Copy JSON'}</span>
                      </button>
                    </div>
                    <pre className="p-3 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-56 bg-[#080c16]">
                      {jsonText}
                    </pre>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </Modal>
  );
};
