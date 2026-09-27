# HydroShield

Automated dam-break and flood-inundation decision-support workflow.

## Run locally

### Fastest development path

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[test]
$env:HYDROSHIELD_DEMO_MODE="true"
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Open the Vite URL shown in the terminal. Set `VITE_API_BASE_URL` in `frontend/.env` to the Render API URL when the frontend is deployed separately.

### Integrated Docker

```powershell
./run.ps1
```

Open `http://localhost:8080`.

## Render + Vercel

`render.yaml` deploys the FastAPI backend from `backend/`. Configure `HYDROSHIELD_DATABASE_URL`, `HYDROSHIELD_ALLOWED_HOSTS`, and `HYDROSHIELD_ALLOWED_ORIGINS` in Render.

Deploy `frontend/` as a Vercel project. Set:

```text
VITE_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com/api/v1
```

`frontend/vercel.json` provides the SPA rewrite required for React Router.

## Checks

```powershell
cd frontend
npm run lint
npm run build
node scripts/source-contract-check.mjs
node scripts/ui-contract-check.mjs
```

```powershell
cd backend
python -m compileall -q app
python -m pytest -q
```

HydroShield results are scenario-based decision-support outputs and depend on the quality and assumptions of the supplied terrain, breach, hydrologic and boundary inputs.
