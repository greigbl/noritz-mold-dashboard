import { useLayoutEffect } from 'react';
import { Link, Outlet, useLocation, useNavigate, useParams, useMatch } from 'react-router-dom';
import { ChatSidebar } from '@/components/block/chat/chat-sidebar';
import { useChatList } from '@/components/block/chat/hooks/use-chat-list';
import { MainLayoutProvider } from '@/components/block/chat/main-layout-context';
import { SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar';
import { PATHS } from '@/constants/path';
import { ChartNoAxesCombined } from 'lucide-react';

export function MainLayout() {
  const { chatId = '' } = useParams<{ chatId?: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const setChatIdHandler = (id: string) => {
    navigate({
      pathname: `/chat/${id}`,
      search: location.pathname === PATHS.CHAT_EMPTY ? location.search : '',
    });
  };

  const isChatEmptyPage = useMatch('/chat');
  const isChatSelectedPage = useMatch('/chat/:chatId');
  const isDashboardPage = useMatch(PATHS.DASHBOARD);
  const isDashboardAlertPage = useMatch(PATHS.DASHBOARD_ALERT);
  const isChat = isChatEmptyPage || isChatSelectedPage;

  const {
    hasChat,
    isNewChat,
    chats,
    isLoadingChats,
    addChatHandler,
    deleteChatHandler,
    isDeletingChat,
    refetchChats,
  } = useChatList({
    chatId,
    setChatId: setChatIdHandler,
    showStartChat: !chatId,
  });

  useLayoutEffect(() => {
    if (isLoadingChats || !chats || chats?.find(c => c.id === chatId)) {
      return;
    }
    if (!isChat) {
      return;
    }
    if (!chats.length) {
      addChatHandler();
    } else {
      setChatIdHandler(chats[0].id);
    }
  }, [chats, isLoadingChats, isChat, chatId]);

  return (
    <div className="flex h-svh w-full flex-row">
      <ChatSidebar
        isLoading={isLoadingChats}
        chatId={chatId}
        chats={chats}
        onChatCreate={addChatHandler}
        onChatSelect={setChatIdHandler}
        onChatDelete={deleteChatHandler}
        isDeletingChat={isDeletingChat}
        topMenuitem={
          <SidebarMenuItem key="dashboard">
            <SidebarMenuButton asChild isActive={!!isDashboardPage || !!isDashboardAlertPage}>
              <Link to={PATHS.DASHBOARD}>
                <ChartNoAxesCombined />
                <span>Dashboard</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        }
      />
      <MainLayoutProvider
        value={{
          hasChat,
          isNewChat,
          isLoadingChats,
          addChatHandler,
          refetchChats,
        }}
      >
        <Outlet />
      </MainLayoutProvider>
    </div>
  );
}
