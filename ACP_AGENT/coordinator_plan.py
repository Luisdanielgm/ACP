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
        outcome = self._normalize_outcome(result["outcome"])
        task["status"] = outcome
        next_action: dict[str, Any] | None = None
        if outcome == "completed":
            next_action = self._prepare_next_safe_action()
        else:
            self._refresh_blocked_dependencies()
        self._state["receipts"][message_id] = {
            "task_id": task_id,
            "sender": sender,
            "action": str(action).upper(),
            "outcome": outcome,
            "next_task_id": next_action.get("task_id") if next_action else None,
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
                or task_id in tasks
            ):
                raise PlanError("plan task is invalid")
            tasks[task_id] = {
                "task_id": task_id,
                "owner": owner,
                "instructions": instructions,
                "depends_on": list(dependencies),
                "approval_required": bool(raw_task.get("approval_required", False)),
                "status": status,
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
            message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"acp-plan-task:{self._state['plan_id']}:{task_id}"))
            emission = {
                "message_id": message_id,
                "task_id": task_id,
                "to": task["owner"],
                "action": "TASK",
                "payload": json.dumps(
                    {"task_id": task_id, "instructions": task["instructions"], "plan_id": self._state["plan_id"]},
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
