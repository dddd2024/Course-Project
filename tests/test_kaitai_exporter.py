from __future__ import annotations

from pathlib import Path

import pytest

from course_project.exporters import build_kaitai_schema, write_kaitai_schema
from course_project.models import VerifiedField


def test_verified_fields_flow_to_kaitai_schema(tmp_path: Path) -> None:
    fields = [
        VerifiedField(
            field_id="length",
            offset=2,
            size=2,
            semantic_type="length",
            interpretation="verified length bytes",
            verification_score=0.99,
            evidence_ids=("ev-length",),
        ),
        VerifiedField(
            field_id="payload",
            offset=4,
            size=None,
            semantic_type="payload",
            interpretation="remaining verified payload",
            verification_score=0.9,
            evidence_ids=("ev-payload",),
        ),
    ]

    schema = build_kaitai_schema(fields, protocol_name="Demo Protocol")

    assert "id: demo_protocol" in schema
    assert "id: unverified_gap_00000000" in schema
    assert "size: 2" in schema
    assert "id: length" in schema
    assert "id: payload" in schema
    assert "size-eos: true" in schema
    assert "verificationScore=0.99" in schema

    target = write_kaitai_schema(tmp_path / "schema" / "demo.ksy", fields, protocol_name="Demo Protocol")
    assert target.read_text(encoding="utf-8") == schema


def test_kaitai_export_is_conservative_about_unverified_semantics() -> None:
    field = VerifiedField(
        field_id="sequence-number",
        offset=0,
        size=4,
        semantic_type="sequence",
        interpretation="sequence-like bytes; endian not represented in shared contract",
        verification_score=1.0,
    )

    schema = build_kaitai_schema([field])

    assert "id: sequence_number" in schema
    assert "size: 4" in schema
    assert "type: u4" not in schema
    assert "type: s4" not in schema


def test_kaitai_export_rejects_ambiguous_layouts() -> None:
    first = VerifiedField(
        field_id="first",
        offset=0,
        size=4,
        semantic_type="bytes",
        interpretation="first field",
        verification_score=1.0,
    )
    overlap = VerifiedField(
        field_id="overlap",
        offset=2,
        size=2,
        semantic_type="bytes",
        interpretation="overlapping field",
        verification_score=1.0,
    )
    with pytest.raises(ValueError, match="overlaps"):
        build_kaitai_schema([first, overlap])

    variable = VerifiedField(
        field_id="variable",
        offset=0,
        size=None,
        semantic_type="payload",
        interpretation="variable bytes",
        verification_score=1.0,
    )
    later = VerifiedField(
        field_id="later",
        offset=8,
        size=1,
        semantic_type="flag",
        interpretation="later byte",
        verification_score=1.0,
    )
    with pytest.raises(ValueError, match="final verified field"):
        build_kaitai_schema([variable, later])


def test_empty_verified_field_set_preserves_raw_payload() -> None:
    schema = build_kaitai_schema([], protocol_name="empty")
    assert "id: payload" in schema
    assert "size-eos: true" in schema
