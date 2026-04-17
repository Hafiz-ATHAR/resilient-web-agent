import uuid
from fastapi import APIRouter, BackgroundTasks, Request
from ..schemas.schema import CreateJobRequest
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
        print(f"Traces in cleanup in jobs {traces}")


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
