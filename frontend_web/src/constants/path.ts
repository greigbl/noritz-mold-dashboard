export const PATHS = {
  CHAT_EMPTY: '/chat',
  CHAT: '/chat/:chatId',
  DASHBOARD: '/dashboard',
  DASHBOARD_ALERT: '/dashboard/alerts/:alertId',
  OAUTH_CB: '/oauth/callback',
  SETTINGS: {
    ROOT: '/settings',
  },
} as const;
