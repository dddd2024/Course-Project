from __future__ import annotations

from pathlib import Path

import pytest

from course_project.io import ExtractedPacket, PreprocessResult, load_raw
from course_project.models import InputMetadata
from course_project.sidecar import track_d_backend
from course_project.sidecar.track_d_backend import TrackDBaselineBackend


def _config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "mode": "baseline",
        "llmEnabled": False,
        "verificationEnabled": False,
        "behaviorEnabled": True,
        "optionalDependencyPolicy": "degrade",
    }
    config.update(overrides)
    return config


def test_known_dtls_preprocess_is_wired_into_production_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "capture.dat"
    capture.write_bytes(b"not-used-by-fake-preprocess")
    metadata = InputMetadata(
        input_id="input-dtls",
        kind="dat",
        size_bytes=capture.stat().st_size,
    )

    prepared_stream = load_raw(b"helloworld", source_id=metadata.input_id)
    prepared = PreprocessResult(
        container="pcap",
        protocol_hint="dtls",
        stream=prepared_stream,
        packets=(
            ExtractedPacket(
                index=4,
                payload=b"hello",
                timestamp=1.0,
                transport="udp",
                src="127.0.0.1:1000",
                dst="127.0.0.1:2000",
            ),
            ExtractedPacket(
                index=5,
                payload=b"world",
                timestamp=2.0,
                transport="udp",
                src="127.0.0.1:2000",
                dst="127.0.0.1:1000",
            ),
        ),
    )
    monkeypatch.setattr(track_d_backend, "preprocess", lambda stream: prepared)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("known DTLS must not enter generic unknown-protocol inference")

    monkeypatch.setattr(track_d_backend, "detect_boundaries", forbidden)
    monkeypatch.setattr(track_d_backend, "family_analysis", forbidden)
    monkeypatch.setattr(track_d_backend, "infer_field_candidates", forbidden)

    backend = TrackDBaselineBackend(state_dir=tmp_path / "state")
    result = backend.analyze(
        task_id="dtls-production-wiring",
        input_metadata=metadata,
        input_path=capture,
        config=_config(),
    )

    assert metadata.kind == "pcap"
    assert result.status == "partial"
    assert result.findings == ()
    assert result.metrics["trackDExecuted"] is True
    assert result.metrics["preprocessContainer"] == "pcap"
    assert result.metrics["protocolHint"] == "dtls"
    assert result.metrics["genericInferenceGated"] is True
    assert result.metrics["transportPacketCount"] == 2
    assert result.metrics["packetCount"] == 2
    assert result.metrics["fieldCandidateCount"] == 0
    assert any("Generic unknown-protocol field inference" in item for item in result.limitations)


def test_preprocess_failure_never_falls_back_to_raw_blind_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "capture.dat"
    capture.write_bytes(b"opaque-capture")
    metadata = InputMetadata(
        input_id="input-pcap-without-parser",
        kind="dat",
        size_bytes=capture.stat().st_size,
    )
    original = load_raw(capture.read_bytes(), source_id=metadata.input_id)
    prepared = PreprocessResult(
        container="pcap",
        protocol_hint=None,
        stream=original,
        error_category="dependency_unavailable",
        detail="scapy unavailable",
    )
    monkeypatch.setattr(track_d_backend, "preprocess", lambda stream: prepared)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("preprocess failure must fail closed before raw inference")

    monkeypatch.setattr(track_d_backend, "detect_boundaries", forbidden)
    monkeypatch.setattr(track_d_backend, "infer_field_candidates", forbidden)

    backend = TrackDBaselineBackend(state_dir=tmp_path / "state")
    result = backend.analyze(
        task_id="pcap-dependency-fallback",
        input_metadata=metadata,
        input_path=capture,
        config=_config(),
    )

    assert metadata.kind == "pcap"
    assert result.status == "partial"
    assert result.metrics["trackDExecuted"] is False
    assert result.metrics["preprocessContainer"] == "pcap"
    assert result.metrics["preprocessErrorCategory"] == "dependency_unavailable"
    assert result.metrics["genericInferenceGated"] is True
    assert any("raw capture was not blind-scanned" in item for item in result.limitations)
