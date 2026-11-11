/**
 * REPLICA LAB — Frontend Core Domain Types.
 * 
 * Maps directly to backend FastAPI Pydantic schemas and endpoints:
 * - Health check: /api/health
 * - Projects: /api/projects
 * - Uploads: /api/uploads
 * - Jobs: /api/jobs
 */

export interface SystemHealth {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'offline';
  project: string;
  version: string;
  environment: string;
  uptime_seconds: number;
  components: {
    database: string;
    rea_mcp_engine?: string;
    rea_mcp?: string;
    storage_ready?: boolean;
  };
}

export interface ArtifactSummary {
  id: string;
  original_filename: string;
  file_size_bytes: number;
  sha256_hash: string;
  detected_format: string;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  artifact_count: number;
  artifacts?: ArtifactSummary[];
}

export interface ProjectCreate {
  name: string;
  description?: string;
}

export type JobStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';

export interface AnalysisJob {
  id: string;
  project_id: string;
  artifact_id: string;
  status: JobStatus;
  progress_percent: number;
  current_step: string;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface EvidenceRecordResponse {
  id: string;
  job_id: string;
  tool_name: string;
  category: string;
  raw_evidence?: any;
  created_at: string;
}

export interface FindingsSummary {
  technologies?: string[];
  imports?: Array<{ dll?: string; functions?: string[]; [key: string]: any }>;
  exports?: Array<{ name?: string; address?: string; [key: string]: any }>;
  resources?: Array<{ type?: string; name?: string; size_bytes?: number; [key: string]: any }>;
  certificates?: Array<{ subject?: string; issuer?: string; is_valid?: boolean; [key: string]: any }>;
  compiler_info?: Record<string, any>;
  database_info?: Record<string, any>;
  model_info?: Record<string, any>;
  security_flags?: Record<string, any>;
  [key: string]: any;
}

export interface JobDetailResponse extends AnalysisJob {
  summary?: FindingsSummary | null;
  evidence_records: EvidenceRecordResponse[];
}

export type NavigationTab = 
  | 'overview' 
  | 'projects' 
  | 'analysis' 
  | 'evidence' 
  | 'architecture' 
  | 'settings';
