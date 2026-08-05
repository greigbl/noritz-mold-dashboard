# Copyright 2026 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MetricName = Literal[
    "lots_produced",
    "bleedout_rate",
    "coater_temperature",
    "coater_humidity",
    "pump_pressure",
    "drying_zone1_temperature",
    "drying_zone2_temperature",
    "uv_irradiance",
    "lamp_lighting_hours",
    "chamber_o2_concentration",
    "uv_roll_temperature",
    # Noritz mold-machine X-R metrics
    "a_agent_flow_pressure",
    "b_agent_flow_pressure",
    "a_tank1_pressure",
    "a_tank2_pressure",
    "b_tank1_pressure",
    "b_tank2_pressure",
    "a_mix_ratio_speed",
    "b_mix_ratio_speed",
    "production_flow_rate",
    "production_discharge_time",
]

AlertType = Literal["prediction_ai", "spc_rbar", "business_rule"]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["firing", "resolved"]
InsightStatus = Literal["not_requested", "ready", "error"]
PredictionStatus = Literal["available", "local", "running", "unavailable", "error"]


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ManufacturingBaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ManufacturingDailyRecord(ManufacturingBaseModel):
    date: date
    lot_id: str | None = None
    lots_produced: int
    total_coating_length_m: float
    bleedout_count: int
    bleedout_rate: float
    coating_length_category: str
    coating_length_avg_m: float
    product_type: str
    coater_temperature: float
    coater_temperature_range: float
    coater_humidity: float
    coater_humidity_range: float
    pump_pressure: float
    pump_pressure_range: float
    drying_zone1_temperature: float
    drying_zone1_temperature_range: float
    drying_zone2_temperature: float
    drying_zone2_temperature_range: float
    uv_irradiance: float
    uv_irradiance_range: float
    lamp_lighting_hours: float
    chamber_o2_concentration: float
    chamber_o2_concentration_range: float
    uv_roll_temperature: float
    uv_roll_temperature_range: float
    prediction_probability: float | None = None
    prediction_label: str | None = None
    alert_ids: list[str] = Field(default_factory=list)


class ManufacturingRange(ManufacturingBaseModel):
    start_date: date
    end_date: date
    grain: Literal["day"]


class ManufacturingSummary(ManufacturingBaseModel):
    latest_date: date
    lots_produced: int
    total_coating_length_m: float
    bleedout_count: int
    bleedout_rate: float
    alert_count: int
    prediction_alert_count: int
    business_rule_alert_count: int
    critical_alert_count: int


class ManufacturingAlert(ManufacturingBaseModel):
    id: str
    dedup_key: str
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    source: str
    metric: MetricName
    date: date
    title: str
    description: str
    actual: float
    threshold: float | None = None
    control_limit: float | None = None
    center_line: float | None = None
    rule_id: str
    rule_version: str
    evidence: dict[str, Any]
    insight_status: InsightStatus = "not_requested"
    insight: str | None = None
    # Max ANOMALY_SCORE for the alert's production day (from live deployment or local fallback).
    anomaly_score: float | None = None


class RbarChartPoint(ManufacturingBaseModel):
    date: date
    value: float
    alert_id: str | None = None
    violation_rules: list[int] = Field(default_factory=list)
    pattern: int | None = None


class RbarChart(ManufacturingBaseModel):
    metric: MetricName
    pattern: int | None = None
    center_line: float
    ucl: float
    lcl: float
    upper_2sigma: float | None = None
    upper_1sigma: float | None = None
    lower_1sigma: float | None = None
    lower_2sigma: float | None = None
    points: list[RbarChartPoint]


class DailyCountPoint(ManufacturingBaseModel):
    date: date
    count: int
    max_anomaly_score: float | None = None


class DailyCountChart(ManufacturingBaseModel):
    points: list[DailyCountPoint]
    anomaly_score_threshold: float = 0.085


class ManufacturingDashboard(ManufacturingBaseModel):
    prediction_status: PredictionStatus
    range: ManufacturingRange
    summary: ManufacturingSummary
    series: list[ManufacturingDailyRecord]
    rbar_chart: RbarChart | None = None
    rbar_charts: dict[MetricName, RbarChart]
    # metric -> pattern(str) -> chart for mold X-R dual selection
    xr_charts: dict[MetricName, dict[str, RbarChart]] = Field(default_factory=dict)
    available_patterns: list[int] = Field(default_factory=list)
    daily_count_chart: DailyCountChart | None = None
    jis_rule_descriptions: dict[str, str] = Field(default_factory=dict)
    alerts: list[ManufacturingAlert]


class PredictionResult(ManufacturingBaseModel):
    date: date
    probability: float
    label: str | None = None
    source_id: str | None = None
