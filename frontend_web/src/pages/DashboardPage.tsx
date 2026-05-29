import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Bot,
  BrainCircuit,
  Gauge,
  LineChart,
  PackageCheck,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useManufacturingAlert, useManufacturingDashboard } from '@/api/manufacturing/hooks';
import type {
  ManufacturingAlert,
  ManufacturingDailyRecord,
  ManufacturingMetric,
  RbarChart,
} from '@/api/manufacturing/types';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PATHS } from '@/constants/path';
import { cn } from '@/lib/utils';

type SeriesKey = keyof Pick<
  ManufacturingDailyRecord,
  'bleedoutRate' | 'coaterTemperature' | 'coaterHumidity' | 'uvIrradiance'
>;

const dateFormatter = new Intl.DateTimeFormat('ja-JP', {
  month: 'numeric',
  day: 'numeric',
});

const numberFormatter = new Intl.NumberFormat('ja-JP');

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
};

const seriesLabels: Record<SeriesKey, string> = {
  bleedoutRate: 'ブリードアウト率',
  coaterTemperature: 'コーター部温度',
  coaterHumidity: 'コーター部相対湿度',
  uvIrradiance: 'UV照度',
};

const rbarMetricOptions: ManufacturingMetric[] = [
  'coater_temperature',
  'coater_humidity',
  'pump_pressure',
  'drying_zone1_temperature',
  'drying_zone2_temperature',
  'uv_irradiance',
  'chamber_o2_concentration',
  'uv_roll_temperature',
];

