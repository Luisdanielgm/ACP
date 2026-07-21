from __future__ import annotations

import importlib.util
import json
import sys
import uuid
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
                "owner": "worker",
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
    assert restarted.action_for_receipt("reply-1") == {**emitted, "delivery_status": "sent"}


def test_failure_or_quarantine_blocks_dependents_without_emitting(tmp_path: Path) -> None:
    for outcome in ("failed", "quarantined"):
        plan = plan_module.CoordinatorPlan(tmp_path / f"{outcome}.json", _plan())
        result = plan.record_result(message_id=f"reply-{outcome}", sender="worker", action="REPLY", payload=_result(outcome=outcome))

        assert result == {"status": "blocked", "task_id": "inspect", "outcome": outcome}
        state = plan.snapshot()
        assert state["tasks"]["inspect"]["status"] == outcome
        assert state["tasks"]["next-safe"]["status"] == "blocked_dependency"
        assert plan.next_safe_action() is None


def test_explicit_retry_budget_emits_a_new_attempt_without_reusing_delivery_id(tmp_path: Path) -> None:
    definition = _plan()
    definition["tasks"][0]["max_attempts"] = 2
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", definition)

    retry = plan.record_result(
        message_id="reply-failed-attempt-1",
        sender="worker",
        action="REPLY",
        payload=_result(outcome="failed"),
    )

    first_attempt_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "acp-plan-task:pilot-plan:inspect"))
    assert retry["status"] == "ready"
    assert retry["task_id"] == "inspect"
    assert retry["message_id"] != first_attempt_id
    assert json.loads(retry["payload"])["attempt"] == 2
    assert plan.snapshot()["tasks"]["inspect"]["attempt"] == 2


def test_retry_attempt_is_restart_safe_and_success_unblocks_dependencies(tmp_path: Path) -> None:
    definition = _plan()
    definition["tasks"][0]["max_attempts"] = 2
    path = tmp_path / "plan.json"
    plan = plan_module.CoordinatorPlan(path, definition)
    retry = plan.record_result(
        message_id="reply-failed-attempt-1",
        sender="worker",
        action="REPLY",
        payload=_result(outcome="interrupted"),
    )
    plan.mark_sent(message_id=retry["message_id"])

    restarted = plan_module.CoordinatorPlan(path, definition)
    next_action = restarted.record_result(
        message_id="reply-success-attempt-2",
        sender="worker",
        action="REPLY",
        payload=_result(outcome="success"),
    )

    assert next_action["task_id"] == "next-safe"
    assert restarted.snapshot()["tasks"]["inspect"]["status"] == "completed"
    duplicate = restarted.record_result(
        message_id="reply-failed-attempt-1",
        sender="worker",
        action="REPLY",
        payload=_result(outcome="interrupted"),
    )
    assert duplicate["task_id"] == "inspect"


def test_existing_state_migrates_attempt_budget_without_rewriting_task_set(tmp_path: Path) -> None:
    definition = _plan()
    path = tmp_path / "plan.json"
    original = plan_module.CoordinatorPlan(path, definition)
    legacy = original.snapshot()
    for task in legacy["tasks"].values():
        task.pop("attempt", None)
        task.pop("max_attempts", None)
    path.write_text(json.dumps(legacy), encoding="utf-8")
    definition["tasks"][0]["max_attempts"] = 2

    migrated = plan_module.CoordinatorPlan(path, definition).snapshot()

    assert migrated["tasks"]["inspect"]["attempt"] == 1
    assert migrated["tasks"]["inspect"]["max_attempts"] == 2


def test_quarantine_blocks_dependents_but_advances_independent_work(tmp_path: Path) -> None:
    definition = _plan()
    definition["tasks"].append(
        {"task_id": "independent", "owner": "coordinator", "instructions": "Continue independent audit", "depends_on": []}
    )
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", definition)

    result = plan.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result(outcome="quarantined"))

    assert result["status"] == "ready"
    assert result["task_id"] == "independent"
    assert plan.snapshot()["tasks"]["next-safe"]["status"] == "blocked_dependency"


def test_fail_closed_for_unknown_task_malformed_payload_or_unauthorized_action(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())

    with pytest.raises(plan_module.PlanError, match="unknown task"):
        plan.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result("missing"))
    with pytest.raises(plan_module.PlanError, match="JSON object"):
        plan.record_result(message_id="reply-2", sender="worker", action="REPLY", payload="not json")
    with pytest.raises(plan_module.PlanError, match="REPLY or INFO"):
        plan.record_result(message_id="reply-3", sender="worker", action="TASK", payload=_result())


def test_result_sender_must_match_dispatched_task_owner(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())

    with pytest.raises(plan_module.PlanError, match="task owner"):
        plan.record_result(message_id="reply-1", sender="other-worker", action="REPLY", payload=_result())

    assert plan.snapshot()["tasks"]["inspect"]["status"] == "dispatched"


def test_sensitive_risk_requires_explicit_approval_gate(tmp_path: Path) -> None:
    definition = _plan()
    definition["tasks"].append(
        {
            "task_id": "unsafe",
            "owner": "worker",
            "instructions": "Perform a sensitive mutation",
            "risk": "sensitive",
            "depends_on": [],
        }
    )

    with pytest.raises(plan_module.PlanError, match="sensitive risk requires explicit approval"):
        plan_module.CoordinatorPlan(tmp_path / "plan.json", definition)


def test_risk_is_declarative_and_preserved_in_emitted_task(tmp_path: Path) -> None:
    definition = _plan()
    definition["tasks"][1]["risk"] = "read_only"
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", definition)

    action = plan.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result())

    assert plan.snapshot()["tasks"]["next-safe"]["risk"] == "read_only"
    assert json.loads(action["payload"])["risk"] == "read_only"


def test_approval_gate_can_only_be_released_explicitly(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())
    plan.record_result(message_id="reply-1", sender="worker", action="REPLY", payload=_result())

    with pytest.raises(plan_module.PlanError, match="approval"):
        plan.release_approval("approval-gated", approved=False)
    plan.release_approval("approval-gated", approved=True)
    assert plan.snapshot()["tasks"]["approval-gated"]["status"] == "pending"


def test_collector_planner_reuses_delivery_after_crash_and_marks_it_sent(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())
    planner = plan_module.CoordinatorPlanCollector(plan)
    message = {"id": "reply-1", "from": "worker", "action": "REPLY", "payload": _result()}

    first = planner.prepare(message)
    assert first is not None
    assert planner.prepare(message) == first
    planner.mark_forwarded(first)
    assert plan.next_safe_action() is None
    assert planner.prepare(message) == first


def test_planner_ignores_structured_results_owned_by_another_product_plan(tmp_path: Path) -> None:
    plan = plan_module.CoordinatorPlan(tmp_path / "plan.json", _plan())
    planner = plan_module.CoordinatorPlanCollector(plan)
    message = {
        "id": "reply-unrelated",
        "from": "worker",
        "action": "REPLY",
        "payload": json.dumps({"task_id": "ad-hoc-task", "outcome": "success"}),
    }

    assert planner.prepare(message) is None
    assert plan.snapshot()["receipts"] == {}
