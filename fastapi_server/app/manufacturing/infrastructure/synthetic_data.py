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

import csv
from pathlib import Path

from app.manufacturing.infrastructure.csv_data_source import (
    SYNTHETIC_CSV_PATH,
    build_fallback_csv_rows,
)

FIELDNAMES = [
    "日付",
    "ロット番号",
    "塗布長",
    "種別",
    "号機",
    "コーター部温度",
    "コーター部相対湿度",
    "ポンプ圧力",
    "乾燥ゾーン1温度",
    "乾燥ゾーン2温度",
    "UV照度",
    "ランプ点灯時間",
    "チャンバー内O2濃度",
    "UVロール温度",
    "ブリードアウト",
]


def write_synthetic_csv(path: Path = SYNTHETIC_CSV_PATH, days: int = 40) -> Path:
    rows = build_fallback_csv_rows(days=days)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return path


if __name__ == "__main__":
    generated_path = write_synthetic_csv()
    print(generated_path)
