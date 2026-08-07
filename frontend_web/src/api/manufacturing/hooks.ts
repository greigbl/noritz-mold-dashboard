import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import {
  getManufacturingAlert,
  getManufacturingDashboard,
  processManufacturingDashboard,
} from './api-requests';
import { manufacturingKeys } from './keys';
import type { ManufacturingAlert, ManufacturingDashboard } from './types';

const staleTime = 60 * 1000;

type DashboardResponse = { data: ManufacturingDashboard };
type AlertResponse = { data: ManufacturingAlert };

function seedAlertCaches(
  queryClient: ReturnType<typeof useQueryClient>,
  alerts: ManufacturingAlert[] | undefined
) {
  for (const alert of alerts ?? []) {
    queryClient.setQueryData<AlertResponse>(manufacturingKeys.alert(alert.id), {
      data: alert,
    });
  }
}

function findAlertInDashboardCache(
  queryClient: ReturnType<typeof useQueryClient>,
  alertId: string
): ManufacturingAlert | undefined {
  const dashboard = queryClient.getQueryData<DashboardResponse>(manufacturingKeys.dashboard);
  return dashboard?.data?.alerts?.find(alert => alert.id === alertId);
}

export function useManufacturingDashboard() {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: manufacturingKeys.dashboard,
    queryFn: async ({ signal }) => {
      const response = await getManufacturingDashboard({ signal });
      seedAlertCaches(queryClient, response.data.alerts);
      return response;
    },
    select: response => response.data,
    refetchInterval: query =>
      query.state.data?.data.predictionStatus === 'running' ? 3000 : false,
    staleTime,
  });
}

export function useProcessManufacturingDashboard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => processManufacturingDashboard({ file }),
    onSuccess: response => {
      seedAlertCaches(queryClient, response.data.alerts);
      queryClient.setQueryData(manufacturingKeys.dashboard, response);
    },
  });
}

export function useManufacturingAlert(alertId: string | undefined) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: alertId ? manufacturingKeys.alert(alertId) : manufacturingKeys.alert(''),
    queryFn: async ({ signal }) => {
      const id = alertId ?? '';
      try {
        return await getManufacturingAlert({ alertId: id, signal });
      } catch (error) {
        // After a backend hot-reload the in-memory alert map can be empty even
        // while the dashboard React Query cache still has the alert.
        if (isAxiosError(error) && error.response?.status === 404) {
          const cached = findAlertInDashboardCache(queryClient, id);
          if (cached) {
            return { data: cached };
          }
        }
        throw error;
      }
    },
    select: response => response.data,
    staleTime,
    enabled: Boolean(alertId),
    placeholderData: () => {
      if (!alertId) {
        return undefined;
      }
      const cached = findAlertInDashboardCache(queryClient, alertId);
      return cached ? { data: cached } : undefined;
    },
  });
}
