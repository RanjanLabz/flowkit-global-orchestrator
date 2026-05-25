from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query

from worker.accounts.manager import AccountManager
from worker.config.settings import Settings, load_settings
from worker.core.app_state import AppState
from worker.core.logging_config import configure_logging
from worker.health.reporter import HealthReporter
from worker.queue.manager import QueueManager
from worker.queue.scheduler import Scheduler
from worker.storage.account_store import AccountStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    settings.ensure_directories()
    configure_logging(settings)
    queue = QueueManager(settings.redis_url, settings.queue)
    await queue.connect()

    store = AccountStore(settings.paths.accounts_dir)
    account_manager = AccountManager(settings, store)
    await account_manager.load_existing_accounts()

    scheduler = Scheduler(settings, account_manager, queue)
    reporter = HealthReporter(settings, account_manager, queue)
    state = AppState(settings=settings, accounts=account_manager, queue=queue, scheduler=scheduler, health=reporter)
    app.state.worker = state

    await scheduler.start()
    yield
    await scheduler.stop()
    await account_manager.shutdown()
    await queue.close()


app = FastAPI(title="Flow Worker Appliance", version="1.0.0", lifespan=lifespan)


def state() -> AppState:
    return app.state.worker


@app.get("/health")
async def health() -> dict:
    return await state().health.snapshot()


@app.get("/accounts")
async def list_accounts() -> list[dict]:
    return [account.model_dump() for account in state().accounts.list_accounts()]


@app.get("/accounts/{account_id}")
async def get_account(account_id: str) -> dict:
    account = state().accounts.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return account.model_dump()


@app.post("/accounts", status_code=201)
async def create_account(payload: dict) -> dict:
    account = await state().accounts.create_account(payload)
    return account.model_dump()


@app.delete("/accounts/{account_id}")
async def delete_account(account_id: str, remove_profile: bool = Query(False)) -> dict:
    await state().accounts.delete_account(account_id, remove_profile=remove_profile)
    return {"deleted": True, "id": account_id, "profile_removed": remove_profile}


@app.post("/accounts/{account_id}/start")
async def start_account(account_id: str) -> dict:
    account = await state().accounts.start_account(account_id)
    return account.model_dump()


@app.post("/accounts/{account_id}/stop")
async def stop_account(account_id: str) -> dict:
    account = await state().accounts.stop_account(account_id)
    return account.model_dump()


@app.post("/accounts/{account_id}/restart")
async def restart_account(account_id: str) -> dict:
    account = await state().accounts.restart_account(account_id)
    return account.model_dump()


@app.post("/accounts/{account_id}/recover")
async def recover_account(account_id: str) -> dict:
    account = await state().accounts.recover_account(account_id, reason="manual-api")
    return account.model_dump()


@app.patch("/accounts/{account_id}/proxy")
async def patch_proxy(account_id: str, payload: dict) -> dict:
    account = await state().accounts.update_proxy(account_id, payload)
    return account.model_dump()


@app.patch("/accounts/{account_id}/settings")
async def patch_settings(account_id: str, payload: dict) -> dict:
    account = await state().accounts.update_settings(account_id, payload)
    return account.model_dump()


@app.post("/jobs", status_code=201)
async def create_job(payload: dict) -> dict:
    job = await state().queue.enqueue(payload)
    return job.model_dump()


@app.post("/flowkit/{account_id}/callback")
async def flowkit_callback(account_id: str, payload: dict) -> dict:
    return await state().accounts.handle_flowkit_callback(account_id, payload)


@app.get("/jobs")
async def list_jobs(limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    jobs = await state().queue.list_jobs(limit=limit)
    return [job.model_dump() for job in jobs]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await state().queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()


@app.get("/")
async def root() -> dict:
    return {"service": "flow-worker-appliance", "docs": "/docs", "health": "/health"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("worker.api.main:app", host="0.0.0.0", port=8080, workers=1, reload=False)
