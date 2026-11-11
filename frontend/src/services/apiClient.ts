/**
 * REPLICA LAB — API HTTP Client.
 * 
 * Provides unified request handling, error normalization, and timeout controls
 * for communication with the FastAPI backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export class ApiError extends Error {
  public status: number;
  public detail: string;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail || message;
  }
}

interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 10000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const url = endpoint.startsWith('http') 
    ? endpoint 
    : `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...(fetchOptions.headers || {}),
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      let errorMessage = `HTTP Error ${response.status}: ${response.statusText}`;
      let detail = errorMessage;
      try {
        const errorData = await response.json();
        if (errorData.detail) {
          detail = typeof errorData.detail === 'string' 
            ? errorData.detail 
            : JSON.stringify(errorData.detail);
          errorMessage = detail;
        }
      } catch {
        // Response was not JSON
      }
      throw new ApiError(response.status, errorMessage, detail);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return await response.json() as T;
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    if (error instanceof ApiError) {
      throw error;
    }
    if ((error as { name?: string }).name === 'AbortError') {
      throw new ApiError(408, 'Request timed out waiting for backend response.');
    }
    throw new ApiError(0, error instanceof Error ? error.message : 'Network failure connecting to backend.');
  }
}
