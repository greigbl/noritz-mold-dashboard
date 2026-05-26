'use client';
import React, { useEffect, useMemo, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { v4 as uuid } from 'uuid';
import { Skeleton } from '@/components/ui/skeleton';
import { useManufacturingAlert } from '@/api/manufacturing/hooks';
import type { ManufacturingAlert } from '@/api/manufacturing/types';
import {
  Chat,
  useChatScroll,
  useChatContext,
  ChatMessages,
  ChatProgress,
  ChatTextInput,
  ChatError,
  ChatMessageMemo,
  StepEvent,
  ThinkingEvent,
  ChatProvider,
  StartNewChat,
} from '@/components/block/chat';
import {
  isErrorStateEvent,
  isMessageStateEvent,
  isStepStateEvent,
  isThinkingEvent,
} from '@/components/block/chat/types';
import { type MessageResponse } from '@/api/chat/types';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useMainLayout } from '@/components/block/chat/main-layout-context';

const initialMessages: MessageResponse[] = [
  {
    id: uuid(),
    role: 'assistant',
    content: {
      format: 2,
      parts: [
        {
          type: 'text',
          text: `Hello!`,
        },
      ],
    },
    createdAt: new Date(),
    type: 'initial',
  },
];

export interface ChatPageContentProps {
  chatId: string;
  hasChat: boolean;
  isNewChat: boolean;
  isLoadingChats: boolean;
  addChatHandler: () => void;
}

export function ChatImplementation({ chatId }: { chatId: string }) {
  const [searchParams] = useSearchParams();
  const alertId = searchParams.get('alertId') ?? undefined;
  const { data: alert } = useManufacturingAlert(alertId);
  const sentAlertPromptRef = useRef<string | null>(null);
  const {
    sendMessage,
    userInput,
    setUserInput,
    combinedEvents,
    progress,
    deleteProgress,
    isLoadingHistory,
    isAgentRunning,
  } = useChatContext();

  const alertPrompt = useMemo(() => {
    if (!alert) {
      return null;
    }
    return buildAlertChatPrompt(alert);
  }, [alert]);

  useEffect(() => {
    if (
      !alert ||
      !alertPrompt ||
      isLoadingHistory ||
      isAgentRunning ||
      sentAlertPromptRef.current === `${chatId}:${alert.id}`
    ) {
      return;
    }

    sentAlertPromptRef.current = `${chatId}:${alert.id}`;
    void sendMessage(alertPrompt);
  }, [alert, alertPrompt, chatId, isAgentRunning, isLoadingHistory, sendMessage]);

  const { scrollContainerRef, onChatScroll } = useChatScroll({
    chatId,
    events: combinedEvents,
  });

  // Example for a tool with a handler
  // useAgUiTool({
  //   name: 'alert',
  //   description: 'Action. Display an alert to the user',
  //   handler: ({ message }) => alert(message),
  //   parameters: z.object({
  //     message: z
  //       .string()
  //       .describe('The message that will be displayed to the user'),
  //   }),
  //   background: false,
  // });
  //
  // Example for a custom UI widget
  //
  // useAgUiTool({
  //   name: 'weather',
  //   description: 'Widget. Displays weather result to user',
  //   render: ({ args }) => {
  //     return <WeatherWidget {...args} />;
  //   },
  //   parameters: z.object({
  //     temperature: z.number(),
  //     feelsLike: z.number(),
  //     humidity: z.number(),
  //     windSpeed: z.number(),
  //     windGust: z.number(),
  //     conditions: z.string(),
  //     location: z.string(),
  //   }),
  // });

  return (
    <Chat initialMessages={initialMessages}>
      <ScrollArea
        className="mb-5 min-h-0 w-full flex-1"
        scrollViewportRef={scrollContainerRef}
        onWheel={onChatScroll}
      >
        <div className="w-full justify-self-center">
          <ChatMessages isLoading={isLoadingHistory} messages={combinedEvents} chatId={chatId}>
            {combinedEvents &&
              combinedEvents.map(m => {
                if (isErrorStateEvent(m)) {
                  return <ChatError key={m.value.id} {...m.value} />;
                }
                if (isMessageStateEvent(m)) {
                  return <ChatMessageMemo key={m.value.id} {...m.value} />;
                }
                if (isStepStateEvent(m)) {
                  return <StepEvent key={m.value.id} {...m.value} />;
                }
                if (isThinkingEvent(m)) {
                  return <ThinkingEvent key={m.type} />;
                }
              })}
          </ChatMessages>
          <ChatProgress progress={progress || {}} deleteProgress={deleteProgress} />
        </div>
      </ScrollArea>

      <ChatTextInput
        userInput={userInput}
        setUserInput={setUserInput}
        onSubmit={sendMessage}
        runningAgent={isAgentRunning}
      />
    </Chat>
  );
}

export function buildAlertChatPrompt(alert: ManufacturingAlert) {
  const searchOnlyInstructions =
    alert.alertType === 'prediction_ai'
      ? []
      : [
          '実行モード: search_only',
          'この依頼では predict_realtime を呼ばず、既存アラート情報をもとに search_agent に検索だけを1回行わせてください。',
        ];
  const lines = [
    '次の製造アラートについて、原因仮説、確認すべき工程データ、初動対応を整理してください。',
    ...searchOnlyInstructions,
    '',
    `アラートID: ${alert.id}`,
    `種別: ${alert.alertType}`,
    `重要度: ${alert.severity}`,
    `対象指標: ${alert.metric}`,
    `日付: ${alert.date}`,
    `タイトル: ${alert.title}`,
    `説明: ${alert.description}`,
    `実績: ${alert.actual}`,
    alert.threshold !== null ? `しきい値: ${alert.threshold}` : null,
    alert.controlLimit !== null ? `管理限界: ${alert.controlLimit}` : null,
    alert.centerLine !== null ? `中心線: ${alert.centerLine}` : null,
    `ルール: ${alert.ruleId} v${alert.ruleVersion}`,
    alert.insight ? `既存考察: ${alert.insight}` : null,
  ].filter(Boolean);

  return lines.join('\n');
}

export const ChatPage: React.FC = () => {
  const { chatId } = useParams<{ chatId: string }>();
  const { hasChat, isNewChat, isLoadingChats, addChatHandler, refetchChats } = useMainLayout();

  if (!chatId) {
    return null;
  }

  if (isLoadingChats) {
    return (
      <div className="flex w-full flex-1 flex-col space-y-4 p-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (!hasChat) {
    return <StartNewChat createChat={addChatHandler} />;
  }

  return (
    <ChatProvider
      chatId={chatId}
      runInBackground={true}
      isNewChat={isNewChat}
      refetchChats={refetchChats}
    >
      <ChatImplementation chatId={chatId} />
    </ChatProvider>
  );
};
