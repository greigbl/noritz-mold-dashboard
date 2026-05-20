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
import os
from collections import Counter
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

from app.manufacturing.models import ManufacturingDailyRecord

SYNTHETIC_CSV_PATH = Path(__file__).parent / "data" / "synthetic_manufacturing.csv"
LEGACY_CSV_PATH = Path(
    "/Users/ryosuke.hata/Documents/デモデータ/ブリードアウト/"
    "コーティング製品ブリードアウトmain_train.csv"
)
DEFAULT_CSV_PATH = SYNTHETIC_CSV_PATH
CSV_PATH_ENV = "MANUFACTURING_DASHBOARD_CSV_PATH"
SYNTHETIC_END_DATE = date(2026, 4, 27)
LOTS_PER_SYNTHETIC_DAY = 250

CsvManufacturingRow = dict[str, str]


def get_csv_path() -> Path:
    configured_path = os.getenv(CSV_PATH_ENV)
    return Path(configured_path) if configured_path else DEFAULT_CSV_PATH


def parse_length_m(value: str) -> float:
    return float(value.strip().lower().removesuffix("m"))


def parse_optional_float(value: str) -> float | None:
    stripped_value = value.strip()
    return float(stripped_value) if stripped_value else None


def parse_bool(value: str) -> bool:
    return value.strip().upper() == "TRUE"


def parse_row_date(value: str) -> date:
    return date.fromisoformat(value.strip())


def load_csv_rows(path: Path | None = None) -> list[CsvManufacturingRow]:
    csv_path = path or get_csv_path()
    if (
        not csv_path.exists()
        and csv_path == SYNTHETIC_CSV_PATH
        and LEGACY_CSV_PATH.exists()
    ):
        csv_path = LEGACY_CSV_PATH
    if not csv_path.exists():
        return build_fallback_csv_rows()

    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        return [dict(row) for row in csv.DictReader(csv_file)]


def build_fallback_csv_rows(days: int = 40) -> list[CsvManufacturingRow]:
    rows: list[CsvManufacturingRow] = []
    start_date = SYNTHETIC_END_DATE - timedelta(days=days - 1)
    global_index = 0
    for day_index in range(days):
        current_date = start_date + timedelta(days=day_index)
        lots_for_day = 220 + ((day_index * 17) % 61)
        for lot_index in range(lots_for_day):
            is_latest_issue = day_index == days - 1 and lot_index % 9 == 0
            rows.append(
                {
                    "日付": current_date.isoformat(),
                    "ロット番号": f"SC{current_date:%Y%m%d}-{lot_index + 1:04d}",
                    "塗布長": f"{[500, 1000, 1200, 1500][global_index % 4]}m",
                    "種別": "試作品" if global_index % 17 == 0 else "製造",
                    "号機": "YC-08",
                    "コーター部温度": (
                        f"{28.2 + (lot_index % 3) * 0.01 + (0.15 if is_latest_issue else 0):.2f}"
                    ),
                    "コーター部相対湿度": (
                        f"{50.5 + (lot_index % 5) * 0.1 + (1.2 if is_latest_issue else 0):.1f}"
                    ),
                    "ポンプ圧力": f"{0.9 + (lot_index % 4) * 0.002:.3f}",
                    "乾燥ゾーン1温度": f"{120.0 + (lot_index % 6) * 0.02:.2f}",
                    "乾燥ゾーン2温度": f"{122.0 + (lot_index % 7) * 0.025:.2f}",
                    "UV照度": (
                        f"{1020.2 + (lot_index % 9) * 0.2 + (5.0 if is_latest_issue else 0):.1f}"
                    ),
                    "ランプ点灯時間": str(600 + global_index % 1800),
                    "チャンバー内O2濃度": f"{0.011 + (0.001 if is_latest_issue else 0):.5f}",
                    "UVロール温度": f"{89.05 + (0.02 if global_index % 19 == 0 else 0):.2f}",
                    "ブリードアウト": "TRUE" if is_latest_issue else "FALSE",
                }
            )
            global_index += 1
    return rows


def values(rows: Iterable[CsvManufacturingRow], key: str) -> list[float]:
    return [
        parsed_value
        for row in rows
        if (parsed_value := parse_optional_float(row.get(key, ""))) is not None
    ]


