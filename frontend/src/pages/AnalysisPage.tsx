import React, { useState, useEffect, useCallback } from 'react';
import {
  Binary,
  Cpu,
  Layers,
  FolderGit2,
  Clock,
  XCircle,
  RefreshCw,
  Eye,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { EmptyState } from '../components/common/EmptyState';
import { AnalysisResultsModal } from '../components/evidence/AnalysisResultsModal';
import type { Project, AnalysisJob, JobDetailResponse } from '../types';
import { fetchProjectJobs, cancelJob, fetchJobDetails } from '../services/jobService';

interface AnalysisPageProps {
  projects: Project[];
  onNavigateProjects: () => void;
  onSelectProject?: (project: Project) => void;
}

export const AnalysisPage: React.FC<AnalysisPageProps> = ({
  projects,
  onNavigateProjects,
}) => {
  const [allJobs, setAllJobs] = useState<AnalysisJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedJobDetails, setSelectedJobDetails] = useState<JobDetailResponse | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Verified REA Tool Mappings
  const verifiedToolMappings = [
    {
      format: 'PE Binary (.exe, .dll)',
      tools: ['inspect_pe_imports', 'inspect_pe_resources', 'inspect_pe_certificates'],
      description: 'Extracts imported dynamic libraries, Win32 embedded resources, and digital signature certificates.',
    },
    {
      format: 'SQLite Database (.db, .sqlite)',
      tools: ['inspect_sqlite_database'],
      description: 'Introspects table schemas, indices, record counts, and internal database structures.',
    },
    {
      format: 'GGUF Neural Models (.gguf)',
      tools: ['inspect_model_artifact'],
      description: 'Extracts model architecture tensors, hyperparameter metadata, and quantization formats.',
    },
    {
      format: 'JavaScript Application (.js)',
      tools: ['analyze_javascript_application'],
      description: 'Dispatches AST parser with strict input_path schema to inspect module exports and native boundaries.',
    },
    {
      format: 'Electron ASAR (.asar)',
      tools: ['analyze_javascript_application'],
      description: 'Dispatches targeted JavaScript route when structural ASAR headers are verified.',
    },
  ];

  // Fetch jobs for all projects
  const loadAllJobs = useCallback(async () => {
    if (projects.length === 0) {
      setAllJobs([]);
      return;
    }
    try {
      setLoading(true);
      const jobsPerProject = await Promise.allSettled(
        projects.map((p) => fetchProjectJobs(p.id))
      );
      const aggregated: AnalysisJob[] = [];
      for (const res of jobsPerProject) {
        if (res.status === 'fulfilled') {
          aggregated.push(...res.value);
        }
      }
      aggregated.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setAllJobs(aggregated);
    } catch {
      // Backend offline
    } finally {
      setLoading(false);
    }
  }, [projects]);

  // Initial job sync and project changes
  useEffect(() => {
    let active = true;

    async function syncJobs() {
      if (projects.length === 0) {
        if (active) setAllJobs([]);
        return;
      }
      try {
        if (active) setLoading(true);
        const jobsPerProject = await Promise.allSettled(
          projects.map((p) => fetchProjectJobs(p.id))
        );
        const aggregated: AnalysisJob[] = [];
        for (const res of jobsPerProject) {
          if (res.status === 'fulfilled') {
            aggregated.push(...res.value);
          }
        }
        aggregated.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        if (active) setAllJobs(aggregated);
      } catch {
        // Backend offline
      } finally {
        if (active) setLoading(false);
      }
    }

    void syncJobs();

    return () => {
      active = false;
    };
  }, [projects]);

  // Polling if any active
  useEffect(() => {
    const hasActive = allJobs.some((j) => j.status === 'queued' || j.status === 'running');
    if (!hasActive) return;

    const interval = setInterval(() => {
      loadAllJobs();
    }, 1500);

    return () => clearInterval(interval);
  }, [allJobs, loadAllJobs]);

  // Cancel job
  const handleCancel = async (jobId: string) => {
    try {
      await cancelJob(jobId);
      await loadAllJobs();
    } catch {
      // Ignore
    }
  };

  // View details
  const handleViewDetails = async (job: AnalysisJob) => {
    try {
      const details = await fetchJobDetails(job.id);
      setSelectedJobDetails(details);
      setIsModalOpen(true);
    } catch {
      // Error
    }
  };

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Overview Banner */}
      <div className="rounded-xl bg-[#0f1422] border border-[#1e2638] p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-950/60 text-indigo-300 border border-indigo-800/40 mb-2">
              <Cpu className="w-3 h-3" /> DETERMINISTIC ENGINE DISPATCHER
            </div>
            <h3 className="text-base font-semibold text-slate-100 mb-1">
              REA Tool Dispatch Pipeline
            </h3>
            <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
              When software artifacts are analyzed, REPLICA LAB validates the database record, enforces
              quarantine containment, inspects magic-bytes, and dispatches verified REA MCP tools over Streamable HTTP.
            </p>
          </div>
          <Badge variant="indigo" size="md">
            <span>Bounded Concurrency: 2 Jobs</span>
          </Badge>
        </div>
      </div>

      {/* Verified Tools Matrix */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-cyan-400" /> Supported Formats & Verified REA Mappings
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {verifiedToolMappings.map((mapping) => (
            <Card key={mapping.format} className="p-4 flex flex-col justify-between">
              <div>
                <div className="font-semibold text-xs text-slate-200 mb-1 font-mono">
                  {mapping.format}
                </div>
                <p className="text-[11px] text-slate-400 mb-3 leading-relaxed">
                  {mapping.description}
                </p>
              </div>
              <div className="pt-2.5 border-t border-[#1b2334] space-y-1">
                <span className="text-[10px] text-slate-500 uppercase font-mono">Target Tools:</span>
                <div className="flex flex-wrap gap-1">
                  {mapping.tools.map((t) => (
                    <span
                      key={t}
                      className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-900 border border-slate-800 text-indigo-300"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* Active Jobs Queue */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-indigo-400" /> Analysis Execution Queue ({allJobs.length})
          </h4>
          <Button
            variant="ghost"
            size="sm"
            icon={<RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />}
            onClick={loadAllJobs}
          >
            Refresh
          </Button>
        </div>

        {allJobs.length === 0 ? (
          <EmptyState
            icon={<Binary className="w-6 h-6" />}
            title="No Active or Recent Analysis Jobs"
            description="Software analysis jobs are executed in the background via the Step 9 Job Runner. Select a project workspace to inspect artifacts and trigger analysis."
            actionLabel="Go to Projects"
            actionIcon={<FolderGit2 className="w-4 h-4" />}
            onAction={onNavigateProjects}
          />
        ) : (
          <div className="space-y-2">
            {allJobs.map((job) => {
              const isActive = job.status === 'queued' || job.status === 'running';
              return (
                <div
                  key={job.id}
                  className="p-3.5 rounded-xl bg-[#0f1422] border border-[#1e2638] flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-300 font-semibold">{job.current_step}</span>
                      <Badge
                        variant={
                          job.status === 'completed'
                            ? 'success'
                            : job.status === 'partial'
                            ? 'warning'
                            : job.status === 'running'
                            ? 'indigo'
                            : job.status === 'failed'
                            ? 'error'
                            : 'neutral'
                        }
                        size="sm"
                        dot={isActive}
                      >
                        {job.status}
                      </Badge>
                    </div>
                    <div className="text-[11px] text-slate-500">
                      Job ID: {job.id} · Artifact: {job.artifact_id}
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5">
                    {isActive && (
                      <div className="w-32 h-2 bg-slate-900 border border-slate-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 transition-all duration-200"
                          style={{ width: `${job.progress_percent}%` }}
                        />
                      </div>
                    )}
                    {job.status !== 'queued' && (
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={<Eye className="w-3 h-3" />}
                        onClick={() => handleViewDetails(job)}
                      >
                        Findings
                      </Button>
                    )}
                    {isActive && (
                      <Button
                        variant="danger"
                        size="sm"
                        icon={<XCircle className="w-3 h-3" />}
                        onClick={() => handleCancel(job.id)}
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <AnalysisResultsModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        job={selectedJobDetails}
      />
    </div>
  );
};
