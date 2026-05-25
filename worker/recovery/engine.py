from __future__ import annotations

import asyncio
import logging

from worker.accounts.models import Account, AccountStatus
from worker.browser.chrome_manager import ChromeManager
from worker.browser.runtime import AccountRuntime
from worker.browser.vnc_manager import VncManager
from worker.config.settings import Settings

logger = logging.getLogger(__name__)


class RecoveryEngine:
    def __init__(self, settings: Settings, chrome: ChromeManager, vnc: VncManager) -> None:
        self.settings = settings
        self.chrome = chrome
        self.vnc = vnc

    async def recover(self, account: Account, runtime: AccountRuntime, reason: str) -> None:
        logger.warning("recovering account=%s reason=%s", account.id, reason)
        account.status = AccountStatus.BROKEN_SESSION
        account.health_score = max(0, account.health_score - 15)
        account.mark_updated()

        for attempt in range(1, self.settings.recovery.max_attempts + 1):
            try:
                await self._soft_recover(account, runtime)
                account.status = AccountStatus.READY
                account.health_score = min(100, account.health_score + 5)
                account.mark_updated()
                logger.info("soft recovery succeeded account=%s attempt=%s", account.id, attempt)
                return
            except Exception as exc:
                logger.warning("soft recovery failed account=%s attempt=%s error=%s", account.id, attempt, exc)
                await asyncio.sleep(1)

        await self._hard_recover(account, runtime)
        account.status = AccountStatus.READY
        account.mark_updated()

    async def _soft_recover(self, account: Account, runtime: AccountRuntime) -> None:
        if runtime.playwright_context is None:
            await self.chrome.connect(account, runtime)
        if runtime.playwright_context is None:
            raise RuntimeError("no Playwright context after reconnect")

        page = None
        for candidate in runtime.playwright_context.pages:
            if "labs.google" in candidate.url:
                page = candidate
                break
        if page is None:
            await self.chrome.open_flow(account, runtime)
            return
        await page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }")
        await page.reload(wait_until="domcontentloaded", timeout=self.settings.browser.navigation_timeout_ms)

    async def _hard_recover(self, account: Account, runtime: AccountRuntime) -> None:
        logger.warning("hard recovery restarting browser account=%s", account.id)
        await runtime.terminate()
        await self.vnc.start(account, runtime)
        await self.chrome.start(account, runtime)
