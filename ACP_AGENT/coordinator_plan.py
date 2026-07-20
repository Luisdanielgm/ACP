"""Durable, host-neutral coordinator plan advancement.

The plan is deliberately generic: ACP persists task state and emits a single
dependency-ready TASK, while the consuming product owns task content, business
priorities, approvals, and any domain-specific evidence.
"""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping


class PlanError(ValueError):
    """Raised when a plan or result cannot advance safely."""


_SUCCESS = {"success", "succeeded", "completed", "done", "ok", "passed"}
_TERMINAL_FAILURE = {"failed", "error", "quarantined", "interrupted"}
_INITIAL_STATUSES = {"pending", "dispatched"}
_RISKS = {"read_only", "low", "medium", "high", "sensitive"}
_APPROVAL_RISKS = {"high", "sensitive"}


class CoordinatorPlan:
    """Persist result correlation and exactly-one next safe task delivery."""

    def __init__(self, path: Path, definition: Mapping[str, Any]) -> None:
        self.path = Path(path)
        self.definition = self._normalize_definition(definition)
        self._task_order = tuple(self.definition["tasks"])
        if self.path.exists():
            self._state = self._load_existing()
        else:
            self._state = self._initial_state()
            self._save()

    def snapshot(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._state))

    def record_result(self, *, message_id: str, sender: str, action: str, payload: str) -> dict[str, Any]:
        if not isinstance(message_id, str) or not message_id.strip():
            raise PlanError("result requires a message id")
        if not isinstance(sender, str) or not sender.strip():
            raise PlanError("result requires a sender")
        if str(action).upper() not in {"REPLY", "INFO"}:
            raise PlanError("plan accepts only REPLY or INFO results")
        receipt = self._state["receipts"].get(message_id)
        if isinstance(receipt, dict):
            return {
                "status": "duplicate",
                "message_id": message_id,
                "task_id": receipt.get("next_task_id"),
            }
        result = self._parse_result(payload)
        task_id = result["task_id"]
        task = self._state["tasks"].get(task_id)
        if not isinstance(task, dict):
            raise PlanError("result references an unknown task")
        if task["status"] != "dispatched":
            raise PlanError("result does not match a dispatched task")
        if sender != task["owner"]:
            raise PlanError("result sender does not match task owner")
        outcome = self._normalize_outcome(result["outcome"])
        task["status"] = outcome
        task["last_outcome"] = outcome
        next_action: dict[str, Any] | None = None
        if outcome == "completed":
            next_action = self._prepare_next_safe_action()
        else:
            if task["attempt"] < task["max_attempts"]:
                task["status"] = "pending"
            next_action = self._prepare_next_safe_action()
        self._state["receipts"][message_id] = {
            "task_id": task_id,
            "sender": sender,
            "action": str(action).upper(),
            "outcome": outcome,
            "next_task_id": next_action.get("task_id") if next_action else None,
            "next_message_id": next_action.get("message_id") if next_action else None,
        }
        self._save()
        if next_action is not None:
            return next_action
        return {"status": "blocked", "task_id": task_id, "outcome": outcome}

    def next_safe_action(self) -> dict[str, Any] | None:
        for emission in self._state["emissions"].values():
            if isinstance(emission, dict) and emission.get("status") == "pending":
                return self._public_emission(emission)
        return None

    def action_for_receipt(self, message_id: str) -> dict[str, Any] | None:
        receipt = self._state["receipts"].get(message_id)
        if not isinstance(receipt, dict):
            raise PlanError("unknown result receipt")
        delivery_id = receipt.get("next_message_id")
        if not isinstance(delivery_id, str) or not delivery_id:
            return None
        emission = self._state["emissions"].get(delivery_id)
        if not isinstance(emission, dict):
            raise PlanError("result receipt references an unknown delivery")
        return {**self._public_emission(emission), "delivery_status": emission["status"]}

    def mark_sent(self, *, message_id: str) -> None:
        emission = self._state["emissions"].get(message_id)
        if not isinstance(emission, dict):
            raise PlanError("unknown task delivery")
        if emission.get("status") == "sent":
            return
        if emission.get("status") != "pending":
            raise PlanError("task delivery is not pending")
        task = self._state["tasks"][emission["task_id"]]
        task["status"] = "dispatched"
        emission["status"] = "sent"
        self._save()

    def release_approval(self, task_id: str, *, approved: bool) -> None:
        if approved is not True:
            raise PlanError("approval must be explicit")
        task = self._state["tasks"].get(task_id)
        if not isinstance(task, dict):
            raise PlanError("unknown task")
        if task.get("status") != "blocked_approval":
            raise PlanError("task is not blocked on approval")
        task["approval_required"] = False
        task["status"] = "pending"
        self._save()

    def _initial_state(self) -> dict[str, Any]:
        tasks: dict[str, dict[str, Any]] = {}
        for task in self.definition["tasks"].values():
            tasks[task["task_id"]] = dict(task)
        return {
            "schema_version": 1,
            "plan_id": self.definition["plan_id"],
            "tasks": tasks,
            "receipts": {},
            "emissions": {},
        }

    def _load_existing(self) -> dict[str, Any]:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PlanError("plan state is unreadable") from exc
        if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
            raise PlanError("plan state has an invalid format")
        if loaded.get("plan_id") != self.definition["plan_id"]:
            raise PlanError("plan id does not match durable state")
        tasks = loaded.get("tasks")
        if not isinstance(tasks, dict) or set(tasks) != set(self.definition["tasks"]):
            raise PlanError("plan task set does not match durable state")
        if not isinstance(loaded.get("receipts"), dict) or not isinstance(loaded.get("emissions"), dict):
            raise PlanError("plan state has an invalid format")
        for task_id, task in tasks.items():
            if isinstance(task, dict):
                task.setdefault("risk", self.definition["tasks"][task_id]["risk"])
                task["max_attempts"] = self.definition["tasks"][task_id]["max_attempts"]
                task.setdefault(
                    "attempt",
                    0 if task.get("status") in {"pending", "blocked_dependency", "blocked_approval"} else 1,
                )
        return loaded

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
            json.dump(self._state, handle, sort_keys=True, separators=(",", ":"))
            temporary = Path(handle.name)
        temporary.replace(self.path)

    @staticmethod
    def _normalize_definition(definition: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(definition, Mapping):
            raise PlanError("plan definition must be an object")
        plan_id = definition.get("plan_id")
        raw_tasks = definition.get("tasks")
        if not isinstance(plan_id, str) or not plan_id.strip() or not isinstance(raw_tasks, list) or not raw_tasks:
            raise PlanError("plan definition requires plan_id and tasks")
        tasks: dict[str, dict[str, Any]] = {}
        for raw_task in raw_tasks:
            if not isinstance(raw_task, Mapping):
                raise PlanError("plan task must be an object")
            task_id = raw_task.get("task_id")
            owner = raw_task.get("owner")
            instructions = raw_task.get("instructions")
            dependencies = raw_task.get("depends_on") or []
            status = raw_task.get("status", "pending")
            risk = raw_task.get("risk", "low")
            approval_required = bool(raw_task.get("approval_required", False))
            max_attempts = raw_task.get("max_attempts", 1)
            if (
                not isinstance(task_id, str)
                or not task_id.strip()
                or not isinstance(owner, str)
                or not owner.strip()
                or not isinstance(instructions, str)
                or not instructions.strip()
                or not isinstance(dependencies, list)
                or not all(isinstance(dep, str) and dep.strip() for dep in dependencies)
                or status not in _INITIAL_STATUSES
                or risk not in _RISKS
                or not isinstance(max_attempts, int)
                or isinstance(max_attempts, bool)
                or not 1 <= max_attempts <= 5
                or task_id in tasks
            ):
                raise PlanError("plan task is invalid")
            if risk in _APPROVAL_RISKS and not approval_required:
                raise PlanError(f"{risk} risk requires explicit approval")
            tasks[task_id] = {
                "task_id": task_id,
                "owner": owner,
                "instructions": instructions,
                "depends_on": list(dependencies),
                "approval_required": approval_required,
                "risk": risk,
                "status": status,
                "attempt": 1 if status == "dispatched" else 0,
                "max_attempts": max_attempts,
            }
        for task in tasks.values():
            if any(dep not in tasks for dep in task["depends_on"]):
                raise PlanError("plan task has an unknown dependency")
        return {"plan_id": plan_id, "tasks": tasks}

    @staticmethod
    def _parse_result(payload: str) -> dict[str, str]:
        try:
            result = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PlanError("result payload must be a JSON object") from exc
        if not isinstance(result, dict):
            raise PlanError("result payload must be a JSON object")
        task_id = result.get("task_id")
        outcome = result.get("outcome")
        if not isinstance(task_id, str) or not task_id.strip() or not isinstance(outcome, str) or not outcome.strip():
            raise PlanError("result payload requires task_id and outcome")
        return {"task_id": task_id.strip(), "outcome": outcome.strip()}

    @staticmethod
    def _normalize_outcome(outcome: str) -> str:
        normalized = outcome.strip().lower()
        if normalized in _SUCCESS:
            return "completed"
        if normalized == "quarantined":
            return "quarantined"
        if normalized in _TERMINAL_FAILURE:
            return "failed"
        raise PlanError("result outcome is not terminal")

    def _prepare_next_safe_action(self) -> dict[str, Any] | None:
        self._refresh_blocked_dependencies()
        for task_id in self._task_order:
            task = self._state["tasks"][task_id]
            if task["status"] != "pending" or not self._dependencies_completed(task):
                continue
            if task["approval_required"]:
                task["status"] = "blocked_approval"
                continue
            next_attempt = task["attempt"] + 1
            if next_attempt > task["max_attempts"]:
                task["status"] = "failed"
                continue
            task["attempt"] = next_attempt
            identity = f"acp-plan-task:{self._state['plan_id']}:{task_id}"
            if next_attempt > 1:
                identity = f"{identity}:attempt:{next_attempt}"
            message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
            emission = {
                "message_id": message_id,
                "task_id": task_id,
                "to": task["owner"],
                "action": "TASK",
                "payload": json.dumps(
                    {
                        "task_id": task_id,
                        "instructions": task["instructions"],
                        "plan_id": self._state["plan_id"],
                        "risk": task["risk"],
                        "attempt": next_attempt,
                        "max_attempts": task["max_attempts"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "status": "pending",
            }
            self._state["emissions"][message_id] = emission
            task["status"] = "ready_to_send"
            return self._public_emission(emission)
        return None

    def _refresh_blocked_dependencies(self) -> None:
        for task_id in self._task_order:
            task = self._state["tasks"][task_id]
            if task["status"] not in {"pending", "blocked_dependency", "blocked_approval"}:
                continue
            if not self._dependencies_completed(task):
                task["status"] = "blocked_dependency"
            elif task["approval_required"]:
                task["status"] = "blocked_approval"
            elif task["status"] == "blocked_dependency":
                task["status"] = "pending"

    def _dependencies_completed(self, task: Mapping[str, Any]) -> bool:
        return all(self._state["tasks"][dependency]["status"] == "completed" for dependency in task["depends_on"])

    @staticmethod
    def _public_emission(emission: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": "ready",
            "message_id": emission["message_id"],
            "task_id": emission["task_id"],
            "to": emission["to"],
            "action": emission["action"],
            "payload": emission["payload"],
        }


class CoordinatorPlanCollector:
    """Adapt a CoordinatorPlan to ReplyCollector's durable planner contract."""

    def __init__(self, plan: CoordinatorPlan) -> None:
        self.plan = plan

    def prepare(self, message: Mapping[str, Any]) -> dict[str, Any] | None:
        message_id = str(message.get("id") or "")
        try:
            candidate = json.loads(message.get("payload"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if (
            not isinstance(candidate, dict)
            or not isinstance(candidate.get("task_id"), str)
            or not isinstance(candidate.get("outcome"), str)
        ):
            return None
        self.plan.record_result(
            message_id=message_id,
            sender=str(message.get("from") or ""),
            action=str(message.get("action") or ""),
            payload=message.get("payload"),
        )
        action = self.plan.action_for_receipt(message_id)
        if action is None:
            return None
        action.pop("delivery_status", None)
        return action

    def mark_forwarded(self, emission: Mapping[str, Any]) -> None:
        self.plan.mark_sent(message_id=str(emission.get("message_id") or ""))
