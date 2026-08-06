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

"""Run mold pipeline phases 1–3 on uploaded monthly test data."""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.manufacturing.pipeline import config as pipeline_config
from app.manufacturing.pipeline.phase1 import DataValidator, load_data
from app.manufacturing.pipeline.phase2 import XRControlChart
from app.manufacturing.pipeline.phase3 import MoldFeatureEngineering, analyze_daily_data_count

logger = logging.getLogger(__name__)

RAW_UPLOAD_GLOB = "uploaded_*.csv"
REQUIRED_RAW_COLUMNS = frozenset({"パレットNo", "セット位置", "吐出パターン番号", "生産日"})


@dataclass(frozen=True)
class MoldPipelineResult:
    """Artifacts produced by phases 1–3."""

    raw_csv_path: Path
    features_csv_path: Path
    daily_stats_path: Path
    anomalies_path: Path | None
    missing_ids_path: Path
    daily_counts_path: Path
    total_rows: int
    valid_rows: int
    missing_rows: int
    anomaly_count: int


def sanitize_upload_filename(filename: str) -> str:
    stem = Path(filename or "upload.csv").stem
    cleaned = re.sub(r"[^\w\u3000-\u9fff\-]+", "_", stem, flags=re.UNICODE).strip("_")
    return cleaned or "upload"


def is_raw_mold_csv(rows: list[dict[str, str]]) -> bool:
    if not rows:
        return False
    headers = {key.strip() for key in rows[0]}
    return REQUIRED_RAW_COLUMNS.issubset(headers)


def write_missing_ids(
    *,
    data_dir: Path,
    df,
    invalid_df,
) -> Path:
    """Persist phase-1 missing row indices for phase-2 consumption."""
    path = data_dir / pipeline_config.PHASE1_MISSING_IDS_JSON
    missing_indices = [int(index) for index in invalid_df.index.tolist()]
    payload = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "total_rows": int(len(df)),
        "missing_rows_count": int(len(invalid_df)),
        "missing_rate": f"{(len(invalid_df) / len(df) * 100) if len(df) else 0:.2f}%",
        "missing_indices": missing_indices,
        "missing_details": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _copy_phase2_outputs(work_reports_dir: Path, data_dir: Path) -> tuple[Path, Path | None]:
    daily_src = work_reports_dir / "phase2_daily_stats.csv"
    anomalies_src = work_reports_dir / "phase2_anomalies.csv"
    daily_dst = data_dir / "phase2_daily_stats.csv"
    anomalies_dst = data_dir / "phase2_anomalies.csv"

    if not daily_src.exists():
        raise FileNotFoundError(f"Phase 2 daily stats were not generated: {daily_src}")

    shutil.copy2(daily_src, daily_dst)
    anomalies_path: Path | None = None
    if anomalies_src.exists():
        shutil.copy2(anomalies_src, anomalies_dst)
        anomalies_path = anomalies_dst
    elif anomalies_dst.exists():
        anomalies_dst.unlink()
    return daily_dst, anomalies_path


def run_mold_pipeline(
    *,
    raw_csv_path: Path,
    data_dir: Path,
    control_limits_path: Path | None = None,
) -> MoldPipelineResult:
    """Execute phases 1–3 for one uploaded monthly mold CSV."""
    raw_csv_path = raw_csv_path.resolve()
    data_dir = data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    limits_path = control_limits_path or (data_dir / "phase0_control_limits.json")
    if not limits_path.exists():
        raise FileNotFoundError(
            f"Phase 0 control limits not found at {limits_path}. "
            "Train limits offline before uploading monthly test data."
        )

    work_dir = data_dir / ".pipeline_work"
    reports_dir = work_dir / "reports"
    logs_dir = work_dir / "logs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Phase 1: validating %s", raw_csv_path.name)
    df = load_data(str(raw_csv_path))
    validator = DataValidator(log_dir=str(logs_dir), output_dir=str(work_dir))
    valid_df, invalid_df = validator.validate(df, data_path=str(raw_csv_path))
    missing_ids_path = write_missing_ids(
        data_dir=data_dir,
        df=df,
        invalid_df=invalid_df,
    )

    logger.info("Phase 2: X-R control chart on %s", raw_csv_path.name)
    xr_chart = XRControlChart(
        log_dir=str(logs_dir),
        output_dir=str(work_dir),
        target_columns=list(pipeline_config.TARGET_COLUMNS),
    )
    anomalies_df, _control_limits = xr_chart.run(
        data_path=str(raw_csv_path),
        missing_ids_path=str(missing_ids_path),
        control_limits_path=str(limits_path),
    )
    daily_stats_path, anomalies_path = _copy_phase2_outputs(reports_dir, data_dir)

    logger.info("Phase 3: feature engineering (%s mode)", pipeline_config.PHASE3_FEATURE_MODE)
    analyze_daily_data_count(raw_csv_path, output_dir=data_dir)
    feature_engineering = MoldFeatureEngineering(
        raw_csv_path,
        feature_mode=pipeline_config.PHASE3_FEATURE_MODE,
        log_to_file=False,
    )
    feature_engineering.run()
    features_csv_path = raw_csv_path.with_name(
        pipeline_config.get_phase3_output_filename(raw_csv_path.name, "features")
    )
    if not features_csv_path.exists():
        raise FileNotFoundError(
            f"Phase 3 features file was not generated: {features_csv_path.name}"
        )

    from app.manufacturing.infrastructure.mold_session import write_upload_manifest

    write_upload_manifest(
        data_dir=data_dir,
        source_file=raw_csv_path.name,
        upload_kind="raw",
        metadata={
            "total_rows": len(df),
            "valid_rows": len(valid_df),
            "missing_rows": len(invalid_df),
            "anomaly_count": len(anomalies_df),
        },
    )

    return MoldPipelineResult(
        raw_csv_path=raw_csv_path,
        features_csv_path=features_csv_path,
        daily_stats_path=daily_stats_path,
        anomalies_path=anomalies_path,
        missing_ids_path=missing_ids_path,
        daily_counts_path=data_dir / pipeline_config.PHASE3_DAILY_DATA_COUNTS_FILE,
        total_rows=len(df),
        valid_rows=len(valid_df),
        missing_rows=len(invalid_df),
        anomaly_count=len(anomalies_df),
    )
