# Mold X-R dashboard adaptation

This branch adapts the Hata manufacturing demo into a **Noritz mold-machine X-R control chart dashboard**.

## Data layout

Static Phase 0 control limits and runtime pipeline outputs are split:

```
fastapi_server/app/manufacturing/data/
  phase0_data/
    phase0_control_limits.json     # shipped in git (offline training)
  generated/                       # gitignored — uploads + pipeline outputs
    upload_manifest.json
    {upload_stem}.csv
    phase1_missing_ids.json
    phase2_daily_stats.csv
    phase2_anomalies.csv
    phase3_daily_data_counts.json
    {upload_stem}_features.csv
    .pipeline_work/
```

Override directories with `MOLD_PHASE0_DATA_DIR` and `MOLD_GENERATED_DATA_DIR`
(`MOLD_DASHBOARD_DATA_DIR` remains a legacy alias for the generated directory).
Point scoring at a specific features file with `MOLD_FEATURES_CSV` (otherwise
`テストデータ_*_features.csv` is preferred over other `*_features.csv` files).

Test fixtures live under `fastapi_server/tests/fixtures/manufacturing/`.

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

## Monthly test data upload (phases 1–4)

Phase 0 (training data / control limits) is **not** run in the app. Ship
`phase0_control_limits.json` from offline training (`学習データ_202509-202603.csv`).

Users upload one month of raw mold CSV (~`テストデータ_202604.csv` format) from the dashboard
(**データ取込**) or via API:

```bash
curl -X POST http://localhost:8080/api/v1/manufacturing/dashboard/process \
  -F "file=@テストデータ_202604.csv"
```

The backend runs:

1. **Phase 1** — missing-row validation → `phase1_missing_ids.json`
2. **Phase 2** — daily X-R stats + JIS alerts → `phase2_daily_stats.csv`, `phase2_anomalies.csv`
3. **Phase 3** — TOP25 feature engineering → `{upload_stem}_features.csv`, `phase3_daily_data_counts.json`
4. **Phase 4** — live DataRobot batch scoring (background; dashboard polls until complete)

Pipeline code is vendored from [noritz_dashboard/src](https://github.com/datarobot/noritz_dashboard/tree/main/src)
under `fastapi_server/app/manufacturing/pipeline/`.

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
