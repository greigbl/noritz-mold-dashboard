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

from fastapi import APIRouter, HTTPException

from app.manufacturing.application.dashboard_service import (
    ManufacturingDashboardService,
)
from app.manufacturing.composition import create_manufacturing_dashboard_service
from app.manufacturing.domain.models import ManufacturingAlert, ManufacturingDashboard

manufacturing_router = APIRouter(prefix="/manufacturing", tags=["Manufacturing"])
_manufacturing_service = create_manufacturing_dashboard_service()


def get_manufacturing_service() -> ManufacturingDashboardService:
    return _manufacturing_service


@manufacturing_router.get("/dashboard")
async def get_manufacturing_dashboard() -> ManufacturingDashboard:
    return await get_manufacturing_service().build_dashboard()


@manufacturing_router.get("/alerts/{alert_id}")
async def get_manufacturing_alert(alert_id: str) -> ManufacturingAlert:
    service = get_manufacturing_service()
    try:
        return service.get_alert(alert_id)
    except KeyError:
        await service.build_dashboard()

    try:
        return service.get_alert(alert_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Alert not found") from exc


@manufacturing_router.post("/alerts/{alert_id}/insight:refresh")
async def refresh_manufacturing_alert_insight(alert_id: str) -> ManufacturingAlert:
    service = get_manufacturing_service()
    try:
        return await service.refresh_alert_insight(alert_id)
    except KeyError:
        await service.build_dashboard()

    try:
        return await service.refresh_alert_insight(alert_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Alert not found") from exc
