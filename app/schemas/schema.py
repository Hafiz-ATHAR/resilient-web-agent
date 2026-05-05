from pydantic import BaseModel, Field, field_validator
from typing import Literal
from app.config import get_settings

JobStatus = Literal["pending", "running", "completed", "failed"]


class CreateJobRequest(BaseModel):
    job_name: str = Field(min_length=1, max_length=200)
    urls: list[str] = Field(min_length=1)

    @field_validator("urls")
    @classmethod
    def _cap_url_count(cls, v: list[str]) -> list[str]:
        cap = get_settings().max_urls_per_job
        if len(v) > cap:
            raise ValueError(f"Too many URLs: {len(v)} (max {cap})")
        return v


class ResumeJob(BaseModel):
    job_name: str
    thread_id: str
