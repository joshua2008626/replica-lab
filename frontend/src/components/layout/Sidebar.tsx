import React from 'react';
import {
  LayoutDashboard,
  FolderGit2,
  Binary,
  SearchCode,
  Network,
  Settings,
  ShieldCheck,
  ChevronRight,
  Terminal,
} from 'lucide-react';
import type { NavigationTab } from '../../types';

interface SidebarProps {
  currentTab: NavigationTab;
  onTabChange: (tab: NavigationTab) => void;
  isOpen: boolean;
  onCloseMobile: () => void;
}

interface NavItem {
  id: NavigationTab;
  label: string;
  icon: React.ReactNode;
  tag?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onTabChange,
  isOpen,
  onCloseMobile,
}) => {
  const navItems: NavItem[] = [
    { id: 'overview', label: 'Overview', icon: <LayoutDashboard className="w-4 h-4" /> },
    { id: 'projects', label: 'Projects', icon: <FolderGit2 className="w-4 h-4" /> },
    { id: 'analysis', label: 'Software Analysis', icon: <Binary className="w-4 h-4" /> },
    { id: 'evidence', label: 'Evidence Explorer', icon: <SearchCode className="w-4 h-4" /> },
    { id: 'architecture', label: 'Architecture', icon: <Network className="w-4 h-4" /> },
    { id: 'settings', label: 'Settings', icon: <Settings className="w-4 h-4" /> },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={onCloseMobile}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed lg:static top-0 bottom-0 left-0 z-40 w-64 bg-[#090d16] border-r border-[#1a2233] flex flex-col transition-transform duration-200 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Branding Header */}
        <div className="h-16 px-5 border-b border-[#1a2233] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 font-bold shadow-inner">
              <Terminal className="w-4 h-4" />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-wide text-slate-100 flex items-center gap-1.5">
                REPLICA LAB
              </span>
              <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500 block">
                Software Intelligence
              </span>
            </div>
          </div>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-950/60 text-indigo-300 border border-indigo-800/40">
            v0.1
          </span>
        </div>

        {/* Navigation Items */}
        <div className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
          <div className="px-3 pb-2 text-[11px] font-semibold tracking-wider uppercase text-slate-500">
            Platform Studio
          </div>
          {navItems.map((item) => {
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  onTabChange(item.id);
                  onCloseMobile();
                }}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-indigo-600/15 text-indigo-300 border border-indigo-500/30'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <span className={isActive ? 'text-indigo-400' : 'text-slate-400'}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </div>
                {isActive && <ChevronRight className="w-3.5 h-3.5 text-indigo-400" />}
              </button>
            );
          })}
        </div>

        {/* Security & REA Engine Footer */}
        <div className="p-3 border-t border-[#1a2233] bg-[#0c111d]/70">
          <div className="rounded-lg p-2.5 bg-slate-900/80 border border-slate-800 text-[11px] space-y-1.5">
            <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
              <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
              <span>Static Engine Protected</span>
            </div>
            <p className="text-[10px] text-slate-500 leading-relaxed">
              Quarantined reverse engineering via REA MCP HTTP transport. Zero host execution.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
};
