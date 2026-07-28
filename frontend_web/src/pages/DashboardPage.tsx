import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Bot,
  BrainCircuit,
  LineChart,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Dot,
  Line,
  LineChart as RechartsLineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useManufacturingAlert, useManufacturingDashboard } from '@/api/manufacturing/hooks';
import type {
  ManufacturingAlert,
  ManufacturingMetric,
  RbarChart,
  RbarChartPoint,
} from '@/api/manufacturing/types';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PATHS } from '@/constants/path';
import { cn } from '@/lib/utils';

type XrChartRow = RbarChartPoint & {
  label: string;
};

const dateFormatter = new Intl.DateTimeFormat('ja-JP', {
  month: 'numeric',
  day: 'numeric',
});

const metricLabels: Record<ManufacturingMetric, string> = {
  lots_produced: '生産ロット数',
  bleedout_rate: 'ブリードアウト率',
  coater_temperature: 'コーター部温度',
  coater_humidity: 'コーター部相対湿度',
  pump_pressure: 'ポンプ圧力',
  drying_zone1_temperature: '乾燥ゾーン1温度',
  drying_zone2_temperature: '乾燥ゾーン2温度',
  uv_irradiance: 'UV照度',
  lamp_lighting_hours: 'ランプ点灯時間',
  chamber_o2_concentration: 'チャンバー内O2濃度',
  uv_roll_temperature: 'UVロール温度',
  a_agent_flow_pressure: 'A剤流圧',
  b_agent_flow_pressure: 'B剤流圧',
  a_tank1_pressure: 'A剤タンク1圧力',
  a_tank2_pressure: 'A剤タンク2圧力',
  b_tank1_pressure: 'B剤タンク1圧力',
  b_tank2_pressure: 'B剤タンク2圧力',
  a_mix_ratio_speed: 'A剤配合比速度',
  b_mix_ratio_speed: 'B剤配合比速度',
  production_flow_rate: '生産総合流速',
  production_discharge_time: '生産吐出時間',
};

const xrMetricOptions: ManufacturingMetric[] = [
  'a_agent_flow_pressure',
  'b_agent_flow_pressure',
  'a_tank1_pressure',
  'a_tank2_pressure',
  'b_tank1_pressure',
  'b_tank2_pressure',
  'a_mix_ratio_speed',
  'b_mix_ratio_speed',
  'production_flow_rate',
  'production_discharge_time',
];

function formatDate(value: string) {
  return dateFormatter.format(new Date(`${value}T00:00:00`));
}

function formatAlertValue(alert: ManufacturingAlert) {
  if (alert.alertType === 'prediction_ai') {
    return `${(alert.actual * 100).toFixed(1)}%`;
  }
  return alert.actual.toLocaleString('ja-JP', { maximumFractionDigits: 4 });
}

function formatViolationRules(alert: ManufacturingAlert) {
  const raw = alert.evidence?.violationRulesStr;
  if (typeof raw === 'string' && raw.length > 0) {
    return `違反ルール ${raw}`;
  }
  return alert.description;
}

