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

from statistics import mean

from app.manufacturing.models import (
    ManufacturingAlert,
    ManufacturingDailyRecord,
    MetricName,
    PredictionResult,
    RbarChart,
    RbarChartPoint,
)

PREDICTION_ALERT_THRESHOLD = 0.8
R_BAR_RULE_ID = "spc.rbar.beyond_control_limit"
PREDICTION_RULE_ID = "prediction.probability.threshold"
RULE_VERSION = "1.0.0"

# The daily source file has one logical subgroup per day after aggregation.
# Use n=5 constants as a conservative first rational-subgroup approximation.
RATIONAL_SUBGROUP_SIZE = 5
R_CHART_CONSTANTS: dict[int, tuple[float, float]] = {
    2: (0.0, 3.267),
    3: (0.0, 2.574),
    4: (0.0, 2.282),
    5: (0.0, 2.114),
    6: (0.0, 2.004),
    7: (0.076, 1.924),
    8: (0.136, 1.864),
    9: (0.184, 1.816),
    10: (0.223, 1.777),
}

RBAR_METRIC_CONFIG: dict[MetricName, tuple[str, str]] = {
    "coater_temperature": ("coater_temperature_range", "コーター部温度"),
    "coater_humidity": ("coater_humidity_range", "コーター部相対湿度"),
    "pump_pressure": ("pump_pressure_range", "ポンプ圧力"),
    "drying_zone1_temperature": ("drying_zone1_temperature_range", "乾燥ゾーン1温度"),
    "drying_zone2_temperature": ("drying_zone2_temperature_range", "乾燥ゾーン2温度"),
    "uv_irradiance": ("uv_irradiance_range", "UV照度"),
    "chamber_o2_concentration": (
        "chamber_o2_concentration_range",
        "チャンバー内O2濃度",
    ),
    "uv_roll_temperature": ("uv_roll_temperature_range", "UVロール温度"),
}


def detect_prediction_alerts(
    series: list[ManufacturingDailyRecord],
    predictions: list[PredictionResult],
    threshold: float = PREDICTION_ALERT_THRESHOLD,
) -> list[ManufacturingAlert]:
    prediction_by_date = {prediction.date: prediction for prediction in predictions}
    alerts: list[ManufacturingAlert] = []

    for record in series:
        prediction = prediction_by_date.get(record.date)
        if prediction is None:
            continue

        record.prediction_probability = round(prediction.probability, 4)
        record.prediction_label = prediction.label

        if prediction.probability < threshold:
            continue

        alert_id = f"prediction-{record.date.isoformat()}"
        alerts.append(
            ManufacturingAlert(
                id=alert_id,
                dedup_key=f"prediction_ai:bleedout_rate:{record.date.isoformat()}",
                alert_type="prediction_ai",
                severity="critical",
                status="firing",
                source="datarobot_prediction",
                metric="bleedout_rate",
                date=record.date,
                title="予測AIがブリードアウト高リスクを検知",
                description="DataRobot予測確率が運用しきい値を超過しました。",
                actual=round(prediction.probability, 4),
                threshold=threshold,
                rule_id=PREDICTION_RULE_ID,
                rule_version=RULE_VERSION,
                evidence={
                    "probability": round(prediction.probability, 4),
                    "label": prediction.label,
                    "threshold": threshold,
                    "bleedoutRate": record.bleedout_rate,
                },
            )
        )

    return alerts


def detect_spc_rbar_alerts(
    series: list[ManufacturingDailyRecord],
    metric: MetricName = "coater_temperature",
    subgroup_size: int = RATIONAL_SUBGROUP_SIZE,
) -> tuple[list[ManufacturingAlert], RbarChart]:
    range_field, label = RBAR_METRIC_CONFIG.get(
        metric, RBAR_METRIC_CONFIG["coater_temperature"]
    )
    if not series:
        return (
            [],
            RbarChart(
                metric=metric,
                center_line=0.0,
                ucl=0.0,
                lcl=0.0,
                points=[],
            ),
        )

    d3, d4 = R_CHART_CONSTANTS.get(subgroup_size, R_CHART_CONSTANTS[5])
    ranges = [float(getattr(record, range_field)) for record in series]
    raw_center_line = mean(ranges)
    center_line = round(raw_center_line, 4)
    ucl = round(d4 * raw_center_line, 4)
    lcl = round(d3 * raw_center_line, 4)

    points: list[RbarChartPoint] = []
    alerts: list[ManufacturingAlert] = []

    for record in series:
        value = float(getattr(record, range_field))
        alert_id: str | None = None
        is_out_of_control = value > ucl or (lcl > 0 and value < lcl)
        if is_out_of_control:
            alert_id = f"spc-rbar-{record.date.isoformat()}-{metric.replace('_', '-')}"
            limit = ucl if value > ucl else lcl
            alerts.append(
                ManufacturingAlert(
                    id=alert_id,
                    dedup_key=f"spc_rbar:{metric}:{record.date.isoformat()}",
                    alert_type="spc_rbar",
                    severity="warning",
                    status="firing",
                    source="spc",
                    metric=metric,
                    date=record.date,
                    title=f"Rbar管理図で{label}のばらつきを検知",
                    description="日内レンジがRbar管理図の管理限界を超過しました。",
                    actual=value,
                    control_limit=limit,
                    center_line=center_line,
                    rule_id=R_BAR_RULE_ID,
                    rule_version=RULE_VERSION,
                    evidence={
                        "subgroupSize": subgroup_size,
                        "d3": d3,
                        "d4": d4,
                        "ucl": ucl,
                        "lcl": lcl,
                        "range": value,
                    },
                )
            )

        points.append(
            RbarChartPoint(
                date=record.date,
                value=value,
                alert_id=alert_id,
            )
        )

    return alerts, RbarChart(
        metric=metric,
        center_line=center_line,
        ucl=ucl,
        lcl=lcl,
        points=points,
    )


def detect_all_spc_rbar_alerts(
    series: list[ManufacturingDailyRecord],
) -> tuple[list[ManufacturingAlert], dict[MetricName, RbarChart]]:
    alerts: list[ManufacturingAlert] = []
    charts: dict[MetricName, RbarChart] = {}

    for metric in RBAR_METRIC_CONFIG:
        metric_alerts, chart = detect_spc_rbar_alerts(series, metric=metric)
        alerts.extend(metric_alerts)
        charts[metric] = chart

    return alerts, charts
