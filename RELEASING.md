# Releasing

How to cut a release of the `ACP_AGENT` bundle. The release manifest served at
`/downloads/ACP_AGENT.json` is built on demand by
[`bundle_release.py`](apps/hub/src/acp/hub/bundle_release.py) from the current
`ACP_AGENT/` source, so most of a release is updating version metadata and
letting the test suite enforce correctness.

## Checklist

1. **Bump the version.** Update [`ACP_AGENT/VERSION`](ACP_AGENT/VERSION) to the
   new bare version string (for example `0.3.11`).

2. **Update the changelog.** Add a new section to
   [`ACP_AGENT/CHANGELOG.md`](ACP_AGENT/CHANGELOG.md) using the exact format the
   parser expects — a `## <version> - <YYYY-MM-DD>` heading followed by paired
   bilingual bullets:

   ```markdown
   ## 0.3.11 - 2026-07-03
   - EN: Short description of the change.
   - ES: Descripción breve del cambio.
   ```

   The manifest derives `released_at` from the latest changelog date, so keep
   the date accurate.

3. **Run the test suite.** From the repo root:

   ```bash
   python -m pip install -e "apps/hub[test]"
   python -m pytest -q
   ```

   This exercises the release gates in
   [`tests/hub/test_bundle_release.py`](tests/hub/test_bundle_release.py) and
   [`tests/wrapper/test_dropin_bundle.py`](tests/wrapper/test_dropin_bundle.py).
   They must pass before you ship (see **What the tests enforce** below).

4. **Confirm the distribution defaults.** The public community bundle keeps
   [`ACP_AGENT/DISTRIBUTION.json`](ACP_AGENT/DISTRIBUTION.json) with
   `"distribution_id": "acp-community"`, `"default_hub_mode": "explicit"`, and
   null hub/manifest URLs. Users always provide their own `--hub-http`; the
   public bundle must not ship a baked-in hub. This is test-enforced.

5. **Deploy / restart the hub.** The manifest and zip regenerate from the new
   source on request via `ensure_bundle_archive()`, so no separate build step is
   required beyond having the updated files in `ACP_AGENT/`.

6. **Spot-check the published artifacts.**

   ```bash
   curl https://acp.example.com/downloads/ACP_AGENT.json   # reflects new version + sha256
   curl https://acp.example.com/health                     # green
   ```

## What the tests enforce

Treat these as the release contract — they fail the suite if a release would
break the bundle:

- **CLI surface.** The `acp.py` subcommand set must be a superset of the minimum
  list (`run, send, create-session, join-session, wait, listen, status,
  heartbeat, session-info, leave-session`).
- **Skill file.** `ACP_AGENT/skills/acp-session-coordinator/SKILL.md` stays
  ≤180 lines and must literally contain `coordinate --agent <agent>`,
  `connect --role auto`, `listen --stop-after-message --timeout-seconds 300`,
  and `runner start`.
- **Guide files.** `ACP_AGENT/AGENT.md` and `protocol.md` must contain their
  required substrings (for example `install_from_bundle.py --force`,
  `session_dashboard_url`, `/sessions/wait`, and the note that active sessions do
  not survive a hub restart/redeploy) and must contain **no** U+FFFD replacement
  characters (a mojibake guard).
- **Dependencies.** `requirements.txt` includes `websockets`.
- **Changelog format.** Bilingual notes are preserved as `{en, es}` pairs;
  unpaired language bullets are backfilled from each other.
- **Manifest resilience.** The manifest can read `VERSION`/`CHANGELOG` from
  inside the zip when the source directory is absent (for deployed containers),
  and `official_hub_http` / `official_hub_ws` (from `ACP_PUBLIC_HUB_HTTP`) take
  precedence over any passed base URL.
