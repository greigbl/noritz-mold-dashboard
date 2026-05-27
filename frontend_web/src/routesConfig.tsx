import { PATHS } from '@/constants/path.ts';
import { lazy } from 'react';
import { Navigate } from 'react-router-dom';
import { SettingsLayout } from './pages/SettingsLayout';
import { ChatPage } from './pages/ChatPage';
import { EmptyStatePage } from './pages/EmptyState.tsx';
import { MainLayout } from './pages/MainLayoutWithChatList';
import { DashboardPage } from './pages/DashboardPage';

const OAuthCallback = lazy(() => import('./pages/OAuthCallback'));

export const appRoutes = [
  { path: PATHS.OAUTH_CB, element: <OAuthCallback /> },
  {
    element: <MainLayout />,
    children: [
      { index: true, element: <Navigate to={PATHS.DASHBOARD} replace /> },
      { path: PATHS.DASHBOARD, element: <DashboardPage /> },
      { path: PATHS.DASHBOARD_ALERT, element: <DashboardPage /> },
      { path: PATHS.CHAT_EMPTY, element: <EmptyStatePage /> },
      { path: PATHS.CHAT, element: <ChatPage /> },
      {
        path: PATHS.SETTINGS.ROOT,
        element: <SettingsLayout />,
        children: [{ path: 'sources', element: <Navigate to={PATHS.SETTINGS.ROOT} replace /> }],
      },
      { path: '*', element: <Navigate to={PATHS.DASHBOARD} replace /> },
    ],
  },
];
