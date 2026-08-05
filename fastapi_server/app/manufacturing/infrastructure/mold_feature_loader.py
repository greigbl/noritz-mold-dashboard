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

"""Load engineered mold feature rows for anomaly deployment scoring."""

from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path

from app.manufacturing.infrastructure.mold_data_source import (
    get_mold_data_dir,
    parse_production_day,
)

MOLD_FEATURES_CSV_ENV = "MOLD_FEATURES_CSV"
TEST_FEATURES_CSV_GLOB = "テストデータ_*_features.csv"
FEATURES_CSV_GLOB = "*_features.csv"
LEGACY_PREDICTION_CSV_GLOB = "*_features_予測結果.csv"

PASSTHROUGH_COLUMNS = ("生産日", "吐出パターン番号")

PREDICTION_OUTPUT_COLUMNS = frozenset(
    {
        "ANOMALY_SCORE",
        "DEPLOYMENT_APPROVAL_STATUS",
        "prediction_status",
        "SHAP_BASE_VALUE",
        "SHAP_REMAINING_TOTAL",
    }
)


def find_features_csv(data_dir: Path | None = None) -> Path | None:
    configured = os.getenv(MOLD_FEATURES_CSV_ENV)
    if configured:
        path = Path(configured)
        return path if path.is_file() else None

    root = data_dir or get_mold_data_dir()
    test_matches = sorted(root.glob(TEST_FEATURES_CSV_GLOB))
    if test_matches:
        return test_matches[-1]

    matches = sorted(root.glob(FEATURES_CSV_GLOB))
    if matches:
        return matches[0]
    legacy_matches = sorted(root.glob(LEGACY_PREDICTION_CSV_GLOB))
    return legacy_matches[0] if legacy_matches else None


def is_prediction_output_column(column: str) -> bool:
    if column in PREDICTION_OUTPUT_COLUMNS:
        return True
    return column.startswith(("EXPLANATION_", "SHAP_"))


def load_feature_rows(
    *,
    data_dir: Path | None = None,
    feature_columns: list[str],
    min_day: date | None = None,
) -> list[dict[str, str]]:
    """Load feature rows from the mold features CSV, optionally filtered by 生産日."""
    path = find_features_csv(data_dir)
    if path is None:
        return []

    required = set(feature_columns) | set(PASSTHROUGH_COLUMNS)
    rows: list[dict[str, str]] = []

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []

        missing = [column for column in required if column not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"Features file '{path.name}' is missing deployment columns: "
                f"{', '.join(missing)}"
            )

        for row in reader:
            if min_day is not None:
                day = parse_production_day(row.get("生産日", ""))
                if day is None or day < min_day:
                    continue

            rows.append({column: row.get(column, "") for column in required})

    return rows


def features_csv_cache_key(data_dir: Path | None = None) -> str | None:
    path = find_features_csv(data_dir)
    if path is None:
        return None
    return f"{path.resolve()}:{path.stat().st_mtime_ns}"


