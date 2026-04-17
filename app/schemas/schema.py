from pydantic import BaseModel
from typing import Literal

JobStatus = Literal["pending", "running", "completed", "failed"]

class CreateJobRequest(BaseModel):
    job_name: str
    urls: list[str]

class ResumeJob(BaseModel):
    job_name: str
    thread_id: str