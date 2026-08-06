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

"""Load Noritz mold-machine Phase 0/1/2 pipeline outputs for the dashboard."""

from __future__ import annotations

import ast
import csv
import io
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from app.manufacturing.config import (
    DETECTION_DAYS as CONFIG_DETECTION_DAYS,
)
from app.manufacturing.config import (
    JIS_RULES_DESCRIPTION,
)
from app.manufacturing.config import (
    PLOT_DAYS as CONFIG_PLOT_DAYS,
)
from app.manufacturing.domain.anomaly_scores import (
    DEFAULT_ANOMALY_SCORE_THRESHOLD,
    AnomalyScoreAggregates,
    empty_anomaly_scores,
)
from app.manufacturing.domain.models import (
    DailyCountChart,
    DailyCountPoint,
    ManufacturingAlert,
    ManufacturingDailyRecord,
    ManufacturingDashboard,
    ManufacturingRange,
    ManufacturingSummary,
    MetricName,
    RbarChart,
    RbarChartPoint,
)

from app.manufacturing.infrastructure.mold_paths import (
    PHASE0_CONTROL_LIMITS_FILE,
    get_mold_data_dir,
    get_phase0_control_limits_path,
)
DETECTION_DAYS = CONFIG_DETECTION_DAYS
BUSINESS_RULE_ID = "jis.xr.violation_rules"
RULE_VERSION = "1.0.0"
EXCEL_SERIAL_EPOCH = date(1899, 12, 30)

# Pipeline Japanese column -> API metric key
TARGET_COLUMN_TO_METRIC: dict[str, MetricName] = {
    "A剤流圧(Mpa)": "a_agent_flow_pressure",
    "B剤流圧(Mpa)": "b_agent_flow_pressure",
    "A剤タンク1圧力(Mpa)": "a_tank1_pressure",
    "A剤タンク2圧力(Mpa)": "a_tank2_pressure",
    "B剤タンク1圧力(Mpa)": "b_tank1_pressure",
    "B剤タンク2圧力(Mpa)": "b_tank2_pressure",
    "A剤配合比速度(Hz)": "a_mix_ratio_speed",
    "B剤配合比速度(Hz)": "b_mix_ratio_speed",
    "生産総合流速(％)": "production_flow_rate",
    "生産吐出時間(sec)": "production_discharge_time",
}

METRIC_TO_TARGET_COLUMN: dict[MetricName, str] = {
    metric: column for column, metric in TARGET_COLUMN_TO_METRIC.items()
}

METRIC_LABELS: dict[MetricName, str] = {
    "a_agent_flow_pressure": "A剤流圧",
    "b_agent_flow_pressure": "B剤流圧",
    "a_tank1_pressure": "A剤タンク1圧力",
    "a_tank2_pressure": "A剤タンク2圧力",
    "b_tank1_pressure": "B剤タンク1圧力",
    "b_tank2_pressure": "B剤タンク2圧力",
    "a_mix_ratio_speed": "A剤配合比速度",
    "b_mix_ratio_speed": "B剤配合比速度",
    "production_flow_rate": "生産総合流速",
    "production_discharge_time": "生産吐出時間",
}

MOLD_METRICS: tuple[MetricName, ...] = tuple(TARGET_COLUMN_TO_METRIC.values())


PLOT_DAYS = CONFIG_PLOT_DAYS


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value.strip()[:10])


def parse_violation_rules(raw: str) -> list[int]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return [int(item) for item in parsed]
    except (SyntaxError, ValueError):
        pass
    return [int(part) for part in text.split(",") if part.strip().isdigit()]


