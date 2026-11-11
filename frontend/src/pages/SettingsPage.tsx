import React from 'react';
import { Settings } from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import type { SystemHealth } from '../types';

interface SettingsPageProps {
  health: SystemHealth | null;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ health }) => {
  const settingsRows = [
    {
      category: 'API Engine',
      items: [
        { label: 'Backend REST API', value: 'http://127.0.0.1:8000/api', status: health?.status || 'offline' },
        { label: 'Environment Mode', value: health?.environment || 'development', status: 'active' },
        { label: 'Service Version', value: health?.version || '0.1.0', status: 'verified' },
      ],
    },
    {
      category: 'REA MCP Transport',
      items: [
        { label: 'Target MCP Endpoint', value: 'http://127.0.0.1:8080/mcp', status: health?.components?.rea_mcp_engine || health?.components?.rea_mcp || 'offline' },
        { label: 'Protocol Transport', value: 'Streamable HTTP (JSON-RPC 2.0)', status: 'supported' },
        { label: 'Max Tool Response Limit', value: '10 MiB (Chunked Streaming)', status: 'enforced' },
      ],
    },
    {
      category: 'Concurrency & Security Controls',
      items: [
        { label: 'Max Concurrent Jobs', value: '2 simultaneous analyzers (Semaphore bounded)', status: 'active' },
        { label: 'Quarantine Payload Ceiling', value: '100 MiB (SHA-256 Digest Streamed)', status: 'enforced' },
        { label: 'Host Execution Policy', value: 'STRICT ZERO EXECUTION (Static telemetry only)', status: 'protected' },
        { label: 'Restart Recovery Policy', value: 'Fail interrupted jobs (No blind retries)', status: 'enforced' },
      ],
    },
  ];

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="rounded-xl bg-[#0f1422] border border-[#1e2638] p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-950/60 text-indigo-300 border border-indigo-800/40 mb-2">
              <Settings className="w-3 h-3" /> RUNTIME CONFIGURATION
            </div>
            <h3 className="text-base font-semibold text-slate-100 mb-1">
              Studio Environment Parameters
            </h3>
            <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
              System parameters, network endpoints, isolation ceilings, and concurrency boundaries
              governing the REPLICA LAB intelligence engine.
            </p>
          </div>
        </div>
      </div>

      {/* Settings Tables */}
      <div className="space-y-4">
        {settingsRows.map((section) => (
          <div key={section.category} className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {section.category}
            </h4>
            <Card className="p-0 overflow-hidden">
              <div className="divide-y divide-[#1b2334]">
                {section.items.map((item) => (
                  <div
                    key={item.label}
                    className="p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
                  >
                    <span className="text-slate-300 font-medium">{item.label}</span>
                    <div className="flex items-center gap-2.5">
                      <span className="font-mono text-slate-400 bg-slate-900/80 px-2 py-0.5 rounded border border-slate-800">
                        {item.value}
                      </span>
                      <Badge
                        variant={
                          item.status === 'healthy' || item.status === 'connected' || item.status === 'protected'
                            ? 'success'
                            : item.status === 'enforced' || item.status === 'active'
                            ? 'indigo'
                            : 'neutral'
                        }
                        size="sm"
                      >
                        {item.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        ))}
      </div>
    </div>
  );
};
