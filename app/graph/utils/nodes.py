from datetime import datetime, UTC
import httpx
from langchain_core.runnables import RunnableConfig
from .state import AgentState, UrlResult
import textwrap
from .helper_methods import fetch_error, extract_text
from .llm import get_llm


def initializer(state: AgentState) -> AgentState:
    """Initialize the agent state with the list of URLs to process, and set the first URL as the current item."""
    return {
        "pending_urls": state.urls_to_process,  # type: ignore
        "completed_results": [],
        "current_url": state.urls_to_process[0],
        "current_raw_content": None,
        "last_result": None,
        "job_status": "running",
        "processed_count": 0,
        "error_count": 0,
        "final_report": None,
    }


async def fetcher(
    state: AgentState,
) -> dict:  # config: RunnableConfig
    """Fetch the raw content of the current URL. On failure, populate last_result with an error and let the accumulator handle it."""
    print(f"COUNT: {len(state.completed_results)}")
    url = state.current_url

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; research-agent/1.0)"},
        ) as client:  # without User-Agent 403 error is common, and we want to be polite to servers by identifying ourselves
            response = await client.get(url, follow_redirects=True)  # type: ignore
            response.raise_for_status()
            return {"current_raw_content": response.text}

    except httpx.TimeoutException:
        return fetch_error(url, "Request timed out")  # pyright: ignore[reportArgumentType]
    except httpx.HTTPStatusError as e:
        return fetch_error(url, f"HTTP {e.response.status_code}")  # type: ignore
    except Exception as e:
        return fetch_error(url, str(e))  # type: ignore


async def summarizer(state: AgentState, config: RunnableConfig) -> dict:
    """Summarize the fetched content of the current URL. On failure, populate last_result with an error for the accumulator to handle."""

    SUMMARIZER_PROMPT = textwrap.dedent("""\
    You are a precise research assistant. Summarize the following web page content.

    Requirements:
    - 3-5 sentences maximum
    - Focus on the main topic and key facts only
    - Ignore navigation menus, ads, footers, and boilerplate text
    - Plain text output, no markdown

    Content:
    {content}

    Summary:""")

    try:
        summarize_prompt = SUMMARIZER_PROMPT.format(
            content=extract_text(
                state.current_raw_content # type: ignore
            ),  # trim to avoid token limits # type: ignore
        )
        qwen3_model = get_llm()
        response = await qwen3_model.ainvoke(summarize_prompt)
        if not response.content:
            raise ValueError("Empty response from LLM")

        return {
            "current_url": state.current_url,  # unchanged, still needed by accumulator
            "last_result": UrlResult(
                url=state.current_url,  # type: ignore
                summary=response.content,  # type: ignore
                status="success",
                error=None,
                processed_at=datetime.now(UTC),
            ),
        }
    except Exception as e:
        return {
            "last_result": UrlResult(
                url=state.current_url,  # type: ignore
                status="failed",
                error=f"LLM error: {str(e)}",
                processed_at=datetime.now(UTC),
            )
        }


async def accumulator(state: AgentState, config: RunnableConfig) -> dict:
    """Accumulate the result of the current URL processing into the completed_results list, update counters, and set up the next URL to process. If the current item failed, it will still be added to completed_results with its error, and the process will continue to the next URL."""
    result = state.last_result
    remaining_urls = state.pending_urls[1:]

    return {
        "pending_urls": remaining_urls,
        "current_url": remaining_urls[0] if remaining_urls else None,
        "current_raw_content": None,
        # "last_result" : None,
        "completed_results": [result],
        "processed_count": state.processed_count + 1,
        "error_count": state.error_count + 1
        if result.status == "failed" # type: ignore
        else state.error_count,  # type: ignore
    }


async def finalizer(state: AgentState, config: RunnableConfig) -> dict:
    """Generate a final report based on all completed results."""
    deduplicated: dict[str, UrlResult] = {}
    for r in state.completed_results:
        if r.url not in deduplicated or r.status == "success":
            deduplicated[r.url] = r

    results = list(deduplicated.values())
    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status == "failed"]

    return {
        "final_report": {
            "total": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "summaries": [{"url": r.url, "summary": r.summary} for r in successful],
            "errors": [{"url": r.url, "error": r.error} for r in failed],
        },
        "job_status": "completed",
    }
