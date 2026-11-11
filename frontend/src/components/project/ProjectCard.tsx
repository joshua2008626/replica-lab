import React from 'react';
import { FolderGit2, Binary, Calendar, ChevronRight } from 'lucide-react';
import type { Project } from '../../types';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';

interface ProjectCardProps {
  project: Project;
  onSelect?: (project: Project) => void;
}

export const ProjectCard: React.FC<ProjectCardProps> = ({ project, onSelect }) => {
  const formattedDate = new Date(project.created_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <Card
      variant="interactive"
      className="flex flex-col justify-between h-full group"
      onClick={() => onSelect?.(project)}
    >
      <div>
        {/* Card Header: Icon + Name + Artifact Count */}
        <div className="flex items-start justify-between gap-3 mb-2.5">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-950/40 border border-indigo-800/40 flex items-center justify-center text-indigo-400 group-hover:border-indigo-600/50 transition-colors">
              <FolderGit2 className="w-4 h-4" />
            </div>
            <h4 className="font-semibold text-sm text-slate-100 group-hover:text-indigo-300 transition-colors line-clamp-1">
              {project.name}
            </h4>
          </div>
          <Badge variant={project.artifact_count > 0 ? 'indigo' : 'neutral'} size="sm">
            <Binary className="w-3 h-3" />
            <span>{project.artifact_count} {project.artifact_count === 1 ? 'artifact' : 'artifacts'}</span>
          </Badge>
        </div>

        {/* Description or Fallback */}
        <p className="text-xs text-slate-400 line-clamp-2 mb-4 leading-relaxed">
          {project.description || 'No description provided for this software workspace.'}
        </p>
      </div>

      {/* Footer: Date + Action Link */}
      <div className="pt-3 border-t border-[#1b2334] flex items-center justify-between text-[11px] text-slate-500">
        <span className="flex items-center gap-1 font-mono">
          <Calendar className="w-3 h-3 text-slate-500" />
          {formattedDate}
        </span>
        <span className="text-slate-400 group-hover:text-indigo-400 flex items-center gap-0.5 transition-colors font-medium">
          Open Workspace <ChevronRight className="w-3 h-3" />
        </span>
      </div>
    </Card>
  );
};
