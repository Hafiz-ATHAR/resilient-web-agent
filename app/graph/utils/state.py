from typing import Annotated, Literal
import operator
from pydantic import BaseModel, Field
from datetime import datetime, UTC

JobStatus = Literal["pending", "running", "completed", "failed"]

class UrlResult(BaseModel):
    url: str
    summary: str = ""
    status: Literal["success", "failed"]
    error: str | None = None
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class AgentState(BaseModel):
    # Input — set once by initializer, never mutated
    urls_to_process: list[str] = Field(default_factory=list)

    # Mutable queue — router pops from here each cycle
    pending_urls: list[str] = Field(default_factory=list)

    # Single in-flight item — router sets, fetcher/summarizer consume
    current_url: str | None = None

    # Mutable state for current item — fetcher sets, summarizer consumes
    current_raw_content:str | None = None
    
    # Handoff between summarizer → accumulator
    last_result: UrlResult | None = None

    # Results list — accumulator appends; uses add reducer so parallel
    # writes from future subgraph refactor don't clobber each other
    completed_results: Annotated[list[UrlResult], operator.add] = Field(default_factory=list)

    # Counters — accumulator owns these, last-write-wins
    processed_count: int = 0
    error_count: int = 0

    # Control signal — every node can update, router reads it
    job_status: JobStatus = "pending"

    # Output — written once by finalizer
    final_report: dict | None = None