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

from app.manufacturing.models import ManufacturingAlert, ManufacturingDashboard


class InsightService:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    async def prepare_insights(
        self, dashboard: ManufacturingDashboard
    ) -> list[ManufacturingAlert]:
        if not dashboard.alerts:
            return []

        for alert in dashboard.alerts:
            alert.insight = self._cache.get(alert.dedup_key)
            if alert.insight is None:
                alert.insight = await self.generate_insight(alert, dashboard)
                self._cache[alert.dedup_key] = alert.insight
            alert.insight_status = "ready"

        return dashboard.alerts

    async def refresh_insight(
        self,
        alert: ManufacturingAlert,
        dashboard: ManufacturingDashboard | None = None,
    ) -> ManufacturingAlert:
        alert.insight = await self.generate_insight(alert, dashboard)
        alert.insight_status = "ready"
        self._cache[alert.dedup_key] = alert.insight
        return alert

    async def generate_insight(
        self,
        alert: ManufacturingAlert,
        dashboard: ManufacturingDashboard | None = None,
    ) -> str:
        latest_context = ""
        if dashboard is not None and dashboard.series:
            latest = dashboard.series[-1]
            latest_context = (
                f" 最新日のブリードアウト率は{latest.bleedout_rate:.1%}、"
                f"コーター部温度は{latest.coater_temperature:.2f}℃です。"
            )

        if alert.alert_type == "prediction_ai":
            return (
                "原因仮説: 予測モデルは直近の工程条件と品質実績の組み合わせを"
                "高リスクとして捉えています。確認観点: 温湿度、UV照度、"
                "ランプ点灯時間、原材料ロットの変更履歴を確認してください。"
                f"対応案: 影響ロットを優先検査し、しきい値{alert.threshold:.0%}"
                f"超過の継続有無を監視してください。{latest_context}"
            )

        if alert.alert_type == "spc_rbar":
            return (
                "原因仮説: 日内ばらつきがRbar管理限界を超えており、設備条件または"
                "測定条件が一時的に不安定化した可能性があります。確認観点: "
                "センサー校正、原材料ロット、設備設定変更、作業シフト切替時刻を"
                "確認してください。対応案: 同日ロットを層別し、管理限界外の時間帯を"
                f"重点確認してください。{latest_context}"
            )

        return (
            "原因仮説: 業務ルールに合致する異常兆候があります。確認観点: "
            "該当メトリクスの直近推移と設備・材料変更履歴を確認してください。"
            f"{latest_context}"
        )
