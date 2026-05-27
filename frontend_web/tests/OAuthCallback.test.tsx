import { StrictMode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OAuthCallback from '@/pages/OAuthCallback';
import { getOAuthCallback } from '@/api/oauth/requests';

vi.mock('@/api/oauth/requests', () => ({
  getOAuthCallback: vi.fn(),
}));

function renderOAuthCallback() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/oauth/callback?code=test-code&state=test-state']}>
          <Routes>
            <Route path="/oauth/callback" element={<OAuthCallback />} />
            <Route path="/settings" element={<div>Settings page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>
  );
}

describe('OAuthCallback', () => {
  beforeEach(() => {
    vi.mocked(getOAuthCallback).mockReset();
  });

  it('exchanges a returned OAuth code only once across remounts', async () => {
    vi.mocked(getOAuthCallback).mockResolvedValue({});

    renderOAuthCallback();

    await waitFor(() => expect(screen.getByText('Settings page')).toBeInTheDocument());
    expect(getOAuthCallback).toHaveBeenCalledTimes(1);
    expect(getOAuthCallback).toHaveBeenCalledWith('?code=test-code&state=test-state');
  });
});
