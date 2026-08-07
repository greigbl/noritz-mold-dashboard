export const SUPPORTED_APP_LANGUAGES = ['en', 'es', 'fr', 'ja', 'ko', 'pt'] as const;

export type AppLanguage = (typeof SUPPORTED_APP_LANGUAGES)[number];

export const DEFAULT_APP_LANGUAGE: AppLanguage = 'ja';

export function resolveAppLanguage(
  envLanguage?: string,
  savedLanguage?: string | null
): AppLanguage {
  for (const candidate of [envLanguage?.trim(), savedLanguage?.trim(), DEFAULT_APP_LANGUAGE]) {
    if (
      candidate &&
      SUPPORTED_APP_LANGUAGES.includes(candidate as AppLanguage)
    ) {
      return candidate as AppLanguage;
    }
  }
  return DEFAULT_APP_LANGUAGE;
}
