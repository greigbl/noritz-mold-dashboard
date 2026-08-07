import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { DashboardPage } from '../src/pages/DashboardPage';
import { server } from './__mocks__/node';

const businessAlert = {
  id: 'jis-xr-2026-04-21-a-agent-flow-pressure-p1',
  dedupKey: 'business_rule:jis_xr:a_agent_flow_pressure:1:2026-04-21',
  alertType: 'business_rule',
  severity: 'critical',
  status: 'firing',
  source: 'phase2_xr',
  metric: 'a_agent_flow_pressure',
  date: '2026-04-21',
  title: 'A剤流圧 / 吐出パターン1 でJIS管理図違反を検知',
  description: 'ルール1:領域A超過（管理限界超過）',
  actual: 0.32,
  threshold: null,
  controlLimit: 0.2481,
  centerLine: 0.1966,
  ruleId: 'jis.xr.violation_rules',
  ruleVersion: '1.0.0',
  evidence: {
    pattern: 1,
    violationRules: [1],
    violationRulesStr: '1',
    violationRuleDetails: [
      { rule: 1, description: '領域A超過点が1つ（管理限界超過）' },
    ],
  },
  insightStatus: 'ready',
  insight: '確認観点: 吐出パターン1の直近推移を確認してください。',
  anomalyScore: 0.2,
};

