import { describe, expect, it } from 'vitest';
import { resolveAppLanguage } from '@/lib/i18n/language';

describe('resolveAppLanguage', () => {
  it('prefers APP_LANGUAGE from env over saved local preference', () => {
    expect(resolveAppLanguage('ja', 'en')).toBe('ja');
  });

  it('falls back to saved local preference when env is unset', () => {
    expect(resolveAppLanguage(undefined, 'ko')).toBe('ko');
  });

  it('defaults to Japanese when no preference is configured', () => {
    expect(resolveAppLanguage(undefined, null)).toBe('ja');
  });
});
