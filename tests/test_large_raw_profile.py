from __future__ import annotations

import random
from pathlib import Path

from course_project.sidecar.large_raw_profile import profile_large_raw_file


def test_streaming_profile_recovers_record_and_cipher_evidence(tmp_path: Path) -> None:
    marker = b"\x10\x00\xe8\xc0"
    sessions = (bytes.fromhex("38370fa6007f580600bbffd0"), bytes.fromhex("38370c2e007f798900bbffd0"))
    total_lengths = (1538, 84, 1534, 90)
    random_source = random.Random(17)
    capture = tmp_path / "structured-large.dat"
    with capture.open("wb") as handle:
        for index in range(900):
            session = sessions[0] if index < 600 else sessions[1]
            total_length = total_lengths[index % len(total_lengths)]
            payload = random_source.randbytes(total_length - 20)
            handle.write(marker)
            handle.write(index.to_bytes(4, "big"))
            handle.write(session)
            handle.write(payload)

    profile = profile_large_raw_file(capture, size_bytes=capture.stat().st_size)

    assert profile["bytesScanned"] == capture.stat().st_size
    assert profile["markerHex"] == marker.hex()
    assert profile["markerOccurrenceCount"] == 900
    assert profile["inferredHeaderBytes"] == 20
    assert profile["headerEvidence"]["counterUniqueRatio"] == 1.0
    assert profile["headerEvidence"]["counterIncrementByOneRatio"] > 0.8
    assert profile["payloadEvidence"]["entropyBitsPerByte"] > 7.9
    assert profile["payloadEvidence"]["zlibRatio"] > 0.99
    claims = " ".join(item["claim"] for item in profile["conclusions"])
    assert "逐包记录流" in claims
    assert "长度保持型流式加密" in claims
    assert "Ethernet" in claims