def parse_csv_rows(content: str | bytes) -> list[dict[str, str]]:
    """Parse CSV text/bytes into row dicts (utf-8-sig / cp932 aware)."""
    if isinstance(content, (bytes, bytearray)):
        text: str | None = None
        for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Could not decode uploaded CSV with a supported encoding.")
    else:
        text = content.lstrip("\ufeff")
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def load_daily_stats(data_dir: Path | None = None) -> list[dict[str, str]]:
    path = (data_dir or get_mold_data_dir()) / "phase2_daily_stats.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_control_limits(data_dir: Path | None = None) -> dict:
    path = (
        data_dir / PHASE0_CONTROL_LIMITS_FILE
        if data_dir is not None
        else get_phase0_control_limits_path()
    )
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_anomalies(data_dir: Path | None = None) -> list[dict[str, str]]:
    path = (data_dir or get_mold_data_dir()) / "phase2_anomalies.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_daily_counts(
    data_dir: Path | None = None,
    *,
    scores_by_day: dict[date, float] | None = None,
    anomaly_score_threshold: float = DEFAULT_ANOMALY_SCORE_THRESHOLD,
) -> DailyCountChart | None:
    path = (data_dir or get_mold_data_dir()) / "phase3_daily_data_counts.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    daily_counts = payload.get("daily_counts") or {}
    max_scores = scores_by_day if scores_by_day is not None else {}
    points = [
        DailyCountPoint(
            date=date.fromisoformat(day),
            count=int(count),
            max_anomaly_score=max_scores.get(date.fromisoformat(day)),
        )
        for day, count in sorted(daily_counts.items())
    ]
    return DailyCountChart(
        points=points,
        anomaly_score_threshold=anomaly_score_threshold,
    )


def parse_production_day(raw: str) -> date | None:
    """Parse 生産日 as ISO date, slash date, or Excel serial day number."""
    value = (raw or "").strip()
    if not value:
        return None
    if "T" in value:
        value = value.split("T", 1)[0]
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    if "/" in value:
        parts = value.split("/")
        if len(parts) == 3:
            try:
                year, month, day = (int(parts[0]), int(parts[1]), int(parts[2]))
                return date(year, month, day)
            except ValueError:
                return None
    try:
        serial = float(value)
    except ValueError:
        return None
    try:
        return EXCEL_SERIAL_EPOCH + timedelta(days=int(serial))
    except OverflowError:
        return None


def resolve_alert_anomaly_score(
    *,
    day: date,
    pattern: int | None,
    scores_by_day_pattern: dict[tuple[date, int], float],
    scores_by_day: dict[date, float],
) -> float | None:
    """Pick the anomaly score for a selected alert from prediction aggregates."""
    if pattern is not None:
        score = scores_by_day_pattern.get((day, pattern))
        if score is not None:
            return score
    return scores_by_day.get(day)


def classify_phase2_csv_rows(
    rows: list[dict[str, str]],
) -> str | None:
    """Return 'daily_stats', 'anomalies', or None from CSV headers."""
    if not rows:
        return None
    headers = {key.strip() for key in rows[0]}
    if "平均" in headers and "ターゲットカラム" in headers:
        return "daily_stats"
    if "平均値" in headers and ("違反ルール" in headers or "違反ルール_str" in headers):
        return "anomalies"
    return None


def resolve_display_windows(
    all_dates: list[date],
) -> tuple[date, date, date]:
    """Return (latest, plot_start, alert_start)."""
    if not all_dates:
        today = date.today()
        return today, today, today
    latest = max(all_dates)
    plot_start = latest - timedelta(days=PLOT_DAYS - 1)
    alert_start = latest - timedelta(days=DETECTION_DAYS - 1)
    return latest, plot_start, alert_start


def build_anomaly_lookup(
    anomaly_rows: list[dict[str, str]],
) -> dict[tuple[MetricName, int, date], dict]:
    lookup: dict[tuple[MetricName, int, date], dict] = {}
    for row in anomaly_rows:
        target = row.get("ターゲットカラム", "")
        metric = TARGET_COLUMN_TO_METRIC.get(target)
        if metric is None:
            continue
        pattern = int(float(row["吐出パターン番号"]))
        day = parse_iso_date(row["注入開始日"])
        rules = parse_violation_rules(
            row.get("違反ルール", row.get("違反ルール_str", ""))
        )
        lookup[(metric, pattern, day)] = {
            "value": float(row["平均値"]),
            "rules": rules,
            "rules_str": row.get("違反ルール_str") or ",".join(str(r) for r in rules),
            "cl": float(row["CL"]),
            "ucl": float(row["UCL_3sigma"]),
            "lcl": float(row["LCL_3sigma"]),
        }
    return lookup


