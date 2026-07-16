"""Cross-process reservation for ACP agent configuration files."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


@dataclass(frozen=True)
class ConfigReservation:
    config_path: Path
    lock_path: Path
    token: str
    was_missing: bool


def _lock_path(config_path: Path) -> Path:
    return config_path.with_name(f"{config_path.name}.join.lock")


def _payload(lock_path: Path) -> dict[str, Any] | None:
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"pid=(\d+)", raw)
        return {"pid": int(match.group(1))} if match else {}
    return parsed if isinstance(parsed, dict) else {}


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _remove_if_stale(lock_path: Path) -> bool:
    payload = _payload(lock_path)
    if payload is None:
        return True
    pid = payload.get("pid")
    stale = isinstance(pid, int) and not _process_is_alive(pid)
    if not isinstance(pid, int):
        try:
            stale = time.time() - lock_path.stat().st_mtime > 300
        except FileNotFoundError:
            return True
    if not stale:
        return False
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass
    return True


def assert_reservation_owned(reservation: ConfigReservation) -> None:
    payload = _payload(reservation.lock_path)
    if payload is None or payload.get("token") != reservation.token:
        raise ValueError(f"config reservation for {reservation.config_path.name} is no longer owned by this process")


@contextmanager
def reserve_config(config_path: Path) -> Iterator[ConfigReservation]:
    """Serialize every official writer and recover locks whose owner process died."""

    config_path = config_path.resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path(config_path)
    was_missing = not config_path.is_file()
    token = uuid4().hex
    descriptor: int | None = None
    for _ in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError as exc:
            if _remove_if_stale(lock_path):
                continue
            raise ValueError(
                f"config {config_path.name} is reserved by another process; wait or use a different agent/config."
            ) from exc
    if descriptor is None:
        raise ValueError(f"unable to reserve config {config_path.name}")

    reservation = ConfigReservation(config_path, lock_path, token, was_missing)
    try:
        os.write(
            descriptor,
            (json.dumps({"pid": os.getpid(), "created_at": time.time(), "token": token}) + "\n").encode("ascii"),
        )
        os.close(descriptor)
        descriptor = None
        if was_missing and config_path.is_file():
            raise ValueError(f"config {config_path.name} was created while its reservation was being acquired")
        yield reservation
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if (_payload(lock_path) or {}).get("token") == token:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
