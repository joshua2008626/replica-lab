import type { ArtifactSummary } from '../types';
import { ApiError } from './apiClient';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Upload service for streaming software artifacts to quarantined backend storage.
 */
export async function uploadArtifact(
  projectId: string,
  file: File,
  onProgress?: (percent: number) => void
): Promise<ArtifactSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const url = `${API_BASE_URL}/uploads`;

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        const percent = Math.round((e.loaded / e.total) * 100);
        onProgress(percent);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText) as ArtifactSummary;
          resolve(response);
        } catch {
          reject(new ApiError(xhr.status, 'Invalid JSON returned from server during upload.'));
        }
      } else {
        let detail = `Upload failed with HTTP ${xhr.status}`;
        try {
          const errorData = JSON.parse(xhr.responseText);
          if (errorData.detail) {
            detail = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
          }
        } catch {
          // Response was not JSON
        }
        reject(new ApiError(xhr.status, detail));
      }
    });

    xhr.addEventListener('error', () => {
      reject(new ApiError(0, 'Network connection error while uploading artifact.'));
    });

    xhr.addEventListener('abort', () => {
      reject(new ApiError(0, 'Upload was cancelled by user.'));
    });

    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('file', file);

    xhr.open('POST', url);
    xhr.send(formData);
  });
}
