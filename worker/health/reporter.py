from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import psutil

from worker.accounts.manager import AccountManager
from worker.accounts.models import AccountStatus
from worker.config.settings import Settings
from worker.queue.manager import QueueManager


class HealthReporter:
    def __init__(self, settings: Settings, accounts: AccountManager, queue: QueueManager) -> None:
        self.settings = settings
        self.accounts = accounts
        self.queue = queue

    async def snapshot(self) -> dict:
        accounts = self.accounts.list_accounts()
        queue_stats = await self.queue.stats()
        return {
            "worker_id": self.settings.worker_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "active_accounts": len(accounts),
            "busy_accounts": sum(1 for account in accounts if account.status == AccountStatus.BUSY),
            "browser_status": {
                account.id: {
                    "pid": account.browser_pid,
                    "running": bool(account.browser_pid and psutil.pid_exists(account.browser_pid)),
                    "display": account.display,
                    "vnc_port": account.vnc_port,
                    "debug_port": account.remote_debugging_port,
                    "flowkit": self.accounts.flowkit.status(account.id),
                }
                for account in accounts
            },
            "extension_status": {
                "path": str(self.settings.paths.extension_dir),
                "manifest_present": (self.settings.paths.extension_dir / "manifest.json").exists(),
                "flowkit_runtime_dir": str(self.settings.paths.runtime_extension_dir),
            },
            "queue": queue_stats,
        }
