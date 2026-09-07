from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from course_project.behavior import extract_behavior_features, from_packet_candidates
from course_project.boundary import detect_boundaries, to_message_candidates
from course_project.inference import family_analysis, infer_field_candidates
from course_project.io import load_bin, load_dat
from course_project.models import AnalysisResult, ArtifactRef, ArtifactType, InputMetadata


class TrackDBaselineBackend:
    """Run the deterministic Track D pipeline behind the Sidecar v1 boundary.

    Track D produces pre-semantic protocol structure only. Until Track C is
    connected, this backend deliberately returns ``partial`` and never promotes
    a ``FieldCandidate`` into an ``AnalysisFinding``.
    """

    def __init__(self, *, state_dir: Path) -> None:
        self.state_dir = state_dir.expanduser().resolve()

    def analyze(
        self,
        *,
        task_id: str,
        input_metadata: InputMetadata,
        input_path: Path,
        config: Mapping[str, Any],
    ) -> AnalysisResult:
        kind = input_metadata.kind
        if kind == "unknown":
            suffix = input_path.suffix.lower()
            if suffix == ".dat":
                kind = "dat"
            elif suffix == ".bin":
                kind = "bin"

        if kind not in {"dat", "bin"}:
            return AnalysisResult(
                task_id=task_id,
                status="partial",
                input_id=input_metadata.input_id,
                metrics={
                    "analysisBackend": "track-d-baseline-v1",
                    "inputSizeBytes": input_metadata.size_bytes,
                    "mode": config["mode"],
                    "trackDExecuted": False,
                },
                limitations=(
                    (
                        f"Track D baseline currently accepts raw .dat/.bin inputs; "
                        f"registered kind {input_metadata.kind!r} was not analyzed."
                    ),
                ),
            )

        stream = (
            load_dat(input_path, source_id=input_metadata.input_id)
            if kind == "dat"
            else load_bin(input_path, source_id=input_metadata.input_id)
        )
        packets = detect_boundaries(stream)
        messages = to_message_candidates(
            stream,
            packets,
            input_id=input_metadata.input_id,
        )
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

        statistics = {
            "inputSizeBytes": input_metadata.size_bytes,
            "packetCount": len(packets),
            "messageCount": len(messages),
            "familyCount": len(families),
            "alignmentCount": len(alignments),
            "fieldCandidateCount": len(field_candidates),
            "behaviorComputed": behavior is not None,
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

        limitations = [
            (
                "Track D deterministic analysis ran successfully, but Track C semantic "
                "evidence/verification is not connected; field candidates are not promoted "
                "to protocol findings."
            ),
        ]
        if config["mode"] == "evidencegraph":
            limitations.append(
                "EvidenceGraph mode was requested; this backend returns only the "
                "deterministic Track D preprocessing needed by Track C."
            )
        if config.get("llmEnabled"):
            limitations.append("LLM reasoning was requested but is not connected in Track A yet.")
        if config.get("verificationEnabled"):
            limitations.append(
                "Semantic verification was requested but remains pending Track C integration."
            )

        return AnalysisResult(
            task_id=task_id,
            status="partial",
            input_id=input_metadata.input_id,
            artifacts=tuple(artifacts),
            metrics={
                "analysisBackend": "track-d-baseline-v1",
                "mode": config["mode"],
                "trackDExecuted": True,
                **statistics,
            },
            limitations=tuple(limitations),
        )

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
            metadata={"producer": "track-d-baseline-v1"},
        )
