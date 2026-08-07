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
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MANUFACTURING_FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "manufacturing"
)


def _configure_mold_generated_dir(
    monkeypatch: pytest.MonkeyPatch, generated_dir: Path
) -> Path:
    monkeypatch.setenv("MOLD_GENERATED_DATA_DIR", str(generated_dir))
    monkeypatch.setenv("MOLD_DASHBOARD_DATA_DIR", str(generated_dir))
    return generated_dir


def _configure_mold_phase0_dir(
    monkeypatch: pytest.MonkeyPatch, phase0_dir: Path
) -> Path:
    phase0_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        MANUFACTURING_FIXTURES_DIR / "phase0_control_limits.json",
        phase0_dir / "phase0_control_limits.json",
    )
    monkeypatch.setenv("MOLD_PHASE0_DATA_DIR", str(phase0_dir))
    return phase0_dir


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
from app.manufacturing.domain.anomaly_scores import AnomalyScoreAggregates
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
from app.manufacturing.infrastructure.mold_upload_processor import NoritzMoldUploadProcessor
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


class StaticAnomalyPredictionClient:
    run_in_background = False

    def __init__(self, scores: AnomalyScoreAggregates) -> None:
        self.scores = scores

    async def predict_scores(self, **kwargs) -> AnomalyScoreAggregates:
        return self.scores


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
async def test_dashboard_service_accepts_empty_detector_list() -> None:
    service = ManufacturingDashboardService(
        prediction_client=StaticPredictionClient(probability=0.1),
        insight_service=InsightService(),
        detectors=[],
    )

    dashboard = await service.build_dashboard(stable_series(days=3))

    assert dashboard.alerts == []
    assert dashboard.rbar_chart is None
    assert dashboard.rbar_charts == {}


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


