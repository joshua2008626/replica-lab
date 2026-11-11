import React, { useState, useEffect, useCallback } from 'react';
import type { NavigationTab, Project, ProjectCreate, SystemHealth } from './types';
import { fetchSystemHealth } from './services/healthService';
import { fetchProjects, createProject } from './services/projectService';
import { Sidebar } from './components/layout/Sidebar';
import { TopNav } from './components/layout/TopNav';
import { CreateProjectModal } from './components/project/CreateProjectModal';

// Pages
import { OverviewPage } from './pages/OverviewPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { AnalysisPage } from './pages/AnalysisPage';
import { EvidencePage } from './pages/EvidencePage';
import { ArchitecturePage } from './pages/ArchitecturePage';
import { SettingsPage } from './pages/SettingsPage';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<NavigationTab>('overview');
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isCreateProjectOpen, setIsCreateProjectOpen] = useState(false);

  // Live Backend Health State
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  // Projects State
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  // Manual Health Refresh
  const loadHealth = useCallback(async () => {
    try {
      setHealthLoading(true);
      const data = await fetchSystemHealth();
      setHealth(data);
    } catch {
      setHealth({
        status: 'offline',
        project: 'REPLICA LAB',
        version: '0.1.0',
        environment: 'offline',
        uptime_seconds: 0,
        components: {
          database: 'disconnected',
          rea_mcp: 'unreachable',
        },
      });
    } finally {
      setHealthLoading(false);
    }
  }, []);

  // Manual Projects Refresh
  const loadProjects = useCallback(async () => {
    try {
      setProjectsLoading(true);
      const data = await fetchProjects();
      setProjects(data);
    } catch {
      setProjects([]);
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  // Initial Data Fetch & Periodic Health Polling
  useEffect(() => {
    let active = true;

    async function initialSync() {
      try {
        const [healthResult, projectsResult] = await Promise.allSettled([
          fetchSystemHealth(),
          fetchProjects(),
        ]);
        if (!active) return;

        if (healthResult.status === 'fulfilled') {
          setHealth(healthResult.value);
        } else {
          setHealth({
            status: 'offline',
            project: 'REPLICA LAB',
            version: '0.1.0',
            environment: 'offline',
            uptime_seconds: 0,
            components: {
              database: 'disconnected',
              rea_mcp: 'unreachable',
            },
          });
        }

        if (projectsResult.status === 'fulfilled') {
          setProjects(projectsResult.value);
        } else {
          setProjects([]);
        }
      } finally {
        if (active) {
          setHealthLoading(false);
          setProjectsLoading(false);
        }
      }
    }

    void initialSync();

    const interval = setInterval(() => {
      if (active) {
        void fetchSystemHealth()
          .then((data) => {
            if (active) setHealth(data);
          })
          .catch(() => {
            if (active) {
              setHealth({
                status: 'offline',
                project: 'REPLICA LAB',
                version: '0.1.0',
                environment: 'offline',
                uptime_seconds: 0,
                components: {
                  database: 'disconnected',
                  rea_mcp: 'unreachable',
                },
              });
            }
          });
      }
    }, 10000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  // Handle Project Creation
  const handleCreateProject = async (payload: ProjectCreate) => {
    const newProj = await createProject(payload);
    setProjects((prev) => [newProj, ...prev]);
    setSelectedProjectId(newProj.id);
    setCurrentTab('projects');
  };

  const handleSelectProject = (project: Project) => {
    setSelectedProjectId(project.id);
    setCurrentTab('projects');
  };

  const handleTabChange = (tab: NavigationTab) => {
    setCurrentTab(tab);
    if (tab === 'projects') {
      // Return to projects list if clicking Projects tab directly
      setSelectedProjectId(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col lg:flex-row antialiased selection:bg-indigo-600/30 selection:text-indigo-200">
      {/* Sidebar Navigation */}
      <Sidebar
        currentTab={currentTab}
        onTabChange={handleTabChange}
        isOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <TopNav
          currentTab={currentTab}
          health={health}
          healthLoading={healthLoading}
          onRefreshHealth={loadHealth}
          onOpenCreateProject={() => setIsCreateProjectOpen(true)}
          onToggleMobileSidebar={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
        />

        <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-7xl w-full mx-auto overflow-y-auto">
          {currentTab === 'overview' && (
            <OverviewPage
              projects={projects}
              health={health}
              onOpenCreateProject={() => setIsCreateProjectOpen(true)}
              onSelectProject={handleSelectProject}
              onNavigateTab={setCurrentTab}
            />
          )}

          {currentTab === 'projects' && (
            selectedProjectId ? (
              <ProjectDetailPage
                projectId={selectedProjectId}
                onBack={() => {
                  setSelectedProjectId(null);
                  void loadProjects();
                }}
                onProjectDeleted={(id) => {
                  setProjects((prev) => prev.filter((p) => p.id !== id));
                  setSelectedProjectId(null);
                }}
              />
            ) : (
              <ProjectsPage
                projects={projects}
                loading={projectsLoading}
                onRefresh={loadProjects}
                onOpenCreateProject={() => setIsCreateProjectOpen(true)}
                onSelectProject={handleSelectProject}
              />
            )
          )}

          {currentTab === 'analysis' && (
            <AnalysisPage
              projects={projects}
              onNavigateProjects={() => setCurrentTab('projects')}
            />
          )}

          {currentTab === 'evidence' && (
            <EvidencePage
              projects={projects}
              onNavigateProjects={() => setCurrentTab('projects')}
            />
          )}

          {currentTab === 'architecture' && <ArchitecturePage />}

          {currentTab === 'settings' && <SettingsPage health={health} />}
        </main>
      </div>

      {/* Create Project Modal */}
      <CreateProjectModal
        isOpen={isCreateProjectOpen}
        onClose={() => setIsCreateProjectOpen(false)}
        onSubmit={handleCreateProject}
      />
    </div>
  );
};

export default App;
