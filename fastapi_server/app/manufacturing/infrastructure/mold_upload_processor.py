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

from app.manufacturing.application.ports import MoldUploadProcessor
from app.manufacturing.infrastructure.mold_pipeline_service import save_and_process_raw_upload


@dataclass
class NoritzMoldUploadProcessor:
    """Run noritz_dashboard phases 1–3 on uploaded monthly CSV files."""

    def process_upload(self, *, content: bytes, filename: str) -> None:
        save_and_process_raw_upload(content=content, filename=filename)
