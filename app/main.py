import mlflow
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import mlflow.langchain
from .graph.agent import create_workflow
from .api.jobs import job_router
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from .config import get_settings
from .logging_config import configure_logging
from .middleware.request_id import RequestIdMiddleware
import time

settings = get_settings()
configure_logging(settings.environment)
log = structlog.get_logger(__name__)

mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
mlflow.set_experiment(settings.mlflow_experiment)


# Lifespan function to initialize LangGraph workflow and handle cleanup on shutdown, including trace management
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "lifespan.startup",
        environment=settings.environment,
        db_path=str(settings.db_path),
        experiment=settings.mlflow_experiment,
    )
    # Enable MLflow autologging for LangChain
    mlflow.langchain.autolog()  # type: ignore

    db_conn = aiosqlite.connect(settings.db_path, check_same_thread=False)
    checkpointer = AsyncSqliteSaver(
        db_conn,
        serde=JsonPlusSerializer(
            allowed_msgpack_modules=[("app.graph.utils.state", "UrlResult")]
        ),
    )

    # Create and compile the LangGraph workflow, passing the checkpointer for state management
    agent_workflow = create_workflow()
    app.state.graph = agent_workflow.compile(checkpointer=checkpointer)
    # Initialize a dictionary to hold queues for each job thread
    app.state.queues = {}

    yield
    log.info("lifespan.shutdown")
    _cleanup_traces()
    await db_conn.close()


def _cleanup_traces():
    """Helper function to clean up any IN_PROGRESS mlflow traces on server shutdown."""
    client = mlflow.MlflowClient()
    try:
        traces = mlflow.search_traces(
            filter_string="status = 'IN_PROGRESS'", return_type="list"
        )
        log.info("trace_cleanup.scan", count=len(traces))
        for row in traces:
            trace_id = row.info.trace_id  # type: ignore

            log.info("trace_cleanup.end_trace", trace_id=trace_id)

            client.end_trace(
                trace_id=trace_id,
                status="ERROR",
                attributes={
                    "error.type": "ServerShutdown",
                    "error.message": "Trace ended due to server shutdown before completion.",
                },
                end_time_ns=int(time.time() * 1e9),
            )

    except Exception:
        log.exception("trace_cleanup.failed")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

app.include_router(job_router)
