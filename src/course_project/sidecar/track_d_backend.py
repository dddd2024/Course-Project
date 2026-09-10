from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from course_project.behavior import extract_behavior_features, from_packet_candidates
from course_project.boundary import detect_boundaries, to_message_candidates
from course_project.exporters.protocol_schema import build_protocol_schema
from course_project.inference import family_analysis, infer_field_candidates
from course_project.io import ExtractedPacket, load_bin, load_dat, load_raw, preprocess
from course_project.models import (
    AnalysisResult,
    ArtifactRef,
    ArtifactType,
    InputMetadata,
    PacketCandidate,
)
from course_project.sidecar.semantic_bridge import (
    SemanticAnalysis,
    SemanticBackend,
    validate_semantic_analysis,
)

_EVALUATION_ONLY_CONFIG_KEYS = frozenset(
    {
        "answer",
        "answerkey",
        "answerref",
        "expectedfields",
        "expectedprotocol",
        "expectedprotocolstructure",
        "groundtruth",
        "groundtruthpath",
        "groundtruthref",
        "label",
        "labelpath",
        "labelref",
        "labels",
        "teacherdataref",
    }
)


class TrackDBaselineBackend:
    """Run deterministic Track D preprocessing and optionally compose Track C.

    Track D produces pre-semantic protocol structure. Without a semantic backend,
    requests that ask for evidence/verification remain ``partial`` and no
    ``FieldCandidate`` is promoted into an ``AnalysisFinding``. Track C can be
    connected through the narrow project-native ``SemanticBackend`` seam without
    changing the Sidecar v1 request vocabulary or Track D's public DTOs.
    """

    def __init__(
        self,
        *,
        state_dir: Path,
        semantic_backend: SemanticBackend | None = None,
    ) -> None:
        self.state_dir = state_dir.expanduser().resolve()
        self.semantic_backend = semantic_backend

    def analyze(
        self,
        *,
        task_id: str,
        input_metadata: InputMetadata,
        input_path: Path,
        config: Mapping[str, Any],
    ) -> AnalysisResult:
        _reject_evaluation_only_config(config)
        kind = input_metadata.kind
        if kind == "unknown":
            suffix = input_path.suffix.lower()
            if suffix == ".dat":
                kind = "dat"
            elif suffix == ".bin":
                kind = "bin"
            elif suffix == ".pcap":
                kind = "pcap"
            elif suffix == ".pcapng":
                kind = "pcapng"

        if kind not in {"dat", "bin", "pcap", "pcapng"}:
            return AnalysisResult(
                task_id=task_id,
                status="partial",
                input_id=input_metadata.input_id,
                metrics={
                    "analysisBackend": "track-d-baseline-v1",
                    "inputSizeBytes": input_metadata.size_bytes,
                    "mode": config["mode"],
                    "trackDExecuted": False,
                    "semanticExecuted": False,
                },
                limitations=(
                    (
                        "Track D baseline accepts .dat/.bin/PCAP/PCAPNG inputs; "
                        f"registered kind {input_metadata.kind!r} was not analyzed."
                    ),
                ),
            )

        if kind == "dat":
            source_stream = load_dat(input_path, source_id=input_metadata.input_id)
        elif kind == "bin":
            source_stream = load_bin(input_path, source_id=input_metadata.input_id)
        else:
            source_stream = load_raw(
                input_path.read_bytes(),
                source_id=input_metadata.input_id,
                format="raw",
            )

        prepared = preprocess(source_stream)
        if prepared.container in {"pcap", "pcapng"}:
            # The content-derived container is authoritative for analysis. This also
            # updates the registered metadata object held by the Sidecar so later
            # inspect_file calls report the real container even when the filename is
            # misleading (for example a PCAP stored with a .dat suffix).
            input_metadata.kind = prepared.container
            input_metadata.metadata["container"] = prepared.container
            input_metadata.metadata.setdefault("declaredKind", kind)

        if prepared.error_category is not None:
            if config.get("optionalDependencyPolicy", "degrade") == "fail":
                raise RuntimeError(
                    f"{prepared.error_category}: {prepared.detail or 'input preprocessing failed'}"
                )
            preprocess_limitation = (
                "Container preprocessing failed before unknown-protocol inference; "
                "the raw capture was not blind-scanned. "
                f"{prepared.detail or prepared.error_category}"
            )
            return AnalysisResult(
                task_id=task_id,
                status="partial",
                input_id=input_metadata.input_id,
                metrics={
                    "analysisBackend": "track-d-baseline-v1",
                    "inputSizeBytes": input_metadata.size_bytes,
                    "mode": config["mode"],
                    "trackDExecuted": False,
                    "semanticExecuted": False,
                    "preprocessContainer": prepared.container,
                    "preprocessErrorCategory": prepared.error_category,
                    "genericInferenceGated": True,
                },
                limitations=(preprocess_limitation,),
            )

        stream = prepared.stream
        if prepared.packets:
            packets = _transport_packet_candidates(prepared.packets)
        else:
            packets = detect_boundaries(stream)
        messages = to_message_candidates(
            stream,
            packets,
            input_id=input_metadata.input_id,
        )

        known_protocol_gated = prepared.protocol_hint is not None
        if known_protocol_gated:
            families = []
            alignments = []
            field_candidates = []
        else:
            families, alignments = family_analysis(
                stream,
                packets,
                input_id=input_metadata.input_id,
            )
            field_candidates = infer_field_candidates(stream, packets)

        artifact_dir = self.state_dir / "tasks" / task_id / "artifacts"
        artifacts = [
            self._write_artifact(
                artifact_dir=artifact_dir,
                task_id=task_id,
                artifact_id="track-d-messages",
                artifact_type="messages",
                filename="messages.json",
                payload={
                    "packets": [asdict(packet) for packet in packets],
                    "messages": [asdict(message) for message in messages],
                },
                count=len(messages),
            ),
            self._write_artifact(
                artifact_dir=artifact_dir,
                task_id=task_id,
                artifact_id="track-d-alignment",
                artifact_type="alignment",
                filename="alignment.json",
                payload={
                    "families": [asdict(family) for family in families],
                    "alignments": [asdict(alignment) for alignment in alignments],
                    "fieldCandidates": [asdict(candidate) for candidate in field_candidates],
                },
                count=len(field_candidates),
            ),
        ]

        behavior = None
        requested_stages = set(config.get("stages") or ())
        behavior_requested = config.get("behaviorEnabled", True) and (
            not requested_stages or "behavior" in requested_stages
        )
        if behavior_requested:
            behavior = extract_behavior_features(
                from_packet_candidates(packets),
                flow_id=f"{input_metadata.input_id}-flow-0",
            )
            artifacts.append(
                self._write_artifact(
                    artifact_dir=artifact_dir,
                    task_id=task_id,
                    artifact_id="track-d-behavior",
                    artifact_type="behavior",
                    filename="behavior.json",
                    payload=asdict(behavior),
                    count=1,
                )
            )

        semantic_requested = _semantic_requested(config, requested_stages=requested_stages)
        semantic = (
            self._run_semantic_backend(
                input_metadata=input_metadata,
                input_path=input_path,
                packets=tuple(packets),
                messages=tuple(messages),
                families=tuple(families),
                alignments=tuple(alignments),
                field_candidates=tuple(field_candidates),
                behavior=behavior,
                config=config,
            )
            if semantic_requested
            and not known_protocol_gated
            and self.semantic_backend is not None
            else None
        )

        if semantic is not None and semantic.evidence:
            artifacts.append(
                self._write_artifact(
                    artifact_dir=artifact_dir,
                    task_id=task_id,
                    artifact_id="track-c-evidence",
                    artifact_type="evidence",
                    filename="evidence.json",
                    payload={"evidence": [asdict(item) for item in semantic.evidence]},
                    count=len(semantic.evidence),
                    producer=semantic.producer,
                )
            )

        if semantic is not None and semantic.verified_fields:
            artifacts.append(
                self._write_artifact(
                    artifact_dir=artifact_dir,
                    task_id=task_id,
                    artifact_id="verified-protocol-schema",
                    artifact_type="schema",
                    filename="protocol-schema.json",
                    payload=build_protocol_schema(semantic.verified_fields),
                    count=len(semantic.verified_fields),
                    producer=semantic.producer,
                )
            )

        statistics = {
            "inputSizeBytes": input_metadata.size_bytes,
            "packetCount": len(packets),
            "messageCount": len(messages),
            "familyCount": len(families),
            "alignmentCount": len(alignments),
            "fieldCandidateCount": len(field_candidates),
            "behaviorComputed": behavior is not None,
            "semanticExecuted": semantic is not None,
            "findingCount": len(semantic.findings) if semantic is not None else 0,
            "evidenceCount": len(semantic.evidence) if semantic is not None else 0,
            "verifiedFieldCount": len(semantic.verified_fields) if semantic is not None else 0,
            "preprocessContainer": prepared.container,
            "protocolHint": prepared.protocol_hint,
            "transportPacketCount": len(prepared.packets),
            "genericInferenceGated": known_protocol_gated,
        }
        artifacts.append(
            self._write_artifact(
                artifact_dir=artifact_dir,
                task_id=task_id,
                artifact_id="track-d-statistics",
                artifact_type="statistics",
                filename="statistics.json",
                payload=statistics,
                count=len(field_candidates),
            )
        )

        limitations = list(semantic.limitations if semantic is not None else ())
        if known_protocol_gated:
            limitations.append(
                f"Known protocol {prepared.protocol_hint!r} was structurally identified after "
                "container preprocessing. Generic unknown-protocol field inference and semantic "
                "promotion were gated; encrypted payload is not claimed as recoverable plaintext."
            )
        elif semantic_requested and semantic is None:
            limitations.append(
                "Track D deterministic analysis ran successfully, but Track C semantic "
                "evidence/verification is not connected; field candidates are not promoted "
                "to protocol findings."
            )
            if config["mode"] == "evidencegraph":
                limitations.append(
                    "EvidenceGraph mode was requested; this backend returns only the "
                    "deterministic Track D preprocessing needed by Track C."
                )
            if config.get("llmEnabled"):
                limitations.append("LLM reasoning was requested but Track C is not connected.")
            if config.get("verificationEnabled"):
                limitations.append(
                    "Semantic verification was requested but remains pending Track C integration."
                )

        metrics: dict[str, Any] = {
            "analysisBackend": "track-d-baseline-v1",
            "mode": config["mode"],
            "trackDExecuted": True,
            **statistics,
        }
        if semantic is not None:
            metrics["semanticBackend"] = semantic.producer
            if semantic.metrics:
                metrics["semanticMetrics"] = dict(semantic.metrics)

        status = (
            semantic.status
            if semantic is not None
            else "partial"
            if semantic_requested or known_protocol_gated
            else "completed"
        )
        return AnalysisResult(
            task_id=task_id,
            status=status,
            findings=semantic.findings if semantic is not None else (),
            input_id=input_metadata.input_id,
            evidence=semantic.evidence if semantic is not None else (),
            artifacts=tuple(artifacts),
            metrics=metrics,
            limitations=tuple(limitations),
        )

    def _run_semantic_backend(
        self,
        *,
        input_metadata: InputMetadata,
        input_path: Path,
        packets: tuple[Any, ...],
        messages: tuple[Any, ...],
        families: tuple[Any, ...],
        alignments: tuple[Any, ...],
        field_candidates: tuple[Any, ...],
        behavior: Any,
        config: Mapping[str, Any],
    ) -> SemanticAnalysis:
        if self.semantic_backend is None:
            raise RuntimeError("semantic backend is not configured")
        result = self.semantic_backend.analyze(
            input_metadata=input_metadata,
            input_path=input_path,
            packets=packets,
            messages=messages,
            families=families,
            alignments=alignments,
            field_candidates=field_candidates,
            behavior=behavior,
            config=config,
        )
        validate_semantic_analysis(result)
        return result

    def _write_artifact(
        self,
        *,
        artifact_dir: Path,
        task_id: str,
        artifact_id: str,
        artifact_type: ArtifactType,
        filename: str,
        payload: Any,
        count: int,
        producer: str = "track-d-baseline-v1",
    ) -> ArtifactRef:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        target = artifact_dir / filename
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ArtifactRef(
            artifact_id=artifact_id,
            type=artifact_type,
            format="json",
            ref=f"tasks/{task_id}/artifacts/{filename}",
            count=count,
            metadata={"producer": producer},
        )


