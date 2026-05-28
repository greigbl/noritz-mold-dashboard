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

import asyncio
import csv
import io
import logging
import os
from typing import Any, cast
from urllib.parse import urljoin

import httpx

from app.manufacturing.application.ports import PredictionClient
from app.manufacturing.domain.models import (
    ManufacturingDailyRecord,
    PredictionResult,
    PredictionStatus,
)

MANUFACTURING_PREDICTION_DEPLOYMENT_ID = "MANUFACTURING_PREDICTION_DEPLOYMENT_ID"
FALLBACK_DEPLOYMENT_ID = "DEPLOYMENT_ID"
DATAROBOT_ENDPOINT = "DATAROBOT_ENDPOINT"
DATAROBOT_API_TOKEN = "DATAROBOT_API_TOKEN"
DATAROBOT_API_KEY = "DATAROBOT_API_KEY"
DEFAULT_BATCH_POLL_INTERVAL_SECS = 5.0
DEFAULT_BATCH_TIMEOUT_SECS = 600.0
POSITIVE_CLASS_LABELS = {
    "true",
    "1",
    "1.0",
    "yes",
    "y",
    "ブリードアウト",
    "あり",
    "発生",
}
NEGATIVE_CLASS_LABELS = {"false", "0", "0.0", "no", "n", "なし", "未発生", "正常"}
PREDICTION_FEATURE_COLUMNS = [
    "乾燥ゾーン1温度",
    "UVロール温度",
    "塗布長",
    "種別",
    "ランプ点灯時間",
    "チャンバー内O2濃度",
    "コーター部相対湿度",
]

logger = logging.getLogger(__name__)


class LocalManufacturingPredictionClient:
    status: PredictionStatus = "local"

    async def predict(
        self, series: list[ManufacturingDailyRecord]
    ) -> list[PredictionResult]:
        predictions: list[PredictionResult] = []
        for record in series:
            probability = estimate_local_bleedout_probability(record)
            predictions.append(
                PredictionResult(
                    date=record.date,
                    probability=probability,
                    label=(
                        "high_risk"
                        if probability >= LOCAL_PREDICTION_ALERT_THRESHOLD
                        else "normal"
                    ),
                )
            )
        return predictions


