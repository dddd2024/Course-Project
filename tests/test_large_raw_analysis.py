from __future__ import annotations

import hashlib
import math
from pathlib import Path

from course_project.models import InputMetadata
from course_project.sidecar.large_raw_profile import profile_large_raw_file
from course_project.sidecar.track_d_backend import TrackDBaselineBackend


def _config() -> dict[str, object]:
    return {
        "mode": "baseline",
        "llmEnabled": False,
        "verificationEnabled": False,
        "behaviorEnabled": False,
        "optionalDependencyPolicy": "degrade",
    }


def test_large_raw_profile_scans_and_accounts_for_every_byte(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capture = tmp_path / "complete.dat"
    payload = bytes(range(256)) * 9 + b"final-tail"
    capture.write_bytes(payload)
    monkeypatch.setattr(
        "course_project.sidecar.large_raw_profile._SCAN_CHUNK_BYTES", 257
    )

    profile = profile_large_raw_file(capture, size_bytes=len(payload))

    assert profile["bytesScanned"] == len(payload)
    assert profile["coverageRatio"] == 1.0
    assert profile["sha256"] == hashlib.sha256(payload).hexdigest()
    assert profile["chunkCount"] == math.ceil(len(payload) / 257)
    assert sum(item["size"] for item in profile["chunkProfiles"]) == len(payload)
    assert [item["offset"] for item in profile["chunkProfiles"]] == [
        index * 257 for index in range(profile["chunkCount"])
    ]
    assert all("entropyBitsPerByte" in item for item in profile["chunkProfiles"])

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


def test_large_raw_profile_conclusions_are_visible_findings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capture = tmp_path / "profiled.dat"
    capture.write_bytes(bytes.fromhex("1000e8c0") * 2)
    metadata = InputMetadata(
        input_id="profiled-large-raw",
        kind="dat",
        size_bytes=capture.stat().st_size,
    )
    profile = {
        "bytesScanned": capture.stat().st_size,
        "conclusions": [
            {
                "claim": "候选负载呈高熵且不可压缩",
                "confidence": "high",
                "basis": ["熵接近 8 bit/Byte", "zlib 比率接近 1"],
            }
        ],
    }
    monkeypatch.setattr(
        "course_project.sidecar.track_d_backend.profile_large_raw_file",
        lambda path, *, size_bytes: profile,
    )

    result = TrackDBaselineBackend(
        state_dir=tmp_path / "state",
        max_raw_analysis_bytes=4,
    ).analyze(
        task_id="large-profile-findings",
        input_metadata=metadata,
        input_path=capture,
        config=_config(),
    )

    assert len(result.findings) == 1
    assert result.findings[0].claim == "候选负载呈高熵且不可压缩"
    assert result.findings[0].status == "uncertain"
    assert result.findings[0].evidence_ids == ("track-d-large-raw-evidence-1",)
    assert result.findings[0].scores["evidence"] == 0.9
    assert result.evidence[0].observation["basis"] == [
        "熵接近 8 bit/Byte",
        "zlib 比率接近 1",
    ]
    assert result.metrics["findingCount"] == 1
    assert result.metrics["largeRawFindingCount"] == 1
    assert result.metrics["semanticFindingCount"] == 0
