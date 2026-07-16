from pathlib import Path


def test_invite_prompt_behavior_runs_in_node_20_ci() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    root_package = Path("apps/hub/frontend/package.json").read_text(encoding="utf-8")
    public_package = Path("apps/hub/frontend/packages/public-app/package.json").read_text(encoding="utf-8")

    assert 'node-version: "20"' in workflow
    assert "npm run build" in workflow
    assert "npm test" in workflow
    assert '"test": "npm test --workspace=packages/public-app"' in root_package
    assert '"test": "node --test src/composables/invitePrompt.test.mjs"' in public_package
