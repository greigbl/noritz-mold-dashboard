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

from app.manufacturing.data_loader import aggregate_daily_records, load_csv_rows
from app.manufacturing.detectors import (
    detect_all_spc_rbar_alerts,
    detect_prediction_alerts,
)
from app.manufacturing.insight_service import InsightService
from app.manufacturing.models import (
    ManufacturingAlert,
    ManufacturingDailyRecord,
    ManufacturingDashboard,
    ManufacturingRange,
    ManufacturingSummary,
    PredictionResult,
    PredictionStatus,
)
from app.manufacturing.prediction_client import (
    PredictionClient,
    create_prediction_client_from_env,
)


class ManufacturingDashboardService:
    def __init__(
        self,
        prediction_client: PredictionClient | None = None,
        insight_service: InsightService | None = None,
    ) -> None:
        self.prediction_client = (
            prediction_client or create_prediction_client_from_env()
        )
        self.insight_service = insight_service or InsightService()
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
        sorted_series = sorted(
            series if series is not None else aggregate_daily_records(load_csv_rows()),
            key=lambda record: record.date,
        )
        if not sorted_series:
            raise ValueError("Manufacturing data is empty.")

        for record in sorted_series:
            record.alert_ids = []

        predictions, prediction_status = await self.resolve_predictions(sorted_series)
        prediction_alerts = detect_prediction_alerts(sorted_series, predictions)
        spc_alerts, rbar_charts = detect_all_spc_rbar_alerts(sorted_series)
        alerts = prediction_alerts + spc_alerts

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
                prediction_alert_count=len(prediction_alerts),
                business_rule_alert_count=len(alerts) - len(prediction_alerts),
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
    latest = series[-1]
    return (
        f"{series[0].date.isoformat()}:{latest.date.isoformat()}:"
        f"{len(series)}:{latest.lots_produced}:{latest.total_coating_length_m}"
    )
