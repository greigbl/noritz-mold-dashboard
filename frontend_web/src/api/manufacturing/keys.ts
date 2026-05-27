const all = ['manufacturing'];

export const manufacturingKeys = {
  all,
  dashboard: [...all, 'dashboard'],
  alert: (alertId: string) => [...all, 'alerts', alertId],
};
