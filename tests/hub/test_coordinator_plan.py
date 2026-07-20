from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "ACP_AGENT"))
_SPEC = importlib.util.spec_from_file_location("acp_coordinator_plan", repo_root / "ACP_AGENT" / "coordinator_plan.py")
assert _SPEC is not None and _SPEC.loader is not None
plan_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = plan_module
_SPEC.loader.exec_module(plan_module)


def _plan() -> dict[str, object]:
    return {
        "plan_id": "pilot-plan",
        "tasks": [
            {
                "task_id": "inspect",
                "owner": "coordinator",
                "instructions": "Inspect the worker result.",
                "status": "dispatched",
            },
            {
                "task_id": "next-safe",
                "owner": "coordinator",
                "instructions": "Issue the next approved task.",
                "depends_on": ["inspect"],
            },
            {
                "task_id": "approval-gated",
                "owner": "coordinator",
                "instructions": "Perform a sensitive mutation.",
                "depends_on": ["inspect"],
                "approval_required": True,
            },
        ],
    }


def _result(task_id: str = "inspect", outcome: str = "success") -> str:
    return json.dumps({"task_id": task_id, "outcome": outcome, "summary": "safe result"})


def test_result_advances_exactly_one_dependency_ready_task(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())

    action = plan.record_result(
        message_id="reply-1",
        sender="worker",
        action="REPLY",
        payload=_result(),
    )

    assert action["status"] == "ready"
    assert action["task_id"] == "next-safe"
    assert action["to"] == "coordinator"
    assert action["message_id"]
    state = plan.snapshot()
    assert state["tasks"]["inspect"]["status"] == "completed"
    assert state["tasks"]["next-safe"]["status"] == "ready_to_send"
    assert state["tasks"]["approval-gated"]["status"] == "blocked_approval"


def test_duplicate_result_never_creates_a_second_task_or_turn(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())

    first = plan.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result())
    duplicate = plan.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result())

    assert duplicate == {"status": "duplicate", "message_id": "reply-1", "task_id": "next-safe"}
    assert first["message_id"] == plan.next_safe_action()["message_id"]
    assert len(plan.snapshot()["receipts"]) == 1


def test_restart_reuses_the_same_durable_task_delivery_id(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    first = plan_module.CoordinatorPlan(path, _plan())
    emitted = first.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result())

    restarted = plan_module.CoordinatorPlan(path, _plan())
    assert restarted.next_safe_action() == emitted
    restarted.mark_sent(message_id=emitted["message_id"])
    assert restarted.next_safe_action() is None


def test_failure_or_quarantine_blocks_dependents_without_emitting(tmp_path: Path) -> None:
    for outcome in ("failed", "quarantined"):
        plan = plan_module.CoordinatorPlan(tmp_path / f"{outcome}.json", _plan())
        result = plan.record_result(message_id=f"reply-{outcome}", sender="worker", action="REPLY", payload=_result(outcome=outcome))

        assert result == {"status": "blocked", "task_id": "inspect", "outcome": outcome}
        state = plan.snapshot()
        assert state["tasks"]["inspect"]["status"] == outcome
        assert state["tasks"]["next-safe"]["status"] == "blocked_dependency"
        assert plan.next_safe_action() is None


def test_fail_closed_for_unknown_task_malformed_payload_or_unauthorized_action(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())

    with pytest.raises(plan_module.PlanError, match="unknown task"):
        plan.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result("missing"))
    with pytest.raises(plan_module.PlanError, match="JSON object"):
        plan.record_result(message_id="reply-2", sender="worker", action="REPLY", payload="not json")
    with pytest.raises(plan_module.PlanError, match="REPLY or INFO"):
        plan.record_result(message_id="reply-3", sender="worker", action="TASK", payload=_result())


def test_approval_gate_can_only_be_released_explicitly(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())
    plan.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result())

    with pytest.raises(plan_module.PlanError, match="approval"):
        plan.release_approval("approval-gated", approved=False)
    plan.release_approval("approval-gated", approved=True)
    assert plan.snapshot()["tasks"]["approval-gated"]["status"] == "pending"
