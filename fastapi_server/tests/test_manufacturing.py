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

import asyncio
import csv
import io
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import manufacturing as manufacturing_api
from app.manufacturing.application.dashboard_service import (
    ManufacturingDashboardService,
)
from app.manufacturing.application.ports import ManufacturingDataSet
from app.manufacturing.domain.detectors import (
    DetectorContext,
    DetectorResult,
    ManufacturingDetector,
    build_default_detectors,
    detect_spc_rbar_alerts,
    run_detectors,
)
from app.manufacturing.domain.models import (
    ManufacturingAlert,
    ManufacturingDailyRecord,
    ManufacturingDashboard,
    PredictionResult,
    PredictionStatus,
)
from app.manufacturing.infrastructure.csv_data_source import (
    aggregate_daily_records,
    build_fallback_csv_rows,
    build_lot_prediction_records,
)
from app.manufacturing.infrastructure.insight_service import InsightService
from app.manufacturing.infrastructure.prediction_client import (
    PREDICTION_FEATURE_COLUMNS,
    LocalManufacturingPredictionClient,
    build_prediction_csv,
    extract_probability,
    parse_prediction_csv_response,
    record_to_prediction_payload,
)


def make_daily_record(
    day: date,
    bleedout_rate: float = 0.02,
    coater_temperature_range: float = 1.0,
) -> ManufacturingDailyRecord:
    return ManufacturingDailyRecord(
        date=day,
        lots_produced=250,
        total_coating_length_m=250000.0,
        bleedout_count=round(250 * bleedout_rate),
        bleedout_rate=bleedout_rate,
        coating_length_category="1000m",
        coating_length_avg_m=1000.0,
        product_type="製造",
        coater_temperature=28.2,
        coater_temperature_range=coater_temperature_range,
        coater_humidity=50.5,
        coater_humidity_range=0.8,
        pump_pressure=0.9,
        pump_pressure_range=0.02,
        drying_zone1_temperature=120.1,
        drying_zone1_temperature_range=0.3,
        drying_zone2_temperature=122.1,
        drying_zone2_temperature_range=0.35,
        uv_irradiance=1020.4,
        uv_irradiance_range=1.6,
        lamp_lighting_hours=900.0,
        chamber_o2_concentration=0.011,
        chamber_o2_concentration_range=0.0002,
        uv_roll_temperature=89.05,
        uv_roll_temperature_range=0.12,
    )


class StaticPredictionClient:
    status: PredictionStatus = "available"

    def __init__(self, probability: float) -> None:
        self.probability = probability

    async def predict(
        self, series: list[ManufacturingDailyRecord]
    ) -> list[PredictionResult]:
        return [
            PredictionResult(
                date=record.date,
                probability=self.probability if record == series[-1] else 0.08,
                label="high_risk" if record == series[-1] else "normal",
            )
            for record in series
        ]


class DelayedPredictionClient(StaticPredictionClient):
    run_in_background = True

    async def predict(
        self, series: list[ManufacturingDailyRecord]
    ) -> list[PredictionResult]:
        await asyncio.sleep(0)
        return await super().predict(series)


class LotAwarePredictionClient:
    status: PredictionStatus = "available"

    def __init__(self, probabilities: dict[str, float]) -> None:
        self.probabilities = probabilities
        self.predicted_lot_ids: list[str | None] = []

    async def predict(
        self, series: list[ManufacturingDailyRecord]
    ) -> list[PredictionResult]:
        self.predicted_lot_ids = [record.lot_id for record in series]
        return [
            PredictionResult(
                date=record.date,
                probability=self.probabilities.get(record.lot_id or "", 0.05),
                label="TRUE",
                source_id=record.lot_id,
            )
            for record in series
        ]


class StaticManufacturingDataSource:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def load(self) -> ManufacturingDataSet:
        return ManufacturingDataSet(
            source_series=aggregate_daily_records(self.rows),
            prediction_series=build_lot_prediction_records(self.rows),
        )


class CountingInsightService(InsightService):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def prepare_insights(
        self, dashboard: ManufacturingDashboard
    ) -> list[ManufacturingAlert]:
        self.calls += 1
        return await super().prepare_insights(dashboard)


