import { memo, useMemo, Component, type ReactNode, type ErrorInfo } from 'react';
import { User, Bot, Cog, AlertTriangle, Brain } from 'lucide-react';
import { CodeBlock } from '@/components/ui/code-block';
import { cn } from '@/lib/utils';
import type { ContentPart, ToolInvocationUIPart, ChatMessageEvent } from './types';
import { useChatContext } from '@/components/block/chat/hooks/use-chat-context';
import { Markdown } from '@/components/block/markdown';
import { useTranslation } from '@/lib/i18n';

interface ChatMessageErrorBoundaryProps {
  children: ReactNode;
  message: ChatMessageEvent;
  title: string;
}

interface ChatMessageErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ChatMessageErrorBoundary extends Component<
  ChatMessageErrorBoundaryProps,
  ChatMessageErrorBoundaryState
> {
  constructor(props: ChatMessageErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ChatMessageErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ChatMessage render error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className={'flex gap-3 rounded-lg bg-card p-4'}>
          <div className="shrink-0">
            <div className="flex size-8 items-center justify-center rounded-full bg-destructive/20 text-destructive">
              <AlertTriangle className="size-4" />
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-2">
              <span className="mn-label text-destructive">{this.props.title}</span>
            </div>
            <CodeBlock code={JSON.stringify(this.props.message, null, 2)} />
            {this.state.error && (
              <div className="my-2 caption-01">
                <div>{this.state.error.message}</div>
                <div>{this.state.error.stack}</div>
              </div>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export function UniversalContentPart({ part }: { part: ContentPart }) {
  if (part.type === 'text') {
    return <TextContentPart content={part.text} />;
  }
  if (part.type === 'reasoning') {
    return <TextContentPart content={part.reasoning} />;
  }
  if (part.type === 'tool-invocation') {
    return <ToolInvocationPart part={part} />;
  }
  return <CodeBlock code={JSON.stringify(part, null, '  ')} />;
}

export function TextContentPart({ content }: { content: string }) {
  return <Markdown>{content ? content : ''}</Markdown>;
}

export function ToolInvocationPart({ part }: { part: ToolInvocationUIPart }) {
  const { toolInvocation } = part;
  const { toolName } = toolInvocation;
  const ctx = useChatContext();
  const tool = ctx.getTool(toolName);

  // Only registered client UI tools render. Agent/MCP tools (search_agent, etc.)
  // must not show the default Tool Call card — they leave a forever-spinning loader.
  if (tool?.render) {
    return tool.render({ status: 'complete', args: toolInvocation.args });
  }
  if (tool?.renderAndWait) {
    return tool.renderAndWait({
      status: 'complete',
      args: toolInvocation.args,
      callback: event => {
        // eslint-disable-next-line no-console
        console.debug('Tool render event', event);
      },
    });
  }

  return null;
}

function ChatMessageContent({
  id,
  role,
  threadId,
  resourceId,
  content,
  type = 'default',
}: ChatMessageEvent) {
  const isUser = role === 'user';
  const ctx = useChatContext();
  const visibleParts = content.parts.filter(part => {
    if (part.type !== 'tool-invocation') {
      return true;
    }
    const tool = ctx.getTool(part.toolInvocation.toolName);
    return !!(tool?.render || tool?.renderAndWait);
  });

  const Icon = useMemo(() => {
    if (isUser) {
      return User;
    } else if (role === 'system') {
      return Cog;
    } else if (role === 'reasoning') {
      return Brain;
    } else {
      return Bot;
    }
  }, [role, isUser]);

  // Hide empty assistant shells that only contained hidden agent tool calls.
  if (!isUser && visibleParts.length === 0) {
    return null;
  }

  return (
    <div
      className={cn('flex gap-3 rounded-lg p-4', isUser ? 'bg-card' : '')}
      data-message-id={id}
      data-thread-id={threadId}
      data-resource-id={resourceId}
      data-testid={`${type}-${role}-message-${id}`}
    >
      <div className="shrink-0">
        <div
          className={cn(
            'flex size-8 items-center justify-center rounded-full',
            isUser
              ? 'bg-primary text-primary-foreground'
              : role === 'assistant'
                ? 'bg-secondary text-secondary-foreground'
                : role === 'reasoning'
                  ? 'bg-muted text-muted-foreground'
                  : 'bg-accent text-accent-foreground'
          )}
        >
          <Icon className="size-4" />
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="mn-label capitalize">{role}</span>
        </div>
        <div
          className={`
            overflow-hidden body text-wrap break-words
            [line-break:anywhere]
          `}
        >
          {visibleParts.map((part, i) => (
            <UniversalContentPart key={i} part={part} />
          ))}
        </div>
      </div>
    </div>
  );
}

export function ChatMessage(props: ChatMessageEvent) {
  const { t } = useTranslation();
  return (
    <ChatMessageErrorBoundary message={props} title={t('Failed to render message')}>
      <ChatMessageContent {...props} />
    </ChatMessageErrorBoundary>
  );
}

export const ChatMessageMemo = memo(ChatMessage);
