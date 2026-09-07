from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _run(script: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, str(EXAMPLES / script), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session")
def datasets(tmp_path_factory) -> Path:
    outdir = tmp_path_factory.mktemp("synthetic-datasets")
    _run("generate_synthetic_datasets.py", "--outdir", str(outdir))
    return outdir


def _metrics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_baseline_dataset_a(datasets: Path) -> None:
    dataset_dir = datasets / "dataset-a"
    _run("run_trackd_baseline.py", str(dataset_dir))
    metrics = _metrics(dataset_dir / "baseline-metrics.json")["metrics"]
    assert metrics["boundary_f1"] >= 0.9
    assert metrics["field_semantic_accuracy"] >= 0.9

    # deterministic rerun produces identical metrics
    _run("run_trackd_baseline.py", str(dataset_dir))
    rerun = _metrics(dataset_dir / "baseline-metrics.json")["metrics"]
    assert rerun == metrics


def test_baseline_dataset_b(datasets: Path) -> None:
    dataset_dir = datasets / "dataset-b"
    _run("run_trackd_baseline.py", str(dataset_dir))
    metrics = _metrics(dataset_dir / "baseline-metrics.json")["metrics"]
    assert metrics["boundary_f1"] >= 0.9
    assert metrics["field_semantic_accuracy"] >= 0.9


def test_baseline_dataset_c_behavior(datasets: Path) -> None:
    dataset_dir = datasets / "dataset-c"
    _run("run_trackd_baseline.py", str(dataset_dir))
    metrics = _metrics(dataset_dir / "baseline-metrics.json")["metrics"]
    assert metrics["behavior_accuracy"] == 1.0
    for flow in metrics["flows"].values():
        assert flow["boundary_f1"] >= 0.9
