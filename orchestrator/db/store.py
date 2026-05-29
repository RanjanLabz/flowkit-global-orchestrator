from __future__ import annotations

import logging
from typing import Any

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from orchestrator.queue.models import GlobalJob
from orchestrator.workers.models import WorkerStatus

logger = logging.getLogger(__name__)


class OrchestratorStore:
    def __init__(self, database_url: str | None, mongodb_uri: str | None = None, mongodb_database: str = "flowkit_orchestrator") -> None:
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None
        self.mongodb_uri = mongodb_uri
        self.mongodb_database = mongodb_database
        self.mongo_client: AsyncIOMotorClient | None = None
        self.mongo_db: AsyncIOMotorDatabase | None = None
        self.backend = "mongodb" if mongodb_uri else "postgres" if database_url else "disabled"
        self.connection_error: str | None = None

    async def connect(self) -> None:
        if self.mongodb_uri:
            try:
                self.mongo_client = AsyncIOMotorClient(self.mongodb_uri, serverSelectionTimeoutMS=8000)
                await self.mongo_client.admin.command("ping")
                self.mongo_db = self.mongo_client[self.mongodb_database]
                await self._migrate_mongo()
                self.connection_error = None
            except Exception as exc:
                self.connection_error = str(exc)
                logger.exception("MongoDB persistence is unavailable")
                if self.mongo_client is not None:
                    self.mongo_client.close()
                self.mongo_client = None
                self.mongo_db = None
            return
        if not self.database_url:
            return
        self.pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5)
        await self._migrate()

    async def close(self) -> None:
        if self.mongo_client is not None:
            self.mongo_client.close()
        if self.pool is not None:
            await self.pool.close()

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "connected": self.mongo_db is not None or self.pool is not None,
            "database": self.mongodb_database if self.mongodb_uri else None,
            "error": self.connection_error,
        }

    async def save_job(self, job: GlobalJob) -> None:
        if self.mongo_db is not None:
            await self.mongo_db.jobs.update_one(
                {"_id": job.id},
                {
                    "$set": {
                        **job.model_dump(mode="json"),
                        "_id": job.id,
                        "state": job.state.value,
                        "selected_worker": job.assigned_worker_id,
                        "selected_account": job.preferred_account_id,
                        "flow_model": job.flow_model,
                        "estimated_credits": job.estimated_credits,
                    }
                },
                upsert=True,
            )
            return
        if self.pool is None:
            return
        await self.pool.execute(
            """
            insert into jobs (id, state, generation_type, prompt, selected_worker, selected_account, flow_model, estimated_credits, payload)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
            on conflict (id) do update set
              state = excluded.state,
              selected_worker = excluded.selected_worker,
              selected_account = excluded.selected_account,
              flow_model = excluded.flow_model,
              estimated_credits = excluded.estimated_credits,
              payload = excluded.payload,
              updated_at = now()
            """,
            job.id,
            job.state.value,
            job.generation_type,
            job.prompt,
            job.assigned_worker_id,
            job.preferred_account_id,
            job.flow_model,
            job.estimated_credits,
            job.model_dump_json(),
        )

    async def save_worker_status(self, status: WorkerStatus) -> None:
        if self.mongo_db is not None:
            payload = status.model_dump(mode="json")
            await self.mongo_db.worker_metrics.insert_one(payload)
            await self.mongo_db.workers.update_one(
                {"_id": status.vps_id},
                {"$set": {**payload, "_id": status.vps_id}},
                upsert=True,
            )
            return
        if self.pool is None:
            return
        await self.pool.execute(
            """
            insert into worker_metrics (vps_id, online, accounts_total, accounts_busy, accounts_ready, max_jobs, active_jobs, queue_size, cpu, ram, health_score, payload)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
            """,
            status.vps_id,
            status.online,
            status.accounts_total,
            status.accounts_busy,
            status.accounts_ready,
            status.max_jobs,
            status.active_jobs,
            status.queue_size,
            status.cpu,
            status.ram,
            status.health_score,
            status.model_dump_json(),
        )

    async def _migrate(self) -> None:
        assert self.pool is not None
        await self.pool.execute(
            """
            create table if not exists jobs (
              id text primary key,
              state text not null,
              generation_type text not null,
              prompt text not null,
              selected_worker text,
              selected_account text,
              flow_model text,
              estimated_credits integer,
              payload jsonb not null,
              created_at timestamptz not null default now(),
              updated_at timestamptz not null default now()
            );
            create table if not exists workers (
              id text primary key,
              base_url text not null,
              enabled boolean not null default true,
              max_jobs integer not null default 10,
              updated_at timestamptz not null default now()
            );
            create table if not exists accounts (
              id text not null,
              worker_id text not null,
              status text not null,
              payload jsonb not null,
              updated_at timestamptz not null default now(),
              primary key (worker_id, id)
            );
            create table if not exists flow_settings (
              id text primary key default 'global',
              payload jsonb not null,
              updated_at timestamptz not null default now()
            );
            create table if not exists worker_metrics (
              id bigserial primary key,
              vps_id text not null,
              online boolean not null,
              accounts_total integer not null,
              accounts_busy integer not null,
              accounts_ready integer not null,
              max_jobs integer not null,
              active_jobs integer not null,
              queue_size integer not null,
              cpu double precision not null,
              ram double precision not null,
              health_score integer not null,
              payload jsonb not null,
              created_at timestamptz not null default now()
            );
            create table if not exists logs (
              id bigserial primary key,
              level text not null,
              message text not null,
              payload jsonb,
              created_at timestamptz not null default now()
            );
            """
        )

    async def _migrate_mongo(self) -> None:
        assert self.mongo_db is not None
        await self.mongo_db.jobs.create_index("id", unique=True)
        await self.mongo_db.jobs.create_index("state")
        await self.mongo_db.jobs.create_index("created_at")
        await self.mongo_db.workers.create_index("vps_id")
        await self.mongo_db.worker_metrics.create_index("vps_id")
        await self.mongo_db.worker_metrics.create_index("last_seen")
