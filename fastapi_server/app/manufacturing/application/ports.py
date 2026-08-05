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

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from app.manufacturing.domain.models import (
    ManufacturingAlert,
    ManufacturingDailyRecord,
    ManufacturingDashboard,
    PredictionResult,
    PredictionStatus,
)

if TYPE_CHECKING:
    from app.manufacturing.domain.anomaly_scores import AnomalyScoreAggregates


@dataclass(frozen=True)
class ManufacturingDataSet:
    source_series: list[ManufacturingDailyRecord]
    prediction_series: list[ManufacturingDailyRecord]


class ManufacturingDataSource(Protocol):
    def load(self) -> ManufacturingDataSet: ...


class PredictionClient(Protocol):
    status: PredictionStatus

    async def predict(
        self, series: list[ManufacturingDailyRecord]
    ) -> list[PredictionResult]: ...


class AnomalyPredictionClient(Protocol):
    run_in_background: bool

    async def predict_scores(
        self,
        *,
        min_day: date | None = None,
        data_dir: Path | None = None,
    ) -> "AnomalyScoreAggregates": ...


class InsightGenerator(Protocol):
    async def prepare_insights(
        self, dashboard: ManufacturingDashboard
    ) -> list[ManufacturingAlert]: ...

    async def refresh_insight(
        self,
        alert: ManufacturingAlert,
        dashboard: ManufacturingDashboard | None = None,
    ) -> ManufacturingAlert: ...


class MoldDashboardProvider(Protocol):
    def resolve_plot_start(
        self,
        *,
        daily_rows: list[dict[str, str]] | None = None,
    ) -> date: ...

    def build(self) -> ManufacturingDashboard: ...
