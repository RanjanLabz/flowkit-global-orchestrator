from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

from worker.accounts.manager import AccountManager
from worker.accounts.models import Account
from worker.config.settings import Settings
from worker.queue.models import Job, JobState

logger = logging.getLogger(__name__)


class JobExecutor:
    def __init__(self, settings: Settings, accounts: AccountManager) -> None:
        self.settings = settings
        self.accounts = accounts

    async def run(self, job: Job, account: Account) -> Job:
        job.account_id = account.id
        job.state = JobState.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        if job.payload.get("flowkit"):
            result = await self._run_flowkit_bridge(job, account)
            job.output_urls = result.get("output_urls", [])
            job.payload["flowkit_result"] = result
            job.state = JobState.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            return job

        runtime = self.accounts.runtime_for(account.id)
        if runtime.playwright_context is None:
            await self.accounts.recover_account(account.id, reason="missing-playwright-context")
            runtime = self.accounts.runtime_for(account.id)
        if runtime.playwright_context is None:
            raise RuntimeError("Playwright context unavailable after recovery")

        page = await self._flow_page(runtime.playwright_context.pages)
        if page is None:
            await self.accounts.chrome.open_flow(account, runtime)
            page = await self._flow_page(runtime.playwright_context.pages)
        if page is None:
            raise RuntimeError("Google Flow page unavailable")

        page.set_default_timeout(self.settings.browser.navigation_timeout_ms)
        await page.bring_to_front()
        await self._submit_prompt(page, job.prompt)
        output_urls = await self._wait_for_outputs(page)
        job.output_urls = output_urls
        job.state = JobState.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        return job

    async def _run_flowkit_bridge(self, job: Job, account: Account) -> dict:
        flowkit_payload = job.payload.get("flowkit")
        if not isinstance(flowkit_payload, dict):
            raise RuntimeError("flowkit payload must be an object")
        method = str(flowkit_payload.get("method") or "api_request")
        params = flowkit_payload.get("params")
        if not isinstance(params, dict):
            raise RuntimeError("flowkit.params must be an object")
        timeout = float(flowkit_payload.get("timeout", self.settings.queue.job_timeout_seconds))
        result = await self.accounts.flowkit.send(account.id, method, params, timeout=timeout)
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        urls = await self._extract_urls(result)
        return {"result": result, "output_urls": urls}

    async def _extract_urls(self, payload: object) -> list[str]:
        text = str(payload)
        return sorted(set(re.findall(r"https?://[^\s\"'<>}]+", text)))

    async def _flow_page(self, pages) -> object | None:
        for page in pages:
            if "labs.google" in page.url:
                return page
        return None

    async def _submit_prompt(self, page, prompt: str) -> None:
        selectors = [
            "textarea",
            "[contenteditable='true']",
            "input[type='text']",
        ]
        last_error: Exception | None = None
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.fill(prompt)
                break
            except Exception as exc:
                last_error = exc
        else:
            raise RuntimeError(f"prompt input not found: {last_error}")

        buttons = [
            "button:has-text('Generate')",
            "button:has-text('Create')",
            "button:has-text('Submit')",
            "button[type='submit']",
        ]
        for selector in buttons:
            try:
                button = page.locator(selector).first
                await button.wait_for(state="visible", timeout=5000)
                await button.click()
                return
            except Exception:
                continue
        await page.keyboard.press("Control+Enter")

    async def _wait_for_outputs(self, page) -> list[str]:
        deadline = asyncio.get_running_loop().time() + self.settings.queue.job_timeout_seconds
        seen: set[str] = set()
        url_pattern = re.compile(r"https?://[^\s\"']+")
        while asyncio.get_running_loop().time() < deadline:
            links = await page.locator("a").evaluate_all("(els) => els.map(a => a.href).filter(Boolean)")
            for link in links:
                if "labs.google" not in link:
                    seen.add(link)
            text = await page.locator("body").inner_text(timeout=5000)
            for match in url_pattern.findall(text):
                if "labs.google" not in match:
                    seen.add(match)
            if seen:
                return sorted(seen)
            await asyncio.sleep(5)
        raise asyncio.TimeoutError("timed out waiting for generated output URLs")
