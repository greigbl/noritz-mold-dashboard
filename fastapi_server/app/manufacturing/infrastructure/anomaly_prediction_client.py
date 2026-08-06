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

"""Live anomaly scoring for the mold dashboard via DataRobot deployments."""

from __future__ import annotations

import asyncio
import csv
import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import datarobot as dr
import pandas as pd
import requests
from datarobot import Deployment

from app.manufacturing.application.ports import AnomalyPredictionClient
from app.manufacturing.domain.anomaly_scores import (
    DEFAULT_ANOMALY_SCORE_THRESHOLD,
    AnomalyScoreAggregates,
)
from app.manufacturing.domain.models import PredictionStatus
from app.manufacturing.infrastructure.mold_data_source import (
    get_mold_data_dir,
    parse_production_day,
)
from app.manufacturing.infrastructure.mold_feature_loader import (
    PASSTHROUGH_COLUMNS,
    features_csv_cache_key,
    find_features_csv,
    load_feature_rows,
)

MANUFACTURING_PREDICTION_DEPLOYMENT_ID = "MANUFACTURING_PREDICTION_DEPLOYMENT_ID"
MANUFACTURING_ANOMALY_SCORE_THRESHOLD = "MANUFACTURING_ANOMALY_SCORE_THRESHOLD"
DATAROBOT_ENDPOINT = "DATAROBOT_ENDPOINT"
DATAROBOT_API_TOKEN = "DATAROBOT_API_TOKEN"
DATAROBOT_API_KEY = "DATAROBOT_API_KEY"
LEGACY_PREDICTION_CSV_GLOB = "*_features_予測結果.csv"

logger = logging.getLogger(__name__)


def read_passthrough_value(row: pd.Series, column: str) -> object | None:
    """Read a passthrough column from a prediction row.

    DataRobot batch responses may suffix duplicate passthrough columns as
    ``column_x`` / ``column_y`` when merging prediction output with inputs.
    """
    for key in (column, f"{column}_x", f"{column}_y"):
        if key not in row.index:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, float) and pd.isna(value):
            continue
        if value == "":
            continue
        return value
    return None


@dataclass
class LocalCsvAnomalyPredictionClient:
    """Read pre-scored ANOMALY_SCORE values from a legacy local results CSV."""

    run_in_background: bool = False
    threshold: float = DEFAULT_ANOMALY_SCORE_THRESHOLD

    async def predict_scores(
        self,
        *,
        min_day: date | None = None,
        data_dir: Path | None = None,
    ) -> AnomalyScoreAggregates:
        return await asyncio.to_thread(
            self._predict_scores_sync,
            min_day=min_day,
            data_dir=data_dir,
        )

    def _predict_scores_sync(
        self,
        *,
        min_day: date | None,
        data_dir: Path | None,
    ) -> AnomalyScoreAggregates:
        root = data_dir or get_mold_data_dir()
        matches = sorted(root.glob(LEGACY_PREDICTION_CSV_GLOB))
        if not matches:
            return AnomalyScoreAggregates({}, {}, "unavailable", self.threshold)

        path = matches[0]
        by_day: dict[date, float] = {}
        by_day_pattern: dict[tuple[date, int], float] = {}

        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                return AnomalyScoreAggregates({}, {}, "unavailable", self.threshold)

            try:
                score_idx = header.index("ANOMALY_SCORE")
                date_idx = header.index("生産日")
                pattern_idx = header.index("吐出パターン番号")
            except ValueError:
                return AnomalyScoreAggregates({}, {}, "error", self.threshold)

            for row in reader:
                if len(row) <= max(score_idx, date_idx, pattern_idx):
                    continue
                day = parse_production_day(row[date_idx])
                if day is None or (min_day is not None and day < min_day):
                    continue
                try:
                    score = float(row[score_idx])
                    pattern = int(float(row[pattern_idx]))
                except ValueError:
                    continue

                current_day = by_day.get(day)
                if current_day is None or score > current_day:
                    by_day[day] = score

                key = (day, pattern)
                current_pattern = by_day_pattern.get(key)
                if current_pattern is None or score > current_pattern:
                    by_day_pattern[key] = score

        status: PredictionStatus = "local" if by_day else "unavailable"
        return AnomalyScoreAggregates(
            by_day=by_day,
            by_day_pattern=by_day_pattern,
            status=status,
            threshold=self.threshold,
        )


