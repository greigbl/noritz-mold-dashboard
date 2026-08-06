import apiClient from '@/api/apiClient';
import type { ManufacturingAlert, ManufacturingDashboard } from './types';

export async function getManufacturingDashboard({ signal }: { signal: AbortSignal }) {
  return apiClient.get<ManufacturingDashboard>('/v1/manufacturing/dashboard', { signal });
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

export async function processManufacturingDashboard({
  file,
  signal,
}: {
  file: File;
  signal?: AbortSignal;
}) {
  const formData = new FormData();
  formData.append('file', file);
  return apiClient.post<ManufacturingDashboard>('/v1/manufacturing/dashboard/process', formData, {
    signal,
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}
