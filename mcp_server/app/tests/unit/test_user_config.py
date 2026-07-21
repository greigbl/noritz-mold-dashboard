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

from app.core.user_config import UserAppConfig


def test_runtime_parameter_payload_sets_user_name(
    monkeypatch,
) -> None:
    monkeypatch.delenv("USER_NAME", raising=False)
    monkeypatch.setenv(
        "MLOPS_RUNTIME_PARAM_USER_NAME",
        '{"type": "string", "payload": "runtime-parameter-user"}',
    )

    config = UserAppConfig()

    assert config.user_name == "runtime-parameter-user"
