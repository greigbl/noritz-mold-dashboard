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

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.manufacturing.domain.models import PredictionStatus

DEFAULT_ANOMALY_SCORE_THRESHOLD = 1.5e-6


@dataclass(frozen=True)
class AnomalyScoreAggregates:
    by_day: dict[date, float]
    by_day_pattern: dict[tuple[date, int], float]
    status: PredictionStatus
    threshold: float = DEFAULT_ANOMALY_SCORE_THRESHOLD


def empty_anomaly_scores() -> AnomalyScoreAggregates:
    return AnomalyScoreAggregates(
        by_day={},
        by_day_pattern={},
        status="unavailable",
        threshold=DEFAULT_ANOMALY_SCORE_THRESHOLD,
    )