def _transport_packet_candidates(
    extracted_packets: tuple[ExtractedPacket, ...],
) -> list[PacketCandidate]:
    """Map extracted transport payloads onto the concatenated preprocess stream."""
    candidates: list[PacketCandidate] = []
    offset = 0
    for packet in extracted_packets:
        if not packet.payload:
            continue
        end = offset + len(packet.payload)
        candidates.append(
            PacketCandidate(
                start_offset=offset,
                end_offset=end,
                confidence=1.0,
                evidence={
                    "source": "pcap-transport-payload",
                    "packetIndex": packet.index,
                    "transport": packet.transport,
                    "src": packet.src,
                    "dst": packet.dst,
                },
                direction=packet.direction,
                timestamp=packet.timestamp,
            )
        )
        offset = end
    return candidates


def _semantic_requested(config: Mapping[str, Any], *, requested_stages: set[str]) -> bool:
    if config.get("verificationEnabled") or config.get("llmEnabled"):
        return True
    if config.get("mode") == "evidencegraph":
        return True
    if not requested_stages:
        return True
    return bool({"evidence", "llm", "verification", "export"} & requested_stages)


def _reject_evaluation_only_config(config: Mapping[str, Any]) -> None:
    """Keep labels and expected answers outside the inference configuration.

    The public Sidecar contract already rejects every unknown analyze parameter.
    This recursive check is a defense for direct backend callers and future nested
    configuration objects, which otherwise bypass the JSONL request validator.
    """

    pending: list[tuple[str, Mapping[str, Any]]] = [("config", config)]
    while pending:
        prefix, current = pending.pop()
        for key, value in current.items():
            normalized = "".join(
                character for character in str(key).lower() if character.isalnum()
            )
            path = f"{prefix}.{key}"
            if normalized in _EVALUATION_ONLY_CONFIG_KEYS:
                raise ValueError(
                    f"{path} is evaluation-only; ground truth, labels, and expected "
                    "answers must not enter Track D inference configuration"
                )
            if isinstance(value, Mapping):
                pending.append((path, value))