class BleedoutRateDetector:
    rule_id = "business.bleedout_rate.threshold"
    rule_version = "1.0.0"

    def detect(
        self,
        series: list[ManufacturingDailyRecord],
        context: DetectorContext,
    ) -> DetectorResult:
        alerts: list[ManufacturingAlert] = []
        for record in series:
            if record.bleedout_rate < 0.05:
                continue
            alerts.append(
                ManufacturingAlert(
                    id=f"business-bleedout-rate-{record.date.isoformat()}",
                    dedup_key=f"business_rule:bleedout_rate:{record.date.isoformat()}",
                    alert_type="business_rule",
                    severity="warning",
                    status="firing",
                    source="business_rule",
                    metric="bleedout_rate",
                    date=record.date,
                    title="ブリードアウト率が業務しきい値を超過",
                    description="日次ブリードアウト率が業務上の確認基準を超えました。",
                    actual=record.bleedout_rate,
                    threshold=0.05,
                    rule_id=self.rule_id,
                    rule_version=self.rule_version,
                    evidence={"bleedoutRate": record.bleedout_rate},
                )
            )
        return DetectorResult(alerts=alerts)


def assert_detector_type(_detector: ManufacturingDetector) -> None:
    return None


def stable_series(days: int = 12) -> list[ManufacturingDailyRecord]:
    start = date(2026, 4, 1)
    return [make_daily_record(start + timedelta(days=index)) for index in range(days)]


def test_manufacturing_layers_follow_clean_architecture_boundaries() -> None:
    manufacturing_root = Path(__file__).parents[1] / "app" / "manufacturing"

    assert (manufacturing_root / "domain").is_dir()
    assert (manufacturing_root / "application").is_dir()
    assert (manufacturing_root / "infrastructure").is_dir()

    domain_text = "\n".join(
        path.read_text() for path in (manufacturing_root / "domain").glob("*.py")
    )
    application_text = "\n".join(
        path.read_text() for path in (manufacturing_root / "application").glob("*.py")
    )

    assert "app.manufacturing.application" not in domain_text
    assert "app.manufacturing.infrastructure" not in domain_text
    assert "app.manufacturing.infrastructure" not in application_text
    assert "app.manufacturing.composition" not in application_text


def test_get_manufacturing_dashboard(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        manufacturing_api,
        "_manufacturing_service",
        ManufacturingDashboardService(
            prediction_client=LocalManufacturingPredictionClient(),
            insight_service=InsightService(),
            data_source=StaticManufacturingDataSource(build_fallback_csv_rows()),
        ),
    )

    response = client.get("/api/v1/manufacturing/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert data["range"] == {
        "startDate": "2026-03-19",
        "endDate": "2026-04-27",
        "grain": "day",
    }
    assert data["summary"]["latestDate"] == "2026-04-27"
    assert data["summary"]["lotsProduced"] == data["series"][-1]["lotsProduced"]
    assert data["predictionStatus"] == "local"
    assert "predictionAlertCount" in data["summary"]
    assert data["summary"]["predictionAlertCount"] > 0
    assert "businessRuleAlertCount" in data["summary"]
    assert len(data["series"]) == 40
    assert "alertIds" in data["series"][-1]
    assert data["series"][-1]["predictionProbability"] is not None
    assert "rbarCharts" in data
    assert "coater_humidity" in data["rbarCharts"]


def test_aggregate_daily_records_assigns_synthetic_dates() -> None:
    rows = build_fallback_csv_rows(days=2)

    daily_records = aggregate_daily_records(
        rows,
        lots_per_day=250,
        end_date=date(2026, 4, 27),
    )

    assert [record.date for record in daily_records] == [
        date(2026, 4, 26),
        date(2026, 4, 27),
    ]
    assert daily_records[0].lots_produced == 220
    assert daily_records[1].lots_produced == 237
    assert daily_records[0].total_coating_length_m > 0
    assert daily_records[0].coating_length_category.endswith("m")
    assert daily_records[0].product_type in {"製造", "試作品"}
    assert daily_records[0].coater_temperature_range > 0
    assert daily_records[0].uv_irradiance_range > 0
    assert rows[0]["日付"] == "2026-04-26"
    assert rows[0]["ロット番号"] == "SC20260426-0001"


def test_build_lot_prediction_records_preserves_source_rows() -> None:
    rows = [
        {
            "日付": "2026-04-27",
            "ロット番号": "SC20260427-0274",
            "塗布長": "1500m",
            "種別": "研究所テスト",
            "号機": "YC-08",
            "コーター部温度": "28.22",
            "コーター部相対湿度": "50.7",
            "ポンプ圧力": "0.900",
            "乾燥ゾーン1温度": "120.04",
            "乾燥ゾーン2温度": "122.15",
            "UV照度": "1020.6",
            "ランプ点灯時間": "3581",
            "チャンバー内O2濃度": "0.01100",
            "UVロール温度": "89.05",
            "ブリードアウト": "TRUE",
        }
    ]

    records = build_lot_prediction_records(rows)

    assert len(records) == 1
    assert records[0].lot_id == "SC20260427-0274"
    assert records[0].product_type == "研究所テスト"
    assert records[0].coating_length_category == "1500m"
    assert records[0].lamp_lighting_hours == 3581
    assert records[0].bleedout_rate == 1.0


