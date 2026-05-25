from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from worker.accounts.manager import AccountManager
from worker.accounts.models import Account, AccountStatus
from worker.config.settings import Settings
from worker.queue.executor import JobExecutor
from worker.queue.manager import QueueManager
from worker.queue.models import Job, JobState

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, settings: Settings, accounts: AccountManager, queue: QueueManager) -> None:
        self.settings = settings
        self.accounts = accounts
        self.queue = queue
        self.executor = JobExecutor(settings, accounts)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._running_jobs: set[asyncio.Task] = set()

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="flow-job-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._running_jobs:
            await asyncio.gather(*self._running_jobs, return_exceptions=True)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = await self.queue.pop_ready()
                if job is None:
                    await asyncio.sleep(self.settings.queue.scheduler_interval_seconds)
                    continue
                account = self._select_account()
                if account is None:
                    await self.queue.requeue(job, delay_seconds=3)
                    await asyncio.sleep(self.settings.queue.scheduler_interval_seconds)
                    continue
                job.state = JobState.ASSIGNED
                job.account_id = account.id
                await self.queue.mark_active(job)
                task = asyncio.create_task(self._run_job(job, account), name=f"job-{job.id}")
                self._running_jobs.add(task)
                task.add_done_callback(self._running_jobs.discard)
            except Exception:
                logger.exception("scheduler loop error")
                await asyncio.sleep(2)

    def _select_account(self) -> Account | None:
        now = datetime.now(timezone.utc)
        candidates = []
        for account in self.accounts.list_accounts():
            if account.status not in {AccountStatus.READY, AccountStatus.COOLDOWN}:
                continue
            if account.settings.cooldown_until and account.settings.cooldown_until > now:
                continue
            if account.jobs_running >= account.settings.max_concurrent_jobs:
                continue
            score = account.health_score
            score -= account.jobs_running * 30
            score -= account.failure_count * 3
            if account.proxy_enabled:
                score += int((account.proxy_health_score - 100) / 2)
            if account.last_used:
                score += min(20, int((now - account.last_used).total_seconds() / 60))
            if account.proxy_enabled and not account.proxy_url:
                score -= 50
            candidates.append((score, account))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    async def _run_job(self, job: Job, account: Account) -> None:
        await self.accounts.mark_job_started(account.id)
        logger.info(
            "job started job_id=%s account=%s retries=%s prompt=%r",
            job.id,
            account.id,
            job.retries,
            job.prompt,
        )
        try:
            job = await asyncio.wait_for(self.executor.run(job, account), timeout=self.settings.queue.job_timeout_seconds)
            await self.accounts.mark_job_finished(account.id, success=True)
            await self.queue.remove_active(job)
            processing_time = None
            if job.started_at and job.completed_at:
                processing_time = (job.completed_at - job.started_at).total_seconds()
            logger.info(
                "job completed job_id=%s account=%s queue_time=%s processing_time=%s output_urls=%s",
                job.id,
                account.id,
                (job.started_at - job.queued_at).total_seconds() if job.started_at else None,
                processing_time,
                job.output_urls,
            )
        except asyncio.TimeoutError as exc:
            await self._handle_failure(job, account, JobState.TIMEOUT, exc)
        except Exception as exc:
            await self._handle_failure(job, account, JobState.FAILED, exc)

    async def _handle_failure(self, job: Job, account: Account, state: JobState, exc: Exception) -> None:
        logger.exception("job failed job_id=%s account=%s retries=%s error=%s", job.id, account.id, job.retries, exc)
        job.last_error = str(exc)
        job.retries += 1
        await self.accounts.mark_job_finished(account.id, success=False)
        await self.accounts.recover_account(account.id, reason=f"job-{state.value.lower()}")
        if job.retries <= job.max_retries:
            await self.queue.remove_active(job)
            await self.queue.requeue(job, delay_seconds=self.settings.queue.retry_delay_seconds)
        else:
            job.state = state
            job.completed_at = datetime.now(timezone.utc)
            await self.queue.remove_active(job)
