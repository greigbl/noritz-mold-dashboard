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

from app.manufacturing.application.dashboard_service import (
    ManufacturingDashboardService,
)
from app.manufacturing.domain.detectors import build_default_detectors
from app.manufacturing.infrastructure.csv_data_source import CsvManufacturingDataSource
from app.manufacturing.infrastructure.insight_service import InsightService
from app.manufacturing.infrastructure.prediction_client import (
    create_prediction_client_from_env,
)


def create_manufacturing_dashboard_service() -> ManufacturingDashboardService:
    return ManufacturingDashboardService(
        data_source=CsvManufacturingDataSource(),
        prediction_client=create_prediction_client_from_env(),
        insight_service=InsightService(),
        detectors=build_default_detectors(),
    )
