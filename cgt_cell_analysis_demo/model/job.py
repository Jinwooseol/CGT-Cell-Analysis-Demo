"""Data models describing a pipeline job and its execution state."""

from __future__ import annotations

import uuid
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class TestSpec(BaseModel):
    """Specification of the inputs for a single analysis job."""

    sample_id: str
    optical_dir: Path | None = None
    pcr_dir: Path | None = None


class TestJob(BaseModel):
    """A queued/running analysis job and its progress state."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # unique row identifier
    sample_id: str
    optical_dir: Path | None = None
    pcr_dir: Path | None = None
    out_root: Path = Path("work")
    status: JobStatus = JobStatus.pending
    current_step: int = 0  # current step (1-4)
    percent: int = 0  # progress 0-100
