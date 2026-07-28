import { useMutation, useQuery } from '@tanstack/react-query';
import {
  getManufacturingAlert,
  getManufacturingDashboard,
  uploadManufacturingDashboard,
} from './api-requests';
import { manufacturingKeys } from './keys';

const staleTime = 60 * 1000;

export function useManufacturingDashboard() {
  return useQuery({
    queryKey: manufacturingKeys.dashboard,
    queryFn: ({ signal }) => getManufacturingDashboard({ signal }),
    select: response => response.data,
    refetchInterval: query =>
      query.state.data?.data.predictionStatus === 'running' ? 3000 : false,
    staleTime,
  });
}

export function useUploadManufacturingDashboard() {
  return useMutation({
    mutationFn: (files: File[]) => uploadManufacturingDashboard({ files }),
  });
}

export function useManufacturingAlert(alertId: string | undefined) {
  return useQuery({
    queryKey: alertId ? manufacturingKeys.alert(alertId) : manufacturingKeys.alert(''),
    queryFn: ({ signal }) => getManufacturingAlert({ alertId: alertId ?? '', signal }),
    select: response => response.data,
    staleTime,
    enabled: Boolean(alertId),
  });
}
