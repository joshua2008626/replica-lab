import type { AnalysisJob, JobDetailResponse } from '../types';
import { request } from './apiClient';

/**
 * Job Service for triggering, monitoring, and cancelling asynchronous analysis jobs.
 */

export async function triggerAnalysis(
  projectId: string,
  artifactId: string
): Promise<AnalysisJob> {
  return await request<AnalysisJob>(
    `/projects/${projectId}/artifacts/${artifactId}/analyze`,
    {
      method: 'POST',
    }
  );
}

export async function fetchJobDetails(jobId: string): Promise<JobDetailResponse> {
  return await request<JobDetailResponse>(`/jobs/${jobId}`);
}

export async function fetchProjectJobs(projectId: string): Promise<AnalysisJob[]> {
  return await request<AnalysisJob[]>(`/projects/${projectId}/jobs`);
}

export async function cancelJob(jobId: string): Promise<AnalysisJob> {
  return await request<AnalysisJob>(`/jobs/${jobId}/cancel`, {
    method: 'POST',
  });
}
