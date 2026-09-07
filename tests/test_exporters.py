from __future__ import annotations

import json
from pathlib import Path

import pytest

from course_project.exporters import build_protocol_schema, write_protocol_schema
from course_project.models import VerifiedField


def test_verified_fields_flow_to_protocol_schema(tmp_path: Path) -> None:
    fields = [
        VerifiedField(
            field_id="payload",
            offset=4,
            size=None,
            semantic_type="payload",
            interpretation="remaining bytes",
            verification_score=0.9,
            evidence_ids=("ev-payload",),
        ),
        VerifiedField(
            field_id="length",
            offset=2,
            size=2,
            semantic_type="length",
            interpretation="big-endian full-message length",
            verification_score=0.99,
            evidence_ids=("ev-length",),
        ),
    ]

    payload = build_protocol_schema(fields, protocol_name="demo")
    assert payload["protocolName"] == "demo"
    assert [item["fieldId"] for item in payload["fields"]] == ["length", "payload"]
    assert payload["fields"][0]["verificationScore"] == 0.99

    target = write_protocol_schema(tmp_path / "schema" / "protocol.json", fields, protocol_name="demo")
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == payload


def test_protocol_schema_export_rejects_invalid_verified_fields() -> None:
    duplicate = VerifiedField(
        field_id="length",
        offset=0,
        size=2,
        semantic_type="length",
        interpretation="candidate",
        verification_score=1.0,
    )
    with pytest.raises(ValueError, match="unique"):
        build_protocol_schema([duplicate, duplicate])

    invalid_score = VerifiedField(
        field_id="bad",
        offset=0,
        size=1,
        semantic_type="unknown",
        interpretation="invalid score",
        verification_score=1.2,
    )
    with pytest.raises(ValueError, match="verification_score"):
        build_protocol_schema([invalid_score])
