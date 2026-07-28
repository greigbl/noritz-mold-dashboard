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

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.manufacturing.application.dashboard_service import (
    ManufacturingDashboardService,
)
from app.manufacturing.composition import create_manufacturing_dashboard_service
from app.manufacturing.domain.models import ManufacturingAlert, ManufacturingDashboard
from app.manufacturing.infrastructure.mold_data_source import (
    classify_phase2_csv_rows,
    parse_csv_rows,
)

manufacturing_router = APIRouter(prefix="/manufacturing", tags=["Manufacturing"])
_manufacturing_service = create_manufacturing_dashboard_service()


def get_manufacturing_service() -> ManufacturingDashboardService:
    return _manufacturing_service


@manufacturing_router.get("/dashboard")
async def get_manufacturing_dashboard() -> ManufacturingDashboard:
    return await get_manufacturing_service().build_dashboard()


@manufacturing_router.post("/dashboard/upload")
async def upload_manufacturing_dashboard(
    files: list[UploadFile] = File(...),
) -> ManufacturingDashboard:
    """Build the mold dashboard from uploaded phase2 CSV files.

    Accept 1–2 CSVs (daily_stats required, anomalies optional). Files are
    classified by header columns when possible, otherwise by filename.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one CSV file is required.")

    daily_rows: list[dict[str, str]] | None = None
    anomaly_rows: list[dict[str, str]] | None = None

    for upload in files:
        content = await upload.read()
        filename = (upload.filename or "").lower()
        rows = parse_csv_rows(content)
        kind = classify_phase2_csv_rows(rows)
        if kind is None:
            if "anomal" in filename:
                kind = "anomalies"
            elif "daily" in filename or "stats" in filename:
                kind = "daily_stats"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Unrecognized CSV '{upload.filename}'. "
                        "Expected phase2 daily_stats or anomalies columns."
                    ),
                )

        if kind == "daily_stats":
            if daily_rows is not None:
                raise HTTPException(
                    status_code=400, detail="Multiple daily_stats CSVs uploaded."
                )
            daily_rows = rows
        else:
            if anomaly_rows is not None:
                raise HTTPException(
                    status_code=400, detail="Multiple anomalies CSVs uploaded."
                )
            anomaly_rows = rows

    if daily_rows is None:
        raise HTTPException(
            status_code=400,
            detail="phase2_daily_stats CSV is required (anomalies is optional).",
        )

    service = get_manufacturing_service()
    try:
        return await service.build_mold_dashboard_from_upload(
            daily_rows=daily_rows,
            anomaly_rows=anomaly_rows if anomaly_rows is not None else [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
