"""
LangGraph workflow — wires all agents into the multi-agent pipeline.

Graph topology:

  START
    │
    ▼
  [router]          ← classifies intent: "qa" | "summary" | "quiz"
    │
    ▼
  [retrieval]       ← embeds query → pgvector similarity search → builds context
    │
    ▼ (conditional edge via route_after_retrieval)
    ├── "qa"      ──────────────────────────────────────────▶ [final_response]
    ├── "summary" ──▶ [summary] ─────────────────────────── ▶ [final_response]
    └── "quiz"    ──────────────▶ [quiz] ──────────────────▶ [final_response]
                                                                     │
                                                                    END

Compilation:
  The graph is compiled ONCE at module import and reused across all requests.
  This is safe because:
    1. The compiled graph is stateless — state is passed per invocation.
    2. Services (retrieval, context builder) are injected per-invocation via
       config["configurable"], not baked into the graph at compile time.

Invocation patterns:
  Regular:   await workflow_app.ainvoke(initial_state, config=config)
  Streaming: async for event in workflow_app.astream(initial_state, config=config): ...

The `config` dict follows LangGraph's RunnableConfig convention:
  config = {
      "configurable": {
          "retrieval_service": <RetrievalService>,
          "context_builder":   <ContextBuilderService>,
      },
      "run_name": "agentflow-query",
  }
"""

from langgraph.graph import END, START, StateGraph

from app.agents.final_response_agent import final_response_node
from app.agents.quiz_agent import quiz_node
from app.agents.retrieval_agent import retrieval_node
from app.agents.router_agent import route_after_retrieval, router_node
from app.agents.state import AgentState
from app.agents.summary_agent import summary_node

# ── Build the graph ───────────────────────────────────────────────────────────

_builder = StateGraph(AgentState)

# Register nodes
_builder.add_node("router", router_node)
_builder.add_node("retrieval", retrieval_node)
_builder.add_node("summary", summary_node)
_builder.add_node("quiz", quiz_node)
_builder.add_node("final_response", final_response_node)

# Entry point
_builder.add_edge(START, "router")

# Router → Retrieval (always)
_builder.add_edge("router", "retrieval")

# Retrieval → conditional branch
_builder.add_conditional_edges(
    "retrieval",
    route_after_retrieval,
    {
        "qa": "final_response",
        "summary": "summary",
        "quiz": "quiz",
        "final_response": "final_response",  # error shortcut
    },
)

# Specialist agents → FinalResponse
_builder.add_edge("summary", "final_response")
_builder.add_edge("quiz", "final_response")

# FinalResponse → END
_builder.add_edge("final_response", END)

# ── Compile ───────────────────────────────────────────────────────────────────
# Compiled once at module import; thread-safe; used for all requests.
workflow_app = _builder.compile()
