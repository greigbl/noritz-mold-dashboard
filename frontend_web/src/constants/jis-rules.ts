/** JIS X-R control chart violation rules (mirrors fastapi_server manufacturing config). */
export const JIS_RULE_DESCRIPTIONS: Record<string, string> = {
  '1': '領域A超過点が1つ（管理限界超過）',
  '2': '連続9点が中心線に対して同一側',
  '3': '連続6点で単調増加または単調減少トレンド',
  '4': '連続14点が交互に増減',
  '5': '連続3点中2点以上が領域Aまたはそれを超えた領域（±2σ超過）',
  '6': '連続5点中4点以上が領域Bまたはそれを超えた領域（±1σ超過）',
  '7': '連続15点が領域C内（±1σ以内）',
  '8': '連続8点が領域C超過（±1σ超過）',
};
