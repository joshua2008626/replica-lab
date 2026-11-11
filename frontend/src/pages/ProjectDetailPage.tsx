import React, { useState, useEffect, useCallback } from 'react';
import {
  ArrowLeft,
  Binary,
  Trash2,
  Play,
  FileCode,
  Copy,
  Check,
  RefreshCw,
  XCircle,
  Clock,
  Layers,
  AlertTriangle,
} from 'lucide-react';
import type { Project, ArtifactSummary, AnalysisJob, JobDetailResponse } from '../types';
import { fetchProjectById, deleteProjectById } from '../services/projectService';
import { uploadArtifact } from '../services/uploadService';
import { triggerAnalysis, fetchProjectJobs, fetchJobDetails, cancelJob } from '../services/jobService';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { UploadArea } from '../components/upload/UploadArea';
import { AnalysisResultsModal } from '../components/evidence/AnalysisResultsModal';

interface ProjectDetailPageProps {
  projectId: string;
  onBack: () => void;
  onProjectDeleted: (projectId: string) => void;
}

export const ProjectDetailPage: React.FC<ProjectDetailPageProps> = ({
  projectId,
  onBack,
  onProjectDeleted,
}) => {
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [activeUploadProgress, setActiveUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Selected job for results modal
  const [selectedJobDetails, setSelectedJobDetails] = useState<JobDetailResponse | null>(null);
  const [selectedArtifactName, setSelectedArtifactName] = useState<string>('');
  const [selectedArtifactFormat, setSelectedArtifactFormat] = useState<string>('');
  const [isResultsModalOpen, setIsResultsModalOpen] = useState(false);

  // Clipboard copy state
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Load project details
  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchProjectById(projectId);
      setProject(data);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to load project details.');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  // Load project jobs
  const loadJobs = useCallback(async () => {
    try {
      const jobList = await fetchProjectJobs(projectId);
      setJobs(jobList);
    } catch {
      // Backend not running or offline
    }
  }, [projectId]);

  useEffect(() => {
    let active = true;

    async function init() {
      try {
        if (active) setLoading(true);
        const [projRes, jobsRes] = await Promise.allSettled([
          fetchProjectById(projectId),
          fetchProjectJobs(projectId),
        ]);
        if (!active) return;
        if (projRes.status === 'fulfilled') {
          setProject(projRes.value);
        } else {
          setActionError('Failed to load project details.');
        }
        if (jobsRes.status === 'fulfilled') {
          setJobs(jobsRes.value);
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void init();

    return () => {
      active = false;
    };
  }, [projectId]);

  // Live polling of jobs if any is queued or running
  useEffect(() => {
    const hasActiveJobs = jobs.some((j) => j.status === 'queued' || j.status === 'running');
    if (!hasActiveJobs) return;

    const interval = setInterval(() => {
      loadJobs();
    }, 1500);

    return () => clearInterval(interval);
  }, [jobs, loadJobs]);

  // Format file size
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
  };

  // Handle direct file upload to this project
  const handleUploadFile = async (file: File) => {
    try {
      setUploadError(null);
      setActiveUploadProgress(0);
      await uploadArtifact(projectId, file, (percent) => {
        setActiveUploadProgress(percent);
      });
      setActiveUploadProgress(null);
      await loadProject();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Failed to upload artifact.');
      setActiveUploadProgress(null);
    }
  };

  // Trigger analysis on artifact
  const handleTriggerAnalysis = async (artifactId: string) => {
    try {
      setActionError(null);
      await triggerAnalysis(projectId, artifactId);
      await loadJobs();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to launch analysis job.');
    }
  };

  // Cancel in-flight job
  const handleCancelJob = async (jobId: string) => {
    try {
      setActionError(null);
      await cancelJob(jobId);
      await loadJobs();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to cancel job.');
    }
  };

  // View findings for an artifact
  const handleViewFindings = async (artifact: ArtifactSummary) => {
    try {
      setActionError(null);
      // Find latest completed or active job for this artifact
      const relatedJob = jobs.find((j) => j.artifact_id === artifact.id);
      if (!relatedJob) return;

      const details = await fetchJobDetails(relatedJob.id);
      setSelectedJobDetails(details);
      setSelectedArtifactName(artifact.original_filename);
      setSelectedArtifactFormat(artifact.detected_format);
      setIsResultsModalOpen(true);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to load analysis findings.');
    }
  };

  // Delete project workspace
  const handleDeleteProject = async () => {
    if (!window.confirm(`Are you sure you want to permanently delete workspace "${project?.name}"? All associated quarantined artifacts will be purged.`)) {
      return;
    }
    try {
      await deleteProjectById(projectId);
      onProjectDeleted(projectId);
      onBack();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to delete project.');
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(text);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-slate-400 text-xs font-mono">
        <RefreshCw className="w-4 h-4 animate-spin mr-2" /> Loading project workspace telemetry...
      </div>
    );
  }

  if (!project) {
    return (
      <div className="p-8 text-center space-y-4">
        <h3 className="text-sm font-semibold text-slate-200">Project Workspace Not Found</h3>
        <Button variant="secondary" onClick={onBack} icon={<ArrowLeft className="w-4 h-4" />}>
          Back to Projects
        </Button>
      </div>
    );
  }

  const artifacts = project.artifacts || [];

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Top Header Bar */}
      <div className="flex items-start justify-between gap-4 pb-4 border-b border-[#1a2233]">
        <div className="flex items-start gap-3">
          <button
            onClick={onBack}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors mt-0.5"
            title="Back to all projects"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-lg md:text-xl font-bold text-slate-100">{project.name}</h2>
              <Badge variant="indigo" size="sm">
                <span>{artifacts.length} {artifacts.length === 1 ? 'artifact' : 'artifacts'}</span>
              </Badge>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl leading-relaxed">
              {project.description || 'No description provided for this software container.'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="danger"
            size="sm"
            icon={<Trash2 className="w-3.5 h-3.5" />}
            onClick={handleDeleteProject}
          >
            Delete Workspace
          </Button>
        </div>
      </div>

      {/* Action / Upload Error Notice */}
      {(actionError || uploadError) && (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{actionError || uploadError}</span>
          </div>
          <button
            onClick={() => {
              setActionError(null);
              setUploadError(null);
            }}
            className="text-rose-400 hover:text-rose-200 text-xs"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Artifact Quarantine Dropzone */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Binary className="w-3.5 h-3.5 text-indigo-400" /> Upload Artifact to this Workspace
        </h3>
        <UploadArea onFileSelect={handleUploadFile} />
        {activeUploadProgress !== null && (
          <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1.5 text-xs font-mono">
            <div className="flex items-center justify-between text-slate-300">
              <span>Streaming file to quarantine storage...</span>
              <span>{activeUploadProgress}%</span>
            </div>
            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-all duration-150"
                style={{ width: `${activeUploadProgress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Quarantined Artifacts Table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-cyan-400" /> Quarantined Software Artifacts ({artifacts.length})
          </h3>
          <Button variant="ghost" size="sm" icon={<RefreshCw className="w-3 h-3" />} onClick={loadProject}>
            Refresh
          </Button>
        </div>

        {artifacts.length === 0 ? (
          <Card className="p-8 text-center text-xs text-slate-500 font-mono">
            No software artifacts quarantined in this workspace yet. Drag and drop a binary or package above.
          </Card>
        ) : (
          <div className="rounded-xl border border-[#1e2638] overflow-hidden bg-[#0f1422]">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-900/90 text-slate-400 border-b border-[#1e2638]">
                <tr>
                  <th className="p-3">Artifact</th>
                  <th className="p-3">Detected Format</th>
                  <th className="p-3">File Size</th>
                  <th className="p-3">Cryptographic SHA-256</th>
                  <th className="p-3 text-right">Analysis Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1b2334] text-slate-300">
                {artifacts.map((art) => {
                  const matchingJob = jobs.find((j) => j.artifact_id === art.id);
                  const isAnalyzing = matchingJob?.status === 'queued' || matchingJob?.status === 'running';

                  return (
                    <tr key={art.id} className="hover:bg-slate-900/40 transition-colors">
                      <td className="p-3 font-semibold text-slate-100 flex items-center gap-2">
                        <FileCode className="w-4 h-4 text-indigo-400 shrink-0" />
                        <span className="truncate max-w-xs">{art.original_filename}</span>
                      </td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded text-[10px] uppercase font-mono bg-indigo-950/70 border border-indigo-800/40 text-indigo-300">
                          {art.detected_format}
                        </span>
                      </td>
                      <td className="p-3 text-slate-400">{formatFileSize(art.file_size_bytes)}</td>
                      <td className="p-3">
                        <button
                          onClick={() => copyToClipboard(art.sha256_hash)}
                          className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
                          title="Click to copy full SHA-256 hash"
                        >
                          <span className="font-mono">{art.sha256_hash.slice(0, 16)}...</span>
                          {copiedHash === art.sha256_hash ? (
                            <Check className="w-3 h-3 text-emerald-400" />
                          ) : (
                            <Copy className="w-3 h-3 text-slate-500" />
                          )}
                        </button>
                      </td>
                      <td className="p-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {matchingJob && matchingJob.status !== 'queued' && (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleViewFindings(art)}
                            >
                              Findings
                            </Button>
                          )}
                          <Button
                            variant="primary"
                            size="sm"
                            loading={isAnalyzing}
                            disabled={isAnalyzing}
                            icon={<Play className="w-3 h-3" />}
                            onClick={() => handleTriggerAnalysis(art.id)}
                          >
                            {isAnalyzing ? `Analyzing (${matchingJob?.progress_percent}%)` : 'Run Analysis'}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Analysis Jobs Execution Log */}
      {jobs.length > 0 && (
        <div className="space-y-3 pt-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-indigo-400" /> Analysis Execution Queue ({jobs.length})
          </h3>
          <div className="space-y-2">
            {jobs.map((job) => {
              const isActive = job.status === 'queued' || job.status === 'running';
              return (
                <div
                  key={job.id}
                  className="p-3.5 rounded-xl bg-[#0f1422] border border-[#1e2638] flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400 font-semibold">{job.current_step}</span>
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
                      ID: {job.id} · Created: {new Date(job.created_at).toLocaleTimeString()}
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {isActive && (
                      <div className="w-28 md:w-36 h-2 bg-slate-900 border border-slate-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 transition-all duration-200"
                          style={{ width: `${job.progress_percent}%` }}
                        />
                      </div>
                    )}
                    {isActive && (
                      <Button
                        variant="danger"
                        size="sm"
                        icon={<XCircle className="w-3 h-3" />}
                        onClick={() => handleCancelJob(job.id)}
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Analysis Results & Evidence Modal */}
      <AnalysisResultsModal
        isOpen={isResultsModalOpen}
        onClose={() => setIsResultsModalOpen(false)}
        job={selectedJobDetails}
        artifactName={selectedArtifactName}
        artifactFormat={selectedArtifactFormat}
      />
    </div>
  );
};