def test_mold_dashboard_empty_without_upload_manifest(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.manufacturing.infrastructure.mold_data_source import MoldDashboardProvider
    from app.manufacturing.infrastructure.mold_session import clear_upload_sessions

    clear_upload_sessions()
    _configure_mold_generated_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        manufacturing_api,
        "_manufacturing_service",
        ManufacturingDashboardService(
            prediction_client=LocalManufacturingPredictionClient(),
            insight_service=InsightService(),
            mold_dashboard_provider=MoldDashboardProvider(),
        ),
    )

    response = client.get("/api/v1/manufacturing/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert data["dataStatus"] == "empty"
    assert data["alerts"] == []
    assert data["xrCharts"] == {}
    assert data["predictionStatus"] == "unavailable"


def test_mold_dashboard_empty_when_preserve_false_without_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.manufacturing.infrastructure.mold_data_source import MoldDashboardProvider
    from app.manufacturing.infrastructure.mold_session import (
        clear_upload_sessions,
        write_upload_manifest,
    )

    clear_upload_sessions()
    monkeypatch.setenv("PRESERVE_FILE_ON_RELOAD", "false")
    _configure_mold_generated_dir(monkeypatch, tmp_path)
    write_upload_manifest(data_dir=tmp_path, source_file="sample.csv", upload_kind="raw")
    monkeypatch.setattr(
        manufacturing_api,
        "_manufacturing_service",
        ManufacturingDashboardService(
            prediction_client=LocalManufacturingPredictionClient(),
            insight_service=InsightService(),
            mold_dashboard_provider=MoldDashboardProvider(),
        ),
    )

    response = client.get("/api/v1/manufacturing/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert data["dataStatus"] == "empty"
    assert data["preserveFileOnReload"] is False


def test_mold_dashboard_ready_when_preserve_false_with_session_cookie(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.manufacturing.infrastructure.mold_data_source import MoldDashboardProvider
    from app.manufacturing.infrastructure.mold_session import (
        MOLD_SESSION_COOKIE,
        clear_upload_sessions,
        register_upload_session,
        write_upload_manifest,
    )

    clear_upload_sessions()
    monkeypatch.setenv("PRESERVE_FILE_ON_RELOAD", "false")
    generated_dir = _configure_mold_generated_dir(monkeypatch, tmp_path)
    _configure_mold_phase0_dir(monkeypatch, tmp_path / "phase0_data")
    write_upload_manifest(
        data_dir=generated_dir,
        source_file="phase2_daily_stats.csv",
        upload_kind="phase2",
    )
    shutil.copy(
        MANUFACTURING_FIXTURES_DIR / "monthly" / "phase2_daily_stats_2026-04.csv",
        generated_dir / "phase2_daily_stats.csv",
    )
    session_id = "test-session-id"
    register_upload_session(session_id)
    monkeypatch.setattr(
        manufacturing_api,
        "_manufacturing_service",
        ManufacturingDashboardService(
            prediction_client=LocalManufacturingPredictionClient(),
            anomaly_prediction_client=StaticAnomalyPredictionClient(
                AnomalyScoreAggregates(
                    by_day={},
                    by_day_pattern={},
                    status="unavailable",
                    threshold=0.001,
                )
            ),
            insight_service=InsightService(),
            mold_dashboard_provider=MoldDashboardProvider(),
        ),
    )

    client.cookies.set(MOLD_SESSION_COOKIE, session_id)
    response = client.get("/api/v1/manufacturing/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert data["dataStatus"] == "ready"
    assert data["preserveFileOnReload"] is False


def test_upload_manufacturing_dashboard_from_monthly_chunks(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.manufacturing.infrastructure.mold_data_source import MoldDashboardProvider

    generated_dir = _configure_mold_generated_dir(monkeypatch, tmp_path)
    _configure_mold_phase0_dir(monkeypatch, tmp_path / "phase0_data")
    monkeypatch.setattr(
        manufacturing_api,
        "_manufacturing_service",
        ManufacturingDashboardService(
            prediction_client=LocalManufacturingPredictionClient(),
            anomaly_prediction_client=StaticAnomalyPredictionClient(
                AnomalyScoreAggregates(
                    by_day={date(2026, 4, 15): 0.2, date(2026, 4, 16): 0.05},
                    by_day_pattern={(date(2026, 4, 15), 1): 0.2},
                    status="available",
                    threshold=0.085,
                )
            ),
            insight_service=InsightService(),
            mold_dashboard_provider=MoldDashboardProvider(),
        ),
    )

    monthly_dir = MANUFACTURING_FIXTURES_DIR / "monthly"
    daily_path = monthly_dir / "phase2_daily_stats_2026-04.csv"
    anomalies_path = monthly_dir / "phase2_anomalies_2026-04.csv"

    response = client.post(
        "/api/v1/manufacturing/dashboard/upload",
        files=[
            (
                "files",
                (daily_path.name, daily_path.read_bytes(), "text/csv"),
            ),
            (
                "files",
                (anomalies_path.name, anomalies_path.read_bytes(), "text/csv"),
            ),
        ],
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["dataStatus"] == "ready"
    assert data["sourceFile"] == daily_path.name
    assert (generated_dir / "upload_manifest.json").is_file()
    assert data["range"]["endDate"].startswith("2026-04")
    assert "a_agent_flow_pressure" in data["xrCharts"]
    assert data["summary"]["businessRuleAlertCount"] > 0
    assert len(data["alerts"]) > 0
    assert data["availablePatterns"]
    assert data["dailyCountChart"] is None
    assert data["jisRuleDescriptions"]["1"].startswith("領域A超過")
    assert any(
        "violationRuleDetails" in alert.get("evidence", {})
        for alert in data["alerts"]
    )
    assert any(
        alert.get("anomalyScore") is not None
        and alert.get("evidence", {}).get("pattern") is not None
        for alert in data["alerts"]
    )
    critical_anomaly_alerts = [
        alert
        for alert in data["alerts"]
        if alert.get("alertType") == "prediction_ai"
        and alert.get("severity") == "critical"
    ]
    assert critical_anomaly_alerts
    assert critical_anomaly_alerts[0]["id"].startswith("anomaly-score-")
    assert data["alerts"][0]["severity"] == "critical"
    assert data["summary"]["predictionAlertCount"] == len(critical_anomaly_alerts)
    assert data["summary"]["criticalAlertCount"] >= len(critical_anomaly_alerts)


def test_parse_production_day_and_max_anomaly_scores(tmp_path: Path) -> None:
    from app.manufacturing.infrastructure import mold_data_source as mold
    from app.manufacturing.infrastructure.anomaly_prediction_client import (
        LocalCsvAnomalyPredictionClient,
    )

    assert mold.parse_production_day("2026-04-15") == date(2026, 4, 15)
    assert mold.parse_production_day("46127.0") == date(2026, 4, 15)

    csv_path = tmp_path / "demo_features_予測結果.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ANOMALY_SCORE,生産日,吐出パターン番号",
                "0.01,46127.0,1",
                "0.20,46127.0,1",
                "0.15,46127.0,6",
                "0.05,46128.0,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    counts_path = tmp_path / "phase3_daily_data_counts.json"
    counts_path.write_text(
        json.dumps(
            {
                "daily_counts": {
                    "2026-04-15": 10,
                    "2026-04-16": 3,
                }
            }
        ),
        encoding="utf-8",
    )

    import asyncio

    scores = asyncio.run(
        LocalCsvAnomalyPredictionClient(threshold=0.085).predict_scores(data_dir=tmp_path)
    )
    assert scores.by_day[date(2026, 4, 15)] == 0.2
    assert scores.by_day[date(2026, 4, 16)] == 0.05

    by_pattern = scores.by_day_pattern
    assert by_pattern[(date(2026, 4, 15), 1)] == 0.2
    assert by_pattern[(date(2026, 4, 15), 6)] == 0.15
    assert (
        mold.resolve_alert_anomaly_score(
            day=date(2026, 4, 15),
            pattern=6,
            scores_by_day_pattern=by_pattern,
            scores_by_day=scores.by_day,
        )
        == 0.2
    )
    assert mold.format_anomaly_score_display(0.0042041549) == "0.0042"
    assert mold.format_anomaly_threshold_display(1.5e-6) == "0.0000015"
    assert mold.format_anomaly_threshold_display(0.085) == "0.085"

    anomaly_alerts = mold.build_anomaly_score_alerts(
        scores=scores,
        alert_start=date(2026, 4, 15),
        latest=date(2026, 4, 16),
    )
    assert len(anomaly_alerts) == 1
    assert anomaly_alerts[0].severity == "critical"
    assert anomaly_alerts[0].anomaly_score == 0.2
    assert anomaly_alerts[0].date == date(2026, 4, 15)
    assert anomaly_alerts[0].evidence["exceedingPatterns"] == [1, 6]
    assert "0.2000" in anomaly_alerts[0].description
    assert "設定閾値" in anomaly_alerts[0].description

    chart = mold.load_daily_counts(
        tmp_path,
        scores_by_day=scores.by_day,
        anomaly_score_threshold=scores.threshold,
    )
    assert chart is not None
    assert chart.anomaly_score_threshold == 0.085
    by_date = {point.date: point for point in chart.points}
    assert by_date[date(2026, 4, 15)].max_anomaly_score == 0.2


def test_aggregate_predictions_reads_suffixed_passthrough_columns() -> None:
    import pandas as pd

    from app.manufacturing.infrastructure.anomaly_prediction_client import (
        DataRobotAnomalyPredictionClient,
    )

    client = DataRobotAnomalyPredictionClient(
        deployment_id="demo",
        endpoint="https://example.com",
        api_token="token",
        run_in_background=False,
    )
    frame = pd.DataFrame(
        [
            {
                "ANOMALY_SCORE": 0.000002,
                "生産日_x": "46127.0",
                "吐出パターン番号_x": "1",
            },
            {
                "ANOMALY_SCORE": 0.000003,
                "生産日_y": "46127.0",
                "吐出パターン番号_y": "6",
            },
            {
                "ANOMALY_SCORE": 0.000001,
                "生産日": "2026-04-16",
                "吐出パターン番号": "2",
            },
        ]
    )

    scores = client._aggregate_predictions(frame)

    assert scores.status == "available"
    assert scores.by_day[date(2026, 4, 15)] == 0.000003
    assert scores.by_day[date(2026, 4, 16)] == 0.000001
    assert scores.by_day_pattern[(date(2026, 4, 15), 1)] == 0.000002
    assert scores.by_day_pattern[(date(2026, 4, 15), 6)] == 0.000003


def test_load_feature_rows_allows_missing_pattern_passthrough(tmp_path: Path) -> None:
    from app.manufacturing.infrastructure.mold_feature_loader import load_feature_rows
    from app.manufacturing.infrastructure.mold_session import write_upload_manifest

    raw_path = tmp_path / "sample.csv"
    raw_path.write_text(
        "feature_a,生産日,吐出パターン番号\n"
        "1.0,46113.0,1\n"
        "2.0,46114.0,6\n",
        encoding="utf-8-sig",
    )
    features_path = tmp_path / "sample_features.csv"
    features_path.write_text(
        "feature_a,生産日\n"
        "1.0,46113.0\n"
        "2.0,46114.0\n",
        encoding="utf-8-sig",
    )
    write_upload_manifest(data_dir=tmp_path, source_file=raw_path.name, upload_kind="raw")

    rows = load_feature_rows(
        data_dir=tmp_path,
        feature_columns=["feature_a"],
        min_day=date(2026, 4, 1),
    )

    assert len(rows) == 2
    assert rows[0]["feature_a"] == "1.0"
    assert rows[0]["生産日"] == "46113.0"
    assert rows[0]["吐出パターン番号"] == "1"
    assert rows[1]["吐出パターン番号"] == "6"


def test_parse_production_day_accepts_slash_dates() -> None:
    from app.manufacturing.infrastructure.mold_data_source import parse_production_day

    assert parse_production_day("2026/4/1") == date(2026, 4, 1)
    assert parse_production_day("2026-04-01") == date(2026, 4, 1)


def test_process_manufacturing_dashboard_from_raw_csv(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.manufacturing.infrastructure.mold_data_source import MoldDashboardProvider

    generated_dir = _configure_mold_generated_dir(monkeypatch, tmp_path)
    _configure_mold_phase0_dir(monkeypatch, tmp_path / "phase0_data")
    monkeypatch.setattr(
        manufacturing_api,
        "_manufacturing_service",
        ManufacturingDashboardService(
            prediction_client=LocalManufacturingPredictionClient(),
            anomaly_prediction_client=StaticAnomalyPredictionClient(
                AnomalyScoreAggregates(
                    by_day={date(2026, 4, 15): 0.001},
                    by_day_pattern={(date(2026, 4, 15), 1): 0.001},
                    status="available",
                    threshold=0.001,
                )
            ),
            insight_service=InsightService(),
            mold_dashboard_provider=MoldDashboardProvider(),
            mold_upload_processor=NoritzMoldUploadProcessor(),
        ),
    )

    raw_path = MANUFACTURING_FIXTURES_DIR / "テストデータ_202604.csv"
    response = client.post(
        "/api/v1/manufacturing/dashboard/process",
        files={"file": (raw_path.name, raw_path.read_bytes(), "text/csv")},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["dataStatus"] == "ready"
    assert data["sourceFile"] == raw_path.name
    assert (generated_dir / "upload_manifest.json").is_file()
    assert data["range"]["endDate"].startswith("2026-04")
    assert data["dailyCountChart"] is not None
    assert len(data["dailyCountChart"]["points"]) > 0
    assert "a_agent_flow_pressure" in data["xrCharts"]
    assert data["summary"]["businessRuleAlertCount"] > 0