@dataclass
class DataRobotAnomalyPredictionClient:
    """Score mold feature rows through a deployed anomaly model."""

    deployment_id: str
    endpoint: str
    api_token: str
    threshold: float = DEFAULT_ANOMALY_SCORE_THRESHOLD
    run_in_background: bool = True

    _feature_columns: list[str] | None = None
    _features_cache_key: str | None = None
    _cached_result: AnomalyScoreAggregates | None = None

    def clear_cache(self) -> None:
        """Drop cached scores so the next request re-scores fresh feature rows."""
        self._feature_columns = None
        self._features_cache_key = None
        self._cached_result = None

    async def predict_scores(
        self,
        *,
        min_day: date | None = None,
        data_dir: Path | None = None,
    ) -> AnomalyScoreAggregates:
        cache_key = self._build_cache_key(min_day=min_day, data_dir=data_dir)
        if self._cached_result is not None and self._features_cache_key == cache_key:
            return self._cached_result

        result = await asyncio.to_thread(
            self._predict_scores_sync,
            min_day=min_day,
            data_dir=data_dir,
        )
        if result.by_day:
            self._features_cache_key = cache_key
            self._cached_result = result
        return result

    def _build_cache_key(
        self,
        *,
        min_day: date | None,
        data_dir: Path | None,
    ) -> str:
        features_key = features_csv_cache_key(data_dir) or "missing"
        min_day_key = min_day.isoformat() if min_day else "all"
        return f"{self.deployment_id}:{features_key}:{min_day_key}"

    def _predict_scores_sync(
        self,
        *,
        min_day: date | None,
        data_dir: Path | None,
    ) -> AnomalyScoreAggregates:
        if find_features_csv(data_dir) is None:
            logger.warning("No mold features CSV found for anomaly scoring.")
            return AnomalyScoreAggregates({}, {}, "unavailable", self.threshold)

        feature_columns = self._load_feature_columns()
        try:
            rows = load_feature_rows(
                data_dir=data_dir,
                feature_columns=feature_columns,
                min_day=min_day,
            )
        except ValueError as exc:
            logger.warning("Mold features CSV is incompatible with deployment: %s", exc)
            return AnomalyScoreAggregates({}, {}, "error", self.threshold)

        if not rows:
            return AnomalyScoreAggregates({}, {}, "unavailable", self.threshold)

        try:
            dr.Client(token=self.api_token, endpoint=self.endpoint)
            deployment = Deployment.get(self.deployment_id)
            frame = pd.DataFrame(rows)
            passthrough_columns = [
                column for column in PASSTHROUGH_COLUMNS if column in frame.columns
            ]
            result = deployment.predict_batch(
                source=frame,
                passthrough_columns=passthrough_columns,
            )
        except Exception as exc:  # noqa: BLE001 - surface deployment failures to dashboard status
            logger.warning("DataRobot anomaly scoring failed: %s", exc)
            return AnomalyScoreAggregates({}, {}, "error", self.threshold)

        return self._aggregate_predictions(result)

    def _load_feature_columns(self) -> list[str]:
        if self._feature_columns is not None:
            return self._feature_columns

        headers = {
            "Authorization": f"Bearer {self.api_token}",
        }
        response = requests.get(
            f"{self.endpoint.rstrip('/')}/deployments/{self.deployment_id}/features/",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        features = [item["name"] for item in payload.get("data", []) if item.get("name")]
        if not features:
            raise ValueError(
                f"Deployment {self.deployment_id} returned no input features."
            )
        self._feature_columns = features
        return features

    def _aggregate_predictions(self, frame: pd.DataFrame) -> AnomalyScoreAggregates:
        score_column = "ANOMALY_SCORE" if "ANOMALY_SCORE" in frame.columns else "prediction"
        if score_column not in frame.columns:
            logger.warning(
                "Anomaly deployment response missing score column. Columns: %s",
                list(frame.columns),
            )
            return AnomalyScoreAggregates({}, {}, "error", self.threshold)

        by_day: dict[date, float] = {}
        by_day_pattern: dict[tuple[date, int], float] = {}

        for _, row in frame.iterrows():
            try:
                score = float(row[score_column])
            except (TypeError, ValueError):
                continue

            day_raw = read_passthrough_value(row, "生産日")
            day = parse_production_day(str(day_raw or ""))
            if day is None:
                continue

            current_day = by_day.get(day)
            if current_day is None or score > current_day:
                by_day[day] = score

            pattern_raw = read_passthrough_value(row, "吐出パターン番号")
            if pattern_raw in (None, ""):
                continue
            try:
                pattern = int(float(pattern_raw))
            except (TypeError, ValueError):
                continue

            key = (day, pattern)
            current_pattern = by_day_pattern.get(key)
            if current_pattern is None or score > current_pattern:
                by_day_pattern[key] = score

        status: PredictionStatus = "available" if by_day else "error"
        return AnomalyScoreAggregates(
            by_day=by_day,
            by_day_pattern=by_day_pattern,
            status=status,
            threshold=self.threshold,
        )


def resolve_anomaly_score_threshold() -> float:
    raw = os.getenv(MANUFACTURING_ANOMALY_SCORE_THRESHOLD)
    if raw is None or raw.strip() == "":
        return DEFAULT_ANOMALY_SCORE_THRESHOLD
    return float(raw)


def create_anomaly_prediction_client_from_env() -> AnomalyPredictionClient:
    deployment_id = os.getenv(MANUFACTURING_PREDICTION_DEPLOYMENT_ID)
    endpoint = os.getenv(DATAROBOT_ENDPOINT)
    api_token = os.getenv(DATAROBOT_API_TOKEN) or os.getenv(DATAROBOT_API_KEY)
    threshold = resolve_anomaly_score_threshold()

    if deployment_id and endpoint and api_token:
        return DataRobotAnomalyPredictionClient(
            deployment_id=deployment_id,
            endpoint=endpoint,
            api_token=api_token,
            threshold=threshold,
        )

    return LocalCsvAnomalyPredictionClient(threshold=threshold)
