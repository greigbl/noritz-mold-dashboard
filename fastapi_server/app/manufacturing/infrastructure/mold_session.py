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

"""Track whether the mold dashboard has user-uploaded data."""

from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.manufacturing.infrastructure.mold_data_source import get_mold_data_dir

UPLOAD_MANIFEST_FILE = "upload_manifest.json"
MOLD_SESSION_COOKIE = "mold_dashboard_session"
UploadKind = Literal["raw", "phase2"]

_active_upload_sessions: set[str] = set()


def is_preserve_file_on_reload() -> bool:
    raw = os.getenv("PRESERVE_FILE_ON_RELOAD", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def register_upload_session(session_id: str) -> None:
    _active_upload_sessions.add(session_id)


def clear_upload_sessions() -> None:
    _active_upload_sessions.clear()


def upload_manifest_path(data_dir: Path | None = None) -> Path:
    return (data_dir or get_mold_data_dir()) / UPLOAD_MANIFEST_FILE


def has_uploaded_dashboard_data(
    data_dir: Path | None = None,
    *,
    session_id: str | None = None,
) -> bool:
    """Return True when uploaded dashboard data should be shown to the client."""
    if not upload_manifest_path(data_dir).is_file():
        return False
    if is_preserve_file_on_reload():
        return True
    return session_id is not None and session_id in _active_upload_sessions


def read_upload_manifest(data_dir: Path | None = None) -> dict[str, object] | None:
    path = upload_manifest_path(data_dir)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def get_active_source_file(data_dir: Path | None = None) -> str | None:
    manifest = read_upload_manifest(data_dir)
    if not manifest:
        return None
    source_file = manifest.get("source_file")
    return str(source_file) if source_file else None


def resolve_active_raw_csv_path(data_dir: Path | None = None) -> Path | None:
    """Return the uploaded monthly raw CSV referenced by the upload manifest."""
    from app.manufacturing.infrastructure.mold_data_source import parse_csv_rows

    root = data_dir or get_mold_data_dir()
    source_file = get_active_source_file(root)
    if not source_file:
        return None

    candidate = root / source_file
    if candidate.is_file():
        return candidate

    stem = Path(source_file).stem
    matches = sorted(root.glob(f"{stem}.csv"))
    if matches:
        return matches[0]

    for path in root.glob("*.csv"):
        if path.name.endswith("_features.csv") or path.name.startswith("phase2_"):
            continue
        try:
            rows = parse_csv_rows(path.read_bytes())
        except ValueError:
            continue
        if rows and {"パレットNo", "生産日", "吐出パターン番号"}.issubset(rows[0].keys()):
            return path
    return None


def load_raw_passthrough_series(
    *,
    data_dir: Path | None = None,
    columns: tuple[str, ...],
) -> dict[str, list[str]] | None:
    """Load deployment passthrough columns from the uploaded raw monthly CSV."""
    from app.manufacturing.infrastructure.mold_data_source import parse_csv_rows

    raw_path = resolve_active_raw_csv_path(data_dir)
    if raw_path is None:
        return None

    rows = parse_csv_rows(raw_path.read_bytes())
    if not rows:
        return None

    return {
        column: [str(row.get(column, "")) for row in rows]
        for column in columns
    }


def write_upload_manifest(
    *,
    data_dir: Path | None = None,
    source_file: str,
    upload_kind: UploadKind = "raw",
    metadata: dict[str, object] | None = None,
) -> Path:
    payload: dict[str, object] = {
        "source_file": source_file,
        "upload_kind": upload_kind,
        "processed_at": datetime.now(UTC).isoformat(),
    }
    if metadata:
        payload.update(metadata)
    path = upload_manifest_path(data_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def persist_phase2_outputs(
    *,
    data_dir: Path | None = None,
    daily_rows: list[dict[str, str]],
    anomaly_rows: list[dict[str, str]] | None = None,
) -> None:
    """Write phase2 CSV outputs so subsequent GET /dashboard can load them."""
    target_dir = data_dir or get_mold_data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    daily_path = target_dir / "phase2_daily_stats.csv"
    with daily_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(daily_rows[0].keys()))
        writer.writeheader()
        writer.writerows(daily_rows)

    anomalies_path = target_dir / "phase2_anomalies.csv"
    if anomaly_rows:
        with anomalies_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(anomaly_rows[0].keys()))
            writer.writeheader()
            writer.writerows(anomaly_rows)
    elif anomalies_path.exists():
        anomalies_path.unlink()
