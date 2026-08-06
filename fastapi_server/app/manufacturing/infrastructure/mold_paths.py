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

"""Filesystem layout for mold dashboard static and generated artifacts."""

from __future__ import annotations

import os
from pathlib import Path

MANUFACTURING_DATA_DIR = Path(__file__).parents[1] / "data"
DEFAULT_PHASE0_DATA_DIR = MANUFACTURING_DATA_DIR / "phase0_data"
DEFAULT_GENERATED_DATA_DIR = MANUFACTURING_DATA_DIR / "generated"

PHASE0_DATA_DIR_ENV = "MOLD_PHASE0_DATA_DIR"
GENERATED_DATA_DIR_ENV = "MOLD_GENERATED_DATA_DIR"
LEGACY_GENERATED_DATA_DIR_ENV = "MOLD_DASHBOARD_DATA_DIR"

PHASE0_CONTROL_LIMITS_FILE = "phase0_control_limits.json"


def get_phase0_data_dir() -> Path:
    configured = os.getenv(PHASE0_DATA_DIR_ENV)
    return Path(configured) if configured else DEFAULT_PHASE0_DATA_DIR


def get_generated_data_dir() -> Path:
    configured = os.getenv(GENERATED_DATA_DIR_ENV) or os.getenv(
        LEGACY_GENERATED_DATA_DIR_ENV
    )
    return Path(configured) if configured else DEFAULT_GENERATED_DATA_DIR


def get_mold_data_dir() -> Path:
    """Backward-compatible alias for the generated upload/pipeline directory."""
    return get_generated_data_dir()


def get_phase0_control_limits_path() -> Path:
    return get_phase0_data_dir() / PHASE0_CONTROL_LIMITS_FILE