def build_xr_charts_and_alerts(
    data_dir: Path | None = None,
    *,
    daily_rows: list[dict[str, str]] | None = None,
    anomaly_rows: list[dict[str, str]] | None = None,
    anomaly_scores: AnomalyScoreAggregates | None = None,
) -> tuple[
    dict[MetricName, dict[str, RbarChart]],
    list[ManufacturingAlert],
    list[int],
    date,
    date,
]:
    data_dir = data_dir or get_mold_data_dir()
    if daily_rows is None:
        daily_rows = load_daily_stats(data_dir)
    if anomaly_rows is None:
        anomaly_rows = load_anomalies(data_dir)
    control_limits_payload = load_control_limits()
    anomaly_lookup = build_anomaly_lookup(anomaly_rows)
    scores = anomaly_scores or empty_anomaly_scores()
    scores_by_day = scores.by_day
    scores_by_day_pattern = scores.by_day_pattern

    control_limits = control_limits_payload.get("control_limits", {})

    # Group daily stats: metric -> pattern -> [(date, mean)]
    grouped: dict[MetricName, dict[int, list[tuple[date, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    all_dates: list[date] = []
    patterns: set[int] = set()

    for row in daily_rows:
        target = row.get("ターゲットカラム", "")
        metric = TARGET_COLUMN_TO_METRIC.get(target)
        if metric is None:
            continue
        pattern = int(float(row["吐出パターン番号"]))
        day = parse_iso_date(row["注入開始日"])
        value = float(row["平均"])
        grouped[metric][pattern].append((day, value))
        all_dates.append(day)
        patterns.add(pattern)

    latest, plot_start, alert_start = resolve_display_windows(all_dates)

    xr_charts: dict[MetricName, dict[str, RbarChart]] = {}
    alerts: list[ManufacturingAlert] = []

    for metric, by_pattern in grouped.items():
        target_column = METRIC_TO_TARGET_COLUMN[metric]
        metric_limits = control_limits.get(target_column, {})
        charts_for_metric: dict[str, RbarChart] = {}

        for pattern, points in by_pattern.items():
            points_sorted = sorted(points, key=lambda item: item[0])
            plot_points = [
                (day, value) for day, value in points_sorted if day >= plot_start
            ]
            if not plot_points:
                continue

            limits = metric_limits.get(str(pattern)) or metric_limits.get(pattern) or {}
            center_line = float(limits.get("CL", 0.0))
            ucl = float(limits.get("UCL", 0.0))
            lcl = float(limits.get("LCL", 0.0))
            upper_2sigma = float(limits["upper_2sigma"]) if "upper_2sigma" in limits else None
            upper_1sigma = float(limits["upper_1sigma"]) if "upper_1sigma" in limits else None
            lower_1sigma = float(limits["lower_1sigma"]) if "lower_1sigma" in limits else None
            lower_2sigma = float(limits["lower_2sigma"]) if "lower_2sigma" in limits else None

            chart_points: list[RbarChartPoint] = []
            for day, value in plot_points:
                anomaly = anomaly_lookup.get((metric, pattern, day))
                alert_id: str | None = None
                violation_rules: list[int] = []

                # Alert highlighting only for the last DETECTION_DAYS window.
                if day >= alert_start and anomaly and anomaly["rules"]:
                    violation_rules = anomaly["rules"]
                    alert_id = (
                        f"jis-xr-{day.isoformat()}-{metric.replace('_', '-')}"
                        f"-p{pattern}"
                    )
                    rule_labels = "、".join(
                        f"ルール{rule}:{JIS_RULES_DESCRIPTION.get(rule, '')}"
                        for rule in violation_rules
                    )
                    alerts.append(
                        ManufacturingAlert(
                            id=alert_id,
                            dedup_key=f"business_rule:jis_xr:{metric}:{pattern}:{day.isoformat()}",
                            alert_type="business_rule",
                            severity="warning"
                            if 1 not in violation_rules
                            else "critical",
                            status="firing",
                            source="phase2_xr",
                            metric=metric,
                            date=day,
                            title=(
                                f"{METRIC_LABELS[metric]} / 吐出パターン{pattern} "
                                f"でJIS管理図違反を検知"
                            ),
                            description=rule_labels
                            or "新JIS X-R管理図の違反ルールに該当",
                            actual=float(anomaly["value"]),
                            control_limit=float(anomaly["ucl"]),
                            center_line=float(anomaly["cl"]),
                            rule_id=BUSINESS_RULE_ID,
                            rule_version=RULE_VERSION,
                            evidence={
                                "pattern": pattern,
                                "violationRules": violation_rules,
                                "violationRulesStr": anomaly["rules_str"],
                                "violationRuleDetails": [
                                    {
                                        "rule": rule,
                                        "description": JIS_RULES_DESCRIPTION.get(rule, ""),
                                    }
                                    for rule in violation_rules
                                ],
                                "ucl": float(anomaly["ucl"]),
                                "lcl": float(anomaly["lcl"]),
                                "cl": float(anomaly["cl"]),
                                "targetColumn": target_column,
                            },
                            anomaly_score=resolve_alert_anomaly_score(
                                day=day,
                                pattern=pattern,
                                scores_by_day_pattern=scores_by_day_pattern,
                                scores_by_day=scores_by_day,
                            ),
                        )
                    )

                chart_points.append(
                    RbarChartPoint(
                        date=day,
                        value=round(value, 6),
                        alert_id=alert_id,
                        violation_rules=violation_rules,
                        pattern=pattern,
                    )
                )

            charts_for_metric[str(pattern)] = RbarChart(
                metric=metric,
                pattern=pattern,
                center_line=round(center_line, 6),
                ucl=round(ucl, 6),
                lcl=round(lcl, 6),
                upper_2sigma=round(upper_2sigma, 6) if upper_2sigma is not None else None,
                upper_1sigma=round(upper_1sigma, 6) if upper_1sigma is not None else None,
                lower_1sigma=round(lower_1sigma, 6) if lower_1sigma is not None else None,
                lower_2sigma=round(lower_2sigma, 6) if lower_2sigma is not None else None,
                points=chart_points,
            )

        if charts_for_metric:
            xr_charts[metric] = charts_for_metric

    alerts.sort(key=lambda alert: (alert.date, alert.metric, alert.id), reverse=True)
    return xr_charts, alerts, sorted(patterns), plot_start, latest


def build_stub_series(
    plot_start: date,
    latest: date,
    alerts: list[ManufacturingAlert],
) -> list[ManufacturingDailyRecord]:
    """Minimal daily series so existing dashboard summary/timeline keep working."""
    alert_ids_by_date: dict[str, list[str]] = defaultdict(list)
    for alert in alerts:
        alert_ids_by_date[alert.date.isoformat()].append(alert.id)

    series: list[ManufacturingDailyRecord] = []
    day_count = (latest - plot_start).days + 1
    for offset in range(day_count):
        day = plot_start + timedelta(days=offset)
        series.append(
            ManufacturingDailyRecord(
                date=day,
                lots_produced=0,
                total_coating_length_m=0.0,
                bleedout_count=0,
                bleedout_rate=0.0,
                coating_length_category="-",
                coating_length_avg_m=0.0,
                product_type="モールド",
                coater_temperature=0.0,
                coater_temperature_range=0.0,
                coater_humidity=0.0,
                coater_humidity_range=0.0,
                pump_pressure=0.0,
                pump_pressure_range=0.0,
                drying_zone1_temperature=0.0,
                drying_zone1_temperature_range=0.0,
                drying_zone2_temperature=0.0,
                drying_zone2_temperature_range=0.0,
                uv_irradiance=0.0,
                uv_irradiance_range=0.0,
                lamp_lighting_hours=0.0,
                chamber_o2_concentration=0.0,
                chamber_o2_concentration_range=0.0,
                uv_roll_temperature=0.0,
                uv_roll_temperature_range=0.0,
                alert_ids=alert_ids_by_date.get(day.isoformat(), []),
            )
        )
    return series


def default_chart_for_metric(
    xr_charts: dict[MetricName, dict[str, RbarChart]],
    metric: MetricName,
) -> RbarChart | None:
    charts = xr_charts.get(metric)
    if not charts:
        return None
    # Prefer pattern "1" when present, else first available pattern.
    if "1" in charts:
        return charts["1"]
    return next(iter(charts.values()))


class MoldDashboardProvider:
    """Builds a full ManufacturingDashboard from Phase 0/2 pipeline outputs."""

    def has_uploaded_data(
        self,
        data_dir: Path | None = None,
        *,
        session_id: str | None = None,
    ) -> bool:
        from app.manufacturing.infrastructure.mold_session import (
            has_uploaded_dashboard_data,
        )

        return has_uploaded_dashboard_data(data_dir, session_id=session_id)

    def get_active_source_file(self, data_dir: Path | None = None) -> str | None:
        from app.manufacturing.infrastructure.mold_session import (
            get_active_source_file,
        )

        return get_active_source_file(data_dir)

    def persist_phase2_upload(
        self,
        *,
        daily_rows: list[dict[str, str]],
        anomaly_rows: list[dict[str, str]] | None = None,
        source_file: str,
        data_dir: Path | None = None,
    ) -> None:
        from app.manufacturing.infrastructure.mold_session import (
            persist_phase2_outputs,
            write_upload_manifest,
        )

        persist_phase2_outputs(
            data_dir=data_dir,
            daily_rows=daily_rows,
            anomaly_rows=anomaly_rows,
        )
        write_upload_manifest(
            data_dir=data_dir,
            source_file=source_file,
            upload_kind="phase2",
            metadata={"daily_rows": len(daily_rows)},
        )

    def build_empty(self) -> ManufacturingDashboard:
        from app.manufacturing.infrastructure.mold_session import is_preserve_file_on_reload

        today = date.today()
        return ManufacturingDashboard(
            data_status="empty",
            preserve_file_on_reload=is_preserve_file_on_reload(),
            prediction_status="unavailable",
            range=ManufacturingRange(
                start_date=today,
                end_date=today,
                grain="day",
            ),
            summary=ManufacturingSummary(
                latest_date=today,
                lots_produced=0,
                total_coating_length_m=0.0,
                bleedout_count=0,
                bleedout_rate=0.0,
                alert_count=0,
                prediction_alert_count=0,
                business_rule_alert_count=0,
                critical_alert_count=0,
            ),
            series=[],
            rbar_chart=None,
            rbar_charts={},
            xr_charts={},
            available_patterns=[],
            daily_count_chart=None,
            jis_rule_descriptions={
                str(rule): description
                for rule, description in JIS_RULES_DESCRIPTION.items()
            },
            alerts=[],
        )

    def resolve_plot_start(
        self,
        *,
        daily_rows: list[dict[str, str]] | None = None,
    ) -> date:
        rows = daily_rows if daily_rows is not None else load_daily_stats()
        all_dates = [
            parse_iso_date(row["注入開始日"])
            for row in rows
            if row.get("注入開始日")
        ]
        if not all_dates:
            return date.today()
        _, plot_start, _ = resolve_display_windows(all_dates)
        return plot_start

    def build(
        self,
        *,
        daily_rows: list[dict[str, str]] | None = None,
        anomaly_rows: list[dict[str, str]] | None = None,
        anomaly_scores: AnomalyScoreAggregates | None = None,
    ) -> ManufacturingDashboard:
        scores = anomaly_scores or empty_anomaly_scores()

        xr_charts, alerts, patterns, plot_start, latest = build_xr_charts_and_alerts(
            daily_rows=daily_rows,
            anomaly_rows=anomaly_rows,
            anomaly_scores=scores,
        )
        series = build_stub_series(plot_start, latest, alerts)

        rbar_charts = {}
        for metric in MOLD_METRICS:
            chart = default_chart_for_metric(xr_charts, metric)
            if chart is not None:
                rbar_charts[metric] = chart

        default_metric = next(iter(rbar_charts), None)
        business_rule_alert_count = sum(
            1 for alert in alerts if alert.alert_type == "business_rule"
        )
        from app.manufacturing.infrastructure.mold_session import is_preserve_file_on_reload

        return ManufacturingDashboard(
            data_status="ready",
            preserve_file_on_reload=is_preserve_file_on_reload(),
            source_file=self.get_active_source_file(),
            prediction_status=scores.status,
            range=ManufacturingRange(
                start_date=plot_start,
                end_date=latest,
                grain="day",
            ),
            summary=ManufacturingSummary(
                latest_date=latest,
                lots_produced=0,
                total_coating_length_m=0.0,
                bleedout_count=0,
                bleedout_rate=0.0,
                alert_count=len(alerts),
                prediction_alert_count=0,
                business_rule_alert_count=business_rule_alert_count,
                critical_alert_count=sum(
                    1 for alert in alerts if alert.severity == "critical"
                ),
            ),
            series=series,
            rbar_chart=rbar_charts.get(default_metric) if default_metric else None,
            rbar_charts=rbar_charts,
            xr_charts=xr_charts,
            available_patterns=patterns,
            daily_count_chart=load_daily_counts(
                scores_by_day=scores.by_day,
                anomaly_score_threshold=scores.threshold,
            ),
            jis_rule_descriptions={
                str(rule): description
                for rule, description in JIS_RULES_DESCRIPTION.items()
            },
            alerts=alerts,
        )