function formatDate(value: string) {
  return dateFormatter.format(new Date(`${value}T00:00:00`));
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatAlertValue(alert: ManufacturingAlert) {
  if (alert.alertType === 'prediction_ai') {
    return formatPercent(alert.actual);
  }
  if (alert.metric === 'bleedout_rate') {
    return formatPercent(alert.actual);
  }
  return alert.actual.toLocaleString('ja-JP', { maximumFractionDigits: 4 });
}

function formatSeriesValue(metric: SeriesKey, value: number) {
  if (metric === 'bleedoutRate') {
    return formatPercent(value);
  }
  return value.toLocaleString('ja-JP', { maximumFractionDigits: 2 });
}

function pointsForSeries(series: ManufacturingDailyRecord[], metric: SeriesKey) {
  const values = series.map(item => item[metric]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 100;
  const height = 54;

  return values
    .map((value, index) => {
      const x = series.length === 1 ? width : (index / (series.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

function StatTile({
  icon: Icon,
  label,
  value,
  detail,
  testId,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  testId?: string;
}) {
  return (
    <Card className="rounded-md">
      <CardContent className="flex items-start gap-3 p-4">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
          <Icon className="size-5 text-primary" />
        </div>
        <div className="min-w-0">
          <div className="caption-01">{label}</div>
          <div data-testid={testId} className="heading-03 mt-1">
            {value}
          </div>
          <div className="caption-01 mt-1">{detail}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function DailyAlertTimeline({
  series,
  alerts,
}: {
  series: ManufacturingDailyRecord[];
  alerts: ManufacturingAlert[];
}) {
  const alertById = new Map(alerts.map(alert => [alert.id, alert]));
  const maxLots = Math.max(...series.map(item => item.lotsProduced));

  return (
    <div className="h-80 rounded-md border bg-card p-4">
      <div className="flex h-[calc(100%-2rem)] items-end gap-1">
        {series.map(item => {
          const dayAlerts = item.alertIds.map(id => alertById.get(id)).filter(Boolean);
          const hasCritical = dayAlerts.some(alert => alert?.severity === 'critical');
          const hasAlert = dayAlerts.length > 0;
          const height = `${Math.max((item.lotsProduced / maxLots) * 100, 2)}%`;

          return (
            <div
              key={item.date}
              aria-label={hasAlert ? `${item.date} alert day` : `${item.date} normal day`}
              className="relative flex h-full min-w-0 flex-1 items-end justify-center"
              title={`${formatDate(item.date)} ${numberFormatter.format(item.lotsProduced)}ロット`}
            >
              {hasAlert ? (
                <AlertTriangle
                  className={cn(
                    'absolute top-0 z-10 size-4',
                    hasCritical ? 'text-destructive-foreground' : 'text-warning'
                  )}
                />
              ) : null}
              <div
                className={cn(
                  'w-full rounded-t-sm border-t-2 transition-colors',
                  hasCritical && 'border-destructive-foreground bg-destructive-foreground/70',
                  hasAlert && !hasCritical && 'border-warning bg-warning/70',
                  !hasAlert && 'border-primary bg-primary/45'
                )}
                style={{ height }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex justify-between border-t pt-2 caption-01">
        <span>{formatDate(series[0].date)}</span>
        <span>{formatDate(series.at(-1)?.date ?? series[0].date)}</span>
      </div>
    </div>
  );
}

function TrendLine({ series, metric }: { series: ManufacturingDailyRecord[]; metric: SeriesKey }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="heading-06">{seriesLabels[metric]}</div>
        <div className="code text-muted-foreground">
          {formatSeriesValue(metric, series.at(-1)?.[metric] ?? 0)}
        </div>
      </div>
      <svg
        role="img"
        aria-label={`${seriesLabels[metric]} trend`}
        viewBox="0 0 100 62"
        preserveAspectRatio="none"
        className="h-24 w-full overflow-visible"
      >
        <line x1="0" x2="100" y1="54" y2="54" stroke="var(--border)" strokeWidth="0.8" />
        <polyline
          fill="none"
          points={pointsForSeries(series, metric)}
          stroke="var(--primary)"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2.4"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}

function RbarControlChart({
  chart,
  selectedMetric,
  onMetricChange,
}: {
  chart: RbarChart | null;
  selectedMetric: ManufacturingMetric;
  onMetricChange: (metric: ManufacturingMetric) => void;
}) {
  if (!chart) {
    return (
      <Card className="rounded-md">
        <CardHeader className="pb-2">
          <div className="flex flex-col gap-3">
            <CardTitle className="flex items-center gap-2">
              <LineChart className="size-5" />
              {metricLabels[selectedMetric]} 日内レンジ Rbar管理図
            </CardTitle>
            <div className="flex flex-wrap gap-1" aria-label="Rbar metric selector">
              {rbarMetricOptions.map(metric => (
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
          </div>
        </CardHeader>
        <CardContent>
          <Alert className="rounded-md">
            <AlertCircle />
            <AlertTitle>Rbar管理図データなし</AlertTitle>
            <AlertDescription>
              現在の判定ルールでは管理図データが生成されていません。
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const plotValues = chart.points
    .map(point => point.value)
    .concat([chart.ucl, chart.centerLine, chart.lcl]);
  const rawMin = Math.min(...plotValues);
  const rawMax = Math.max(...plotValues);
  const rawSpan = rawMax - rawMin;
  const span = rawSpan > 0 ? rawSpan : Math.max(Math.abs(rawMax), 1) * 0.1;
  const domainMin = Math.max(0, rawMin - span * 0.18);
  const domainMax = rawMax + span * 0.18;
  const chartTop = 8;
  const chartBottom = 72;
  const scaleY = (value: number) =>
    chartTop + ((domainMax - value) / (domainMax - domainMin)) * (chartBottom - chartTop);
  const points = chart.points
    .map((point, index) => {
      const x = chart.points.length === 1 ? 50 : (index / (chart.points.length - 1)) * 100;
      return `${x.toFixed(2)},${scaleY(point.value).toFixed(2)}`;
    })
    .join(' ');

  return (
    <Card className="rounded-md">
      <CardHeader className="pb-2">
        <div className="flex flex-col gap-3">
          <CardTitle className="flex items-center gap-2">
            <LineChart className="size-5" />
            {metricLabels[selectedMetric]} 日内レンジ Rbar管理図
          </CardTitle>
          <div className="flex flex-wrap gap-1" aria-label="Rbar metric selector">
            {rbarMetricOptions.map(metric => (
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
        </div>
      </CardHeader>
      <CardContent>
        <svg
          role="img"
          aria-label={`${metricLabels[selectedMetric]} 日内レンジ Rbar管理図`}
          viewBox="0 0 100 80"
          preserveAspectRatio="none"
          className="h-72 w-full overflow-visible"
        >
          <rect
            x="0"
            y={chartTop}
            width="100"
            height={chartBottom - chartTop}
            fill="var(--muted)"
            opacity="0.18"
          />
          <line
            x1="0"
            x2="100"
            y1={scaleY(chart.ucl)}
            y2={scaleY(chart.ucl)}
            stroke="var(--destructive-foreground)"
            strokeDasharray="4 3"
            strokeWidth="1.2"
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1="0"
            x2="100"
            y1={scaleY(chart.lcl)}
            y2={scaleY(chart.lcl)}
            stroke="var(--destructive-foreground)"
            strokeDasharray="4 3"
            strokeWidth="1.2"
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1="0"
            x2="100"
            y1={scaleY(chart.centerLine)}
            y2={scaleY(chart.centerLine)}
            stroke="var(--muted-foreground)"
            strokeDasharray="2 3"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
          <polyline
            fill="none"
            points={points}
            stroke="var(--primary)"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2.4"
            vectorEffect="non-scaling-stroke"
          />
          {chart.points.map((point, index) => {
            const x = chart.points.length === 1 ? 50 : (index / (chart.points.length - 1)) * 100;
            return (
              <circle
                key={point.date}
                cx={x}
                cy={scaleY(point.value)}
                r={point.alertId ? 2.2 : 1.5}
                fill={point.alertId ? 'var(--warning)' : 'var(--primary)'}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
        <div className="mt-3 grid gap-2 text-muted-foreground caption-01 sm:grid-cols-4">
          <div>CL {chart.centerLine.toFixed(4)}</div>
          <div>UCL {chart.ucl.toFixed(4)}</div>
          <div>LCL {chart.lcl.toFixed(4)}</div>
          <div>
            表示域 {domainMin.toFixed(4)} - {domainMax.toFixed(4)}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AlertList({ alerts }: { alerts: ManufacturingAlert[] }) {
  if (!alerts.length) {
    return (
      <Alert className="rounded-md">
        <AlertCircle />
        <AlertTitle>アラートなし</AlertTitle>
        <AlertDescription>現在の判定ルールで検知された項目はありません。</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {alerts.map(alert => (
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
          <AlertTitle>{alert.description}</AlertTitle>
          <AlertDescription>
            実績 {formatAlertValue(alert)}
            {alert.threshold !== null ? ` / しきい値 ${formatPercent(alert.threshold)}` : ''}
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
  const [selectedRbarMetric, setSelectedRbarMetric] =
    useState<ManufacturingMetric>('coater_temperature');

  if (isLoading) {
    return (
      <main className="flex min-h-svh items-center justify-center bg-background p-6">
        <div role="status" className="body-secondary">
          Loading manufacturing dashboard...
        </div>
      </main>
    );
  }

  if (isError || !data) {
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

  const latest = data.series.at(-1);
  const selectedRbarChart = data.rbarCharts[selectedRbarMetric] ?? data.rbarChart;

  return (
    <main className="min-h-svh flex-1 overflow-auto bg-background">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b pb-5 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge className="rounded-sm">
                {formatDate(data.range.startDate)} - {formatDate(data.range.endDate)}
              </Badge>
              <Badge
                type={data.predictionStatus === 'available' ? 'default' : 'outline'}
                className="rounded-sm"
              >
                prediction {data.predictionStatus}
              </Badge>
              {data.summary.criticalAlertCount > 0 ? (
                <Badge variant="destructive" className="rounded-sm">
                  critical {data.summary.criticalAlertCount}
                </Badge>
              ) : null}
            </div>
            <h1 className="heading-02">製造ダッシュボード</h1>
          </div>
          <Button asChild variant="secondary" size="sm" className="w-fit">
            <Link to={PATHS.CHAT_EMPTY}>
              <ArrowLeft className="size-4" />
              Chat
            </Link>
          </Button>
        </header>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <StatTile
            icon={BrainCircuit}
            label="予測AIアラート"
            value={`${data.summary.predictionAlertCount}件`}
            detail={
              data.predictionStatus === 'running'
                ? 'DataRobotバッチ予測実行中'
                : 'DataRobot予測しきい値超過'
            }
            testId="prediction-alert-count"
          />
          <StatTile
            icon={ShieldAlert}
            label="業務ロジックアラート"
            value={`${data.summary.businessRuleAlertCount}件`}
            detail="SPC/業務ルール検知"
            testId="business-alert-count"
          />
          <StatTile
            icon={PackageCheck}
            label="最新日ロット"
            value={`${numberFormatter.format(data.summary.lotsProduced)}ロット`}
            detail={`ブリードアウト ${data.summary.bleedoutCount}件`}
          />
          <StatTile
            icon={Gauge}
            label="ブリードアウト率"
            value={formatPercent(data.summary.bleedoutRate)}
            detail={`最新日 ${formatDate(data.summary.latestDate)}`}
          />
        </section>

        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.85fr)]">
          <Card className="rounded-md">
            <CardHeader className="pb-2">
              <CardTitle>日次時系列</CardTitle>
            </CardHeader>
            <CardContent>
              <DailyAlertTimeline series={data.series} alerts={data.alerts} />
            </CardContent>
          </Card>

          <Card className="rounded-md">
            <CardHeader className="pb-2">
              <CardTitle>アラート一覧</CardTitle>
            </CardHeader>
            <CardContent>
              <AlertList alerts={data.alerts} />
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
          <RbarControlChart
            chart={selectedRbarChart}
            selectedMetric={selectedRbarMetric}
            onMetricChange={setSelectedRbarMetric}
          />
          {alertId ? (
            <AlertDetail alertId={alertId} />
          ) : (
            <Card className="rounded-md">
              <CardHeader className="pb-2">
                <CardTitle>最新日の工程値</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-2">
                {[
                  ['塗布長平均', `${(latest?.coatingLengthAvgM ?? 0).toLocaleString('ja-JP')}m`],
                  ['コーター部温度', `${(latest?.coaterTemperature ?? 0).toFixed(2)}℃`],
                  ['コーター部相対湿度', `${(latest?.coaterHumidity ?? 0).toFixed(1)}%`],
                  ['UV照度', `${(latest?.uvIrradiance ?? 0).toFixed(1)}`],
                  [
                    '予測確率',
                    latest?.predictionProbability === null ||
                    latest?.predictionProbability === undefined
                      ? '未取得'
                      : formatPercent(latest.predictionProbability),
                  ],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="flex items-center justify-between gap-3 rounded-md border p-3"
                  >
                    <span className="body-secondary">{label}</span>
                    <span className="code text-right">{value}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </section>

        <section className="grid gap-4 lg:grid-cols-4">
          <TrendLine series={data.series} metric="bleedoutRate" />
          <TrendLine series={data.series} metric="coaterTemperature" />
          <TrendLine series={data.series} metric="coaterHumidity" />
          <TrendLine series={data.series} metric="uvIrradiance" />
        </section>
      </div>
    </main>
  );
}
