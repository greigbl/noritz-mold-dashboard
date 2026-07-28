import apiClient from '@/api/apiClient';
import type { ManufacturingAlert, ManufacturingDashboard } from './types';

export async function getManufacturingDashboard({ signal }: { signal: AbortSignal }) {
  return apiClient.get<ManufacturingDashboard>('/v1/manufacturing/dashboard', { signal });
}

export async function uploadManufacturingDashboard({
  files,
  signal,
}: {
  files: File[];
  signal?: AbortSignal;
}) {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }
  // Drop the default application/json Content-Type so the browser sets
  // multipart/form-data with the correct boundary.
  return apiClient.post<ManufacturingDashboard>('/v1/manufacturing/dashboard/upload', formData, {
    signal,
    headers: {
      'Content-Type': undefined,
      'Content-type': undefined,
    },
  });
}

export async function getManufacturingAlert({
  alertId,
  signal,
}: {
  alertId: string;
  signal: AbortSignal;
}) {
  return apiClient.get<ManufacturingAlert>(`/v1/manufacturing/alerts/${alertId}`, { signal });
}

export async function refreshManufacturingAlertInsight({ alertId }: { alertId: string }) {
  return apiClient.post<ManufacturingAlert>(`/v1/manufacturing/alerts/${alertId}/insight:refresh`);
}
