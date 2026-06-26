"""Portable ACP bootstrap installer for one copied ACP_AGENT folder."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ACP_ROOT = Path(__file__).resolve().parent
if str(ACP_ROOT) not in sys.path:
    sys.path.insert(0, str(ACP_ROOT))

from acp_distribution import AgentDistribution, load_distribution

ACP_ENTRYPOINT = ACP_ROOT / "acp.py"
ACP_REQUIREMENTS = ACP_ROOT / "requirements.txt"
ACP_VERSION = ACP_ROOT / "VERSION"
ACP_CHANGELOG = ACP_ROOT / "CHANGELOG.md"
ACP_BUNDLE_INFO = ACP_ROOT / "BUNDLE_INFO.json"
ACP_DISTRIBUTION = ACP_ROOT / "DISTRIBUTION.json"
ACP_DISTRIBUTION_MODULE = ACP_ROOT / "acp_distribution.py"
ACP_RELEASE_CHECKLIST = ACP_ROOT / "RELEASE_CHECKLIST.md"
SKILL_SOURCE = ACP_ROOT / "skills" / "acp-session-coordinator"
_DISTRIBUTION = load_distribution(ACP_ROOT)


def _distribution() -> AgentDistribution:
    return _DISTRIBUTION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install ACP skill and initialize the copied ACP_AGENT folder in place")
    parser.add_argument(
        "--hub-mode",
        choices=("official", "custom"),
        default=None,
        help="Hub mode. Uses the bundled hosted hub only when this distribution defines one.",
    )
    parser.add_argument("--hub-http", required=False, help="Hub HTTP base URL")
    parser.add_argument("--hub-ws", required=False, help="Hub websocket URL")
    parser.add_argument("--agent", action="append", required=False, help="Agent name to provision. Repeat for multiple agents.")
    parser.add_argument("--token", default=None, help="Optional ACP token")
    parser.add_argument("--skill-home", default=None, help="Override Codex skill home. Defaults to ~/.codex/skills")
    parser.add_argument("--claude-skill-home", default=None, help="Override Claude skill home. Defaults to ~/.claude/skills when --skill-home is not set")
    parser.add_argument(
        "--non-interactive",
        "--yes",
        dest="non_interactive",
        action="store_true",
        help="Never prompt; fail when required values are missing.",
    )
    parser.add_argument(
        "--skip-install-deps",
        action="store_true",
        help="Skip Python dependency installation checks for ACP runtime",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing ACP bundle and skill if needed")
    return parser


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


_GITIGNORE_BLOCK_HEADER = "# >>> ACP_AGENT managed (do not edit between markers) >>>"
_GITIGNORE_BLOCK_FOOTER = "# <<< ACP_AGENT managed <<<"


def _ensure_gitignore_block(target: Path, block_body: str) -> None:
    """Idempotently insert a managed block into a .gitignore file.

    Preserves any pre-existing user content. If the block already exists it is
    replaced in place so pattern updates ship to existing installs.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    block = f"{_GITIGNORE_BLOCK_HEADER}\n{block_body.strip()}\n{_GITIGNORE_BLOCK_FOOTER}\n"
    if _GITIGNORE_BLOCK_HEADER in existing and _GITIGNORE_BLOCK_FOOTER in existing:
        start = existing.index(_GITIGNORE_BLOCK_HEADER)
        end = existing.index(_GITIGNORE_BLOCK_FOOTER) + len(_GITIGNORE_BLOCK_FOOTER)
        # consume the trailing newline if present so we don't double-blank
        tail = existing[end:]
        if tail.startswith("\n"):
            tail = tail[1:]
        rewritten = existing[:start] + block + tail
        target.write_text(rewritten, encoding="utf-8")
        return
    separator = "" if existing == "" or existing.endswith("\n") else "\n"
    target.write_text(existing + separator + block, encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_bundle_version() -> str | None:
    if not ACP_VERSION.is_file():
        return None
    version = ACP_VERSION.read_text(encoding="utf-8").strip()
    return version or None


def _read_release_date(*, version: str | None) -> str | None:
    if version is None or not ACP_CHANGELOG.is_file():
        return None
    for raw_line in ACP_CHANGELOG.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("## "):
            continue
        heading = line[3:].strip()
        release_version, _, release_date = heading.partition(" - ")
        if release_version.strip() == version:
            cleaned = release_date.strip()
            return cleaned or None
    return None


def write_bundle_info(
    *,
    target_root: Path,
    source: str,
    release_manifest_url: str | None = None,
) -> dict[str, object]:
    version = _read_bundle_version()
    payload: dict[str, object] = {
        "installed_at": _utc_now_iso(),
        "installed_version": version,
        "release_date": _read_release_date(version=version),
        "source": source,
        "distribution_id": _distribution().distribution_id,
    }
    if release_manifest_url:
        payload["release_manifest_url"] = release_manifest_url
    info_path = target_root / ACP_BUNDLE_INFO.name
    info_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def _copy_file(source: Path, destination: Path, *, force: bool) -> None:
    try:
        if source.resolve() == destination.resolve():
            return
    except FileNotFoundError:
        pass
    if destination.exists() and not force:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def ensure_runtime_dependencies(*, skip_install: bool) -> dict[str, object]:
    try:
        import websockets  # noqa: F401
    except ImportError:
        if skip_install:
            raise RuntimeError(
                "ACP requires the Python package 'websockets'. Install it with "
                f"'{sys.executable} -m pip install -r {ACP_REQUIREMENTS.name}' and run the installer again."
            ) from None

        if not ACP_REQUIREMENTS.exists():
            raise RuntimeError(
                "ACP requirements.txt is missing; cannot install the required 'websockets' dependency automatically."
            ) from None

        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(ACP_REQUIREMENTS)],
            cwd=str(ACP_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        if install.returncode != 0:
            stderr = install.stderr.strip() or install.stdout.strip() or "unknown pip error"
            raise RuntimeError(
                "Automatic dependency installation failed. Run "
                f"'{sys.executable} -m pip install -r {ACP_REQUIREMENTS}' manually. Details: {stderr}"
            ) from None
        return {"installed": True, "requirements": str(ACP_REQUIREMENTS)}

    return {"installed": False, "requirements": str(ACP_REQUIREMENTS)}


def _agent_config(*, name: str, hub_mode: str, hub_http: str, hub_ws: str, token: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_name": name,
        "hub_mode": hub_mode,
        "hub_http": hub_http,
        "hub_ws": hub_ws,
        "update_policy": "notify",
        "inbox_dir": f"inbox/{name}",
        "outbox_dir": f"outbox/{name}",
        "sent_dir": f"sent/{name}",
        "poll_ms": 800,
        "backoff": [0.5, 1.0, 2.0, 5.0],
        "connect_timeout": 10.0,
    }
    if token:
        payload["token"] = token
    return payload


def _prompt_required(label: str, current: str | None) -> str:
    if current:
        return current
    if not sys.stdin.isatty():
        raise ValueError(f"{label} is required in non-interactive mode.")
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} is required.")


