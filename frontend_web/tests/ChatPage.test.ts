import { describe, expect, it } from 'vitest';
import { buildAlertChatPrompt, buildAlertChatTitle } from '../src/pages/ChatPage';
import type { ManufacturingAlert } from '../src/api/manufacturing/types';

function makeAlert(alertType: ManufacturingAlert['alertType']): ManufacturingAlert {
  return {
    id: `${alertType}-2026-04-27`,
    dedupKey: `${alertType}:coater_temperature:2026-04-27`,
    alertType,
    severity: 'warning',
    status: 'firing',
    source: alertType === 'prediction_ai' ? 'datarobot_prediction' : 'business_rule',
    metric: 'coater_temperature',
    date: '2026-04-27',
    title: 'コーター部温度の確認が必要',
    description: '業務ルールで確認対象になりました。',
    actual: 3,
    threshold: null,
    controlLimit: 2.31,
    centerLine: 1.09,
    ruleId: alertType === 'prediction_ai' ? 'prediction.probability.threshold' : 'business.temperature.threshold',
    ruleVersion: '1.0.0',
    evidence: { value: 3 },
    insightStatus: 'ready',
    insight: '確認観点: 設備設定変更を確認してください。',
    // Fixture only — runtime value comes from alert API / prediction CSV.
    anomalyScore: 0.15,
  };
}

describe('buildAlertChatPrompt', () => {
  it('marks business rule alerts as search only', () => {
    const prompt = buildAlertChatPrompt(makeAlert('business_rule'));

    expect(prompt).toContain('実行モード: search_only');
    expect(prompt).toContain('predict_realtime を呼ばず');
    expect(prompt).toContain('search_agent に検索だけを1回');
    expect(prompt).toContain('種別: business_rule');
    expect(prompt).toContain('異常予測モデルの異常値は0.15です');
    expect(prompt).toContain('Web検索要件:');
    expect(prompt).toContain('日本語の検索クエリで tavily_search');
    expect(prompt).toContain('是正・再発防止の具体的な対処法');
  });

  it('does not mark prediction alerts as search only', () => {
    const prompt = buildAlertChatPrompt(makeAlert('prediction_ai'));

    expect(prompt).not.toContain('実行モード: search_only');
    expect(prompt).toContain('種別: prediction_ai');
  });

  it('omits anomaly score when not available', () => {
    const alert = makeAlert('business_rule');
    alert.anomalyScore = null;
    const prompt = buildAlertChatPrompt(alert);

    expect(prompt).not.toContain('異常予測モデルの異常値は');
  });
});

describe('buildAlertChatTitle', () => {
  it('uses Japanese metric name and date', () => {
    expect(buildAlertChatTitle(makeAlert('business_rule'))).toBe('コーター部温度 / 2026-04-27');
    expect(buildAlertChatTitle({ ...makeAlert('business_rule'), metric: 'production_flow_rate' })).toBe(
      '生産総合流速 / 2026-04-27'
    );
    expect(buildAlertChatTitle({ ...makeAlert('business_rule'), metric: 'b_tank1_pressure' })).toBe(
      'B剤タンク1圧力 / 2026-04-27'
    );
  });
});
