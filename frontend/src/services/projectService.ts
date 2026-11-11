import type { Project, ProjectCreate } from '../types';
import { request } from './apiClient';

/**
 * Projects service integration hitting verified /api/projects endpoints.
 */

export async function fetchProjects(search?: string): Promise<Project[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : '';
  return await request<Project[]>(`/projects${query}`);
}

export async function createProject(payload: ProjectCreate): Promise<Project> {
  return await request<Project>('/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchProjectById(projectId: string): Promise<Project> {
  return await request<Project>(`/projects/${projectId}`);
}

export async function deleteProjectById(projectId: string): Promise<{ success: boolean; message: string }> {
  return await request<{ success: boolean; message: string }>(`/projects/${projectId}`, {
    method: 'DELETE',
  });
}