def average(rows: Iterable[CsvManufacturingRow], key: str) -> float:
    parsed_values = values(rows, key)
    if not parsed_values:
        return 0.0
    return round(mean(parsed_values), 4)


def value_range(rows: Iterable[CsvManufacturingRow], key: str) -> float:
    parsed_values = values(rows, key)
    if len(parsed_values) < 2:
        return 0.0
    return round(max(parsed_values) - min(parsed_values), 4)


def most_common_value(rows: Iterable[CsvManufacturingRow], key: str) -> str:
    values_by_key = [row[key].strip() for row in rows if row.get(key, "").strip()]
    if not values_by_key:
        return ""
    return Counter(values_by_key).most_common(1)[0][0]


def aggregate_daily_records(
    rows: list[CsvManufacturingRow],
    lots_per_day: int = LOTS_PER_SYNTHETIC_DAY,
    end_date: date = SYNTHETIC_END_DATE,
) -> list[ManufacturingDailyRecord]:
    if not rows:
        return []

    daily_records: list[ManufacturingDailyRecord] = []
    rows_with_dates = [row for row in rows if row.get("日付", "").strip()]

    if rows_with_dates:
        grouped_rows: dict[date, list[CsvManufacturingRow]] = {}
        for row in rows_with_dates:
            grouped_rows.setdefault(parse_row_date(row["日付"]), []).append(row)

        for record_date in sorted(grouped_rows):
            daily_records.append(
                build_daily_record(record_date, grouped_rows[record_date])
            )
        return daily_records

    day_count = (len(rows) + lots_per_day - 1) // lots_per_day
    start_date = end_date - timedelta(days=day_count - 1)

    for day_index in range(day_count):
        day_rows = rows[day_index * lots_per_day : (day_index + 1) * lots_per_day]
        daily_records.append(
            build_daily_record(start_date + timedelta(days=day_index), day_rows)
        )

    return daily_records


def build_daily_record(
    record_date: date,
    day_rows: list[CsvManufacturingRow],
) -> ManufacturingDailyRecord:
    coating_lengths = [parse_length_m(row["塗布長"]) for row in day_rows]
    bleedout_count = sum(1 for row in day_rows if parse_bool(row["ブリードアウト"]))
    lots_produced = len(day_rows)

    return ManufacturingDailyRecord(
        date=record_date,
        lots_produced=lots_produced,
        total_coating_length_m=round(sum(coating_lengths), 1),
        bleedout_count=bleedout_count,
        bleedout_rate=round(bleedout_count / lots_produced, 4),
        coating_length_category=most_common_value(day_rows, "塗布長"),
        coating_length_avg_m=round(mean(coating_lengths), 1),
        product_type=most_common_value(day_rows, "種別"),
        coater_temperature=average(day_rows, "コーター部温度"),
        coater_temperature_range=value_range(day_rows, "コーター部温度"),
        coater_humidity=average(day_rows, "コーター部相対湿度"),
        coater_humidity_range=value_range(day_rows, "コーター部相対湿度"),
        pump_pressure=average(day_rows, "ポンプ圧力"),
        pump_pressure_range=value_range(day_rows, "ポンプ圧力"),
        drying_zone1_temperature=average(day_rows, "乾燥ゾーン1温度"),
        drying_zone1_temperature_range=value_range(day_rows, "乾燥ゾーン1温度"),
        drying_zone2_temperature=average(day_rows, "乾燥ゾーン2温度"),
        drying_zone2_temperature_range=value_range(day_rows, "乾燥ゾーン2温度"),
        uv_irradiance=average(day_rows, "UV照度"),
        uv_irradiance_range=value_range(day_rows, "UV照度"),
        lamp_lighting_hours=average(day_rows, "ランプ点灯時間"),
        chamber_o2_concentration=average(day_rows, "チャンバー内O2濃度"),
        chamber_o2_concentration_range=value_range(day_rows, "チャンバー内O2濃度"),
        uv_roll_temperature=average(day_rows, "UVロール温度"),
        uv_roll_temperature_range=value_range(day_rows, "UVロール温度"),
    )
