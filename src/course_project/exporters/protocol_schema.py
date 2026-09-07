from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from course_project.models import VerifiedField


def build_protocol_schema(
    fields: Iterable[VerifiedField],
    *,
    protocol_name: str = "inferred_protocol",
) -> dict[str, object]:
    """Build the project-native protocol schema from already verified fields only."""

    normalized = sorted(fields, key=lambda item: (item.offset, item.field_id))
    field_ids = [item.field_id for item in normalized]
    if len(field_ids) != len(set(field_ids)):
        raise ValueError("VerifiedField IDs must be unique before export")
    if not protocol_name.strip():
        raise ValueError("protocol_name must be non-empty")

    exported_fields: list[dict[str, object]] = []
    for item in normalized:
        if item.offset < 0:
            raise ValueError(f"field {item.field_id} has a negative offset")
        if item.size is not None and item.size <= 0:
            raise ValueError(f"field {item.field_id} size must be positive or None")
        if not 0.0 <= item.verification_score <= 1.0:
            raise ValueError(f"field {item.field_id} verification_score must be within [0, 1]")
        exported_fields.append(
            {
                "fieldId": item.field_id,
                "offset": item.offset,
                "size": item.size,
                "semanticType": item.semantic_type,
                "interpretation": item.interpretation,
                "verificationScore": item.verification_score,
                "evidenceIds": list(item.evidence_ids),
            }
        )

    return {
        "schemaVersion": 1,
        "protocolName": protocol_name,
        "fields": exported_fields,
    }


def write_protocol_schema(
    path: Path,
    fields: Iterable[VerifiedField],
    *,
    protocol_name: str = "inferred_protocol",
) -> Path:
    """Write a deterministic UTF-8 JSON protocol schema and return its path."""

    payload = build_protocol_schema(fields, protocol_name=protocol_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
