import React, { useState } from 'react';
import {
  Menu,
  Activity,
  Database,
  Cpu,
  RefreshCw,
  Plus,
  Radio,
} from 'lucide-react';
import type { NavigationTab, SystemHealth } from '../../types';
import { Button } from '../common/Button';

interface TopNavProps {
  currentTab: NavigationTab;
  health: SystemHealth | null;
  healthLoading: boolean;
  onRefreshHealth: () => void;
  onOpenCreateProject: () => void;
  onToggleMobileSidebar: () => void;
}

const tabTitles: Record<NavigationTab, { title: string; subtitle: string }> = {
  overview: { title: 'Studio Overview', subtitle: 'Global telemetry, project status, and reverse engineering pipeline' },
  projects: { title: 'Project Workspaces', subtitle: 'Software analysis containers and quarantined artifact repositories' },
  analysis: { title: 'Software Analysis Engine', subtitle: 'Targeted REA MCP multi-tool analysis dispatcher' },
  evidence: { title: 'Evidence Explorer', subtitle: 'Immutable raw findings, compiler signatures, and technical facts' },
  architecture: { title: 'System Architecture', subtitle: 'Interactive dependency graphs and reverse-engineered module flow' },
  settings: { title: 'Studio Settings', subtitle: 'REA runtime configuration, MCP endpoint endpoints, and concurrency limits' },
};

export const TopNav: React.FC<TopNavProps> = ({
  currentTab,
  health,
  healthLoading,
  onRefreshHealth,
  onOpenCreateProject,
  onToggleMobileSidebar,
}) => {
  const [showHealthDetails, setShowHealthDetails] = useState(false);
  const info = tabTitles[currentTab];

  const isHealthy = health?.status === 'healthy';
  const isDbConnected = health?.components?.database === 'connected';
  const reaStatus = health?.components?.rea_mcp_engine || health?.components?.rea_mcp || 'unknown';
  const isReaReachable = reaStatus === 'reachable';

  return (
    <header className="h-16 px-4 md:px-6 bg-[#090d16]/95 border-b border-[#1a2233] backdrop-blur sticky top-0 z-30 flex items-center justify-between gap-4">
      {/* Left: Mobile Toggle & Page Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleMobileSidebar}
          className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-sm md:text-base font-semibold text-slate-100 tracking-tight">
              {info.title}
            </h1>
            <span className="hidden sm:inline-block text-slate-600 font-mono text-xs">/</span>
            <span className="hidden sm:inline-block text-xs font-mono text-slate-400">
              {currentTab}
            </span>
          </div>
          <p className="hidden md:block text-[11px] text-slate-400 line-clamp-1">
            {info.subtitle}
          </p>
        </div>
      </div>

      {/* Right: Health Status Indicator & Actions */}
      <div className="flex items-center gap-3">
        {/* Backend Health Badge with Popover Toggle */}
        <div className="relative">
          <button
            onClick={() => setShowHealthDetails(!showHealthDetails)}
            className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              isHealthy
                ? 'bg-emerald-950/30 border-emerald-800/40 text-emerald-400 hover:bg-emerald-950/50'
                : 'bg-rose-950/30 border-rose-800/40 text-rose-400 hover:bg-rose-950/50'
            }`}
          >
            <span className="relative flex h-2 w-2">
              {isHealthy && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              )}
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  isHealthy ? 'bg-emerald-500' : 'bg-rose-500'
                }`}
              />
            </span>
            <span className="font-mono text-[11px]">
              {healthLoading ? 'Connecting...' : isHealthy ? 'API Connected' : 'API Offline'}
            </span>
          </button>

          {/* Health Details Dropdown */}
          {showHealthDetails && (
            <div className="absolute right-0 mt-2 w-72 rounded-xl bg-[#0f1422] border border-[#222c40] p-3.5 shadow-2xl z-50 text-xs text-slate-300 space-y-2.5 animate-fadeIn">
              <div className="flex items-center justify-between pb-2 border-b border-[#1b2334]">
                <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-indigo-400" /> Backend Telemetry
                </span>
                <button
                  onClick={onRefreshHealth}
                  disabled={healthLoading}
                  className="p-1 text-slate-400 hover:text-slate-200 rounded hover:bg-slate-800"
                  title="Refresh status"
                >
                  <RefreshCw className={`w-3 h-3 ${healthLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>

              <div className="space-y-2 text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 flex items-center gap-1">
                    <Radio className="w-3 h-3" /> Core Service:
                  </span>
                  <span className="font-mono text-emerald-400 font-medium">
                    {health?.project || 'FastAPI 0.1.0'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400 flex items-center gap-1">
                    <Database className="w-3 h-3" /> SQLite Storage:
                  </span>
                  <span
                    className={`font-mono font-medium ${
                      isDbConnected ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {health?.components?.database || 'disconnected'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400 flex items-center gap-1">
                    <Cpu className="w-3 h-3" /> REA MCP Engine:
                  </span>
                  <span
                    className={`font-mono font-medium ${
                      isReaReachable ? 'text-emerald-400' : 'text-amber-400'
                    }`}
                  >
                    {reaStatus}
                  </span>
                </div>

                {health?.uptime_seconds !== undefined && (
                  <div className="flex items-center justify-between pt-1 border-t border-[#1b2334] text-[10px] text-slate-500">
                    <span>Uptime:</span>
                    <span className="font-mono">{health.uptime_seconds}s</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Quick New Project Button */}
        <Button
          variant="primary"
          size="sm"
          icon={<Plus className="w-3.5 h-3.5" />}
          onClick={onOpenCreateProject}
        >
          New Project
        </Button>
      </div>
    </header>
  );
};
