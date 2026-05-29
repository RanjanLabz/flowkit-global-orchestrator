from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import HTTPException
import yaml

from orchestrator.config.settings import WorkerSeed
from orchestrator.workers.client import WorkerClient
from orchestrator.workers.models import WorkerRecord, WorkerStatus


class WorkerRegistry:
    def __init__(self, seeds: list[WorkerSeed], client: WorkerClient, config_path: Path | None = None) -> None:
        self.client = client
        self.config_path = config_path
        self._workers: dict[str, WorkerRecord] = {
            seed.id: WorkerRecord(
                id=seed.id,
                base_url=seed.base_url,
                enabled=seed.enabled,
                max_jobs=seed.max_jobs,
                weight=seed.weight,
            )
            for seed in seeds
        }
        self._lock = asyncio.Lock()

    def list_workers(self) -> list[WorkerRecord]:
        return sorted(self._workers.values(), key=lambda worker: worker.id)

    def get(self, worker_id: str) -> WorkerRecord | None:
        return self._workers.get(worker_id)

    async def upsert(self, payload: dict) -> WorkerRecord:
        seed = WorkerSeed.model_validate(payload)
        async with self._lock:
            worker = WorkerRecord(
                id=seed.id,
                base_url=seed.base_url,
                enabled=seed.enabled,
                max_jobs=seed.max_jobs,
                weight=seed.weight,
                status=self._workers.get(seed.id).status if seed.id in self._workers else None,
            )
            self._workers[seed.id] = worker
            self._persist_locked()
            return worker

    async def delete(self, worker_id: str) -> None:
        async with self._lock:
            if worker_id not in self._workers:
                raise HTTPException(status_code=404, detail="worker not found")
            self._workers.pop(worker_id)
            self._persist_locked()

    async def refresh_one(self, worker: WorkerRecord) -> WorkerStatus:
        status = await self.client.health(worker)
        worker.status = status
        return status

    async def refresh_all(self) -> list[WorkerStatus]:
        statuses = await asyncio.gather(
            *(self.refresh_one(worker) for worker in self._workers.values() if worker.enabled),
            return_exceptions=True,
        )
        result: list[WorkerStatus] = []
        for status in statuses:
            if isinstance(status, WorkerStatus):
                result.append(status)
        return result

    def _persist_locked(self) -> None:
        if self.config_path is None:
            return
        data: dict[str, Any] = {}
        if self.config_path.exists():
            data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        data["workers"] = [
            {
                "id": worker.id,
                "base_url": worker.base_url,
                "enabled": worker.enabled,
                "max_jobs": worker.max_jobs,
                "weight": worker.weight,
            }
            for worker in self.list_workers()
        ]
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
