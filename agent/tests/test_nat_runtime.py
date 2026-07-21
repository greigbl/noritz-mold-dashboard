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

from pathlib import Path


def test_nat_workflow_uses_the_dragent_standard_path() -> None:
    agent_root = Path(__file__).parents[1]

    assert (agent_root / "workflow.yaml").is_file()
    assert not (agent_root / "agent" / "workflow.yaml").exists()