function XrControlChart({
  chart,
  selectedMetric,
  onMetricChange,
  selectedPattern,
  onPatternChange,
  availablePatterns,
}: {
  chart: RbarChart | null;
  selectedMetric: ManufacturingMetric;
  onMetricChange: (metric: ManufacturingMetric) => void;
  selectedPattern: number;
  onPatternChange: (pattern: number) => void;
  availablePatterns: number[];
}) {
  const alertPoint = chart?.points.find(point => point.alertId);

  if (!chart) {
    return (
      <Card className="rounded-md">
        <CardHeader className="pb-2">
          <div className="flex flex-col gap-3">
            <CardTitle className="flex items-center gap-2">
              <LineChart className="size-5" />
              {metricLabels[selectedMetric]} X管理図
            </CardTitle>
            <div className="flex flex-wrap gap-1" aria-label="XR metric selector">
              {xrMetricOptions.map(metric => (
                <Button
                  key={metric}
                  type="button"
                  size="sm"
                  variant={selectedMetric === metric ? 'primary' : 'secondary'}
                  aria-pressed={selectedMetric === metric}
                  onClick={() => onMetricChange(metric)}
                  className="h-7 rounded-sm px-2 text-xs"
                >
                  {metricLabels[metric]}
                </Button>
              ))}
            </div>
            <label className="flex w-fit items-center gap-2 caption-01">
              吐出パターン番号
              <select
                aria-label="吐出パターン番号"
                className="h-8 rounded-sm border bg-background px-2 text-sm"
                value={selectedPattern}
                onChange={event => onPatternChange(Number(event.target.value))}
              >
                {availablePatterns.map(pattern => (
                  <option key={pattern} value={pattern}>
                    {pattern}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </CardHeader>
        <CardContent>
          <Alert className="rounded-md">
            <AlertCircle />
            <AlertTitle>X管理図データなし</AlertTitle>
            <AlertDescription>
              選択中の特徴量 / 吐出パターン番号の管理図データがありません。
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const plotValues = chart.points
    .map(point => point.value)
    .concat([
      chart.ucl,
      chart.centerLine,
      chart.lcl,
      chart.upper2Sigma,
      chart.upper1Sigma,
      chart.lower1Sigma,
      chart.lower2Sigma,
    ])
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  const rawMin = Math.min(...plotValues);
  const rawMax = Math.max(...plotValues);
  const rawSpan = rawMax - rawMin;
  const span = rawSpan > 0 ? rawSpan : Math.max(Math.abs(rawMax), 1) * 0.1;
  const domainMin = rawMin - span * 0.18;
  const domainMax = rawMax + span * 0.18;
  const chartData: XrChartRow[] = chart.points.map(point => ({
    ...point,
    label: formatDate(point.date),
  }));
  const sigma2Stroke = '#fde68a';
  const sigma1Stroke = '#86efac';
  const sigmaStrokeWidth = 1;

  return (
    <Card className="rounded-md">
      <CardHeader className="pb-2">
        <div className="flex flex-col gap-3">
          <CardTitle className="flex items-center gap-2">
            <LineChart className="size-5" />
            {metricLabels[selectedMetric]} X管理図
          </CardTitle>
          <div className="flex flex-wrap gap-1" aria-label="XR metric selector">
            {xrMetricOptions.map(metric => (
              <Button
                key={metric}
                type="button"
                size="sm"
                variant={selectedMetric === metric ? 'primary' : 'secondary'}
                aria-pressed={selectedMetric === metric}
                onClick={() => onMetricChange(metric)}
                className="h-7 rounded-sm px-2 text-xs"
              >
                {metricLabels[metric]}
              </Button>
            ))}
          </div>
          <label className="flex w-fit items-center gap-2 caption-01">
            吐出パターン番号
            <select
              aria-label="吐出パターン番号"
              className="h-8 rounded-sm border bg-background px-2 text-sm"
              value={selectedPattern}
              onChange={event => onPatternChange(Number(event.target.value))}
            >
              {availablePatterns.map(pattern => (
                <option key={pattern} value={pattern}>
                  {pattern}
                </option>
              ))}
            </select>
          </label>
        </div>
      </CardHeader>
      <CardContent>
        <div
          role="img"
          aria-label={`${metricLabels[selectedMetric]} 吐出パターン${selectedPattern} X管理図`}
          className="h-72 w-full"
        >
          <ResponsiveContainer width="100%" height="100%">
            <RechartsLineChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
              <XAxis
                dataKey="label"
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: 'var(--border)' }}
                minTickGap={24}
              />
              <YAxis
                domain={[domainMin, domainMax]}
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={56}
                tickFormatter={value => Number(value).toFixed(3)}
              />
              <Tooltip
                cursor={{ stroke: 'var(--muted-foreground)', strokeDasharray: '4 4' }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) {
                    return null;
                  }
                  const point = payload[0]?.payload as XrChartRow | undefined;
                  if (!point) {
                    return null;
                  }
                  return (
                    <div className="rounded-md border bg-background px-3 py-2 shadow-sm caption-01">
                      <div className="font-medium">{point.date}</div>
                      <div className="mt-1">値 {point.value.toFixed(4)}</div>
                      {point.violationRules?.length ? (
                        <div className="mt-1 text-warning">
                          違反ルール {point.violationRules.join(',')}
                        </div>
                      ) : null}
                    </div>
                  );
                }}
              />
              {chart.upper2Sigma != null ? (
                <ReferenceLine
                  y={chart.upper2Sigma}
                  stroke={sigma2Stroke}
                  strokeWidth={sigmaStrokeWidth}
                  strokeDasharray="4 4"
                />
              ) : null}
              {chart.lower2Sigma != null ? (
                <ReferenceLine
                  y={chart.lower2Sigma}
                  stroke={sigma2Stroke}
                  strokeWidth={sigmaStrokeWidth}
                  strokeDasharray="4 4"
                />
              ) : null}
              {chart.upper1Sigma != null ? (
                <ReferenceLine
                  y={chart.upper1Sigma}
                  stroke={sigma1Stroke}
                  strokeWidth={sigmaStrokeWidth}
                  strokeDasharray="3 3"
                />
              ) : null}
              {chart.lower1Sigma != null ? (
                <ReferenceLine
                  y={chart.lower1Sigma}
                  stroke={sigma1Stroke}
                  strokeWidth={sigmaStrokeWidth}
                  strokeDasharray="3 3"
                />
              ) : null}
              <ReferenceLine
                y={chart.ucl}
                stroke="var(--destructive-foreground)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                label={{
                  value: 'UCL',
                  position: 'insideTopRight',
                  fill: 'var(--muted-foreground)',
                  fontSize: 10,
                }}
              />
              <ReferenceLine
                y={chart.lcl}
                stroke="var(--destructive-foreground)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                label={{
                  value: 'LCL',
                  position: 'insideBottomRight',
                  fill: 'var(--muted-foreground)',
                  fontSize: 10,
                }}
              />
              <ReferenceLine
                y={chart.centerLine}
                stroke="var(--muted-foreground)"
                strokeWidth={1.2}
                strokeDasharray="2 3"
                label={{
                  value: 'CL',
                  position: 'insideTopRight',
                  fill: 'var(--muted-foreground)',
                  fontSize: 10,
                }}
              />
              <Line
                type="monotone"
                dataKey="value"
                name="値"
                stroke="var(--primary)"
                strokeWidth={2.4}
                dot={props => {
                  const { cx, cy, payload, key, ...rest } = props;
                  if (cx == null || cy == null) {
                    return <g key={key} />;
                  }
                  const isAlert = Boolean(payload?.alertId);
                  return (
                    <Dot
                      {...rest}
                      key={key}
                      cx={cx}
                      cy={cy}
                      r={isAlert ? 5 : 3.5}
                      fill={isAlert ? 'var(--warning)' : 'var(--primary)'}
                      stroke={isAlert ? 'var(--warning)' : 'var(--primary)'}
                    />
                  );
                }}
                activeDot={{ r: 6 }}
                isAnimationActive={false}
              />
            </RechartsLineChart>
          </ResponsiveContainer>
        </div>
        {alertPoint ? (
          <div className="mt-2 inline-flex rounded-sm bg-muted px-2 py-1 caption-01">
            {formatDate(alertPoint.date)}
            {alertPoint.violationRules?.length
              ? ` 違反ルール ${alertPoint.violationRules.join(',')}`
              : ''}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function AlertList({
  alerts,
  selectedMetric,
  selectedPattern,
}: {
  alerts: ManufacturingAlert[];
  selectedMetric: ManufacturingMetric;
  selectedPattern: number;
}) {
  const filtered = alerts.filter(alert => {
    if (alert.metric !== selectedMetric) {
      return false;
    }
    const pattern = alert.evidence?.pattern;
    return pattern === undefined || pattern === selectedPattern;
  });

  if (!filtered.length) {
    return (
      <Alert className="rounded-md">
        <AlertCircle />
        <AlertTitle>アラートなし</AlertTitle>
        <AlertDescription>
          選択中の特徴量 / 吐出パターンで検知された業務アラートはありません。
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {filtered.map(alert => (
        <Link
          key={alert.id}
          to={`${PATHS.CHAT_EMPTY}?alertId=${encodeURIComponent(alert.id)}`}
          className={cn(
            'block rounded-md border p-4 no-underline transition-colors hover:bg-muted',
            alert.severity === 'critical' && 'border-destructive-foreground',
            alert.severity === 'warning' && 'border-warning'
          )}
        >
          <div className="mb-2 flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2">
              {alert.alertType === 'prediction_ai' ? (
                <BrainCircuit className="size-4 shrink-0 text-primary" />
              ) : (
                <ShieldAlert className="size-4 shrink-0 text-warning" />
              )}
              <span className="body truncate">{alert.title}</span>
            </div>
            <Badge
              variant={alert.severity === 'critical' ? 'destructive' : 'warning'}
              className="rounded-sm"
            >
              {alert.severity}
            </Badge>
          </div>
          <div className="caption-01 text-muted-foreground">
            {metricLabels[alert.metric]} / {formatDate(alert.date)} / 実績 {formatAlertValue(alert)}
          </div>
          <div className="mt-1 caption-01 text-muted-foreground">{formatViolationRules(alert)}</div>
        </Link>
      ))}
    </div>
  );
}

function AlertDetail({ alertId }: { alertId: string }) {
  const { data: alert, isLoading, isError } = useManufacturingAlert(alertId);

  if (isLoading) {
    return (
      <Card className="rounded-md">
        <CardContent className="p-4 body-secondary">Loading alert insight...</CardContent>
      </Card>
    );
  }

  if (isError || !alert) {
    return (
      <Alert variant="destructive" className="rounded-md">
        <AlertTriangle />
        <AlertTitle>Alert unavailable</AlertTitle>
        <AlertDescription>アラート詳細を取得できませんでした。</AlertDescription>
      </Alert>
    );
  }

  return (
    <Card className="rounded-md">
      <CardHeader className="pb-3">
        <div className="mb-3">
          <Button asChild variant="ghost" size="sm">
            <Link to={PATHS.DASHBOARD}>
              <ArrowLeft className="size-4" />
              Dashboard
            </Link>
          </Button>
        </div>
        <CardTitle className="flex items-center gap-2">
          <Bot className="size-5" />
          アラート考察
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="heading-05">{alert.title}</div>
          <div className="mt-1 caption-01 text-muted-foreground">
            {metricLabels[alert.metric]} / {formatDate(alert.date)} / {alert.ruleId}
          </div>
        </div>
        <Alert
          variant={alert.severity === 'critical' ? 'destructive' : 'warning'}
          className="rounded-md"
        >
          <AlertTriangle />
          <AlertTitle>{formatViolationRules(alert)}</AlertTitle>
          <AlertDescription>
            実績 {formatAlertValue(alert)}
            {alert.controlLimit !== null
              ? ` / 管理限界 ${alert.controlLimit.toLocaleString('ja-JP', {
                  maximumFractionDigits: 4,
                })}`
              : ''}
          </AlertDescription>
        </Alert>
        <div className="rounded-md border p-4">
          <div className="mb-2 flex items-center gap-2 heading-06">
            <RefreshCw className="size-4" />
            Insight
          </div>
          <p className="body-secondary">{alert.insight ?? '考察はまだ生成されていません。'}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const { alertId } = useParams();
  const { data, isLoading, isError } = useManufacturingDashboard();
  const [selectedMetric, setSelectedMetric] = useState<ManufacturingMetric>(
    'a_agent_flow_pressure'
  );
  const [selectedPattern, setSelectedPattern] = useState<number>(1);

  const availablePatterns = useMemo(() => {
    if (!data) {
      return [1];
    }
    const fromMetric = Object.keys(data.xrCharts?.[selectedMetric] ?? {})
      .map(Number)
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    if (fromMetric.length) {
      return fromMetric;
    }
    return data.availablePatterns?.length ? data.availablePatterns : [1];
  }, [data, selectedMetric]);

  useEffect(() => {
    if (!availablePatterns.includes(selectedPattern)) {
      setSelectedPattern(availablePatterns[0] ?? 1);
    }
  }, [availablePatterns, selectedPattern]);

  if (isLoading) {
    return (
      <main className="flex min-h-svh items-center justify-center bg-background p-6">
        <div role="status" className="body-secondary">
          Loading manufacturing dashboard...
        </div>
      </main>
    );
  }

  const dashboard =
    data && typeof data === 'object' && 'summary' in data && 'range' in data ? data : null;

  if (isError || !dashboard) {
    return (
      <main className="flex min-h-svh items-center justify-center bg-background p-6">
        <Alert variant="destructive" className="max-w-md rounded-md">
          <AlertTriangle />
          <AlertTitle>Dashboard data unavailable</AlertTitle>
          <AlertDescription>Manufacturing metrics could not be loaded.</AlertDescription>
        </Alert>
      </main>
    );
  }

  const selectedChart =
    dashboard.xrCharts?.[selectedMetric]?.[String(selectedPattern)] ??
    dashboard.rbarCharts?.[selectedMetric] ??
    dashboard.rbarChart ??
    null;

  const filteredAlertCount = (dashboard.alerts ?? []).filter(alert => {
    if (alert.metric !== selectedMetric) {
      return false;
    }
    const pattern = alert.evidence?.pattern;
    return pattern === undefined || pattern === selectedPattern;
  }).length;

  return (
    <main className="min-h-svh flex-1 overflow-auto bg-background">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b pb-5 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge className="rounded-sm">
                表示 {formatDate(dashboard.range.startDate)} - {formatDate(dashboard.range.endDate)}
              </Badge>
              <Badge type="outline" className="rounded-sm">
                アラート判定 直近7日
              </Badge>
              {dashboard.summary.criticalAlertCount > 0 ? (
                <Badge variant="destructive" className="rounded-sm">
                  critical {dashboard.summary.criticalAlertCount}
                </Badge>
              ) : null}
            </div>
            <h1 className="heading-02">モールド装置 X-R管理図</h1>
          </div>
          <Button asChild variant="secondary" size="sm" className="w-fit">
            <Link to={PATHS.CHAT_EMPTY}>
              <ArrowLeft className="size-4" />
              Chat
            </Link>
          </Button>
        </header>

        <section className="grid gap-3 md:grid-cols-2">
          <Card className="rounded-md">
            <CardContent className="flex items-start gap-3 p-4">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
                <ShieldAlert className="size-5 text-primary" />
              </div>
              <div className="min-w-0">
                <div className="caption-01">業務アラート（全体）</div>
                <div data-testid="business-alert-count" className="heading-03 mt-1">
                  {dashboard.summary.businessRuleAlertCount}件
                </div>
                <div className="caption-01 mt-1">新JIS 違反ルール検知</div>
              </div>
            </CardContent>
          </Card>
          <Card className="rounded-md">
            <CardContent className="flex items-start gap-3 p-4">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
                <LineChart className="size-5 text-primary" />
              </div>
              <div className="min-w-0">
                <div className="caption-01">選択中のアラート</div>
                <div className="heading-03 mt-1">{filteredAlertCount}件</div>
                <div className="caption-01 mt-1">
                  {metricLabels[selectedMetric]} / パターン{selectedPattern}
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)]">
          <XrControlChart
            chart={selectedChart}
            selectedMetric={selectedMetric}
            onMetricChange={setSelectedMetric}
            selectedPattern={selectedPattern}
            onPatternChange={setSelectedPattern}
            availablePatterns={availablePatterns}
          />
          {alertId ? (
            <AlertDetail alertId={alertId} />
          ) : (
            <Card className="rounded-md">
              <CardHeader className="pb-2">
                <CardTitle>業務アラート一覧</CardTitle>
              </CardHeader>
              <CardContent>
                <AlertList
                  alerts={dashboard.alerts ?? []}
                  selectedMetric={selectedMetric}
                  selectedPattern={selectedPattern}
                />
              </CardContent>
            </Card>
          )}
        </section>
      </div>
    </main>
  );
}