def test_prediction_payload_uses_deployment_training_features_only() -> None:
    record = make_daily_record(date(2026, 4, 27))
    payload = record_to_prediction_payload(record)

    assert payload == {
        "乾燥ゾーン1温度": 120.1,
        "UVロール温度": 89.05,
        "塗布長": "1000m",
        "種別": "製造",
        "ランプ点灯時間": 900.0,
        "チャンバー内O2濃度": 0.011,
        "コーター部相対湿度": 50.5,
    }

    csv_text = build_prediction_csv([record])
    csv_reader = csv.DictReader(io.StringIO(csv_text))
    assert csv_reader.fieldnames == PREDICTION_FEATURE_COLUMNS
    assert list(csv_reader)[0]["塗布長"] == "1000m"


def test_prediction_response_prefers_positive_class_probability() -> None:
    probability, label = extract_probability(
        {
            "prediction": "FALSE",
            "predictionValues": [
                {"label": "FALSE", "value": 0.91},
                {"label": "TRUE", "value": 0.09},
            ],
        }
    )

    assert probability == 0.09
    assert label == "TRUE"


def test_prediction_csv_response_prefers_positive_class_probability() -> None:
    response_csv = "prediction,FALSE_PREDICTION,TRUE_PREDICTION\nFALSE,0.91,0.09\n"

    predictions = parse_prediction_csv_response(
        response_csv,
        [make_daily_record(date(2026, 4, 27))],
    )

    assert predictions[0].probability == 0.09
    assert predictions[0].label == "TRUE"


@pytest.mark.anyio
async def test_prediction_alert_created_when_probability_exceeds_threshold() -> None:
    service = ManufacturingDashboardService(
        prediction_client=StaticPredictionClient(probability=0.91),
        insight_service=InsightService(),
    )

    dashboard = await service.build_dashboard(stable_series())

    prediction_alerts = [
        alert for alert in dashboard.alerts if alert.alert_type == "prediction_ai"
    ]
    assert len(prediction_alerts) == 1
    assert dashboard.prediction_status == "available"
    assert dashboard.summary.prediction_alert_count == 1
    assert dashboard.series[-1].prediction_probability == 0.91
    assert dashboard.series[-1].alert_ids == [prediction_alerts[0].id]
    assert prediction_alerts[0].rule_id == "prediction.probability.threshold"
    assert prediction_alerts[0].threshold == 0.8
    assert prediction_alerts[0].insight_status == "ready"


@pytest.mark.anyio
async def test_dashboard_predicts_each_lot_and_uses_daily_max_probability() -> None:
    rows = build_fallback_csv_rows(days=1)
    rows[-1]["ロット番号"] = "SC20260427-0274"
    rows[-1]["塗布長"] = "1500m"
    rows[-1]["種別"] = "研究所テスト"
    rows[-1]["ランプ点灯時間"] = "3581"
    rows[-1]["ブリードアウト"] = "TRUE"
    prediction_client = LotAwarePredictionClient({"SC20260427-0274": 0.91})
    service = ManufacturingDashboardService(
        prediction_client=prediction_client,
        insight_service=InsightService(),
        data_source=StaticManufacturingDataSource(rows),
    )

    dashboard = await service.build_dashboard()

    prediction_alerts = [
        alert for alert in dashboard.alerts if alert.alert_type == "prediction_ai"
    ]
    assert len(prediction_client.predicted_lot_ids) == len(rows)
    assert "SC20260427-0274" in prediction_client.predicted_lot_ids
    assert dashboard.series[-1].prediction_probability == 0.91
    assert dashboard.summary.prediction_alert_count == 1
    assert prediction_alerts[0].evidence["sourceId"] == "SC20260427-0274"


@pytest.mark.asyncio
async def test_background_prediction_returns_running_until_results_are_ready() -> None:
    service = ManufacturingDashboardService(
        prediction_client=DelayedPredictionClient(probability=0.91),
        insight_service=InsightService(),
    )

    running_dashboard = await service.build_dashboard(stable_series())

    assert running_dashboard.prediction_status == "running"
    assert running_dashboard.summary.prediction_alert_count == 0

    await asyncio.sleep(0.01)
    ready_dashboard = await service.build_dashboard(stable_series())

    assert ready_dashboard.prediction_status == "available"
    assert ready_dashboard.summary.prediction_alert_count == 1


