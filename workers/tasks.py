"""Celery tasks for async agent execution.

The API submits tasks here via .delay() instead of FastAPI BackgroundTasks,
giving us:
  - Persistent job queue (survives API restarts)
  - Horizontal worker scaling (just add more workers)
  - Built-in retries and failure handling
  - Flower UI for worker monitoring
"""
from __future__ import annotations
from workers.celery_app import celery_app
from graph.state import AgentState
import structlog

log = structlog.get_logger()


@celery_app.task(
    bind=True,
    name="workers.tasks.run_agent_task",
    max_retries=1,
    default_retry_delay=5,
    acks_late=True,
)
def run_agent_task(self, task_id: str, state: dict) -> dict:
    """Execute the full LangGraph agent workflow for a given task.

    Args:
        task_id: Unique task identifier (used for status polling).
        state:   Serialised AgentState dict produced by create_initial_state().

    Returns:
        The final AgentState dict after graph completion.
    """
    from graph.workflow import build_graph
    from db import crud as db
    from db.client import is_enabled as supabase_enabled

    log.info("celery_task_started", task_id=task_id)

    try:
        graph = build_graph()
        result: AgentState = graph.invoke(state)

        # Persist result
        db.upsert_task(result)
        log.info("celery_task_done", task_id=task_id, status=result.get("status"))
        return dict(result)

    except Exception as exc:
        log.error("celery_task_failed", task_id=task_id, error=str(exc))
        state["status"] = "failed"
        state["errors"] = state.get("errors", []) + [str(exc)]
        db.upsert_task(state)

        # Retry once after 5 seconds on transient errors
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return state
