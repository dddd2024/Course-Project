from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from course_project.models import InputMetadata
from course_project.sidecar.track_d_backend import TrackDBaselineBackend

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "forbidden_config",
    [
        {"groundTruthRef": "answers.json"},
        {"labels": {"message-1": "header"}},
        {"evaluation": {"answerKey": {"protocol": "SYN1"}}},
        {"evaluation": {"expectedProtocolStructure": ["header", "payload"]}},
    ],
)
def test_direct_track_d_backend_rejects_evaluation_only_config(
    tmp_path: Path,
    forbidden_config: dict[str, Any],
) -> None:
    sample = tmp_path / "placeholder.dat"
    sample.write_bytes(b"SYN1\x01\x00\x00\x00\x01\x00\x0b")
    backend = TrackDBaselineBackend(state_dir=tmp_path / "state")
    metadata = InputMetadata(
        input_id="input-placeholder",
        kind="dat",
        size_bytes=sample.stat().st_size,
    )

    with pytest.raises(ValueError, match="evaluation-only"):
        backend.analyze(
            task_id="task-label-leak",
            input_metadata=metadata,
            input_path=sample,
            config={"mode": "baseline", **forbidden_config},
        )

    assert not (tmp_path / "state" / "tasks").exists()


def test_teacher_dataset_metadata_fixture_matches_contract() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "teacher-dataset-metadata.schema.json").read_text(
            encoding="utf-8"
        )
    )
    fixture = json.loads(
        (ROOT / "contracts" / "fixtures" / "synthetic-dataset-metadata.json").read_text(
            encoding="utf-8"
        )
    )

    errors = sorted(
        Draft202012Validator(schema).iter_errors(fixture),
        key=lambda error: list(error.path),
    )
    assert not errors, "; ".join(error.message for error in errors)
    assert fixture["corpusKind"] == "synthetic"
    assert fixture["groundTruth"] is None
