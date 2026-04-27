# System Architecture

## Overview Diagram

```mermaid
flowchart TB
    Client["🌐 Client<br/>(Browser / API consumer)"]

    subgraph FastAPI["FastAPI App (app/main.py)"]
        direction TB
        MW["Middleware<br/>• CORS<br/>• RequestIdMiddleware (structlog binding)"]

        subgraph Routes["API Routes (app/api/jobs.py)"]
            direction LR
            R1["POST /jobs<br/>create"]
            R2["POST /jobs/{id}/resume"]
            R3["GET  /jobs/{id}<br/>status"]
            R4["GET  /jobs/{id}/result"]
            R5["GET  /jobs/{id}/stream<br/>SSE"]
        end

        BG["Background Task<br/>run_graph() / resume_graph()<br/>graph.astream(...)"]
        Queues["app.state.queues<br/>{thread_id: asyncio.Queue}"]
    end

    subgraph Graph["LangGraph Workflow (app/graph/)"]
        direction TB
        N1["initializer"] --> N2["fetcher<br/>(httpx GET)"]
        N2 -- ok --> N3["summarizer<br/>(Ollama LLM)"]
        N2 -- error --> N4["accumulator"]
        N3 --> N4
        N4 -- pending_urls --> N2
        N4 -- done --> N5["finalizer<br/>final_report"]
    end

    State[("AgentState<br/>urls_to_process,<br/>pending, results,<br/>counters, status")]
    DB[("SQLite Checkpointer<br/>state-db/long-running-job.db<br/>AsyncSqliteSaver")]

    subgraph External["External Services"]
        direction LR
        MLflow["MLflow<br/>(tracing/autolog)"]
        LangSmith["LangSmith<br/>(optional)"]
        Ollama["Ollama<br/>(local LLM)"]
        Web["🌍 Target URLs<br/>(httpx fetch)"]
    end

    Client -->|HTTP| MW
    MW --> Routes
    R1 --> BG
    R2 --> BG
    BG --> Graph
    Graph <--> State
    State <--> DB
    BG -->|node updates| Queues
    R5 -->|drain queue| Queues
    R3 -->|aget_state| DB
    R4 -->|aget_state| DB
    Queues -->|SSE events| Client

    N2 -.fetch.-> Web
    N3 -.invoke.-> Ollama
    Graph -.traces.-> MLflow
    Graph -.traces.-> LangSmith
```

## Request Flow

1. **Create** — `POST /jobs` returns a `thread_id` and schedules `run_graph()` as a background task.
2. **Stream** — `GET /jobs/{id}/stream` (SSE) drains per-job updates from `app.state.queues` as nodes execute.
3. **Status** — `GET /jobs/{id}` reads the latest checkpoint from SQLite via `aget_state`.
4. **Result** — `GET /jobs/{id}/result` returns `final_report` once `job_status == "completed"`.
5. **Resume** — `POST /jobs/{id}/resume` rehydrates state from the checkpoint and continues the loop.

## Components

| Component | Responsibility |
| --- | --- |
| `app/main.py` | FastAPI entry point, lifespan, checkpointer init, MLflow setup, trace cleanup |
| `app/api/jobs.py` | REST + SSE routes; orchestrates background graph runs |
| `app/graph/agent.py` | Workflow definition (nodes + edges) |
| `app/graph/utils/nodes.py` | Node implementations: initializer, fetcher, summarizer, accumulator, finalizer |
| `app/graph/utils/routes.py` | Conditional routing logic between nodes |
| `app/graph/utils/state.py` | `AgentState` and `UrlResult` Pydantic models |
| `app/schemas/schema.py` | API request/response shapes |
| `app/middleware/` | `RequestIdMiddleware` for structlog context binding |
| `app/config.py` | Pydantic settings loaded from `.env` |
| `app/logging_config.py` | structlog configuration |

## State & Persistence

- **AgentState** holds `urls_to_process`, `pending_urls`, `completed_results`, counters, and `job_status`.
- **AsyncSqliteSaver** persists every checkpoint to `state-db/long-running-job.db`.
- `JsonPlusSerializer` is configured with `allowed_msgpack_modules=[("app.graph.utils.state", "UrlResult")]` so custom types survive serialization.
- **SSE queues** in `app.state.queues` are in-memory only — they reset on restart, but the graph state itself survives via the checkpointer.

## External Dependencies

- **FastAPI** — web framework
- **LangGraph** — workflow orchestration + checkpointing
- **LangChain / langchain-ollama** — LLM integration (local Ollama)
- **httpx** — async URL fetching
- **MLflow** — experiment & trace tracking
- **LangSmith** *(optional)* — additional tracing
- **structlog** — structured logging
- **Pydantic / pydantic-settings** — validation & config
