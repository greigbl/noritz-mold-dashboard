# Mold X-R dashboard adaptation

This branch adapts the Hata manufacturing demo into a **Noritz mold-machine X-R control chart dashboard**.

## Data source

Pipeline outputs from `noritz_dashboard` are loaded from:

```
fastapi_server/app/manufacturing/data/mold/
  phase0_control_limits.json
  phase2_daily_stats.csv          # April 2026 test window (from monthly/)
  phase2_anomalies.csv
  テストデータ_202604.csv          # raw mold records (CP932)
  テストデータ_202604_features.csv # phase-3 features for live scoring
  phase3_daily_data_counts.json
```

Override with `MOLD_DASHBOARD_DATA_DIR`. Point scoring at a specific features file with
`MOLD_FEATURES_CSV` (otherwise `テストデータ_*_features.csv` is preferred over other
`*_features.csv` files).

Legacy local prediction outputs (`*_features_予測結果.csv`) are no longer required when
`MANUFACTURING_PREDICTION_DEPLOYMENT_ID` is configured. They remain supported as a
fallback for offline development when the deployment ID is unset.

## Anomaly scoring

When `MANUFACTURING_PREDICTION_DEPLOYMENT_ID` and DataRobot credentials are set, the
dashboard scores phase-3 feature rows through the deployed Isolation Forest anomaly model
using the DataRobot Python client (`Deployment.predict_batch`).

- Input features are discovered dynamically from the deployment (`/deployments/{id}/features/`).
- Scores are aggregated to daily maxima and per-(day, pattern) maxima for charts and chat context.
- Tune highlighting with `MANUFACTURING_ANOMALY_SCORE_THRESHOLD` (default `1.5e-6` for the current model scale).

## Behavior

- **Chart:** daily mean (`平均`) with Phase 0 CL / UCL / LCL
- **Display window:** latest **30 days**
- **Alert highlighting:** latest **7 days** only, from Phase 2 `違反ルール`
- **Selectors:** feature buttons → **吐出パターン番号** pulldown (nested)

## Mode switch

- Default: mold pipeline (`MANUFACTURING_MODE=mold` or unset)
- Original coater demo: `MANUFACTURING_MODE=coater`

## Local run

```bash
# backend
cd fastapi_server && uv sync --all-extras --dev && uv run uvicorn app.main:app --reload --port 8000

# frontend
cd frontend_web && npm install && npm run dev
```
