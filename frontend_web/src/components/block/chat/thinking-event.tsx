import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/lib/i18n';
import type { ChatThinkingEvent } from './types';

export function ThinkingEvent({
  stepName,
  isAgentWorking = false,
}: Pick<ChatThinkingEvent, 'stepName' | 'isAgentWorking'>) {
  const { t } = useTranslation();
  const title = stepName ?? (isAgentWorking ? t('Agent is running') : t('Thinking'));
  const detail = isAgentWorking
    ? t('Searching and analyzing. This may take a minute.')
    : null;

  return (
    <div className={cn('flex gap-3 rounded-lg bg-card p-4')} data-testid="agent-working-indicator">
      <div className="shrink-0">
        <div
          className={cn(
            'flex size-8 items-center justify-center rounded-full',
            'bg-blue-500/10 text-blue-500'
          )}
        >
          <Loader2 className={cn('size-4 animate-spin')} />
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex h-full items-center gap-2">
          <span className="flex h-full items-center mn-label" data-testid="thinking-loading">
            {title}
          </span>
        </div>
        {detail ? <p className="caption-01 text-muted-foreground">{detail}</p> : null}
      </div>
    </div>
  );
}
