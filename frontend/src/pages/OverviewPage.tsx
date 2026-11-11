import React from 'react';
import {
  FolderGit2,
  Binary,
  ArrowUpRight,
  Plus,
  Terminal,
  Cpu,
  Shield,
  Layers,
} from 'lucide-react';
import type { Project, SystemHealth } from '../types';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { ProjectCard } from '../components/project/ProjectCard';
import { UploadArea } from '../components/upload/UploadArea';
import { EmptyState } from '../components/common/EmptyState';

interface OverviewPageProps {
  projects: Project[];
  health: SystemHealth | null;
  onOpenCreateProject: () => void;
  onSelectProject: (project: Project) => void;
  onNavigateTab: (tab: any) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  projects,
  health,
  onOpenCreateProject,
  onSelectProject,
  onNavigateTab,
}) => {
  const totalArtifacts = projects.reduce((acc, p) => acc + (p.artifact_count || 0), 0);
  const isHealthy = health?.status === 'healthy';

  const metrics = [
    {
      label: 'Project Workspaces',
      value: projects.length.toString(),
      icon: <FolderGit2 className="w-4 h-4 text-indigo-400" />,
      subtext: projects.length === 1 ? '1 active workspace' : `${projects.length} active workspaces`,
    },
    {
      label: 'Quarantined Artifacts',
      value: totalArtifacts.toString(),
      icon: <Binary className="w-4 h-4 text-cyan-400" />,
      subtext: 'SHA-256 verified files',
    },
    {
      label: 'Engine Subsystems',
      value: isHealthy ? 'Online' : 'Degraded',
      icon: <Cpu className="w-4 h-4 text-emerald-400" />,
      subtext: health ? `REA: ${health.components.rea_mcp_engine || health.components.rea_mcp}` : 'Connecting...',
    },
    {
      label: 'Analysis Isolation',
      value: 'Strict',
      icon: <Shield className="w-4 h-4 text-indigo-400" />,
      subtext: 'Zero host binary execution',
    },
  ];

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Studio Banner */}
      <div className="relative rounded-2xl bg-gradient-to-r from-[#12192c] via-[#0f1424] to-[#0d121f] border border-[#1e273a] p-6 md:p-8 overflow-hidden shadow-xl">
        <div className="relative z-10 max-w-2xl">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-indigo-950/60 border border-indigo-800/40 text-indigo-300 text-xs font-mono mb-3.5">
            <Terminal className="w-3.5 h-3.5" /> REPLICA LAB STUDIO
          </div>
          <h2 className="text-xl md:text-2xl font-bold text-slate-100 tracking-tight mb-2">
            AI-Powered Software Intelligence & Reverse Engineering
          </h2>
          <p className="text-xs md:text-sm text-slate-400 leading-relaxed mb-6">
            Inspect binaries, Electron packages, GGUF models, and compiled artifacts using the local
            REA engine. Reconstruct implementation details, extract compiler signatures, and trace technical facts.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              size="md"
              icon={<Plus className="w-4 h-4" />}
              onClick={onOpenCreateProject}
            >
              New Project Workspace
            </Button>
            <Button
              variant="outline"
              size="md"
              icon={<Layers className="w-4 h-4" />}
              onClick={() => onNavigateTab('projects')}
            >
              View All Projects
            </Button>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        {metrics.map((m) => (
          <Card key={m.label} className="p-4 md:p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400 font-medium">{m.label}</span>
              <div className="w-7 h-7 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center">
                {m.icon}
              </div>
            </div>
            <div className="text-xl md:text-2xl font-bold font-mono text-slate-100 mb-1">
              {m.value}
            </div>
            <div className="text-[11px] text-slate-500 font-mono">{m.subtext}</div>
          </Card>
        ))}
      </div>

      {/* Quick Upload Dropzone */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Binary className="w-3.5 h-3.5 text-indigo-400" /> Quick Artifact Quarantine
          </h3>
          <span className="text-[11px] text-slate-500 font-mono">Streamable 100 MiB limit</span>
        </div>
        <UploadArea onFileSelect={() => onOpenCreateProject()} />
      </div>

      {/* Recent Projects Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">Recent Project Workspaces</h3>
            <p className="text-xs text-slate-400">Recently created analysis containers</p>
          </div>
          {projects.length > 0 && (
            <button
              onClick={() => onNavigateTab('projects')}
              className="text-xs text-indigo-400 hover:text-indigo-300 font-medium flex items-center gap-1 transition-colors"
            >
              All Projects ({projects.length}) <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {projects.length === 0 ? (
          <EmptyState
            icon={<FolderGit2 className="w-6 h-6" />}
            title="No Software Projects Found"
            description="Create your first workspace to organize binaries, packages, and technical evidence."
            actionLabel="Create Workspace"
            actionIcon={<Plus className="w-4 h-4" />}
            onAction={onOpenCreateProject}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.slice(0, 3).map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onSelect={onSelectProject}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
