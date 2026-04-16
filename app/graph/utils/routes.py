from typing import Literal
from .state import AgentState


def route_after_fetch(state: AgentState) -> Literal["summarizer", "accumulator"]:
    """Route to the next node after fetching."""

    if state.current_raw_content is None:
        return "accumulator"
    return "summarizer"


def route_after_accumulate(state: AgentState) -> Literal["fetcher", "finalizer"]:
    """Route to the next node after accumulating."""
    
    if state.pending_urls:
        return "fetcher"  # loop back
    return "finalizer"  # all done
