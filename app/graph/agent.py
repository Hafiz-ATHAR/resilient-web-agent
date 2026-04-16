from langgraph.graph import StateGraph, START, END
from .utils.state import AgentState
from .utils.nodes import initializer, fetcher, summarizer, accumulator, finalizer
from .utils.routes import route_after_fetch, route_after_accumulate


def create_workflow():
    """Factory function to create the agent workflow graph."""
    workflow = StateGraph(AgentState)
    workflow.add_node("initializer", initializer)
    workflow.add_node("fetcher", fetcher)
    workflow.add_node("summarizer", summarizer)
    workflow.add_node("accumulator", accumulator)
    workflow.add_node("finalizer", finalizer)

    workflow.add_edge(START, "initializer")
    workflow.add_edge("initializer", "fetcher")

    workflow.add_conditional_edges("fetcher", route_after_fetch)

    workflow.add_edge("summarizer", "accumulator")

    workflow.add_conditional_edges("accumulator", route_after_accumulate)

    workflow.add_edge("finalizer", END)

    return workflow
