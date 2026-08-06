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

from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from app.manufacturing.application.dashboard_service import (
    ManufacturingDashboardService,
)
from app.manufacturing.composition import create_manufacturing_dashboard_service
from app.manufacturing.domain.models import ManufacturingAlert, ManufacturingDashboard
from app.manufacturing.infrastructure.mold_data_source import (
    classify_phase2_csv_rows,
    parse_csv_rows,
)
from app.manufacturing.infrastructure.mold_session import (
    MOLD_SESSION_COOKIE,
    is_preserve_file_on_reload,
    register_upload_session,
)
from app.manufacturing.pipeline.orchestrator import is_raw_mold_csv

manufacturing_router = APIRouter(prefix="/manufacturing", tags=["Manufacturing"])
_manufacturing_service = create_manufacturing_dashboard_service()


def get_manufacturing_service() -> ManufacturingDashboardService:
    return _manufacturing_service


def _read_upload_session_id(request: Request) -> str | None:
    return request.cookies.get(MOLD_SESSION_COOKIE)


def _begin_upload_session(response: Response) -> str | None:
    if is_preserve_file_on_reload():
        return None
    session_id = str(uuid4())
    register_upload_session(session_id)
    response.set_cookie(
        key=MOLD_SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
    )
    return session_id


@manufacturing_router.get("/dashboard")
async def get_manufacturing_dashboard(request: Request) -> ManufacturingDashboard:
    return await get_manufacturing_service().build_dashboard(
        upload_session_id=_read_upload_session_id(request),
    )


@manufacturing_router.post("/dashboard/process")
async def process_manufacturing_dashboard(
    response: Response,
    file: UploadFile = File(...),
) -> ManufacturingDashboard:
    """Run phases 1–3 on uploaded monthly mold CSV, then score via phase 4."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")

    rows = parse_csv_rows(content)
    if not is_raw_mold_csv(rows):
        raise HTTPException(
            status_code=400,
            detail=(
                "Expected raw mold test data CSV (columns such as パレットNo, 生産日). "
                "For pre-computed phase2 outputs, use POST /dashboard/upload instead."
            ),
        )

    service = get_manufacturing_service()
    upload_session_id = _begin_upload_session(response)
    try:
        return await service.build_mold_dashboard_from_raw_upload(
            content=content,
            filename=file.filename or "upload.csv",
            upload_session_id=upload_session_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@manufacturing_router.post("/dashboard/upload")
async def upload_manufacturing_dashboard(
    response: Response,
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
    daily_source_file: str | None = None
    service = get_manufacturing_service()
    upload_session_id = _begin_upload_session(response)

    for upload in files:
        content = await upload.read()
        filename = (upload.filename or "").lower()
        rows = parse_csv_rows(content)
        if is_raw_mold_csv(rows):
            try:
                return await service.build_mold_dashboard_from_raw_upload(
                    content=content,
                    filename=upload.filename or "upload.csv",
                    upload_session_id=upload_session_id,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

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
            daily_source_file = upload.filename or "phase2_daily_stats.csv"
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

    try:
        return await service.build_mold_dashboard_from_upload(
            daily_rows=daily_rows,
            anomaly_rows=anomaly_rows if anomaly_rows is not None else [],
            source_file=daily_source_file or "phase2_daily_stats.csv",
            upload_session_id=upload_session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@manufacturing_router.get("/alerts/{alert_id}")
async def get_manufacturing_alert(
    alert_id: str,
    request: Request,
) -> ManufacturingAlert:
    service = get_manufacturing_service()
    try:
        return service.get_alert(alert_id)
    except KeyError:
        await service.build_dashboard(upload_session_id=_read_upload_session_id(request))

    try:
        return service.get_alert(alert_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Alert not found") from exc


@manufacturing_router.post("/alerts/{alert_id}/insight:refresh")
async def refresh_manufacturing_alert_insight(
    alert_id: str,
    request: Request,
) -> ManufacturingAlert:
    service = get_manufacturing_service()
    try:
        return await service.refresh_alert_insight(alert_id)
    except KeyError:
        await service.build_dashboard(upload_session_id=_read_upload_session_id(request))

    try:
        return await service.refresh_alert_insight(alert_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Alert not found") from exc
