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
from typing import Protocol

from app.manufacturing.domain.models import (
    ManufacturingAlert,
    ManufacturingDailyRecord,
    ManufacturingDashboard,
    PredictionResult,
    PredictionStatus,
)


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
    def build(self) -> ManufacturingDashboard: ...