class DataRobotPredictionClient:
    run_in_background = True

    def __init__(
        self,
        deployment_id: str,
        endpoint: str,
        api_token: str,
        timeout_secs: float = DEFAULT_BATCH_TIMEOUT_SECS,
        poll_interval_secs: float = DEFAULT_BATCH_POLL_INTERVAL_SECS,
    ) -> None:
        self.deployment_id = deployment_id
        self.endpoint = endpoint.rstrip("/").removesuffix("/api/v2")
        self.api_token = api_token
        self.timeout_secs = timeout_secs
        self.poll_interval_secs = poll_interval_secs
        self.status: PredictionStatus = "available"

    async def predict(
        self, series: list[ManufacturingDailyRecord]
    ) -> list[PredictionResult]:
        if not series:
            return []

        csv_payload = build_prediction_csv(series).encode("utf-8")
        url = urljoin(f"{self.endpoint}/", "api/v2/batchPredictions/")
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "User-Agent": "ManufacturingDashboardBatchPrediction",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_secs,
                follow_redirects=True,
            ) as client:
                job = await self.create_batch_prediction_job(client, url, headers)
                await self.upload_batch_prediction_csv(
                    client,
                    job,
                    csv_payload,
                    headers,
                )
                completed_job = await self.wait_for_batch_prediction_job(
                    client,
                    job,
                    headers,
                )
                response_text = await self.download_batch_prediction_csv(
                    client,
                    completed_job,
                    headers,
                )
        except httpx.HTTPError as exc:
            logger.warning("Manufacturing batch prediction request failed: %s", exc)
            self.status = "error"
            return []
        except KeyError as exc:
            logger.warning("Manufacturing batch prediction response missing %s", exc)
            self.status = "error"
            return []

        self.status = "available"
        return parse_prediction_csv_response(response_text, series)

    async def create_batch_prediction_job(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        response = await client.post(
            url,
            json={
                "deploymentId": self.deployment_id,
                "includePredictionStatus": True,
            },
            headers=headers,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def upload_batch_prediction_csv(
        self,
        client: httpx.AsyncClient,
        job: dict[str, Any],
        csv_payload: bytes,
        headers: dict[str, str],
    ) -> None:
        response = await client.put(
            job["links"]["csvUpload"],
            content=csv_payload,
            headers={
                **headers,
                "Content-Length": str(len(csv_payload)),
                "Content-Type": "text/csv; encoding=utf-8",
            },
        )
        response.raise_for_status()

    async def wait_for_batch_prediction_job(
        self,
        client: httpx.AsyncClient,
        job: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        job_url = job["links"]["self"]
        while True:
            response = await client.get(job_url, headers=headers)
            response.raise_for_status()
            current_job = cast(dict[str, Any], response.json())
            status = current_job["status"]
            if status == "COMPLETED":
                return current_job
            if status == "ABORTED":
                self.status = "error"
                raise httpx.HTTPStatusError(
                    "DataRobot batch prediction job was aborted.",
                    request=response.request,
                    response=response,
                )

            logger.info(
                "Manufacturing batch prediction job %s is %s (%s%%)",
                current_job.get("id"),
                status,
                current_job.get("percentageCompleted", 0),
            )
            await asyncio.sleep(self.poll_interval_secs)

    async def download_batch_prediction_csv(
        self,
        client: httpx.AsyncClient,
        job: dict[str, Any],
        headers: dict[str, str],
    ) -> str:
        response = await client.get(job["links"]["download"], headers=headers)
        response.raise_for_status()
        return response.text


def create_prediction_client_from_env() -> PredictionClient:
    deployment_id = os.getenv(MANUFACTURING_PREDICTION_DEPLOYMENT_ID) or os.getenv(
        FALLBACK_DEPLOYMENT_ID
    )
    endpoint = os.getenv(DATAROBOT_ENDPOINT)
    api_token = os.getenv(DATAROBOT_API_TOKEN) or os.getenv(DATAROBOT_API_KEY)

    if not deployment_id or not endpoint or not api_token:
        return LocalManufacturingPredictionClient()

    return DataRobotPredictionClient(
        deployment_id=deployment_id,
        endpoint=endpoint,
        api_token=api_token,
    )


LOCAL_PREDICTION_ALERT_THRESHOLD = 0.8


def estimate_local_bleedout_probability(record: ManufacturingDailyRecord) -> float:
    probability = (
        0.05
        + 6.0 * record.bleedout_rate
        + 0.03 * record.coater_temperature_range
        + 0.02 * record.coater_humidity_range
        + 0.02 * record.uv_irradiance_range
        + 20.0 * record.chamber_o2_concentration_range
    )
    return round(min(max(probability, 0.01), 0.98), 4)


def record_to_prediction_payload(record: ManufacturingDailyRecord) -> dict[str, Any]:
    return {
        "乾燥ゾーン1温度": record.drying_zone1_temperature,
        "UVロール温度": record.uv_roll_temperature,
        "塗布長": record.coating_length_category,
        "種別": record.product_type,
        "ランプ点灯時間": record.lamp_lighting_hours,
        "チャンバー内O2濃度": record.chamber_o2_concentration,
        "コーター部相対湿度": record.coater_humidity,
    }


def build_prediction_csv(series: list[ManufacturingDailyRecord]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PREDICTION_FEATURE_COLUMNS)
    writer.writeheader()
    writer.writerows(record_to_prediction_payload(record) for record in series)
    return output.getvalue()


def parse_prediction_response(
    payload: dict[str, Any],
    series: list[ManufacturingDailyRecord],
) -> list[PredictionResult]:
    rows = payload.get("data", [])
    predictions: list[PredictionResult] = []

    for index, row in enumerate(rows):
        if index >= len(series):
            break

        probability, label = extract_probability(row)
        if probability is None:
            continue

        predictions.append(
            PredictionResult(
                date=series[index].date,
                probability=probability,
                label=label,
                source_id=series[index].lot_id,
            )
        )

    return predictions


def parse_prediction_csv_response(
    response_text: str,
    series: list[ManufacturingDailyRecord],
) -> list[PredictionResult]:
    rows = list(csv.DictReader(io.StringIO(response_text)))
    predictions: list[PredictionResult] = []

    for index, row in enumerate(rows):
        if index >= len(series):
            break

        probability, label = extract_probability_from_csv_row(row)
        if probability is None:
            continue

        predictions.append(
            PredictionResult(
                date=series[index].date,
                probability=probability,
                label=label,
                source_id=series[index].lot_id,
            )
        )

    return predictions


def extract_probability(row: dict[str, Any]) -> tuple[float | None, str | None]:
    if isinstance(row.get("predictionProbability"), int | float):
        return float(row["predictionProbability"]), row.get("prediction")
    if isinstance(row.get("probability"), int | float):
        return float(row["probability"]), row.get("prediction")

    prediction_values = row.get("predictionValues")
    if not isinstance(prediction_values, list):
        return None, row.get("prediction")

    best_value: tuple[float, str | None] | None = None
    for item in prediction_values:
        if not isinstance(item, dict) or not isinstance(item.get("value"), int | float):
            continue
        label = str(item.get("label")) if item.get("label") is not None else None
        value = float(item["value"])
        if label is not None and label.lower() in POSITIVE_CLASS_LABELS:
            return value, label
        if best_value is None or value > best_value[0]:
            best_value = (value, label)

    if best_value is None:
        return None, row.get("prediction")
    return best_value


def extract_probability_from_csv_row(
    row: dict[str, str],
) -> tuple[float | None, str | None]:
    label = first_prediction_label(row)
    probability_columns = [
        (column, parsed_value)
        for column, raw_value in row.items()
        if is_probability_column(column, label)
        if (parsed_value := parse_float(raw_value)) is not None
    ]

    for column, value in probability_columns:
        column_label = prediction_label_from_column(column)
        if column_label is not None and column_label.lower() in POSITIVE_CLASS_LABELS:
            return value, column_label

    if not probability_columns:
        return None, label

    column, value = max(probability_columns, key=lambda item: item[1])
    return value, prediction_label_from_column(column) or label


def first_prediction_label(row: dict[str, str]) -> str | None:
    if row.get("prediction"):
        return row["prediction"]

    for column, value in row.items():
        if not column.upper().endswith("_PREDICTION"):
            continue
        if parse_float(value) is None and value:
            return value
    return None


def is_probability_column(column: str, predicted_label: str | None = None) -> bool:
    normalized = column.lower()
    if (
        "prediction" in normalized
        or "probability" in normalized
        or "class_" in normalized
    ):
        return True

    column_label = prediction_label_from_column(column)
    if column_label is None:
        return False

    normalized_label = column_label.lower()
    if normalized_label in POSITIVE_CLASS_LABELS | NEGATIVE_CLASS_LABELS:
        return True
    return predicted_label is not None and normalized_label == predicted_label.lower()


def prediction_label_from_column(column: str) -> str | None:
    normalized = column.removesuffix("_PREDICTION")
    parts = [
        part
        for part in normalized.replace("-", "_").replace(" ", "_").split("_")
        if part
    ]
    if not parts:
        return None
    return parts[-1]


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
