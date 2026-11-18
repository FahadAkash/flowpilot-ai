"""Cooperative workflow cancellation registry checked across LangGraph nodes."""

from __future__ import annotations

from flowpilot.guardrails.exceptions import WorkflowCancelledError
from flowpilot.observability.metrics import GUARDRAIL_TRIPS_TOTAL


class CancellationRegistry:
    """Tracks cancellation requests for in-flight workflows."""

    def __init__(self) -> None:
        self._cancelled: set[str] = set()

    def request_cancel(self, workflow_id: str) -> None:
        self._cancelled.add(workflow_id)

    def is_cancelled(self, workflow_id: str) -> bool:
        return workflow_id in self._cancelled

    def clear(self, workflow_id: str) -> None:
        self._cancelled.discard(workflow_id)

    def check(self, workflow_id: str) -> None:
        if self.is_cancelled(workflow_id):
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="workflow_cancelled").inc()
            raise WorkflowCancelledError(
                f"Workflow '{workflow_id}' was cancelled by user request.",
                details={"workflow_id": workflow_id},
            )


_cancellation_registry = CancellationRegistry()


def get_cancellation_registry() -> CancellationRegistry:
    return _cancellation_registry
