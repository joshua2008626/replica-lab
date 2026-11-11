import React from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Network } from 'lucide-react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';

const initialNodes: Node[] = [
  {
    id: '1',
    position: { x: 50, y: 150 },
    data: { label: 'Target Software Artifact (PE, ELF, ASAR, SQLite, GGUF, JS)' },
    sourcePosition: Position.Right,
    style: {
      background: '#141c2e',
      color: '#e2e8f0',
      border: '1px solid #3b82f6',
      borderRadius: '10px',
      padding: '12px',
      fontSize: '12px',
      fontWeight: '600',
      width: 220,
    },
  },
  {
    id: '2',
    position: { x: 340, y: 150 },
    data: { label: 'Quarantine & Format Detection (SHA-256 Digest & Magic Bytes)' },
    targetPosition: Position.Left,
    sourcePosition: Position.Right,
    style: {
      background: '#141c2e',
      color: '#38bdf8',
      border: '1px solid #0284c7',
      borderRadius: '10px',
      padding: '12px',
      fontSize: '12px',
      fontWeight: '600',
      width: 230,
    },
  },
  {
    id: '3',
    position: { x: 640, y: 150 },
    data: { label: 'FastAPI Backend & Background Job Runner (Bounded Semaphore)' },
    targetPosition: Position.Left,
    sourcePosition: Position.Right,
    style: {
      background: '#141c2e',
      color: '#a855f7',
      border: '1px solid #7e22ce',
      borderRadius: '10px',
      padding: '12px',
      fontSize: '12px',
      fontWeight: '600',
      width: 230,
    },
  },
  {
    id: '4',
    position: { x: 940, y: 70 },
    data: { label: 'REA MCP Daemon (Streamable HTTP /mcp :8080)' },
    targetPosition: Position.Left,
    sourcePosition: Position.Bottom,
    style: {
      background: '#141c2e',
      color: '#34d399',
      border: '1px solid #059669',
      borderRadius: '10px',
      padding: '12px',
      fontSize: '12px',
      fontWeight: '600',
      width: 220,
    },
  },
  {
    id: '5',
    position: { x: 940, y: 240 },
    data: { label: 'SQLite Persistent Ledger (Jobs & EvidenceRecords)' },
    targetPosition: Position.Left,
    style: {
      background: '#141c2e',
      color: '#f59e0b',
      border: '1px solid #d97706',
      borderRadius: '10px',
      padding: '12px',
      fontSize: '12px',
      fontWeight: '600',
      width: 220,
    },
  },
];

const initialEdges: Edge[] = [
  { id: 'e1-2', source: '1', target: '2', animated: true, style: { stroke: '#3b82f6', strokeWidth: 2 } },
  { id: 'e2-3', source: '2', target: '3', animated: true, style: { stroke: '#38bdf8', strokeWidth: 2 } },
  { id: 'e3-4', source: '3', target: '4', animated: true, style: { stroke: '#a855f7', strokeWidth: 2 } },
  { id: 'e3-5', source: '3', target: '5', style: { stroke: '#f59e0b', strokeWidth: 2 } },
  { id: 'e4-5', source: '4', target: '5', animated: true, style: { stroke: '#10b981', strokeWidth: 2 } },
];

export const ArchitecturePage: React.FC = () => {
  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="rounded-xl bg-[#0f1422] border border-[#1e2638] p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-950/60 text-indigo-300 border border-indigo-800/40 mb-2">
              <Network className="w-3 h-3" /> PIPELINE ARCHITECTURE
            </div>
            <h3 className="text-base font-semibold text-slate-100 mb-1">
              Software Intelligence Flow Diagram
            </h3>
            <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
              Interactive node topology representing the quarantine, static magic-byte inspection,
              Streamable HTTP MCP daemon communication, and persistent evidence ledger.
            </p>
          </div>
          <Badge variant="cyan" size="md">
            <span>React Flow v12</span>
          </Badge>
        </div>
      </div>

      {/* Interactive React Flow Canvas */}
      <Card className="p-0 overflow-hidden border-[#1e2638]">
        <div className="h-[480px] w-full bg-[#090d16]">
          <ReactFlow
            defaultNodes={initialNodes}
            defaultEdges={initialEdges}
            fitView
            attributionPosition="bottom-right"
          >
            <Background color="#1a2233" gap={16} />
            <Controls className="bg-slate-900 border border-slate-700 text-slate-200 fill-slate-200" />
            <MiniMap
              nodeColor="#1e293b"
              maskColor="rgba(9, 13, 22, 0.85)"
              className="bg-slate-950 border border-slate-800 rounded-lg"
            />
          </ReactFlow>
        </div>
      </Card>
    </div>
  );
};
