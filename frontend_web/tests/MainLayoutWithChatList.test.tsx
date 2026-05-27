import { render, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatListItem } from '@/api/chat/types';
import { useChatList } from '@/components/block/chat/hooks/use-chat-list';
import { MainLayout } from '../src/pages/MainLayoutWithChatList';

vi.mock('@/components/block/chat/hooks/use-chat-list', () => ({
  useChatList: vi.fn(),
}));

vi.mock('@/components/block/chat/chat-sidebar', () => ({
  ChatSidebar: () => null,
}));

const useChatListMock = vi.mocked(useChatList);

const existingChat: ChatListItem = {
  id: 'existing-chat',
  name: 'Existing chat',
  userId: 'user-1',
  createdAt: new Date('2026-05-01T00:00:00Z'),
  updatedAt: null,
};

function renderMainLayout(initialEntry: string) {
  const tree = (
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/chat" element={<div>Empty chat route</div>} />
          <Route path="/chat/:chatId" element={<div>Selected chat route</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );

  return render(tree);
}

describe('MainLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates a new session for dashboard alert chat links even when chats already exist', async () => {
    const addChatHandler = vi.fn();

    useChatListMock.mockImplementation(() => ({
      hasChat: false,
      isNewChat: false,
      chatId: '',
      setChatId: vi.fn(),
      chats: [existingChat],
      newChat: null,
      setNewChat: vi.fn(),
      isLoadingChats: false,
      deleteChat: vi.fn().mockResolvedValue(undefined),
      addChatHandler,
      deleteChatHandler: vi.fn(),
      isDeletingChat: false,
      refetchChats: vi.fn().mockResolvedValue(undefined),
    }));

    renderMainLayout('/chat?alertId=spc-rbar-2026-04-27-coater-temperature');

    await waitFor(() => {
      expect(addChatHandler).toHaveBeenCalledTimes(1);
    });
  });

  it('does not create duplicate sessions for the same dashboard alert link during rerenders', async () => {
    const addChatHandler = vi.fn();

    useChatListMock.mockImplementation(() => ({
      hasChat: false,
      isNewChat: false,
      chatId: '',
      setChatId: vi.fn(),
      chats: [existingChat],
      newChat: null,
      setNewChat: vi.fn(),
      isLoadingChats: false,
      deleteChat: vi.fn().mockResolvedValue(undefined),
      addChatHandler,
      deleteChatHandler: vi.fn(),
      isDeletingChat: false,
      refetchChats: vi.fn().mockResolvedValue(undefined),
    }));

    const view = renderMainLayout('/chat?alertId=spc-rbar-2026-04-27-coater-temperature');

    await waitFor(() => {
      expect(addChatHandler).toHaveBeenCalledTimes(1);
    });

    view.rerender(
      <MemoryRouter initialEntries={['/chat?alertId=spc-rbar-2026-04-27-coater-temperature']}>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/chat" element={<div>Empty chat route</div>} />
            <Route path="/chat/:chatId" element={<div>Selected chat route</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(useChatListMock).toHaveBeenCalledTimes(2);
    });
    expect(addChatHandler).toHaveBeenCalledTimes(1);
  });
});
