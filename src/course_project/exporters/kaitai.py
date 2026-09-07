from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from course_project.exporters.protocol_schema import build_protocol_schema
from course_project.models import VerifiedField

_SAFE_KAITAI_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def _normalize_id(value: str, *, prefix: str) -> str:
    candidate = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not candidate or not candidate[0].isalpha():
        candidate = f"{prefix}_{candidate or 'field'}"
    if not _SAFE_KAITAI_ID.fullmatch(candidate):
        raise ValueError(f"cannot convert {value!r} into a safe Kaitai identifier")
    return candidate


def build_kaitai_schema(
    fields: Iterable[VerifiedField],
    *,
    protocol_name: str = "inferred_protocol",
) -> str:
    """Build a conservative Kaitai Struct schema from verified byte ranges.

    Track A deliberately exports verified fields as byte slices. Semantic numeric/string
    decoding is only added when the shared VerifiedField contract carries enough explicit
    representation information (for example endian and encoding). This prevents the
    exporter from inventing semantics that Track C did not verify.
    """

    normalized = sorted(fields, key=lambda item: (item.offset, item.field_id))
    # Reuse the project-native exporter validation for IDs, offsets, sizes and scores.
    build_protocol_schema(normalized, protocol_name=protocol_name)

    kaitai_id = _normalize_id(protocol_name, prefix="protocol")
    used_ids: set[str] = set()
    cursor = 0
    seq: list[tuple[str, int | None, str]] = []

    for index, field in enumerate(normalized):
        if field.offset < cursor:
            raise ValueError(
                f"verified field {field.field_id} overlaps a previous exported byte range"
            )

        if field.offset > cursor:
            gap_size = field.offset - cursor
            seq.append(
                (
                    f"unverified_gap_{cursor:08x}",
                    gap_size,
                    f"Unverified byte range at offset {cursor} with length {gap_size}.",
                )
            )
            cursor = field.offset

        field_id = _normalize_id(field.field_id, prefix="field")
        if field_id in used_ids or field_id.startswith("unverified_gap_"):
            raise ValueError(
                f"VerifiedField IDs collide after Kaitai normalization: {field.field_id!r}"
            )
        used_ids.add(field_id)

        if field.size is None and index != len(normalized) - 1:
            raise ValueError(
                f"variable-size field {field.field_id} must be the final verified field"
            )

        doc = (
            f"Verified field {field.field_id}: {field.semantic_type}; "
            f"{field.interpretation}; verificationScore={field.verification_score:.6g}."
        )
        seq.append((field_id, field.size, doc))
        if field.size is not None:
            cursor += field.size

    lines = [
        "meta:",
        f"  id: {kaitai_id}",
        "  title: " + json.dumps(protocol_name, ensure_ascii=False),
        "  ks-version: 0.10",
        "seq:",
    ]

    if not seq:
        lines.extend(
            [
                "  - id: payload",
                "    size-eos: true",
                "    doc: \"No verified fields were available; preserve the input as raw bytes.\"",
            ]
        )
    else:
        for field_id, size, doc in seq:
            lines.append(f"  - id: {field_id}")
            if size is None:
                lines.append("    size-eos: true")
            else:
                lines.append(f"    size: {size}")
            lines.append("    doc: " + json.dumps(doc, ensure_ascii=False))

    return "\n".join(lines) + "\n"


def write_kaitai_schema(
    path: Path,
    fields: Iterable[VerifiedField],
    *,
    protocol_name: str = "inferred_protocol",
) -> Path:
    """Write a deterministic `.ksy` file suitable for the Kaitai Struct compiler."""

    payload = build_kaitai_schema(fields, protocol_name=protocol_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path
