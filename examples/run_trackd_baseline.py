"""Deterministic Track D baseline runner (Baseline A).

Runs the statistical pipeline (``io -> boundary -> inference``) against a
generated synthetic dataset and compares the result with its ground-truth
sidecar. For dataset C it additionally evaluates the rule-based behavior
classifier using the flow metadata recorded at generation time (sizes come
from ground truth so the classifier itself is what gets measured).

This is "Baseline A: statistical heuristics only" from
``docs/testing-plan.md`` section 5; the same harness can later host the
Netzob/BinaryInferno adapters as Baseline B.

Metrics (``docs/testing-plan.md`` section 3):

- packet-boundary precision / recall / F1
- field semantic accuracy (see the documented matching rule below)
- false hypothesis rate
- behavior accuracy (dataset C only)

Ground-truth matching rule for field semantics:

    payload   -> hypothesis "payload" at the exact offset
    length    -> hypothesis "length" at the exact offset (+ endian if known)
    sequence  -> hypothesis "sequence" at the exact offset
    enum      -> hypothesis "enum" at the exact offset
    magic     -> hypothesis "magic" at offset 0
    constant  -> hypothesis "constant" (or "magic" spanning the offset)
    unknown   -> never matches

Known limitation recorded honestly in the output: a fixed/minimal payload
start cannot be recovered from column alignment alone, so the "payload" field
only matches when at least one message of the family has a zero-length
payload.

Usage:

    python examples/run_trackd_baseline.py synthetic-datasets/dataset-a

Writes ``<dataset_dir>/baseline-metrics.json`` and prints a summary. The
``metrics`` object is fully deterministic; timing and run metadata live under
``run``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from course_project.behavior import FlowPacket, predict_behavior
from course_project.boundary import detect_boundaries
from course_project.inference import infer_fields
from course_project.io import load_dat
from course_project.models import FieldHypothesis, PacketCandidate

RUNNER_NAME = "examples/run_trackd_baseline.py"


def _boundary_metrics(gt: dict, packets: list[PacketCandidate]) -> dict:
    true_internal = set(gt["boundaries"][1:-1])
    predicted = {p.start_offset for p in packets}
    predicted_internal = predicted - {0, gt["boundaries"][-1]}
    tp = len(predicted_internal & true_internal)
    precision = tp / len(predicted_internal) if predicted_internal else 0.0
    recall = tp / len(true_internal) if true_internal else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "boundary_precision": round(precision, 6),
        "boundary_recall": round(recall, 6),
        "boundary_f1": round(f1, 6),
    }


def _hypothesis_matches(hypothesis: FieldHypothesis, field: dict) -> bool:
    semantic = hypothesis.semantic_type
    offset = hypothesis.offset
    span_end = offset + (hypothesis.size if hypothesis.size is not None else 1)
    f_start = field["offset"]
    f_semantic = field["semantic_type"]

    if semantic == "unknown":
        return False
    if semantic == "payload":
        return f_semantic == "payload" and offset == f_start
    if semantic == "length":
        if f_semantic != "length" or offset != f_start:
            return False
        return not (field.get("endian") and hypothesis.endian != field["endian"])
    if semantic == "magic":
        if f_semantic == "magic":
            return offset == f_start
        if f_semantic == "constant":
            return offset <= f_start < span_end
        return False
    if semantic == "constant":
        return f_semantic == "constant" and offset <= f_start < span_end
    if semantic == "sequence":
        return f_semantic == "sequence" and offset == f_start
    if semantic == "enum":
        return f_semantic == "enum" and offset == f_start
    return False


def _field_metrics(gt: dict, hypotheses: list[FieldHypothesis]) -> dict:
    total_fields = len(gt["schema"])
    matched = sum(
        1
        for field in gt["schema"]
        if any(_hypothesis_matches(h, field) for h in hypotheses)
    )
    false_count = sum(
        1
        for h in hypotheses
        if not any(_hypothesis_matches(h, field) for field in gt["schema"])
    )
    total_hypotheses = len(hypotheses)
    return {
        "field_semantic_accuracy": round(matched / total_fields, 6)
        if total_fields
        else 0.0,
        "false_hypothesis_rate": round(false_count / total_hypotheses, 6)
        if total_hypotheses
        else 0.0,
        "hypothesis_count": total_hypotheses,
    }


def _run_analysis(data_path: Path, gt: dict) -> tuple[dict, float]:
    actual_sha = hashlib.sha256(data_path.read_bytes()).hexdigest()
    if actual_sha != gt["sha256"]:
        raise SystemExit(
            f"sha256 mismatch for {data_path}: expected {gt['sha256']}, got {actual_sha}"
        )
    stream = load_dat(data_path, source_id=gt["dataset_id"])
    t0 = time.perf_counter()
    packets = detect_boundaries(stream)
    hypotheses = infer_fields(stream, packets)
    elapsed = time.perf_counter() - t0
    metrics = {**_boundary_metrics(gt, packets), **_field_metrics(gt, hypotheses)}
    return metrics, elapsed


def run_dataset(dataset_dir: Path) -> dict:
    gt_path = dataset_dir / "ground_truth.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    metrics, elapsed = _run_analysis(dataset_dir / "capture.dat", gt)
    return {
        "dataset_id": gt["dataset_id"],
        "metrics": metrics,
        "run": {
            "runner": RUNNER_NAME,
            "python_version": sys.version.split()[0],
            "processing_time_ms": round(elapsed * 1000, 1),
            "ran_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _run_flow(flow_dir: Path, flow: dict) -> dict:
    gt = json.loads((flow_dir / f"{flow['flow']}.meta.json").read_text(encoding="utf-8"))
    metrics, elapsed = _run_analysis(flow_dir / f"{flow['flow']}.dat", gt)

    sizes = [m["end"] - m["start"] for m in gt["messages"]]
    flow_meta = gt["flow"]
    flow_packets = [
        FlowPacket(size=size, direction=direction, timestamp=timestamp)
        for size, direction, timestamp in zip(
            sizes, flow_meta["directions"], flow_meta["timestamps"]
        )
    ]
    prediction = predict_behavior(flow_packets, flow_id=gt["dataset_id"])
    metrics["behavior_label_ground_truth"] = flow_meta["label"]
    metrics["behavior_label_predicted"] = prediction.label
    metrics["behavior_correct"] = prediction.label == flow_meta["label"]
    return metrics, elapsed


def run_dataset_c(dataset_dir: Path) -> dict:
    flows = json.loads((dataset_dir / "flows.json").read_text(encoding="utf-8"))
    per_flow = {}
    total_elapsed = 0.0
    for flow in flows["flows"]:
        metrics, elapsed = _run_flow(dataset_dir, flow)
        per_flow[flow["flow"]] = metrics
        total_elapsed += elapsed
    correct = sum(1 for m in per_flow.values() if m["behavior_correct"])
    return {
        "dataset_id": "synthetic-c",
        "metrics": {
            "behavior_accuracy": round(correct / len(per_flow), 6) if per_flow else 0.0,
            "flows": per_flow,
        },
        "run": {
            "runner": RUNNER_NAME,
            "python_version": sys.version.split()[0],
            "processing_time_ms": round(total_elapsed * 1000, 1),
            "ran_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", help="generated dataset directory")
    args = parser.parse_args(argv)
    dataset_dir = Path(args.dataset_dir)
    if (dataset_dir / "flows.json").exists():
        result = run_dataset_c(dataset_dir)
    else:
        result = run_dataset(dataset_dir)
    out_path = dataset_dir / "baseline-metrics.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], indent=2))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
