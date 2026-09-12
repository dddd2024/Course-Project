from __future__ import annotations

from pathlib import Path

from course_project.models import InputMetadata
from course_project.sidecar.track_d_backend import TrackDBaselineBackend


def _config() -> dict[str, object]:
    return {
        "mode": "baseline",
        "llmEnabled": False,
        "verificationEnabled": False,
        "behaviorEnabled": False,
        "optionalDependencyPolicy": "degrade",
    }


def test_large_raw_input_uses_bounded_analysis_window(tmp_path: Path) -> None:
    capture = tmp_path / "large.dat"
    capture.write_bytes(b"\x01\x02\x03\x04" * 2048)
    metadata = InputMetadata(
        input_id="large-raw",
        kind="dat",
        size_bytes=capture.stat().st_size,
    )

    result = TrackDBaselineBackend(
        state_dir=tmp_path / "state",
        max_raw_analysis_bytes=1024,
    ).analyze(
        task_id="large-window",
        input_metadata=metadata,
        input_path=capture,
        config=_config(),
    )

    assert result.metrics["inputSizeBytes"] == 8192
    assert result.metrics["analyzedBytes"] == 1024
    assert result.metrics["analysisWindowBytes"] == 1024
    assert result.metrics["analysisTruncated"] is True
    assert any("first 1024 bytes" in item for item in result.limitations)


def test_large_pcap_named_dat_is_sniffed_without_full_analysis(tmp_path: Path) -> None:
    capture = tmp_path / "capture.dat"
    capture.write_bytes(b"\xd4\xc3\xb2\xa1" + b"\x00" * 4092)
    metadata = InputMetadata(
        input_id="large-pcap",
        kind="dat",
        size_bytes=capture.stat().st_size,
    )

    result = TrackDBaselineBackend(
        state_dir=tmp_path / "state",
        max_raw_analysis_bytes=1024,
    ).analyze(
        task_id="large-pcap-window",
        input_metadata=metadata,
        input_path=capture,
        config=_config(),
    )

    assert metadata.kind == "pcap"
    assert result.status == "partial"
    assert result.metrics["analyzedBytes"] == 4
    assert result.metrics["trackDExecuted"] is False
    assert "streaming packet extraction" in result.limitations[0]
