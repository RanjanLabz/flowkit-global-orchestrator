# FlowKit Global Orchestrator

FastAPI global scheduler for the FlowKit VPS worker fleet.

This repository is intentionally orchestrator-only. It does not contain Chrome,
VNC, account profiles, Terraform state, the admin UI, or the worker appliance.

## Responsibilities

- Accept global generation jobs.
- Store and retry jobs in Redis.
- Store job, worker, account, metric, and flow-setting state in MongoDB.
- Track worker VPS capacity and health.
- Select an available VPS worker.
- Forward jobs to the selected worker.
- Keep global Flow model settings consistent for all workers.

## Render Deploy

Render uses `render.yaml` and `docker/orchestrator.Dockerfile`.

Required environment variables:

```text
ORCHESTRATOR_REDIS_URL=redis://...
ORCHESTRATOR_API_KEY=...
WORKER_API_KEY=...
MONGODB_URI=mongodb+srv://...
MONGODB_DATABASE=flowkit_orchestrator
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_BUCKET=flowkit-generated-media
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_PUBLIC_BASE_URL=
```

Worker VPS records are stored in the database. Do not hardcode Oracle IPs in
Render env for normal operation.

Register or update a VPS worker:

```bash
curl -X POST https://flowkit-global-orchestrator.onrender.com/workers \
  -H 'content-type: application/json' \
  -H 'x-api-key: <orchestrator-api-key>' \
  -d '{"id":"vps-1","base_url":"http://<oracle-public-ip>:8080","enabled":true,"max_jobs":10,"weight":100}'
```

Remove a VPS from scheduling:

```bash
curl -X DELETE https://flowkit-global-orchestrator.onrender.com/workers/vps-1 \
  -H 'x-api-key: <orchestrator-api-key>'
```

Health check:

```bash
curl https://flowkit-global-orchestrator.onrender.com/health
```

## Local Run

```bash
pip install -r requirements.txt
export ORCHESTRATOR_CONFIG=config/orchestrator.yaml
export ORCHESTRATOR_REDIS_URL=redis://...
export ORCHESTRATOR_API_KEY=dev-secret
export WORKER_API_KEY=dev-worker-secret
export MONGODB_URI=mongodb+srv://...
uvicorn orchestrator.api.main:app --host 0.0.0.0 --port 8090
```
