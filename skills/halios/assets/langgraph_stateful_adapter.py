"""jsonl-v1 template for a LangGraph compiled with a checkpointer."""

import asyncio
import json
import sys

from app.agent import graph  # Adapt this import to the project.
from opentelemetry.context import attach, detach
from opentelemetry.propagate import extract


async def call_agent(request: dict) -> dict:
    token = attach(extract({"traceparent": request["traceparent"]}))
    try:
        result = await graph.ainvoke(
            {"messages": [request["message"]]},
            {"configurable": {"thread_id": request["trial_id"]}},
        )
    finally:
        detach(token)
    reply = result["messages"][-1]
    return {"message": {"role": "assistant", "content": reply.content}}


async def main() -> None:
    for line in sys.stdin:
        response = await call_agent(json.loads(line))
        try:
            from opentelemetry import trace
            provider = trace.get_tracer_provider()
            if hasattr(provider, "force_flush"):
                provider.force_flush()
        except Exception:
            pass
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
