import json
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.sse import EventSourceResponse
from ..schemas.schema import CreateJobRequest, ResumeJob
import mlflow
import asyncio

job_router = APIRouter(prefix="/jobs", tags=["jobs"])


async def run_graph(graph, initial_state: dict, config: dict, queue: asyncio.Queue):
    try:
        async for event in graph.astream(
            initial_state, config, stream_mode=["updates", "values"], version="v2"
        ):
            if event["type"] == "updates":
                for node_name, state in event["data"].items():
                    if node_name == "finalizer ":
                        await queue.put(None)
                    else:
                        await queue.put(
                            {
                                "node": node_name,
                                "processed_count": state.get("processed_count"),
                                "error_count": state.get("error_count"),
                            }
                        )

    except asyncio.CancelledError:
        pass  # let uvicorn know the task was cancelled, lifespan shutdown will handle traces
    except Exception as e:
        print(f"Graph error: {e}")
    finally:
        traces = mlflow.search_traces(
            filter_string="status = 'IN_PROGRESS'", return_type="list"
        )


async def resume_graph(graph, config: dict):
    async for _ in graph.astream(
        None, config, stream_mode=["updates", "values"], version="v2"
    ):
        pass


@job_router.post("")
async def create_job(
    request: Request, body: CreateJobRequest, background_tasks: BackgroundTasks
):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    request.app.state.queues[thread_id] = asyncio.Queue()
    initial_state = {
        "urls_to_process": body.urls,
        "job_status": "pending",
    }

    background_tasks.add_task(
        run_graph,
        request.app.state.graph,
        initial_state,
        config,
        request.app.state.queues[thread_id],
    )

    return {"thread_id": thread_id, "job_name": body.job_name, "status": "pending"}


@job_router.post("/{thread_id}/resume")
async def resume_job(
    request: Request, body: ResumeJob, background_tasks: BackgroundTasks
):
    config = {"configurable": {"thread_id": body.thread_id}}
    background_tasks.add_task(resume_graph, request.app.state.graph, config)

    return {"thread_id": body.thread_id, "job_name": body.job_name, "status": "pending"}


# SSE endpoint to stream updates for a job
@job_router.get("/{thread_id}/stream")  
async def stream_items(request: Request, thread_id: str):
    queue = request.app.state.queues.get(thread_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield json.dumps(item)

    return EventSourceResponse(event_generator())


@job_router.get("/{thread_id}")
async def get_job_status(request: Request, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state = await request.app.state.graph.aget_state(config)

    if not state or not state.values:
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
    config = {"configurable": {"thread_id": thread_id}}
    state = await request.app.state.graph.aget_state(config)

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Job not found")

    if state.values.get("job_status") != "completed":
        raise HTTPException(status_code=202, detail="Job not completed yet")

    return state.values.get("final_report")
