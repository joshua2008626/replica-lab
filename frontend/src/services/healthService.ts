import type { SystemHealth } from '../types';
import { request } from './apiClient';

/**
 * Health service integration hitting GET /api/health.
 */
export async function fetchSystemHealth(): Promise<SystemHealth> {
  return await request<SystemHealth>('/health', { timeoutMs: 4000 });
}
