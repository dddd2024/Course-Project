from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT / "deliverables" / "pre-teacher"


def test_frozen_delivery_manifest_matches_checkout_bytes() -> None:
    entries: dict[str, str] = {}
    for line in (DELIVERY / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        assert relative not in entries
        entries[relative] = digest

    expected = {
        path.relative_to(DELIVERY).as_posix()
        for path in DELIVERY.rglob("*")
        if path.is_file()
        and path.name not in {"README.md", "SHA256SUMS.txt"}
    }
    assert set(entries) == expected

    for relative, expected_digest in entries.items():
        actual = hashlib.sha256((DELIVERY / relative).read_bytes()).hexdigest()
        assert actual == expected_digest, relative


def test_frozen_delivery_json_and_artifact_references_are_resolvable() -> None:
    for path in DELIVERY.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))

    result_path = (
        DELIVERY / "synthetic-analysis" / "tasks" / "task-demo" / "analysis-result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    for artifact in result["artifacts"]:
        target = DELIVERY / "synthetic-analysis" / artifact["ref"]
        assert target.is_file(), artifact["ref"]