def _prompt_agents(existing: list[str] | None, *, non_interactive: bool = False) -> list[str]:
    if existing:
        return list(dict.fromkeys(existing))
    if non_interactive or not sys.stdin.isatty():
        raise ValueError("Agent names are required in non-interactive mode. Pass --agent <name> at least once.")
    while True:
        raw_value = input("Agent names (comma-separated, e.g. codex-chief,claude-review): ").strip()
        agent_names = [part.strip() for part in raw_value.split(",") if part.strip()]
        if agent_names:
            return list(dict.fromkeys(agent_names))
        print("At least one agent name is required.")


def _prompt_hub_mode(current: str | None, *, has_custom_urls: bool, non_interactive: bool = False) -> str:
    distribution = _distribution()
    if current in {"official", "custom"}:
        return current
    if has_custom_urls:
        return "custom"
    if distribution.default_hub_mode != "official" or not distribution.has_default_hub:
        return "custom"
    if non_interactive or not sys.stdin.isatty():
        return "official"
    while True:
        raw_value = input(
            f"Use {distribution.default_hub_label} ({distribution.default_hub_http})? [Y/n]: "
        ).strip().lower()
        if raw_value in {"", "y", "yes"}:
            return "official"
        if raw_value in {"n", "no", "custom", "own"}:
            return "custom"
        print("Answer yes for the bundled hosted hub or no if you want to use your own hub.")


