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

"""Infrastructure adapter for monthly mold upload processing."""

from __future__ import annotations

from pathlib import Path

from app.manufacturing.infrastructure.mold_data_source import get_mold_data_dir
from app.manufacturing.pipeline.orchestrator import (
    MoldPipelineResult,
    run_mold_pipeline,
    sanitize_upload_filename,
)


def save_and_process_raw_upload(*, content: bytes, filename: str) -> MoldPipelineResult:
    data_dir = get_mold_data_dir()
    safe_stem = sanitize_upload_filename(filename)
    raw_path = data_dir / f"{safe_stem}.csv"
    raw_path.write_bytes(content)
    return run_mold_pipeline(raw_csv_path=raw_path, data_dir=data_dir)


def result_features_path(result: MoldPipelineResult) -> Path:
    return result.features_csv_path