def test_spc_rbar_detector_calculates_limits_and_flags_out_of_control() -> None:
    series = stable_series(days=20)
    series.append(make_daily_record(date(2026, 4, 21), coater_temperature_range=3.0))

    alerts, chart = detect_spc_rbar_alerts(series)

    assert chart.center_line == pytest.approx(1.0952, abs=0.0001)
    assert chart.ucl == pytest.approx(2.3153, abs=0.0001)
    assert chart.lcl == 0
    assert len(alerts) == 1
    assert alerts[0].alert_type == "spc_rbar"
    assert alerts[0].rule_id == "spc.rbar.beyond_control_limit"
    assert alerts[0].control_limit == pytest.approx(chart.ucl)
    assert chart.points[-1].alert_id == alerts[0].id


def test_spc_rbar_detector_can_target_other_process_metrics() -> None:
    series = stable_series(days=20)
    series.append(make_daily_record(date(2026, 4, 21)))
    series[-1].uv_irradiance_range = 5.0

    alerts, chart = detect_spc_rbar_alerts(series, metric="uv_irradiance")

    assert chart.metric == "uv_irradiance"
    assert len(alerts) == 1
    assert alerts[0].metric == "uv_irradiance"
    assert "UV照度" in alerts[0].title


def test_registered_detectors_run_without_service_changes() -> None:
    series = stable_series(days=3)
    series[-1].bleedout_rate = 0.07
    detector = BleedoutRateDetector()
    assert_detector_type(detector)

    alerts, rbar_charts = run_detectors(
        series,
        DetectorContext(predictions=[]),
        [detector, *build_default_detectors()],
    )

    assert any(alert.rule_id == detector.rule_id for alert in alerts)
    assert "coater_temperature" in rbar_charts


def test_run_detectors_distinguishes_default_from_empty_detector_list() -> None:
    series = stable_series(days=3)

    default_alerts, default_rbar_charts = run_detectors(
        series,
        DetectorContext(predictions=[]),
    )
    empty_alerts, empty_rbar_charts = run_detectors(
        series,
        DetectorContext(predictions=[]),
        [],
    )

    assert default_alerts == []
    assert "coater_temperature" in default_rbar_charts
    assert empty_alerts == []
    assert empty_rbar_charts == {}


@pytest.mark.anyio
async def test_dashboard_service_accepts_additional_business_rule_detectors() -> None:
    series = stable_series(days=3)
    series[-1].bleedout_rate = 0.07
    service = ManufacturingDashboardService(
        prediction_client=StaticPredictionClient(probability=0.1),
        insight_service=InsightService(),
        detectors=[BleedoutRateDetector(), *build_default_detectors()],
    )

    dashboard = await service.build_dashboard(series)

    business_alerts = [
        alert for alert in dashboard.alerts if alert.alert_type == "business_rule"
    ]
    assert len(business_alerts) == 1
    assert dashboard.summary.business_rule_alert_count >= 1
    assert business_alerts[0].id in dashboard.series[-1].alert_ids


@pytest.mark.anyio
async def test_insight_generation_runs_only_when_alerts_exist() -> None:
    insight_service = CountingInsightService()
    stable_dashboard_service = ManufacturingDashboardService(
        prediction_client=StaticPredictionClient(probability=0.1),
        insight_service=insight_service,
    )

    await stable_dashboard_service.build_dashboard(stable_series())

    assert insight_service.calls == 0

    alert_dashboard_service = ManufacturingDashboardService(
        prediction_client=StaticPredictionClient(probability=0.92),
        insight_service=insight_service,
    )

    await alert_dashboard_service.build_dashboard(stable_series())

    assert insight_service.calls == 1


@pytest.mark.anyio
async def test_alert_detail_and_refresh_reuse_stored_alert() -> None:
    service = ManufacturingDashboardService(
        prediction_client=StaticPredictionClient(probability=0.91),
        insight_service=InsightService(),
    )
    dashboard = await service.build_dashboard(stable_series())
    alert_id = dashboard.alerts[0].id

    detail = service.get_alert(alert_id)
    refreshed = await service.refresh_alert_insight(alert_id)

    assert detail.id == alert_id
    assert detail.insight_status == "ready"
    assert refreshed.id == alert_id
    assert refreshed.insight is not None
