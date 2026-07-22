export type ManufacturingMetric =
  | 'lots_produced'
  | 'bleedout_rate'
  | 'coater_temperature'
  | 'coater_humidity'
  | 'pump_pressure'
  | 'drying_zone1_temperature'
  | 'drying_zone2_temperature'
  | 'uv_irradiance'
  | 'lamp_lighting_hours'
  | 'chamber_o2_concentration'
  | 'uv_roll_temperature'
  | 'a_agent_flow_pressure'
  | 'b_agent_flow_pressure'
  | 'a_tank1_pressure'
  | 'a_tank2_pressure'
  | 'b_tank1_pressure'
  | 'b_tank2_pressure'
  | 'a_mix_ratio_speed'
  | 'b_mix_ratio_speed'
  | 'production_flow_rate'
  | 'production_discharge_time';

export type AlertType = 'prediction_ai' | 'spc_rbar' | 'business_rule';
export type AlertSeverity = 'info' | 'warning' | 'critical';
export type InsightStatus = 'not_requested' | 'ready' | 'error';
export type PredictionStatus = 'available' | 'local' | 'running' | 'unavailable' | 'error';

export type ManufacturingDailyRecord = {
  date: string;
  lotsProduced: number;
  totalCoatingLengthM: number;
  bleedoutCount: number;
  bleedoutRate: number;
  coatingLengthCategory: string;
  coatingLengthAvgM: number;
  productType: string;
  coaterTemperature: number;
  coaterTemperatureRange: number;
  coaterHumidity: number;
  coaterHumidityRange: number;
  pumpPressure: number;
  pumpPressureRange: number;
  dryingZone1Temperature: number;
  dryingZone1TemperatureRange: number;
  dryingZone2Temperature: number;
  dryingZone2TemperatureRange: number;
  uvIrradiance: number;
  uvIrradianceRange: number;
  lampLightingHours: number;
  chamberO2Concentration: number;
  chamberO2ConcentrationRange: number;
  uvRollTemperature: number;
  uvRollTemperatureRange: number;
  predictionProbability: number | null;
  predictionLabel: string | null;
  alertIds: string[];
};

export type ManufacturingRange = {
  startDate: string;
  endDate: string;
  grain: 'day';
};

export type ManufacturingSummary = {
  latestDate: string;
  lotsProduced: number;
  totalCoatingLengthM: number;
  bleedoutCount: number;
  bleedoutRate: number;
  alertCount: number;
  predictionAlertCount: number;
  businessRuleAlertCount: number;
  criticalAlertCount: number;
};

export type ManufacturingAlert = {
  id: string;
  dedupKey: string;
  alertType: AlertType;
  severity: AlertSeverity;
  status: 'firing' | 'resolved';
  source: string;
  metric: ManufacturingMetric;
  date: string;
  title: string;
  description: string;
  actual: number;
  threshold: number | null;
  controlLimit: number | null;
  centerLine: number | null;
  ruleId: string;
  ruleVersion: string;
  evidence: Record<string, unknown>;
  insightStatus: InsightStatus;
  insight: string | null;
};

export type RbarChartPoint = {
  date: string;
  value: number;
  alertId: string | null;
  violationRules?: number[];
  pattern?: number | null;
};

export type RbarChart = {
  metric: ManufacturingMetric;
  pattern?: number | null;
  centerLine: number;
  ucl: number;
  lcl: number;
  upper2Sigma?: number | null;
  upper1Sigma?: number | null;
  lower1Sigma?: number | null;
  lower2Sigma?: number | null;
  points: RbarChartPoint[];
};

export type ManufacturingDashboard = {
  predictionStatus: PredictionStatus;
  range: ManufacturingRange;
  summary: ManufacturingSummary;
  series: ManufacturingDailyRecord[];
  rbarChart: RbarChart | null;
  rbarCharts?: Partial<Record<ManufacturingMetric, RbarChart>>;
  xrCharts?: Partial<Record<ManufacturingMetric, Record<string, RbarChart>>>;
  availablePatterns?: number[];
  alerts?: ManufacturingAlert[];
};
