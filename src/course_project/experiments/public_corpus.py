"""Reproducible public-data completion benchmark.

The upstream NFStream repository publishes packet captures together with
flow-level expected-result CSV files.  This module pins a small, homogeneous
subset of those fixtures, verifies every downloaded byte, converts packet
observations into project-native behavior features, and exports one plaintext
Modbus/TCP payload stream as the ``.dat`` input required by the course topic.

Expected labels and packet boundaries are used only after inference.  They are
never passed to the behavior feature extractor or Sidecar configuration.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from course_project.behavior import (
    classify,
    evaluate_behavior_predictions,
    extract_behavior_features,
)
from course_project.behavior.records import FlowPacket
from course_project.experiments.records import (
    DatasetIdentity,
    DependencyVersion,
    ExperimentRecord,
    canonical_record,
    metric_for_dataset,
)
from course_project.models import BehaviorFeatures, BehaviorPrediction, InputMetadata
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend

NFSTREAM_COMMIT = "1426d78597bbb8dcf556d65e9b413208c898444f"
NFSTREAM_REPOSITORY = "https://github.com/nfstream/nfstream"
NFSTREAM_LICENSE = "LGPL-3.0"
DPKT_VERSION = "1.9.8"
SCIKIT_LEARN_VERSION = "1.7.2"
PUBLIC_CORPUS_VERSION = f"nfstream-{NFSTREAM_COMMIT[:12]}"

BehaviorLabel = Literal["QUERY", "DOWNLOAD", "UPLOAD", "STREAM"]
SplitName = Literal["train", "test"]


@dataclass(frozen=True, slots=True)
class PublicCapture:
    name: str
    pcap_sha256: str
    pcap_size: int
    expected_sha256: str
    expected_size: int
    role: Literal["behavior", "protocol"]
    behavior_label: BehaviorLabel | None = None
    split: SplitName | None = None


PUBLIC_CAPTURES: tuple[PublicCapture, ...] = (
    PublicCapture("dns_doh.pcap", "b1459348b4a72c24e5646fdc05131ded69afb2fc543dc5568d004807939554c4", 22658, "0362de174ab2e801fee7508f3582e1e260e05cc2483b13162458852ebf415208", 172, "behavior", "QUERY", "train"),
    PublicCapture("dns_dot.pcap", "8f6125abecbf0e28ab824246581ba5fa3b42dcdeb8626d191f25e63699b5fb78", 6277, "688d881d97f306f62ff48b207a7fabf86f4895dd87a5b0c6741280f7f2be3c1f", 170, "behavior", "QUERY", "train"),
    PublicCapture("quic_q43.pcap", "22e7770422ca53b91a77da4876312ae4dbfc39e25116b9e21bf2efaeb01a07a7", 1520, "79a7a735bd087dbd264b5d8d406c84bb4cc3aec7c375a07dcdfc7b285f90a3d5", 170, "behavior", "QUERY", "test"),
    PublicCapture("exe_download.pcap", "7e08d61b8eec4d2ff98fa7a2443a989d7a856d32a2117eef77c6f01b7b74e0f1", 728735, "ce4185c92e47281eabafc7812cad738137c022cb532fcd76d97c307606b0d5cb", 167, "behavior", "DOWNLOAD", "train"),
    PublicCapture("bittorrent_utp.pcap", "ceea173e2af386e5e25952053b449b2ffcb86169dce3b2e0c6e26b2013758cc0", 42889, "2892c0900acf3596115aecf820ec54af82532aff1ef7ae0dbeace9a72e9f5aff", 171, "behavior", "DOWNLOAD", "test"),
    PublicCapture("youtubeupload.pcap", "3400d571eb44598093e084ca39707e28a230dc897ec6b133df58e92cea741861", 131592, "47d45c8021ee0357b690ebd51f5d80e5f9ecaeba26511eaf8b91d539e7649c23", 258, "behavior", "UPLOAD", "train"),
    PublicCapture("quic_q46_b.pcap", "7d8de27e2c1b9979109b9295e133f790f46afab50abf8be49b4bc0cc78402d53", 7364, "356046b355d8f7e6eb06a6541170aeb7790350e97862d1f1538e22359f3fb384", 175, "behavior", "UPLOAD", "test"),
    PublicCapture("mpeg.pcap", "88a72f98e1f4e2875c09f2502f6aea288329bb7cc419822fdca7b9b4e7ba45bf", 11964, "0e4236d4b1eab976fe5a16caa0de362f76ad061952a77bb02316ac794b45cd46", 167, "behavior", "STREAM", "train"),
    PublicCapture("quic046.pcap", "f21beb7c3340ecbd15b6203179854e45816daa0b831090ed7c39957211c425fc", 92921, "a5f34a1fd936a1c4611dffc24a3efc83c4aa457b056af155a3238455c5d3f9a5", 171, "behavior", "STREAM", "train"),
    PublicCapture("mpegts.pcap", "61c6a263a09c8bae574007d292058ca9218d3d80f223cc269c2ca66a00d37d68", 1402, "fd23d5f2e9e93b14c5a17a7bce7c3e3376e6b068688ce98bc16380b33cf212d8", 163, "behavior", "STREAM", "test"),
    PublicCapture("rtsp_setup_http.pcapng", "a0df37ae11d9351f58a0ef0976fba55557055b6de1ce9de9d380dde747f7b8f0", 708, "7c6bf4ce12e0ac1f8aa4d305a7b094663d88d0df5c28712bb3708b74b5f973e7", 159, "behavior", "STREAM", "test"),
    PublicCapture("modbus.pcap", "9e055a2d15a8e447be131002137341ae5f8f8b91b64576cd2fdbd854e141373e", 8337, "aad86b077562ff911fe6fffac4338e1e85b67b4feb85e49ae75c0a9bdebd9f52", 168, "protocol"),
)

_FEATURE_NAMES = (
    "packet_count",
    "total_bytes",
    "up_bytes",
    "down_bytes",
    "up_count",
    "down_count",
    "up_down_ratio",
    "size_mean",
    "size_std",
    "size_min",
    "size_max",
    "direction_switches",
    "burst_count",
    "inter_arrival_mean",
    "inter_arrival_std",
    "duration",
)


@dataclass(slots=True)
class _Flow:
    key: tuple[Any, ...]
    first_endpoint: tuple[bytes, int]
    packets: list[FlowPacket]
    frame_bytes: int = 0
    payload_chunks: list[bytes] | None = None

    def __post_init__(self) -> None:
        if self.payload_chunks is None:
            self.payload_chunks = []


@dataclass(frozen=True, slots=True)
class LabeledFlow:
    flow_id: str
    capture: str
    split: SplitName
    label: BehaviorLabel
    application_name: str
    application_category: str
    features: BehaviorFeatures


def materialize_public_corpus(
    target_dir: Path,
    *,
    fetch: Callable[[str], bytes] | None = None,
) -> Path:
    """Download the pinned corpus or verify an existing local copy."""

    target = target_dir.expanduser().resolve()
    pcap_dir = target / "tests" / "pcaps"
    result_dir = target / "tests" / "results"
    pcap_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)
    downloader = fetch or _fetch_url
    for spec in PUBLIC_CAPTURES:
        _materialize_one(
            pcap_dir / spec.name,
            _raw_url("pcaps", spec.name),
            spec.pcap_sha256,
            spec.pcap_size,
            downloader,
        )
        _materialize_one(
            result_dir / spec.name,
            _raw_url("results", spec.name),
            spec.expected_sha256,
            spec.expected_size,
            downloader,
        )
    return target


def verify_public_corpus(corpus_root: Path) -> None:
    """Verify every pinned capture and expected-result object without network access."""

    root = corpus_root.expanduser().resolve()
    for spec in PUBLIC_CAPTURES:
        _verify_object(
            root / "tests" / "pcaps" / spec.name,
            expected_sha256=spec.pcap_sha256,
            expected_size=spec.pcap_size,
        )
        _verify_object(
            root / "tests" / "results" / spec.name,
            expected_sha256=spec.expected_sha256,
            expected_size=spec.expected_size,
        )


def load_labeled_flows(corpus_root: Path) -> tuple[LabeledFlow, ...]:
    """Extract behavior features, then attach independently stored labels."""

    root = corpus_root.expanduser().resolve()
    verify_public_corpus(root)
    labeled: list[LabeledFlow] = []
    for spec in PUBLIC_CAPTURES:
        if spec.role != "behavior":
            continue
        assert spec.behavior_label is not None and spec.split is not None
        flows = _read_flows(root / "tests" / "pcaps" / spec.name)
        expected = _read_expected(root / "tests" / "results" / spec.name)
        matched = _match_expected(flows, expected, capture=spec.name)
        for row, flow in matched:
            derived = _label_from_upstream(row)
            if derived != spec.behavior_label:
                raise ValueError(
                    f"{spec.name}: declared {spec.behavior_label} conflicts with "
                    f"upstream application/category mapping {derived}"
                )
            flow_id = f"{spec.name}:flow-{row['id']}"
            labeled.append(
                LabeledFlow(
                    flow_id=flow_id,
                    capture=spec.name,
                    split=spec.split,
                    label=spec.behavior_label,
                    application_name=row["application_name"],
                    application_category=row["application_category_name"],
                    features=extract_behavior_features(flow.packets, flow_id=flow_id),
                )
            )
    return tuple(sorted(labeled, key=lambda item: item.flow_id))


def run_public_behavior_benchmark(
    corpus_root: Path,
    *,
    code_sha: str,
    random_seed: int = 20260910,
) -> dict[str, Any]:
    """Compare the existing rule baseline with a pinned RandomForest baseline."""

    flows = load_labeled_flows(corpus_root)
    train = tuple(item for item in flows if item.split == "train")
    test = tuple(item for item in flows if item.split == "test")
    if {item.label for item in train} != {"QUERY", "DOWNLOAD", "UPLOAD", "STREAM"}:
        raise ValueError("training split must contain every declared behavior class")
    if {item.label for item in test} != {"QUERY", "DOWNLOAD", "UPLOAD", "STREAM"}:
        raise ValueError("test split must contain every declared behavior class")

    rule_predictions = tuple(_rule_prediction(item) for item in test)
    forest_predictions = _random_forest_predictions(train, test, random_seed=random_seed)
    labels = {item.flow_id: item.label for item in test}
    rule_eval = evaluate_behavior_predictions(rule_predictions, labels=labels, split_unit="session")
    forest_eval = evaluate_behavior_predictions(
        forest_predictions,
        labels=labels,
        split_unit="session",
    )
    dataset = _behavior_dataset_identity()
    dependencies = (
        DependencyVersion("course-project", "0.1.0"),
        DependencyVersion("dpkt", DPKT_VERSION),
        DependencyVersion("python", platform.python_version()),
        DependencyVersion("scikit-learn", SCIKIT_LEARN_VERSION),
    )
    records = (
        _behavior_record(
            "heuristic",
            dataset,
            rule_eval.accuracy,
            rule_eval.macro_f1,
            code_sha=code_sha,
            random_seed=random_seed,
            dependencies=dependencies,
            config={"classifier": "course-project deterministic rule baseline"},
        ),
        _behavior_record(
            "random_forest",
            dataset,
            forest_eval.accuracy,
            forest_eval.macro_f1,
            code_sha=code_sha,
            random_seed=random_seed,
            dependencies=dependencies,
            config={
                "classifier": "sklearn.ensemble.RandomForestClassifier",
                "nEstimators": 200,
                "classWeight": "balanced",
                "featureNames": list(_FEATURE_NAMES),
            },
        ),
    )
    return {
        "dataset": canonical_record(records[0])["dataset"],
        "splitPolicy": {
            "unit": "source capture/session",
            "trainCaptures": sorted({item.capture for item in train}),
            "testCaptures": sorted({item.capture for item in test}),
            "packetLeakage": False,
        },
        "sampleCounts": {"train": len(train), "test": len(test)},
        "labels": sorted(labels.values()),
        "evaluations": {
            "rule": asdict(rule_eval),
            "randomForest": asdict(forest_eval),
        },
        "testPredictions": {
            "rule": [asdict(item) for item in rule_predictions],
            "randomForest": [asdict(item) for item in forest_predictions],
        },
        "records": [canonical_record(record) for record in records],
    }


def run_public_protocol_e2e(
    corpus_root: Path,
    work_dir: Path,
    *,
    code_sha: str,
) -> dict[str, Any]:
    """Export public Modbus/TCP payloads to ``.dat`` and run the real Sidecar path."""

    root = corpus_root.expanduser().resolve()
    verify_public_corpus(root)
    target = work_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    spec = next(item for item in PUBLIC_CAPTURES if item.name == "modbus.pcap")
    flows = _read_flows(root / "tests" / "pcaps" / spec.name)
    expected = _read_expected(root / "tests" / "results" / spec.name)
    matched = _match_expected(flows, expected, capture=spec.name)
    if len(matched) != 1 or matched[0][0]["application_name"] != "Modbus":
        raise ValueError("pinned Modbus capture no longer matches its upstream reference")
    chunks = tuple(chunk for chunk in matched[0][1].payload_chunks or () if chunk)
    recognition = _recognize_modbus_tcp(chunks)
    data = b"".join(chunks)
    dat_path = target / "public-modbus-payloads.dat"
    dat_path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    metadata = InputMetadata(
        input_id="public-modbus-payloads",
        kind="dat",
        size_bytes=len(data),
        sha256=digest,
        metadata={
            "source": NFSTREAM_REPOSITORY,
            "sourceCommit": NFSTREAM_COMMIT,
            "sourceCapture": spec.name,
            "transformation": "concatenate non-empty TCP application payloads in capture order",
        },
    )
    state_dir = target / "sidecar-state"
    result = TrackDBaselineBackend(
        state_dir=state_dir,
        semantic_backend=DeterministicTrackCSemanticBackend(),
    ).analyze(
        task_id="public-modbus-e2e",
        input_metadata=metadata,
        input_path=dat_path,
        config={
            "mode": "evidencegraph",
            "stages": ["boundary", "inference", "evidence", "verification", "export"],
            "llmEnabled": False,
            "verificationEnabled": True,
            "behaviorEnabled": False,
            "optionalDependencyPolicy": "degrade",
        },
    )
    messages_path = state_dir / "tasks" / "public-modbus-e2e" / "artifacts" / "messages.json"
    messages = json.loads(messages_path.read_text(encoding="utf-8"))["messages"]
    true_boundaries = _cumulative_boundaries(chunks)
    predicted_boundaries = {
        int(item["end_offset"])
        for item in messages
        if int(item["end_offset"]) < len(data)
    }
    boundary_f1 = _boundary_f1(predicted_boundaries, true_boundaries)
    dataset = DatasetIdentity(
        dataset_id="nfstream-public-modbus-payloads",
        corpus_kind="public",
        sha256=digest,
        version=PUBLIC_CORPUS_VERSION,
        size_bytes=len(data),
        ground_truth=frozenset({"packet_boundaries"}),
        redistribution_allowed=None,
    )
    record = ExperimentRecord(
        variant="evidencegraph_pre",
        result_scope="formal_benchmark",
        dataset=dataset,
        code_sha=code_sha,
        config={
            "input": "transport payloads exported to .dat",
            "llmEnabled": False,
            "groundTruthIsolation": True,
        },
        metrics=(
            metric_for_dataset(dataset, "packet_boundary_f1", boundary_f1),
            metric_for_dataset(dataset, "field_boundary_f1", None),
            metric_for_dataset(dataset, "field_semantic_accuracy", None),
            metric_for_dataset(dataset, "restoration_accuracy", None),
        ),
        random_seed=0,
        model_provider="mock",
        model_version="offline-v1",
        dependencies=(
            DependencyVersion("course-project", "0.1.0"),
            DependencyVersion("dpkt", DPKT_VERSION),
            DependencyVersion("python", platform.python_version()),
        ),
        notes=(
            "Packet boundaries come from independently extracted transport payload chunks.",
            "The upstream corpus has no field-boundary, field-semantic, or restoration reference; those metrics remain unavailable.",
        ),
    )
    return {
        "source": {
            "repository": NFSTREAM_REPOSITORY,
            "commit": NFSTREAM_COMMIT,
            "license": NFSTREAM_LICENSE,
            "capture": spec.name,
            "captureSha256": spec.pcap_sha256,
        },
        "dat": {
            "sha256": digest,
            "sizeBytes": len(data),
            "payloadChunkCount": len(chunks),
            "committed": False,
        },
        "protocolRecognitionAndRestoration": recognition,
        "blindInference": {
            "groundTruthPassedToInference": False,
            "status": result.status,
            "messageCount": result.metrics.get("messageCount"),
            "fieldCandidateCount": result.metrics.get("fieldCandidateCount"),
            "verifiedFieldCount": result.metrics.get("verifiedFieldCount"),
            "findingCount": len(result.findings),
            "artifactTypes": [item.type for item in result.artifacts],
            "limitations": list(result.limitations),
        },
        "boundaryEvaluation": {
            "trueInternalBoundaries": len(true_boundaries),
            "predictedInternalBoundaries": len(predicted_boundaries),
            "exactBoundaryF1": boundary_f1,
        },
        "record": canonical_record(record),
    }


def write_public_benchmark(
    corpus_root: Path,
    work_dir: Path,
    output_dir: Path,
    *,
    code_sha: str,
) -> Path:
    """Execute and write sanitized, deterministic public benchmark evidence."""

    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    behavior = run_public_behavior_benchmark(corpus_root, code_sha=code_sha)
    protocol = run_public_protocol_e2e(corpus_root, work_dir, code_sha=code_sha)
    manifest = {
        "schemaVersion": 1,
        "sourceRepository": NFSTREAM_REPOSITORY,
        "sourceCommit": NFSTREAM_COMMIT,
        "sourceLicense": NFSTREAM_LICENSE,
        "rawCapturesCommitted": False,
        "captures": [asdict(item) for item in PUBLIC_CAPTURES],
        "artifacts": ["behavior-benchmark.json", "protocol-e2e.json"],
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("behavior-benchmark.json", behavior),
        ("protocol-e2e.json", protocol),
    ):
        (target / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return target


def _random_forest_predictions(
    train: Sequence[LabeledFlow],
    test: Sequence[LabeledFlow],
    *,
    random_seed: int,
) -> tuple[BehaviorPrediction, ...]:
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError as exc:  # pragma: no cover - exercised without optional extra
        raise RuntimeError(
            "public behavior benchmark requires the public-benchmark dependency extra"
        ) from exc

    model = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        random_state=random_seed,
        n_jobs=1,
    )
    model.fit([_feature_vector(item.features) for item in train], [item.label for item in train])
    matrix = [_feature_vector(item.features) for item in test]
    labels = model.predict(matrix)
    probabilities = model.predict_proba(matrix)
    return tuple(
        BehaviorPrediction(
            flow_id=item.flow_id,
            label=str(label),  # type: ignore[arg-type]
            confidence=float(max(row)),
            features={"model": "RandomForestClassifier", "split": "test"},
        )
        for item, label, row in zip(test, labels, probabilities, strict=True)
    )


def _rule_prediction(item: LabeledFlow) -> BehaviorPrediction:
    label, confidence = classify(dict(item.features.values))
    return BehaviorPrediction(
        flow_id=item.flow_id,
        label=label,
        confidence=round(confidence, 6),
        features=dict(item.features.values),
    )


def _feature_vector(features: BehaviorFeatures) -> list[float]:
    return [float(features.values.get(name) or 0.0) for name in _FEATURE_NAMES]


def _behavior_record(
    variant: Literal["heuristic", "random_forest"],
    dataset: DatasetIdentity,
    accuracy: float | None,
    macro_f1: float | None,
    *,
    code_sha: str,
    random_seed: int,
    dependencies: tuple[DependencyVersion, ...],
    config: Mapping[str, Any],
) -> ExperimentRecord:
    assert accuracy is not None and macro_f1 is not None
    return ExperimentRecord(
        variant=variant,
        result_scope="formal_benchmark",
        dataset=dataset,
        code_sha=code_sha,
        config=config,
        metrics=(
            metric_for_dataset(dataset, "behavior_accuracy", accuracy),
            metric_for_dataset(dataset, "behavior_macro_f1", macro_f1),
        ),
        random_seed=random_seed,
        dependencies=dependencies,
        notes=(
            "Labels are derived by a declared mapping from pinned NFStream expected-result rows.",
            "Train and test captures are disjoint; no packet from one capture appears on both sides.",
        ),
    )


def _behavior_dataset_identity() -> DatasetIdentity:
    specs = [asdict(item) for item in PUBLIC_CAPTURES if item.role == "behavior"]
    encoded = json.dumps(specs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return DatasetIdentity(
        dataset_id="nfstream-public-behavior-v1",
        corpus_kind="public",
        sha256=hashlib.sha256(encoded).hexdigest(),
        version=PUBLIC_CORPUS_VERSION,
        size_bytes=sum(
            item.pcap_size + item.expected_size
            for item in PUBLIC_CAPTURES
            if item.role == "behavior"
        ),
        ground_truth=frozenset({"behavior_labels"}),
        redistribution_allowed=None,
    )


def _read_flows(path: Path) -> tuple[_Flow, ...]:
    try:
        import dpkt
    except ImportError as exc:  # pragma: no cover - exercised without optional extra
        raise RuntimeError("PCAP extraction requires dpkt==1.9.8") from exc

    flows: dict[tuple[Any, ...], _Flow] = {}
    with path.open("rb") as handle:
        magic = handle.read(4)
        handle.seek(0)
        reader = dpkt.pcapng.Reader(handle) if magic == b"\x0a\x0d\x0d\x0a" else dpkt.pcap.Reader(handle)
        for timestamp, raw in reader:
            try:
                network = dpkt.ethernet.Ethernet(raw).data
                if not isinstance(network, (dpkt.ip.IP, dpkt.ip6.IP6)):
                    continue
                transport = network.data
                if not isinstance(transport, (dpkt.tcp.TCP, dpkt.udp.UDP)):
                    continue
                protocol = "tcp" if isinstance(transport, dpkt.tcp.TCP) else "udp"
                source = (bytes(network.src), int(transport.sport))
                destination = (bytes(network.dst), int(transport.dport))
                key = (protocol, *sorted((source, destination)))
                flow = flows.get(key)
                if flow is None:
                    flow = _Flow(key=key, first_endpoint=source, packets=[])
                    flows[key] = flow
                direction = "up" if source == flow.first_endpoint else "down"
                flow.packets.append(
                    FlowPacket(size=len(raw), direction=direction, timestamp=float(timestamp))
                )
                flow.frame_bytes += len(raw)
                payload = bytes(transport.data)
                if payload:
                    assert flow.payload_chunks is not None
                    flow.payload_chunks.append(payload)
            except (ValueError, TypeError, dpkt.dpkt.UnpackError):
                continue
    return tuple(sorted(flows.values(), key=lambda item: repr(item.key)))


def _read_expected(path: Path) -> tuple[dict[str, str], ...]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = tuple(dict(row) for row in csv.DictReader(handle))
    required = {
        "id",
        "bidirectional_packets",
        "bidirectional_bytes",
        "application_name",
        "application_category_name",
    }
    if not rows or any(not required <= set(row) for row in rows):
        raise ValueError(f"invalid NFStream expected-result CSV: {path}")
    return rows


def _match_expected(
    flows: Sequence[_Flow],
    expected: Sequence[dict[str, str]],
    *,
    capture: str,
) -> tuple[tuple[dict[str, str], _Flow], ...]:
    by_signature: dict[tuple[int, int], list[_Flow]] = defaultdict(list)
    for flow in flows:
        by_signature[(len(flow.packets), flow.frame_bytes)].append(flow)
    matched: list[tuple[dict[str, str], _Flow]] = []
    for row in sorted(expected, key=lambda item: int(item["id"])):
        signature = (int(row["bidirectional_packets"]), int(row["bidirectional_bytes"]))
        candidates = by_signature.get(signature, [])
        if not candidates:
            raise ValueError(f"{capture}: no extracted flow matches upstream row {row['id']}")
        matched.append((row, candidates.pop(0)))
    leftovers = sum(len(items) for items in by_signature.values())
    if leftovers:
        raise ValueError(f"{capture}: {leftovers} extracted flows lack upstream expected rows")
    return tuple(matched)


def _label_from_upstream(row: Mapping[str, str]) -> BehaviorLabel:
    application = row["application_name"]
    category = row["application_category_name"]
    if "Upload" in application:
        return "UPLOAD"
    if category == "Download":
        return "DOWNLOAD"
    if "DoH_DoT" in application:
        return "QUERY"
    if category == "Media":
        return "STREAM"
    raise ValueError(
        f"no declared project behavior mapping for application={application!r}, category={category!r}"
    )


def _recognize_modbus_tcp(chunks: Sequence[bytes]) -> dict[str, Any]:
    valid = 0
    requests = 0
    responses = 0
    restored_register_values = 0
    function_codes: set[int] = set()
    for chunk in chunks:
        if len(chunk) < 8:
            continue
        protocol_id = int.from_bytes(chunk[2:4], "big")
        declared_length = int.from_bytes(chunk[4:6], "big")
        if protocol_id != 0 or declared_length != len(chunk) - 6:
            continue
        valid += 1
        pdu = chunk[7:]
        function = pdu[0]
        function_codes.add(function)
        if function == 3 and len(pdu) == 5:
            requests += 1
        elif function == 3 and len(pdu) >= 2 and pdu[1] == len(pdu) - 2:
            responses += 1
            restored_register_values += pdu[1] // 2
    confidence = valid / len(chunks) if chunks else 0.0
    return {
        "detectedProtocol": "Modbus/TCP" if chunks and valid == len(chunks) else "UNKNOWN",
        "confidence": round(confidence, 12),
        "validatedMessageCount": valid,
        "totalMessageCount": len(chunks),
        "functionCodes": sorted(function_codes),
        "readHoldingRegisterRequests": requests,
        "readHoldingRegisterResponses": responses,
        "restoredRegisterValueCount": restored_register_values,
        "method": "MBAP protocol-id and length invariants plus function-code structure",
    }


def _cumulative_boundaries(chunks: Iterable[bytes]) -> set[int]:
    total = 0
    boundaries: set[int] = set()
    normalized = tuple(chunks)
    for index, chunk in enumerate(normalized):
        total += len(chunk)
        if index < len(normalized) - 1:
            boundaries.add(total)
    return boundaries


def _boundary_f1(predicted: set[int], expected: set[int]) -> float:
    if not predicted and not expected:
        return 1.0
    true_positive = len(predicted & expected)
    denominator = 2 * true_positive + len(predicted - expected) + len(expected - predicted)
    return round((2 * true_positive) / denominator, 12) if denominator else 0.0


def _raw_url(kind: Literal["pcaps", "results"], name: str) -> str:
    return (
        "https://raw.githubusercontent.com/nfstream/nfstream/"
        f"{NFSTREAM_COMMIT}/tests/{kind}/{name}"
    )


def _fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "course-project-public-benchmark/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError(f"public corpus object exceeds 16 MiB bound: {url}")
    return data


def _materialize_one(
    path: Path,
    url: str,
    expected_sha256: str,
    expected_size: int,
    fetch: Callable[[str], bytes],
) -> None:
    if path.exists():
        data = path.read_bytes()
    else:
        data = fetch(url)
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if len(data) != expected_size or actual_sha256 != expected_sha256:
        raise ValueError(
            f"public corpus integrity mismatch for {path.name}: "
            f"size={len(data)}, sha256={actual_sha256}"
        )
    if not path.exists():
        path.write_bytes(data)


def _verify_object(path: Path, *, expected_sha256: str, expected_size: int) -> None:
    if not path.is_file():
        raise ValueError(f"public corpus object is missing: {path}")
    data = path.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if len(data) != expected_size or actual_sha256 != expected_sha256:
        raise ValueError(
            f"public corpus integrity mismatch for {path.name}: "
            f"size={len(data)}, sha256={actual_sha256}"
        )
