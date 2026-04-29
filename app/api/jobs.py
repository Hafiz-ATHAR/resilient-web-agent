import json
import uuid
import asyncio
import mlflow
import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.sse import EventSourceResponse
from ..schemas.schema import CreateJobRequest, ResumeJob

log = structlog.get_logger(__name__)

job_router = APIRouter(prefix="/jobs", tags=["jobs"])


async def run_graph(
    graph, initial_state: dict, config: dict, queue: asyncio.Queue, thread_id: str
):
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(thread_id=thread_id, task="run_graph")
    active_run = mlflow.active_run()
    if active_run is not None:
        structlog.contextvars.bind_contextvars(mlflow_run_id=active_run.info.run_id)

    items_sent = 0
    log.info("graph.start", url_count=len(initial_state.get("urls_to_process", [])))
    try:
        async for event in graph.astream(
            initial_state, config, stream_mode=["updates", "values"], version="v2"
        ):
            if event["type"] == "updates":
                for node_name, state in event["data"].items():
                    log.debug(
                        "graph.event", event_type=event["type"], node_name=node_name
                    )
                    if node_name == "finalizer":
                        await queue.put(None)
                        items_sent += 1
                        log.info("graph.sentinel_sent", items_sent=items_sent)
                    else:
                        await queue.put(
                            {
                                "node": node_name,
                                "processed_count": state.get("processed_count"),
                                "error_count": state.get("error_count"),
                            }
                        )
                        items_sent += 1

    except asyncio.CancelledError:
        log.warning("graph.cancelled")
        raise
    except Exception:
        log.exception("graph.failed")
    finally:
        structlog.contextvars.clear_contextvars()


async def resume_graph(graph, config: dict):
    thread_id = config.get("configurable", {}).get("thread_id")
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(thread_id=thread_id, task="resume_graph")
    log.info("graph.resume")
    try:
        async for _ in graph.astream(
            None, config, stream_mode=["updates", "values"], version="v2"
        ):
            pass
    finally:
        structlog.contextvars.clear_contextvars()


@job_router.post("")
async def create_job(
    request: Request, body: CreateJobRequest, background_tasks: BackgroundTasks
):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    structlog.contextvars.bind_contextvars(thread_id=thread_id)
    request.app.state.queues[thread_id] = asyncio.Queue()
    initial_state = {
        "urls_to_process": body.urls,
        "job_status": "pending",
    }

    log.info("job.created", url_count=len(body.urls), job_name=body.job_name)

    background_tasks.add_task(
        run_graph,
        request.app.state.graph,
        initial_state,
        config,
        request.app.state.queues[thread_id],
        thread_id,
    )

    return {"thread_id": thread_id, "job_name": body.job_name, "status": "pending"}


@job_router.post("/{thread_id}/resume")
async def resume_job(
    request: Request, body: ResumeJob, background_tasks: BackgroundTasks
):
    structlog.contextvars.bind_contextvars(thread_id=body.thread_id)
    config = {"configurable": {"thread_id": body.thread_id}}

    state = await request.app.state.graph.aget_state(config)
    if not state or not state.values:
        log.warning("job.resume_unknown_thread")
        raise HTTPException(status_code=404, detail="Job not found")

    log.info("job.resumed", job_name=body.job_name)
    background_tasks.add_task(resume_graph, request.app.state.graph, config)

    return {"thread_id": body.thread_id, "job_name": body.job_name, "status": "pending"}


# SSE endpoint to stream updates for a job
@job_router.get("/{thread_id}/stream")
async def stream_items(request: Request, thread_id: str):
    queue = request.app.state.queues.get(thread_id)
    if not queue:
        log.warning("sse.unknown_thread", thread_id=thread_id)
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        structlog.contextvars.bind_contextvars(thread_id=thread_id, stream="sse")
        log.info("sse.opened")
        items_sent = 0
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                items_sent += 1
                yield json.dumps(item)
            log.info("sse.closed", items_sent=items_sent)
        except asyncio.CancelledError:
            log.warning("sse.client_disconnect", items_sent=items_sent)
            raise
        finally:
            structlog.contextvars.clear_contextvars()

    return EventSourceResponse(event_generator())


@job_router.get("/{thread_id}")
async def get_job_status(request: Request, thread_id: str):
    structlog.contextvars.bind_contextvars(thread_id=thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    state = await request.app.state.graph.aget_state(config)

    if not state or not state.values:
        log.warning("job.status_unknown_thread")
        raise HTTPException(status_code=404, detail="Job not found")

    s = state.values
    return {
        "thread_id": thread_id,
        "job_status": s.get("job_status"),
        "processed_count": s.get("processed_count", 0),
        "error_count": s.get("error_count", 0),
        "total": len(s.get("urls_to_process", [])),
        "pending": len(s.get("pending_urls", [])),
    }


@job_router.get("/{thread_id}/result")
async def get_job_result(request: Request, thread_id: str):
    structlog.contextvars.bind_contextvars(thread_id=thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    state = await request.app.state.graph.aget_state(config)

    if not state or not state.values:
        log.warning("job.result_unknown_thread")
        raise HTTPException(status_code=404, detail="Job not found")

    if state.values.get("job_status") != "completed":
        log.debug("job.result_not_ready", job_status=state.values.get("job_status"))
        raise HTTPException(status_code=202, detail="Job not completed yet")

    return state.values.get("final_report")