const dashboardResponse = {
  dataStatus: 'ready',
  preserveFileOnReload: true,
  sourceFile: 'テストデータ_202604.csv',
  predictionStatus: 'unavailable',
  range: {
    startDate: '2026-03-23',
    endDate: '2026-04-21',
    grain: 'day',
  },
  summary: {
    latestDate: '2026-04-21',
    lotsProduced: 0,
    totalCoatingLengthM: 0,
    bleedoutCount: 0,
    bleedoutRate: 0,
    alertCount: 1,
    predictionAlertCount: 0,
    businessRuleAlertCount: 1,
    criticalAlertCount: 1,
  },
  series: [
    {
      date: '2026-04-21',
      lotsProduced: 0,
      totalCoatingLengthM: 0,
      bleedoutCount: 0,
      bleedoutRate: 0,
      coatingLengthCategory: '-',
      coatingLengthAvgM: 0,
      productType: 'モールド',
      coaterTemperature: 0,
      coaterTemperatureRange: 0,
      coaterHumidity: 0,
      coaterHumidityRange: 0,
      pumpPressure: 0,
      pumpPressureRange: 0,
      dryingZone1Temperature: 0,
      dryingZone1TemperatureRange: 0,
      dryingZone2Temperature: 0,
      dryingZone2TemperatureRange: 0,
      uvIrradiance: 0,
      uvIrradianceRange: 0,
      lampLightingHours: 0,
      chamberO2Concentration: 0,
      chamberO2ConcentrationRange: 0,
      uvRollTemperature: 0,
      uvRollTemperatureRange: 0,
      predictionProbability: null,
      predictionLabel: null,
      alertIds: [businessAlert.id],
    },
  ],
  rbarChart: {
    metric: 'a_agent_flow_pressure',
    pattern: 1,
    centerLine: 0.1966,
    ucl: 0.2481,
    lcl: 0.1451,
    points: [
      { date: '2026-04-15', value: 0.195, alertId: null, violationRules: [], pattern: 1 },
      {
        date: '2026-04-21',
        value: 0.32,
        alertId: businessAlert.id,
        violationRules: [1],
        pattern: 1,
      },
    ],
  },
  rbarCharts: {
    a_agent_flow_pressure: {
      metric: 'a_agent_flow_pressure',
      pattern: 1,
      centerLine: 0.1966,
      ucl: 0.2481,
      lcl: 0.1451,
      points: [
        { date: '2026-04-15', value: 0.195, alertId: null, violationRules: [], pattern: 1 },
        {
          date: '2026-04-21',
          value: 0.32,
          alertId: businessAlert.id,
          violationRules: [1],
          pattern: 1,
        },
      ],
    },
  },
  xrCharts: {
    a_agent_flow_pressure: {
      '1': {
        metric: 'a_agent_flow_pressure',
        pattern: 1,
        centerLine: 0.1966,
        ucl: 0.2481,
        lcl: 0.1451,
        points: [
          { date: '2026-04-15', value: 0.195, alertId: null, violationRules: [], pattern: 1 },
          {
            date: '2026-04-21',
            value: 0.32,
            alertId: businessAlert.id,
            violationRules: [1],
            pattern: 1,
          },
        ],
      },
      '6': {
        metric: 'a_agent_flow_pressure',
        pattern: 6,
        centerLine: 0.1746,
        ucl: 0.2018,
        lcl: 0.1474,
        points: [{ date: '2026-04-15', value: 0.1708, alertId: null, violationRules: [], pattern: 6 }],
      },
    },
    b_agent_flow_pressure: {
      '1': {
        metric: 'b_agent_flow_pressure',
        pattern: 1,
        centerLine: 0.2,
        ucl: 0.25,
        lcl: 0.15,
        points: [{ date: '2026-04-15', value: 0.2, alertId: null, violationRules: [], pattern: 1 }],
      },
    },
  },
  availablePatterns: [1, 6],
  dailyCountChart: {
    anomalyScoreThreshold: 0.085,
    points: [
      { date: '2026-04-15', count: 1194, maxAnomalyScore: 0.001 },
      { date: '2026-04-16', count: 1225, maxAnomalyScore: 0.12 },
      { date: '2026-04-21', count: 1895, maxAnomalyScore: 0.002 },
    ],
  },
  jisRuleDescriptions: {
    '1': '領域A超過点が1つ（管理限界超過）',
    '5': '連続3点中2点以上が領域Aまたはそれを超えた領域（±2σ超過）',
  },
  alerts: [businessAlert],
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
  it('renders mold X-R dashboard with business alerts', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () => HttpResponse.json(dashboardResponse))
    );

    renderDashboard();

    expect(await screen.findByText('モールド装置 X-R管理図')).toBeInTheDocument();
    expect(screen.getByText('テストデータ_202604.csv')).toBeInTheDocument();
    expect(screen.getByText('業務アラート（全体）')).toBeInTheDocument();
    expect(screen.getByText('1件', { selector: '[data-testid="business-alert-count"]' }));
    expect(screen.getByLabelText('日次データ件数')).toBeInTheDocument();
    expect(screen.getByText('A剤流圧 X管理図')).toBeInTheDocument();
    expect(screen.getByText('B剤流圧 X管理図')).toBeInTheDocument();
    expect(screen.getByLabelText('吐出パターン番号')).toBeInTheDocument();
  });

  it('switches pattern and updates all feature charts', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () => HttpResponse.json(dashboardResponse))
    );

    renderDashboard();

    expect(
      await screen.findByRole('img', { name: 'A剤流圧 吐出パターン1 X管理図' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: 'B剤流圧 吐出パターン1 X管理図' })
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('吐出パターン番号'), { target: { value: '6' } });

    expect(
      screen.getByRole('img', { name: 'A剤流圧 吐出パターン6 X管理図' })
    ).toBeInTheDocument();
    expect(screen.getAllByText('X管理図データなし').length).toBeGreaterThan(0);
  });

  it('renders upload empty state before any data is loaded', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () =>
        HttpResponse.json({
          dataStatus: 'empty',
          predictionStatus: 'unavailable',
          range: {
            startDate: '2026-07-31',
            endDate: '2026-07-31',
            grain: 'day',
          },
          summary: {
            latestDate: '2026-07-31',
            lotsProduced: 0,
            totalCoatingLengthM: 0,
            bleedoutCount: 0,
            bleedoutRate: 0,
            alertCount: 0,
            predictionAlertCount: 0,
            businessRuleAlertCount: 0,
            criticalAlertCount: 0,
          },
          series: [],
          rbarChart: null,
          rbarCharts: {},
          xrCharts: {},
          availablePatterns: [],
          dailyCountChart: null,
          jisRuleDescriptions: {},
          alerts: [],
        })
      )
    );

    renderDashboard();

    expect(await screen.findByTestId('dashboard-empty-state')).toBeInTheDocument();
    expect(screen.getByText('テストデータをアップロードしてください')).toBeInTheDocument();
    expect(screen.queryByText('業務アラート（全体）')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('日次データ件数')).not.toBeInTheDocument();
  });

  it('renders empty state when chart data is unavailable', async () => {
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
          rbarChart: null,
          rbarCharts: {},
          xrCharts: {},
          alerts: [],
        })
      )
    );

    renderDashboard();

    expect(await screen.findByText('モールド装置 X-R管理図')).toBeInTheDocument();
    expect(screen.getByText('X管理図データなし')).toBeInTheDocument();
  });

  it('navigates to chat with the alert id when an alert is clicked', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () => HttpResponse.json(dashboardResponse))
    );

    renderDashboard();

    fireEvent.click(await screen.findByRole('link', { name: /A剤流圧/ }));

    expect(await screen.findByText('Chat target')).toBeInTheDocument();
  });

  it('shows scoring spinner while anomaly predictions are running', async () => {
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () =>
        HttpResponse.json({
          ...dashboardResponse,
          predictionStatus: 'running',
        })
      )
    );

    renderDashboard();

    expect(await screen.findByRole('status', { name: '異常スコア算出中' })).toBeInTheDocument();
  });

  it('updates anomaly score threshold from settings dialog', async () => {
    window.localStorage.removeItem('manufacturing.anomalyScoreThreshold');
    server.use(
      http.get('*/api/v1/manufacturing/dashboard', () => HttpResponse.json(dashboardResponse))
    );

    renderDashboard();

    fireEvent.click(await screen.findByRole('button', { name: '設定' }));
    expect(await screen.findByText('異常スコア閾値')).toBeInTheDocument();

    const input = screen.getByLabelText('異常スコア閾値');
    fireEvent.change(input, { target: { value: '0.05' } });
    fireEvent.click(screen.getByRole('button', { name: '適用' }));

    expect(window.localStorage.getItem('manufacturing.anomalyScoreThreshold')).toBe('0.05');

    fireEvent.click(screen.getByRole('button', { name: '設定' }));
    expect(await screen.findByText('現在の閾値: 0.05')).toBeInTheDocument();
  });
});
