# Mold X-R dashboard adaptation

This branch adapts the Hata manufacturing demo into a **Noritz mold-machine X-R control chart dashboard**.

## Data source

Pipeline outputs from `noritz_dashboard` are loaded from:

```
fastapi_server/app/manufacturing/data/mold/
  phase0_control_limits.json
  phase2_daily_stats.csv
  phase2_anomalies.csv
```

Override with `MOLD_DASHBOARD_DATA_DIR`.

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
