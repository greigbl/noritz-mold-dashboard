import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { DashboardPage } from '../src/pages/DashboardPage';
import { server } from './__mocks__/node';

const dailyRecord = {
  lotsProduced: 250,
  totalCoatingLengthM: 250000,
  bleedoutCount: 4,
  bleedoutRate: 0.016,
  coatingLengthCategory: '1000m',
  coatingLengthAvgM: 1000,
  productType: '製造',
  coaterTemperature: 28.2,
  coaterTemperatureRange: 1.1,
  coaterHumidity: 50.5,
  coaterHumidityRange: 0.8,
  pumpPressure: 0.9,
  pumpPressureRange: 0.02,
  dryingZone1Temperature: 120.1,
  dryingZone1TemperatureRange: 0.3,
  dryingZone2Temperature: 122.1,
  dryingZone2TemperatureRange: 0.35,
  uvIrradiance: 1020.4,
  uvIrradianceRange: 1.6,
  lampLightingHours: 900,
  chamberO2Concentration: 0.011,
  chamberO2ConcentrationRange: 0.0002,
  uvRollTemperature: 89.05,
  uvRollTemperatureRange: 0.12,
  predictionProbability: null,
  predictionLabel: null,
  alertIds: [],
};

const predictionAlert = {
  id: 'prediction-2026-04-27',
  alertType: 'prediction_ai',
  severity: 'critical',
  status: 'firing',
  source: 'datarobot_prediction',
  metric: 'bleedout_rate',
  date: '2026-04-27',
  title: '予測AIがブリードアウト高リスクを検知',
  description: '予測確率がしきい値を超過しました。',
  actual: 0.91,
  threshold: 0.8,
  controlLimit: null,
  centerLine: null,
  ruleId: 'prediction.probability.threshold',
  ruleVersion: '1.0.0',
  evidence: { probability: 0.91 },
  insightStatus: 'ready',
  insight: '原因仮説: 直近の温湿度とUV条件を確認してください。',
};

const spcAlert = {
  id: 'spc-rbar-2026-04-27-coater-temperature',
  alertType: 'spc_rbar',
  severity: 'warning',
  status: 'firing',
  source: 'spc',
  metric: 'coater_temperature',
  date: '2026-04-27',
  title: 'Rbar管理図でコーター部温度のばらつきを検知',
  description: '日内レンジが管理限界を超過しました。',
  actual: 3,
  threshold: null,
  controlLimit: 2.31,
  centerLine: 1.09,
  ruleId: 'spc.rbar.beyond_control_limit',
  ruleVersion: '1.0.0',
  evidence: { ucl: 2.31 },
  insightStatus: 'ready',
  insight: '確認観点: センサー校正、原材料ロット、設備設定変更を確認してください。',
};

const dashboardResponse = {
  predictionStatus: 'available',
  range: {
    startDate: '2026-03-19',
    endDate: '2026-04-27',
    grain: 'day',
  },
  summary: {
    latestDate: '2026-04-27',
    lotsProduced: 250,
    totalCoatingLengthM: 250000,
    bleedoutCount: 28,
    bleedoutRate: 0.112,
    alertCount: 2,
    predictionAlertCount: 1,
    businessRuleAlertCount: 1,
    criticalAlertCount: 1,
  },
  series: [
    { ...dailyRecord, date: '2026-04-25' },
    { ...dailyRecord, date: '2026-04-26', bleedoutCount: 3, bleedoutRate: 0.012 },
    {
      ...dailyRecord,
      date: '2026-04-27',
      bleedoutCount: 28,
      bleedoutRate: 0.112,
      coaterTemperatureRange: 3,
      predictionProbability: 0.91,
      predictionLabel: 'high_risk',
      alertIds: [predictionAlert.id, spcAlert.id],
    },
  ],
  rbarChart: {
    metric: 'coater_temperature',
    centerLine: 1.09,
    ucl: 2.31,
    lcl: 0,
    points: [
      { date: '2026-04-25', value: 1.1, alertId: null },
      { date: '2026-04-26', value: 1, alertId: null },
      { date: '2026-04-27', value: 3, alertId: spcAlert.id },
    ],
  },
  rbarCharts: {
    coater_temperature: {
      metric: 'coater_temperature',
      centerLine: 1.09,
      ucl: 2.31,
      lcl: 0,
      points: [
        { date: '2026-04-25', value: 1.1, alertId: null },
        { date: '2026-04-26', value: 1, alertId: null },
        { date: '2026-04-27', value: 3, alertId: spcAlert.id },
      ],
    },
    uv_irradiance: {
      metric: 'uv_irradiance',
      centerLine: 1.6,
      ucl: 3.38,
      lcl: 0,
      points: [
        { date: '2026-04-25', value: 1.6, alertId: null },
        { date: '2026-04-26', value: 1.5, alertId: null },
        { date: '2026-04-27', value: 5, alertId: null },
      ],
    },
  },
  alerts: [predictionAlert, spcAlert],
};

function renderDashboard(initialEntries = ['/dashboard']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/dashboard/alerts/:alertId" element={<DashboardPage />} />
          <Route path="/chat" element={<div>Chat target</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('DashboardPage', () => {
  it('renders prediction and business alert counts with highlighted alert days', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () => HttpResponse.json(dashboardResponse))
    );

    renderDashboard();

    expect(await screen.findByText('製造ダッシュボード')).toBeInTheDocument();
    expect(screen.getByText('予測AIアラート')).toBeInTheDocument();
    expect(screen.getByText('業務ロジックアラート')).toBeInTheDocument();
    expect(screen.getByText('1件', { selector: '[data-testid="prediction-alert-count"]' }));
    expect(screen.getByText('1件', { selector: '[data-testid="business-alert-count"]' }));
    expect(screen.getByLabelText('2026-04-27 alert day')).toBeInTheDocument();
    expect(screen.getByText('コーター部温度 日内レンジ Rbar管理図')).toBeInTheDocument();
  });

  it('switches the Rbar chart metric by toggle', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () => HttpResponse.json(dashboardResponse))
    );

    renderDashboard();

    fireEvent.click(await screen.findByRole('button', { name: 'UV照度' }));

    expect(screen.getByText('UV照度 日内レンジ Rbar管理図')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'UV照度 日内レンジ Rbar管理図' })).toBeInTheDocument();
  });

  it('renders dashboard when Rbar chart data is unavailable', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () =>
        HttpResponse.json({
          ...dashboardResponse,
          summary: {
            ...dashboardResponse.summary,
            alertCount: 0,
            businessRuleAlertCount: 0,
            criticalAlertCount: 0,
          },
          series: dashboardResponse.series.map(record => ({ ...record, alertIds: [] })),
          rbarChart: null,
          rbarCharts: {},
          alerts: [],
        })
      )
    );

    renderDashboard();

    expect(await screen.findByText('製造ダッシュボード')).toBeInTheDocument();
    expect(screen.getByText('Rbar管理図データなし')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /Rbar管理図/ })).not.toBeInTheDocument();
  });

  it('navigates to chat with the alert id when an alert is clicked', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () => HttpResponse.json(dashboardResponse))
    );

    renderDashboard();

    fireEvent.click(await screen.findByRole('link', { name: /Rbar管理図/ }));

    expect(await screen.findByText('Chat target')).toBeInTheDocument();
  });
});
