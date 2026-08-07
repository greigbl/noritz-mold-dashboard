import { describe, expect, it } from 'vitest';
import { shouldShowAgentWorkingIndicator } from '@/components/block/chat/hooks/use-ag-ui-chat';
import type { MessageResponse } from '@/api/chat/types';

const assistantMessage = {
  id: 'assistant-1',
  role: 'assistant',
  content: { format: 2, parts: [{ type: 'text', text: 'hello' }] },
  createdAt: new Date(),
} satisfies MessageResponse;

describe('shouldShowAgentWorkingIndicator', () => {
  it('shows while the agent is running before streamed text arrives', () => {
    expect(
      shouldShowAgentWorkingIndicator({
        isAgentRunning: true,
        isThinking: false,
        message: null,
        reasoningMessage: null,
      })
    ).toBe(true);
  });

  it('hides once assistant text is streaming', () => {
    expect(
      shouldShowAgentWorkingIndicator({
        isAgentRunning: true,
        isThinking: false,
        message: assistantMessage,
        reasoningMessage: null,
      })
    ).toBe(false);
  });

  it('hides after the agent run completes', () => {
    expect(
      shouldShowAgentWorkingIndicator({
        isAgentRunning: false,
        isThinking: false,
        message: null,
        reasoningMessage: null,
      })
    ).toBe(false);
  });
});
