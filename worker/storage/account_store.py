from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from worker.accounts.models import Account


class AccountStore:
    def __init__(self, accounts_dir: Path) -> None:
        self.accounts_dir = accounts_dir
        self._lock = asyncio.Lock()

    async def load_all(self) -> list[Account]:
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        accounts: list[Account] = []
        for path in sorted(self.accounts_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            accounts.append(Account.model_validate(data))
        return accounts

    async def save(self, account: Account) -> None:
        async with self._lock:
            self.accounts_dir.mkdir(parents=True, exist_ok=True)
            path = self.accounts_dir / f"{account.id}.yaml"
            path.write_text(yaml.safe_dump(account.model_dump(mode="json"), sort_keys=False), encoding="utf-8")

    async def delete(self, account_id: str) -> None:
        async with self._lock:
            path = self.accounts_dir / f"{account_id}.yaml"
            if path.exists():
                path.unlink()
