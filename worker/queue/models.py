from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobState(StrEnum):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    PROCESSING = "PROCESSING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class Job(BaseModel):
    id: str = Field(default_factory=lambda: f"job-{uuid4().hex}")
    prompt: str
    payload: dict[str, Any] = Field(default_factory=dict)
    state: JobState = JobState.QUEUED
    account_id: str | None = None
    retries: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=utc_now)
    queued_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error: str | None = None
    output_urls: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any], max_retries: int) -> "Job":
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("job payload requires non-empty prompt")
        return cls(prompt=prompt, payload=payload, max_retries=max_retries)
