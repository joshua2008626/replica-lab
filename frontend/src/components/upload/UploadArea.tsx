import React, { useState, useRef } from 'react';
import {
  UploadCloud,
  ShieldCheck,
  CheckCircle2,
  X,
  Binary,
} from 'lucide-react';
import { Badge } from '../common/Badge';

interface UploadAreaProps {
  onFileSelect?: (file: File) => void;
  className?: string;
}

export const UploadArea: React.FC<UploadAreaProps> = ({
  onFileSelect,
  className = '',
}) => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const supportedFormats = [
    { label: 'PE Binary', ext: '.exe, .dll', color: 'indigo' as const },
    { label: 'ELF Binary', ext: 'Linux/Unix', color: 'cyan' as const },
    { label: 'Electron ASAR', ext: '.asar', color: 'indigo' as const },
    { label: 'SQLite DB', ext: '.db, .sqlite', color: 'neutral' as const },
    { label: 'GGUF Models', ext: '.gguf', color: 'neutral' as const },
    { label: 'JavaScript', ext: '.js, source', color: 'neutral' as const },
  ];

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      setSelectedFile(file);
      onFileSelect?.(file);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      setSelectedFile(file);
      onFileSelect?.(file);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
  };

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Drag & Drop Visual Box */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-6 md:p-8 text-center cursor-pointer transition-all duration-200 ${
          isDragOver
            ? 'border-indigo-500 bg-indigo-950/20'
            : 'border-[#222c40] bg-[#0c111e]/70 hover:border-slate-700 hover:bg-[#0e1424]'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handleFileInputChange}
        />

        <div className="flex flex-col items-center justify-center max-w-md mx-auto">
          <div className="w-12 h-12 rounded-xl bg-indigo-950/40 border border-indigo-800/40 flex items-center justify-center text-indigo-400 mb-3.5 shadow-sm">
            <UploadCloud className="w-6 h-6" />
          </div>

          <h4 className="text-sm font-semibold text-slate-100 mb-1">
            Drop software artifact here or click to browse
          </h4>
          <p className="text-xs text-slate-400 mb-4">
            Maximum payload size: <span className="font-mono text-slate-300">100 MiB</span>. Files are cryptographically fingerprinted via chunked SHA-256.
          </p>

          {/* Supported Formats Pills */}
          <div className="flex flex-wrap items-center justify-center gap-1.5 pt-1">
            {supportedFormats.map((fmt) => (
              <Badge key={fmt.label} variant={fmt.color} size="sm">
                <span className="font-mono">{fmt.label}</span>
                <span className="text-slate-400 text-[10px]">({fmt.ext})</span>
              </Badge>
            ))}
          </div>
        </div>
      </div>

      {/* Selected File Stage / Preview */}
      {selectedFile && (
        <div className="p-3.5 rounded-xl bg-[#0f1422] border border-[#222c40] flex items-center justify-between text-xs animate-fadeIn">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-950/40 border border-indigo-800/40 flex items-center justify-center text-indigo-400">
              <Binary className="w-4 h-4" />
            </div>
            <div>
              <div className="font-semibold text-slate-200 font-mono flex items-center gap-2">
                {selectedFile.name}
                <span className="text-[10px] text-slate-500 font-normal">
                  ({formatFileSize(selectedFile.size)})
                </span>
              </div>
              <div className="text-[11px] text-slate-400 flex items-center gap-1.5 mt-0.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Ready to stream to quarantined backend storage</span>
              </div>
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedFile(null);
            }}
            className="p-1 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Security Quarantine Notice */}
      <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-[#0b101c] border border-[#1b2334] text-[11px] text-slate-400">
        <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-slate-300">Quarantine & Containment: </span>
          Artifacts are streamed in bounded chunks and stored under UUID aliases. Files undergo static structural and binary telemetry inspection only — they are never executed on the host.
        </div>
      </div>
    </div>
  );
};
