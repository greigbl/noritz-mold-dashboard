import type {
  APIChat,
  APIChatWithMessages,
  ChatListItem,
  MessageHistoryResponse,
  MessageResponse,
} from './types';
import {
  type ContentPart,
  isToolInvocationPart,
  type ToolInvocationUIPart,
} from '@/components/block/chat/types';

export function selectChats(res: { data: APIChat[] }): ChatListItem[] {
  return [...res.data]
    .map(chat => ({
      id: chat.thread_id,
      name: chat.name,
      userId: chat.user_uuid,
      createdAt: new Date(chat.created_at),
      updatedAt: chat.update_time ? new Date(chat.update_time) : null,
      metadata: chat.metadata,
      initialised: true,
    }))
    .sort((fChat, sChat) => (sChat.createdAt < fChat.createdAt ? -1 : 1));
}

const mapMessageToRole = (role: MessageHistoryResponse['role']): MessageResponse['role'] => {
  switch (role) {
    case 'developer':
    case 'tool':
      return 'system';
    case 'activity':
      return 'system';
    default:
      return role;
  }
};

export function selectMessages(res: { data: APIChatWithMessages }): MessageResponse[] {
  const uiMessages: MessageResponse[] = [];

  for (const historyMessage of res.data.messages) {
    if (historyMessage.role === 'tool') {
      // Attach results to prior tool widgets when present; never render raw tool
      // payloads as their own chat bubbles.
      addResultToToolInvocation(historyMessage, uiMessages);
      continue;
    }

    const parts = mapMessageToContentPart(historyMessage);
    if (parts.length === 0) {
      continue;
    }

    const content = historyMessage.content ?? '';
    const uiMessage: MessageResponse = {
      id: historyMessage.id,
      role: mapMessageToRole(historyMessage.role),
      createdAt: historyMessage?.timestamp ? new Date(historyMessage.timestamp) : new Date(),
      content: {
        format: 2,
        parts,
        content,
      },
    };
    uiMessages.push(uiMessage);
  }

  return uiMessages;
}
// helper methods

function getToolPart(m: MessageResponse, toolCallId: string): ToolInvocationUIPart | undefined {
  return m.content.parts.find(p => {
    if (isToolInvocationPart(p)) {
      return p.toolInvocation?.toolCallId === toolCallId;
    }
  }) as ToolInvocationUIPart | undefined;
}

function mapMessageToContentPart(m: MessageHistoryResponse): ContentPart[] {
  // Agent tool calls are internal — do not surface them as Tool Call widgets.
  // Prefer any assistant text content on the same history row.
  if (m.toolCalls?.length) {
    if (m.content) {
      return [{ type: 'text', text: m.content }];
    }
    return [];
  }

  if (m.content) {
    return [{ type: 'text', text: m.content }];
  }

  // TODO
  return [{ type: 'text', text: 'Unsupported content type' }];
}

/**
 * Populate tool invocations with result, do not render these history entries as a separate message
 * Mutation here is fine, uiMessages are created in selectMessages
 * @param historyMessage
 * @param uiMessages
 */
function addResultToToolInvocation(
  historyMessage: MessageHistoryResponse,
  uiMessages: MessageResponse[]
): boolean {
  if (historyMessage.role === 'tool' && historyMessage.content) {
    return uiMessages.some((m: MessageResponse) => {
      const toolPart = getToolPart(m, historyMessage.id);
      if (toolPart) {
        toolPart.toolInvocation.result = historyMessage.content ?? undefined;
        toolPart.toolInvocation.state = 'result';
        return true;
      }
    });
  }
  return false;
}
