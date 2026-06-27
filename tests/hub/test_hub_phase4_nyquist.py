from __future__ import annotations

from pathlib import Path

import pytest

_PHASE4_REQUIREMENTS = {
    "HUB-05",
    "HUB-06",
    "HUB-07",
    "HUB-08",
    "OBS-01",
    "OBS-02",
    "OBS-03",
}

_SIGNAL_C_REQUIRED = {
    "HUB-05",
    "HUB-08",
    "OBS-02",
    "OBS-03",
}

_EVIDENCE_MATRIX = {
    "HUB-05": {
        "A": ("tests/hub/test_http_send_parity.py", "test_ws_parity_baseline_shared_route_core_delivers"),
        "B": ("tests/hub/test_http_send_parity.py", "test_http_send_routes_valid_msg_and_emits_route_trace"),
        "C": ("tests/hub/test_http_send_parity.py", "test_http_send_unknown_destination_trace_is_allowlisted"),
    },
    "HUB-06": {
        "A": ("tests/hub/test_http_agents_health.py", "test_get_agents_returns_sorted_connected_agent_names_only"),
        "B": ("tests/hub/test_http_agents_health.py", "test_get_agents_is_deterministic_across_calls"),
        "C": ("tests/hub/test_http_agents_health.py", "test_get_agents_prunes_stale_sessions_before_response"),
    },
    "HUB-07": {
        "A": ("tests/hub/test_http_agents_health.py", "test_get_health_returns_status_ok_only"),
        "B": ("tests/hub/test_http_agents_health.py", "test_get_health_contract_stays_minimal"),
        "C": ("tests/hub/test_http_agents_health.py", "test_get_agents_response_has_only_expected_contract_key"),
    },
    "HUB-08": {
        "A": ("tests/hub/test_dashboard_runtime.py", "test_dashboard_endpoint_serves_hub_shell"),
        "B": ("tests/hub/test_dashboard_runtime.py", "test_dashboard_endpoint_contains_required_filters_and_layout_contract"),
        "C": ("tests/hub/test_dashboard_runtime.py", "test_dashboard_html_exposes_split_panel_and_clear_control"),
    },
    "OBS-01": {
        "A": ("tests/hub/test_dashboard_runtime.py", "test_snapshot_or_nodes_projection_from_snapshot_and_lifecycle_traces"),
        "B": ("tests/hub/test_dashboard_runtime.py", "test_snapshot_or_nodes_ignores_non_agent_lifecycle_and_non_trace_frames"),
        "C": ("tests/hub/test_dashboard_runtime.py", "test_apply_trace_to_nodes_reconnect_sequence_keeps_consistent_set"),
    },
    "OBS-02": {
        "A": ("tests/hub/test_dashboard_runtime.py", "test_filters_single_mode_respects_all_route_error_connect"),
        "B": ("tests/hub/test_dashboard_runtime.py", "test_filter_trace_events_preserves_original_order"),
        "C": ("tests/hub/test_dashboard_runtime.py", "test_bounded_log_window_under_high_volume_stream"),
    },
    "OBS-03": {
        "A": ("tests/hub/test_dashboard_runtime.py", "test_route_animation_requires_known_nodes_and_route_event"),
        "B": ("tests/hub/test_dashboard_runtime.py", "test_route_animation_rejects_frames_without_required_fields"),
        "C": ("tests/hub/test_dashboard_runtime.py", "test_apply_trace_to_nodes_ignores_invalid_agent_names"),
    },
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_file(path: str) -> str:
    return (_repo_root() / path).read_text(encoding="utf-8")


def test_phase4_nyquist_matrix_covers_every_requirement() -> None:
    assert set(_EVIDENCE_MATRIX.keys()) == _PHASE4_REQUIREMENTS


def test_phase4_nyquist_matrix_requires_a_and_b_for_all_rows() -> None:
    for requirement, signals in _EVIDENCE_MATRIX.items():
        assert "A" in signals, f"{requirement} missing A signal"
        assert "B" in signals, f"{requirement} missing B signal"


def test_phase4_nyquist_matrix_requires_mandatory_c_for_high_risk_paths() -> None:
    for requirement in _SIGNAL_C_REQUIRED:
        assert requirement in _EVIDENCE_MATRIX
        assert "C" in _EVIDENCE_MATRIX[requirement], f"{requirement} missing mandatory C signal"


def test_phase4_nyquist_referenced_tests_exist_in_declared_files() -> None:
    file_cache: dict[str, str] = {}

    for signals in _EVIDENCE_MATRIX.values():
        for signal_name in ("A", "B", "C"):
            file_path, test_name = signals[signal_name]
            if file_path not in file_cache:
                file_cache[file_path] = _read_file(file_path)
            file_text = file_cache[file_path]
            assert f"def {test_name}(" in file_text


def test_phase4_nyquist_validation_contract_mentions_required_c_signals() -> None:
    validation_rel = ".planning/phases/04-compatibility-apis-and-dashboard/04-VALIDATION.md"
    if not (_repo_root() / validation_rel).exists():
        pytest.skip("internal .planning phase docs are not shipped in the public repo")
    validation_text = _read_file(validation_rel)

    for requirement in sorted(_SIGNAL_C_REQUIRED):
        assert requirement in validation_text

    assert "Signal C" in validation_text
    assert "Nyquist Requirement Matrix" in validation_text


def test_phase4_nyquist_bundle_targets_core_phase4_test_files() -> None:
    expected_files = {
        "tests/hub/test_http_send_parity.py",
        "tests/hub/test_http_agents_health.py",
        "tests/hub/test_dashboard_runtime.py",
    }

    referenced_files = {
        file_path
        for signals in _EVIDENCE_MATRIX.values()
        for (file_path, _test_name) in signals.values()
    }

    assert expected_files.issubset(referenced_files)