def _prompt_optional_token(current: str | None, *, non_interactive: bool = False) -> str | None:
    if current is not None:
        return current
    if non_interactive or not sys.stdin.isatty():
        return None
    raw_value = input("ACP token (optional, press Enter to skip): ").strip()
    return raw_value or None


def _derive_hub_ws_from_http(hub_http: str | None) -> str | None:
    if not isinstance(hub_http, str) or not hub_http.strip():
        return None
    parsed = urllib.parse.urlparse(hub_http.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    if parsed.scheme == "https":
        ws_scheme = "wss"
    elif parsed.scheme == "http":
        ws_scheme = "ws"
    else:
        return None
    base_path = parsed.path.rstrip("/")
    ws_path = f"{base_path}/ws" if base_path else "/ws"
    return urllib.parse.urlunparse((ws_scheme, parsed.netloc, ws_path, "", "", ""))


def _resolve_hub_selection(args: argparse.Namespace) -> tuple[str, str, str]:
    distribution = _distribution()
    raw_http = args.hub_http.strip() if isinstance(args.hub_http, str) and args.hub_http.strip() else None
    raw_ws = args.hub_ws.strip() if isinstance(args.hub_ws, str) and args.hub_ws.strip() else None
    if raw_http and not raw_ws:
        raw_ws = _derive_hub_ws_from_http(raw_http)
    hub_mode = _prompt_hub_mode(
        args.hub_mode,
        has_custom_urls=bool(raw_http or raw_ws),
        non_interactive=bool(args.non_interactive),
    )

    if hub_mode == "official":
        if raw_http:
            hub_ws = raw_ws or _derive_hub_ws_from_http(raw_http)
            if not hub_ws:
                raise ValueError("Official Hub WebSocket URL is required when it cannot be derived from --hub-http.")
            return "official", raw_http.rstrip("/"), hub_ws
        if distribution.default_hub_mode != "official" or not distribution.has_default_hub:
            raise ValueError("this ACP bundle does not define a default hosted hub. Pass --hub-http and --hub-ws.")
        return "official", str(distribution.default_hub_http), str(distribution.default_hub_ws)

    hub_http = _prompt_required("Custom Hub HTTP URL", raw_http)
    hub_ws = _prompt_required("Custom Hub WebSocket URL", raw_ws or _derive_hub_ws_from_http(hub_http))
    return "custom", hub_http.rstrip("/"), hub_ws


def _bundle_readme() -> str:
    distribution = _distribution()
    default_hub_section = ""
    if distribution.default_hub_mode == "official" and distribution.has_default_hub:
        default_hub_section = f"""Install with the bundled default hub:

```bash
python ACP_AGENT/install_from_bundle.py --agent codex-chief --force
```

The current bundled default hub is:

```text
{distribution.default_hub_label}: {distribution.default_hub_http}
```
"""
    else:
        default_hub_section = """This bundle does not define a hosted default hub.

Pass your Hub URLs explicitly during install:

```bash
python ACP_AGENT/install_from_bundle.py --hub-mode custom --hub-http https://YOUR_HUB --hub-ws wss://YOUR_HUB/ws --agent codex-chief --force
```
"""
    update_section = ""
    if distribution.default_manifest_url:
        update_section = """Check whether a newer release exists for this distribution:

```bash
python ACP_AGENT/update_from_release.py --check
```

Update this installed ACP_AGENT folder in place while preserving agents and queues:

```bash
python ACP_AGENT/update_from_release.py
```
"""
    else:
        update_section = """This bundle does not define a default update manifest.

Use an explicit manifest when checking or updating:

```bash
python ACP_AGENT/update_from_release.py --check --manifest-url https://YOUR_HUB/downloads/ACP_AGENT.json
python ACP_AGENT/update_from_release.py --manifest-url https://YOUR_HUB/downloads/ACP_AGENT.json
```
"""
    return f"""# ACP Agent Folder

This `ACP_AGENT/` folder is the local ACP bridge for this project.

Prerequisites:

```bash
python -m pip install -r ACP_AGENT/requirements.txt
```

{default_hub_section}

Use a custom hub when you need your own deployment:

```bash
python ACP_AGENT/install_from_bundle.py --hub-mode custom --hub-http https://YOUR_HUB --hub-ws wss://YOUR_HUB/ws --agent codex-chief --force
```

{update_section}

Installed bundle metadata is recorded in:

```bash
ACP_AGENT/BUNDLE_INFO.json
```

Release and maintenance checklist:

```bash
ACP_AGENT/RELEASE_CHECKLIST.md
```

Typical flow:

```bash
python ACP_AGENT/acp.py create-session --config ACP_AGENT/agents/codex-chief.json --title "Auth Refactor"
python ACP_AGENT/acp.py join-session --config ACP_AGENT/agents/claude-review.json --code ABC123
python ACP_AGENT/acp.py listen --config ACP_AGENT/agents/claude-review.json
python ACP_AGENT/acp.py status --config ACP_AGENT/agents/claude-review.json --state waiting --text "Listening for next task"
python ACP_AGENT/acp.py send --config ACP_AGENT/agents/codex-chief.json --to claude-review --action TASK --payload "Review auth module"
```

Operational policy:

- Turn-based LLM agents receive with `listen --stop-after-message`; do not use persistent `listen` as their default receiver.
- Always-on workers/chiefs should prefer `runner start`.
- Persistent `listen` is only for external daemon consumers that can safely block.
- Managed workspace sessions use `managed-join --agent-token TOKEN --session-id SESSION_ID --no-listen`; core sessions use `join-session --code`.
- Publish `waiting` while the agent is available and listening.
- Reserve `idle` for true detach/teardown states only.
- If immediate follow-up is likely, or local work is done and the next step depends on external instructions, hold a foreground active-wait window of up to 20 minutes.
- Prefer the built-in helper: `python ACP_AGENT/acp.py wait-window --config ACP_AGENT/agents/<agent>.json --window-minutes 20`
"""


def install_skill(*, skill_home: Path, force: bool) -> Path:
    destination = skill_home / "acp-session-coordinator"
    if destination.exists() and force:
        shutil.rmtree(destination)
    if not destination.exists():
        shutil.copytree(SKILL_SOURCE, destination)
    return destination


def resolve_skill_homes(args: argparse.Namespace) -> list[Path]:
    if args.skill_home:
        return [Path(args.skill_home).expanduser().resolve()]
    homes = [
        Path.home() / ".codex" / "skills",
        Path(args.claude_skill_home).expanduser().resolve()
        if args.claude_skill_home
        else Path.home() / ".claude" / "skills",
    ]
    seen: set[str] = set()
    resolved: list[Path] = []
    for home in homes:
        normalized = str(home.resolve()).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(home)
    return resolved


def initialize_agent_folder(
    *,
    acp_root: Path,
    hub_mode: str,
    hub_http: str,
    hub_ws: str,
    agent_names: list[str],
    token: str | None,
    force: bool,
) -> Path:
    if force:
        _remove_path(acp_root / "wrapper.py")
        _remove_path(acp_root / "markdown_client.py")
        _remove_path(acp_root / "thin_client.py")
        _remove_path(acp_root / "enqueue_message.py")
        _remove_path(acp_root / "send.py")
        _remove_path(acp_root / "src")

    _copy_file(ACP_ENTRYPOINT, acp_root / "acp.py", force=force)
    _copy_file(ACP_DISTRIBUTION_MODULE, acp_root / "acp_distribution.py", force=force)
    _copy_file(ACP_DISTRIBUTION, acp_root / "DISTRIBUTION.json", force=force)
    _copy_file(ACP_REQUIREMENTS, acp_root / "requirements.txt", force=force)
    _copy_file(ACP_VERSION, acp_root / "VERSION", force=force)
    _copy_file(ACP_CHANGELOG, acp_root / "CHANGELOG.md", force=force)
    _copy_file(ACP_RELEASE_CHECKLIST, acp_root / "RELEASE_CHECKLIST.md", force=force)
    _copy_file(ACP_ROOT / "update_from_release.py", acp_root / "update_from_release.py", force=force)
    # Local .gitignore protects tokens (agents/*.json) and message queues from
    # being committed when ACP_AGENT lives inside a host repository. Uses a
    # managed block so users may add their own patterns above/below it.
    _ensure_gitignore_block(
        acp_root / ".gitignore",
        "agents/*.json\n"
        "inbox/\n"
        "outbox/\n"
        "sent/\n"
        "runner_state/\n"
        ".acp_runtime/\n"
        "__pycache__/\n"
        "*.py[cod]\n",
    )
    # Defense in depth: if ACP_AGENT lives inside a git repository, also touch
    # the host .gitignore so leaking tokens stays prevented even if the local
    # .gitignore is removed.
    parent_repo = acp_root.parent
    if (parent_repo / ".git").exists():
        try:
            rel = acp_root.name
            _ensure_gitignore_block(
                parent_repo / ".gitignore",
                f"{rel}/agents/*.json\n"
                f"{rel}/inbox/\n"
                f"{rel}/outbox/\n"
                f"{rel}/sent/\n"
                f"{rel}/runner_state/\n"
                f"{rel}/.acp_runtime/\n",
            )
        except OSError:
            # Best-effort. If the parent .gitignore is not writable we still
            # rely on the local one inside ACP_AGENT.
            pass
    _write_text(acp_root / "README.md", _bundle_readme())

    for name in agent_names:
        _write_text(
            acp_root / "agents" / f"{name}.json",
            json.dumps(
                _agent_config(name=name, hub_mode=hub_mode, hub_http=hub_http, hub_ws=hub_ws, token=token),
                indent=2,
            )
            + "\n",
        )
        (acp_root / "inbox" / name).mkdir(parents=True, exist_ok=True)
        (acp_root / "outbox" / name).mkdir(parents=True, exist_ok=True)
        (acp_root / "sent" / name).mkdir(parents=True, exist_ok=True)

    return acp_root


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    skill_homes = resolve_skill_homes(args)
    ACP_ROOT.mkdir(parents=True, exist_ok=True)
    for skill_home in skill_homes:
        skill_home.mkdir(parents=True, exist_ok=True)

    hub_mode, hub_http, hub_ws = _resolve_hub_selection(args)
    agent_names = _prompt_agents(args.agent, non_interactive=bool(args.non_interactive))
    token = _prompt_optional_token(args.token, non_interactive=bool(args.non_interactive))
    dependency_status = ensure_runtime_dependencies(skip_install=bool(args.skip_install_deps))

    skill_paths = [install_skill(skill_home=skill_home, force=bool(args.force)) for skill_home in skill_homes]
    skill_path = skill_paths[0]
    agent_folder = initialize_agent_folder(
        acp_root=ACP_ROOT,
        hub_mode=hub_mode,
        hub_http=hub_http,
        hub_ws=hub_ws,
        agent_names=agent_names,
        token=token,
        force=bool(args.force),
    )
    bundle_info = write_bundle_info(target_root=agent_folder, source="install_from_bundle")
    print(
        json.dumps(
            {
                "status": "ok",
                "bundle_version": ACP_VERSION.read_text(encoding="utf-8").strip() if ACP_VERSION.exists() else None,
                "bundle_info": bundle_info,
                "distribution_id": _distribution().distribution_id,
                "skill_path": str(skill_path),
                "skill_paths": [str(path) for path in skill_paths],
                "agent_folder": str(agent_folder),
                "hub_mode": hub_mode,
                "hub_http": hub_http,
                "hub_ws": hub_ws,
                "dependencies": dependency_status,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
