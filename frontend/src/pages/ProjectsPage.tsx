import React, { useState } from 'react';
import {
  FolderGit2,
  Plus,
  Search,
  Filter,
  RefreshCw,
  FolderPlus,
} from 'lucide-react';
import type { Project } from '../types';
import { Button } from '../components/common/Button';
import { ProjectCard } from '../components/project/ProjectCard';
import { EmptyState } from '../components/common/EmptyState';

interface ProjectsPageProps {
  projects: Project[];
  loading: boolean;
  onRefresh: () => void;
  onOpenCreateProject: () => void;
  onSelectProject: (project: Project) => void;
}

export const ProjectsPage: React.FC<ProjectsPageProps> = ({
  projects,
  loading,
  onRefresh,
  onOpenCreateProject,
  onSelectProject,
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredProjects = projects.filter((p) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      p.name.toLowerCase().includes(q) ||
      (p.description && p.description.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header Controls: Search + Refresh + New Project */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search workspaces by name or keywords..."
            className="w-full pl-9 pr-3.5 py-1.5 text-xs bg-[#0f1422] border border-[#222c40] rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/40 transition-colors font-mono"
          />
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            loading={loading}
            icon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={onOpenCreateProject}
            icon={<Plus className="w-3.5 h-3.5" />}
          >
            New Project
          </Button>
        </div>
      </div>

      {/* Projects Grid or Honest Empty State */}
      {filteredProjects.length === 0 ? (
        projects.length === 0 ? (
          <EmptyState
            icon={<FolderGit2 className="w-6 h-6" />}
            title="No Workspaces Available"
            description="Your studio does not have any project workspaces yet. Create a workspace to begin organizing software targets and analysis jobs."
            actionLabel="Create First Project"
            actionIcon={<FolderPlus className="w-4 h-4" />}
            onAction={onOpenCreateProject}
          />
        ) : (
          <EmptyState
            icon={<Filter className="w-6 h-6" />}
            title="No Matching Workspaces"
            description={`No project workspaces match your search query "${searchQuery}".`}
            actionLabel="Clear Filter"
            onAction={() => setSearchQuery('')}
          />
        )
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredProjects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onSelect={onSelectProject}
            />
          ))}
        </div>
      )}
    </div>
  );
};
