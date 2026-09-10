from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "test-data" / "dat"
SOURCE_METADATA = FIXTURE_DIR / "public-dtls-snakeoil.source.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_public_dtls_fixture_hashes_match_provenance() -> None:
    metadata = json.loads(SOURCE_METADATA.read_text(encoding="utf-8"))
    for filename, expected in metadata["files"].items():
        data = (FIXTURE_DIR / filename).read_bytes()
        assert len(data) == expected["bytes"]
        assert _sha256(data) == expected["sha256"]


def test_application_data_fixture_is_three_complete_dtls_records() -> None:
    data = (FIXTURE_DIR / "public-dtls-snakeoil-application-data.dat").read_bytes()

    offset = 0
    records: list[tuple[int, int, int]] = []
    while offset < len(data):
        assert len(data) - offset >= 13
        content_type = data[offset]
        epoch = int.from_bytes(data[offset + 3 : offset + 5], "big")
        sequence = int.from_bytes(data[offset + 5 : offset + 11], "big")
        record_length = int.from_bytes(data[offset + 11 : offset + 13], "big")
        end = offset + 13 + record_length
        assert end <= len(data)
        records.append((content_type, epoch, sequence))
        offset = end

    assert offset == len(data)
    assert records == [(23, 1, 1), (23, 1, 3), (23, 1, 2)]
