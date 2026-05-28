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
import hashlib
import json
from collections.abc import Sequence

from app.manufacturing.application.ports import (
    InsightGenerator,
    ManufacturingDataSet,
    ManufacturingDataSource,
    PredictionClient,
)
from app.manufacturing.domain.detectors import (
    DetectorContext,
    ManufacturingDetector,
    build_default_detectors,
    run_detectors,
)
from app.manufacturing.domain.models import (
    ManufacturingAlert,
    ManufacturingDailyRecord,
    ManufacturingDashboard,
    ManufacturingRange,
    ManufacturingSummary,
    PredictionResult,
    PredictionStatus,
)


class ManufacturingDashboardService:
    def __init__(
        self,
        prediction_client: PredictionClient,
        insight_service: InsightGenerator,
        data_source: ManufacturingDataSource | None = None,
        detectors: Sequence[ManufacturingDetector] | None = None,
    ) -> None:
        self.prediction_client = prediction_client
        self.insight_service = insight_service
        self.data_source = data_source
        self.detectors = (
            list(detectors) if detectors is not None else build_default_detectors()
        )
        self._alerts_by_id: dict[str, ManufacturingAlert] = {}
        self._last_dashboard: ManufacturingDashboard | None = None
        self._prediction_task: asyncio.Task[list[PredictionResult]] | None = None
        self._prediction_results: list[PredictionResult] | None = None
        self._prediction_job_key: str | None = None
        self._prediction_status: PredictionStatus | None = None

    async def build_dashboard(
        self,
        series: list[ManufacturingDailyRecord] | None = None,
    ) -> ManufacturingDashboard:
        if series is None:
            if self.data_source is None:
                raise ValueError("Manufacturing data source is not configured.")
            data_set = self.data_source.load()
        else:
            data_set = ManufacturingDataSet(
                source_series=series,
                prediction_series=series,
            )

        sorted_series = sorted(
            data_set.source_series,
            key=lambda record: record.date,
        )
        sorted_prediction_series = sorted(
            data_set.prediction_series,
            key=lambda record: (record.date, record.lot_id or ""),
        )
        if not sorted_series:
            raise ValueError("Manufacturing data is empty.")

        for record in sorted_series:
            record.alert_ids = []

        predictions, prediction_status = await self.resolve_predictions(
            sorted_prediction_series
        )
        alerts, rbar_charts = run_detectors(
            sorted_series,
            DetectorContext(predictions=predictions),
            self.detectors,
        )
        prediction_alert_count = sum(
            1 for alert in alerts if alert.alert_type == "prediction_ai"
        )

        alert_ids_by_date: dict[str, list[str]] = {}
        for alert in alerts:
            alert_ids_by_date.setdefault(alert.date.isoformat(), []).append(alert.id)

        for record in sorted_series:
            record.alert_ids = alert_ids_by_date.get(record.date.isoformat(), [])

        latest = sorted_series[-1]
        dashboard = ManufacturingDashboard(
            prediction_status=prediction_status,
            range=ManufacturingRange(
                start_date=sorted_series[0].date,
                end_date=latest.date,
                grain="day",
            ),
            summary=ManufacturingSummary(
                latest_date=latest.date,
                lots_produced=latest.lots_produced,
                total_coating_length_m=latest.total_coating_length_m,
                bleedout_count=latest.bleedout_count,
                bleedout_rate=latest.bleedout_rate,
                alert_count=len(alerts),
                prediction_alert_count=prediction_alert_count,
                business_rule_alert_count=len(alerts) - prediction_alert_count,
                critical_alert_count=sum(
                    1 for alert in alerts if alert.severity == "critical"
                ),
            ),
            series=sorted_series,
            rbar_chart=rbar_charts["coater_temperature"],
            rbar_charts=rbar_charts,
            alerts=alerts,
        )

        if dashboard.alerts:
            await self.insight_service.prepare_insights(dashboard)

        self._last_dashboard = dashboard
        self._alerts_by_id = {alert.id: alert for alert in dashboard.alerts}
        return dashboard

    async def resolve_predictions(
        self,
        sorted_series: list[ManufacturingDailyRecord],
    ) -> tuple[list[PredictionResult], PredictionStatus]:
        if not getattr(self.prediction_client, "run_in_background", False):
            predictions = await self.prediction_client.predict(sorted_series)
            return predictions, self.prediction_client.status

        job_key = build_prediction_job_key(sorted_series)
        if self._prediction_job_key != job_key:
            self._prediction_job_key = job_key
            self._prediction_results = None
            self._prediction_task = None
            self._prediction_status = None

        if self._prediction_results is not None:
            return self._prediction_results, self._prediction_status or "available"

        if self._prediction_task is not None:
            if not self._prediction_task.done():
                return [], "running"

            try:
                self._prediction_results = self._prediction_task.result()
                self._prediction_status = self.prediction_client.status
            except Exception:
                self._prediction_results = []
                self._prediction_status = "error"
            return self._prediction_results, self._prediction_status

        self._prediction_status = "running"
        self._prediction_task = asyncio.create_task(
            self.prediction_client.predict(
                [record.model_copy(deep=True) for record in sorted_series]
            )
        )
        return [], "running"

    def get_alert(self, alert_id: str) -> ManufacturingAlert:
        alert = self._alerts_by_id.get(alert_id)
        if alert is None:
            raise KeyError(alert_id)
        return alert

    async def refresh_alert_insight(self, alert_id: str) -> ManufacturingAlert:
        alert = self.get_alert(alert_id)
        refreshed = await self.insight_service.refresh_insight(
            alert,
            self._last_dashboard,
        )
        self._alerts_by_id[alert_id] = refreshed
        return refreshed


def build_prediction_job_key(series: list[ManufacturingDailyRecord]) -> str:
    payload = [
        record.model_dump(
            mode="json",
            by_alias=True,
            exclude={"alert_ids", "prediction_probability", "prediction_label"},
        )
        for record in series
    ]
    serialized_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()
    return f"{len(series)}:{digest}"
