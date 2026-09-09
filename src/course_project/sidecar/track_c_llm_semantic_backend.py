from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from course_project.evidence.alignment_producer import produce_alignment_evidence
from course_project.evidence.global_selection import (
    POLICY_VERSION as GLOBAL_SELECTION_POLICY_VERSION,
)
from course_project.evidence.hypothesis_manager import HypothesisManager
from course_project.evidence.provenance_fusion import (
    POLICY_VERSION,
    ProvenanceFusionResult,
    fuse_hypothesis_evidence,
)
from course_project.llm import (
    LLMHypothesisProvider,
    LLMHypothesisRequest,
    OpenAICompatibleLLMProvider,
    OpenAICompatibleProviderConfig,
)
from course_project.models import (
    AlignmentResult,
    AnalysisFinding,
    BehaviorFeatures,
    Evidence,
    FieldCandidate,
    InputMetadata,
    MessageCandidate,
    MessageFamily,
    PacketCandidate,
    ProtocolHypothesis,
)
from course_project.sidecar.semantic_bridge import SemanticAnalysis
from course_project.sidecar.track_c_semantic_backend import (
    DeterministicTrackCSemanticBackend as _DeterministicTrackCSemanticBackend,
)
from course_project.sidecar.track_c_semantic_backend import (
    _AcceptedPromotion,
    _apply_global_selection,
    _finding_claim,
    _fusion_evidence,
    _fusion_metric,
    _independence_group,
    _message_bytes,
    _register_hypotheses,
    _sample_ids,
    _selection_metric,
    _to_hypothesis,
)
from course_project.verification import (
    VerificationError,
    verification_result,
    verify_length,
    verify_sequence,
)

LLMProviderFactory = Callable[[], LLMHypothesisProvider]
_SemanticEntry = tuple[
    FieldCandidate,
    ProtocolHypothesis,
    tuple[bytes, ...],
    tuple[str, ...],
    str,
]
_MAX_CONTEXT_SAMPLES = 16
_MAX_CONTEXT_FIELD_BYTES = 8
_SUPPORTED_LLM_TYPES = frozenset({"length", "sequence"})
_SAFE_PROVIDER_METADATA_KEYS = frozenset(
    {"networkAccess", "endpointHost", "model", "responseModel", "structuredOutput"}
)


@dataclass(slots=True)
class _LLMRun:
    entries: list[_SemanticEntry]
    evidence: list[Evidence]
    hypothesis_ids: set[str]
    limitations: list[str]
    metrics: dict[str, Any]


def _default_live_provider() -> LLMHypothesisProvider:
    """Build the already-supported live provider only when LLM use is requested."""

    return OpenAICompatibleLLMProvider(OpenAICompatibleProviderConfig.from_environment())


class DeterministicTrackCSemanticBackend(_DeterministicTrackCSemanticBackend):
    """Production Track C backend with opt-in LLM hypotheses plus executable checks.

    The existing deterministic path remains byte-for-byte delegated to the legacy
    implementation when ``llmEnabled`` is false.  When LLM use is enabled, this
    class adds provider hypotheses as *derived* evidence for an existing field
    region, runs the same deterministic verifiers, and only then lets the normal
    provenance-aware fusion/global-selection layers decide whether anything can
    be promoted.

    Provider transport is intentionally not reimplemented here.  The default
    factory lazily reuses the project's existing OpenAI-compatible adapter, while
    tests can inject any ``LLMHypothesisProvider`` implementation.
    """

    def __init__(
        self,
        *,
        llm_provider: LLMHypothesisProvider | None = None,
        llm_provider_factory: LLMProviderFactory | None = None,
    ) -> None:
        if llm_provider is not None and llm_provider_factory is not None:
            raise ValueError("configure llm_provider or llm_provider_factory, not both")
        self._llm_provider = llm_provider
        self._llm_provider_factory = llm_provider_factory or _default_live_provider

    def analyze(
        self,
        *,
        input_metadata: InputMetadata,
        input_path: Path,
        packets: tuple[PacketCandidate, ...],
        messages: tuple[MessageCandidate, ...],
        families: tuple[MessageFamily, ...],
        alignments: tuple[AlignmentResult, ...],
        field_candidates: tuple[FieldCandidate, ...],
        behavior: BehaviorFeatures | None,
        config: Mapping[str, Any],
    ) -> SemanticAnalysis:
        # Preserve the existing deterministic/offline behavior exactly and,
        # critically, do not resolve provider configuration or credentials.
        if not config.get("llmEnabled"):
            return super().analyze(
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

        requested_stages = set(config.get("stages") or ())
        if config.get("verificationEnabled") is False and "verification" not in requested_stages:
            base = super().analyze(
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
            metrics = dict(base.metrics)
            metrics.update(
                {
                    "llmRequested": True,
                    "llmExecuted": False,
                    "llmContextPolicy": "structural-summary-v1",
                    "llmHypothesisCount": 0,
                }
            )
            return SemanticAnalysis(
                producer=base.producer,
                status=base.status,
                findings=base.findings,
                evidence=base.evidence,
                verified_fields=base.verified_fields,
                metrics=metrics,
                limitations=tuple(
                    (*base.limitations, "LLM hypotheses are not executed without executable verification.")
                ),
            )

        del packets, behavior
        raw = input_path.read_bytes()
        message_bytes = _message_bytes(raw, messages)
        family_message_ids = {
            family.family_id: family.message_ids for family in families
        }

        manager = HypothesisManager()
        entries: list[_SemanticEntry] = []
        candidate_contexts: list[_SemanticEntry] = []
        alignment_evidence = produce_alignment_evidence(alignments)
        evidence: list[Evidence] = list(alignment_evidence)
        limitations: list[str] = []

        for candidate in field_candidates:
            converted = _to_hypothesis(candidate)
            if converted is None:
                if {"length", "sequence"} & set(candidate.candidate_types):
                    limitations.append(
                        f"Candidate {candidate.candidate_id!r} could not be translated safely."
                    )
                continue

            sample_ids = _sample_ids(candidate, messages, family_message_ids)
            samples = tuple(
                message_bytes[message_id]
                for message_id in sample_ids
                if message_id in message_bytes
            )
            retained_ids = tuple(
                message_id for message_id in sample_ids if message_id in message_bytes
            )
            candidate_evidence_id = f"candidate:{candidate.candidate_id}"
            independence_group = _independence_group(candidate)
            evidence.append(
                Evidence(
                    evidence_id=candidate_evidence_id,
                    source_component="track-d-field-candidate",
                    method="normalized-field-candidate",
                    feature_family=converted.semantic_type,
                    score=max(0.0, min(1.0, float(candidate.score))),
                    observation={
                        "candidateId": candidate.candidate_id,
                        "candidateTypes": list(candidate.candidate_types),
                        "familyId": candidate.family_id,
                        "offset": candidate.offset,
                        "size": candidate.size,
                        "endian": candidate.endian,
                        "attributes": dict(candidate.attributes),
                    },
                    independence_group=independence_group,
                    sample_ids=retained_ids,
                )
            )
            converted.supporting_evidence_ids = (candidate_evidence_id,)
            entry = (
                candidate,
                converted,
                samples,
                retained_ids,
                independence_group,
            )
            entries.append(entry)
            candidate_contexts.append(entry)

        candidate_entry_count = len(entries)
        llm_run = self._run_llm(
            input_id=input_metadata.input_id,
            candidate_contexts=candidate_contexts,
        )
        evidence.extend(llm_run.evidence)
        entries.extend(llm_run.entries)
        limitations.extend(llm_run.limitations)
        llm_hypothesis_ids = llm_run.hypothesis_ids

        _register_hypotheses(manager, entries)

        findings: list[AnalysisFinding] = []
        findings_by_hypothesis: dict[str, AnalysisFinding] = {}
        accepted_promotions: list[_AcceptedPromotion] = []
        verification_decision_counts = {"accepted": 0, "rejected": 0, "uncertain": 0}
        decision_counts = {"accepted": 0, "rejected": 0, "uncertain": 0}
        fusion_results: list[ProvenanceFusionResult] = []
        fusion_evidence_producers: set[str] = set()
        llm_unverifiable = 0

        for candidate, hypothesis, samples, sample_ids, independence_group in entries:
            try:
                check = (
                    verify_length(hypothesis, samples)
                    if hypothesis.semantic_type == "length"
                    else verify_sequence(hypothesis, samples)
                )
            except VerificationError:
                limitations.append(
                    f"Hypothesis {hypothesis.hypothesis_id!r} could not be translated into a safe executable check."
                )
                if hypothesis.hypothesis_id in llm_hypothesis_ids:
                    llm_unverifiable += 1
                continue

            result = verification_result(check)
            manager.record_verification(result)
            verification_decision_counts[result.status] += 1

            verification_evidence_id = f"verification:{hypothesis.hypothesis_id}"
            verification_evidence = Evidence(
                evidence_id=verification_evidence_id,
                source_component="track-c-executable-verifier",
                method=check.check_type,
                feature_family=hypothesis.semantic_type,
                score=check.score,
                observation={
                    "hypothesisId": hypothesis.hypothesis_id,
                    "status": result.status,
                    "sampleCount": check.sample_count,
                    "supportCount": check.support_count,
                    "violationCount": check.violation_count,
                    "checkId": check.check_id,
                },
                parent_evidence_ids=hypothesis.supporting_evidence_ids,
                independence_group=independence_group,
                sample_ids=sample_ids,
            )
            evidence.append(verification_evidence)

            relevant_evidence = _fusion_evidence(
                candidate,
                hypothesis,
                alignment_evidence,
                evidence,
                verification_evidence_id,
            )
            fusion = fuse_hypothesis_evidence(
                hypothesis.hypothesis_id,
                relevant_evidence,
                result,
            )
            fusion_results.append(fusion)
            decision_counts[fusion.status] += 1
            fusion_evidence_producers.update(
                item.source_component for item in relevant_evidence
            )
            fused_evidence_ids = tuple(sorted(item.evidence_id for item in relevant_evidence))

            finding = AnalysisFinding(
                finding_id=f"finding:{hypothesis.hypothesis_id}",
                claim=_finding_claim(hypothesis, fusion.status),
                status=fusion.status,
                evidence_ids=fused_evidence_ids,
                semantic_type=hypothesis.semantic_type,
                scores={
                    "evidence": fusion.support_score,
                    "verification": result.score,
                },
            )
            findings.append(finding)
            findings_by_hypothesis[hypothesis.hypothesis_id] = finding

            if fusion.status == "accepted":
                assert hypothesis.size is not None
                accepted_promotions.append(
                    _AcceptedPromotion(
                        candidate=candidate,
                        hypothesis=hypothesis,
                        fusion=fusion,
                        verification_score=result.score,
                        fused_evidence_ids=fused_evidence_ids,
                        sample_ids=sample_ids,
                    )
                )

        verified_fields, selection = _apply_global_selection(
            accepted_promotions,
            findings_by_hypothesis=findings_by_hypothesis,
            evidence=evidence,
        )

        if not entries:
            limitations.append(
                "No executable length/sequence field candidate was available for the semantic slice."
            )

        status = "completed" if entries and not limitations else "partial"
        evidence_producers = sorted({item.source_component for item in evidence})
        llm_metrics = dict(llm_run.metrics)
        llm_metrics["llmUnverifiableHypothesisCount"] = llm_unverifiable
        return SemanticAnalysis(
            producer=self.producer,
            status=status,
            findings=tuple(findings),
            evidence=tuple(evidence),
            verified_fields=verified_fields,
            metrics={
                "verificationExecuted": bool(verification_decision_counts["accepted"] + verification_decision_counts["rejected"] + verification_decision_counts["uncertain"]),
                "fusionExecuted": bool(fusion_results),
                "fusionPolicy": POLICY_VERSION,
                "fusionAcceptanceSupportThreshold": 0.75,
                "fusionMaxConflictForAccept": 0.25,
                "globalSelectionExecuted": bool(fusion_results),
                "globalSelectionPolicy": GLOBAL_SELECTION_POLICY_VERSION,
                "semanticSlice": "length-sequence",
                "hypothesisCount": len(entries),
                "alignmentEvidenceCount": len(alignment_evidence),
                "candidateEvidenceCount": candidate_entry_count,
                "verificationEvidenceCount": sum(verification_decision_counts.values()),
                "evidenceProducerCount": len(evidence_producers),
                "evidenceProducers": evidence_producers,
                "fusionEvidenceProducerCount": len(fusion_evidence_producers),
                "fusionEvidenceProducers": sorted(fusion_evidence_producers),
                "fusionAudit": [_fusion_metric(item) for item in fusion_results],
                "fusionAcceptedHypothesisCount": len(accepted_promotions),
                "globalConflictGroupCount": selection.conflict_group_count,
                "globalConflictHypothesisCount": selection.conflict_hypothesis_count,
                "globalAbstainedHypothesisCount": selection.abstained_hypothesis_count,
                "globalSelectionAudit": [
                    _selection_metric(item, accepted_promotions)
                    for item in selection.decisions
                ],
                "acceptedFieldCount": len(verified_fields),
                "globallySelectedFieldCount": len(verified_fields),
                "verificationDecisionCounts": verification_decision_counts,
                "decisionCounts": decision_counts,
                "inputId": input_metadata.input_id,
                **llm_metrics,
            },
            limitations=tuple(limitations),
        )

    def _run_llm(
        self,
        *,
        input_id: str,
        candidate_contexts: list[_SemanticEntry],
    ) -> _LLMRun:
        metrics: dict[str, Any] = {
            "llmRequested": True,
            "llmExecuted": False,
            "llmContextPolicy": "structural-summary-v1",
            "llmRequestCount": 0,
            "llmSuccessfulRequestCount": 0,
            "llmHypothesisCount": 0,
            "llmOutOfScopeHypothesisCount": 0,
            "llmProviderFailureCount": 0,
            "llmProviderMetadata": [],
        }
        if not candidate_contexts:
            return _LLMRun(
                entries=[],
                evidence=[],
                hypothesis_ids=set(),
                limitations=["LLM reasoning was requested, but no executable candidate region was available."],
                metrics=metrics,
            )

        try:
            provider = self._llm_provider or self._llm_provider_factory()
        except Exception as exc:  # external/config boundary: fail closed without leaking values
            metrics["llmProviderFailureCount"] = 1
            return _LLMRun(
                entries=[],
                evidence=[],
                hypothesis_ids=set(),
                limitations=[
                    f"LLM provider could not be initialized ({type(exc).__name__}); no LLM hypothesis was accepted."
                ],
                metrics=metrics,
            )

        if not isinstance(provider, LLMHypothesisProvider):
            metrics["llmProviderFailureCount"] = 1
            return _LLMRun(
                entries=[],
                evidence=[],
                hypothesis_ids=set(),
                limitations=["Configured LLM provider does not satisfy LLMHypothesisProvider; no LLM hypothesis was accepted."],
                metrics=metrics,
            )

        generated_entries: list[_SemanticEntry] = []
        generated_evidence: list[Evidence] = []
        generated_ids: set[str] = set()
        limitations: list[str] = []
        deterministic_ids = {entry[1].hypothesis_id for entry in candidate_contexts}
        provider_records: list[dict[str, Any]] = []

        for candidate, _baseline, samples, sample_ids, independence_group in candidate_contexts:
            candidate_evidence_id = f"candidate:{candidate.candidate_id}"
            request = LLMHypothesisRequest(
                request_id=f"semantic:{input_id}:{candidate.candidate_id}",
                input_id=input_id,
                allowed_evidence_ids=(candidate_evidence_id,),
                context=_structural_context(candidate, samples, sample_ids),
            )
            metrics["llmRequestCount"] += 1
            try:
                result = provider.propose(request)
            except Exception as exc:  # provider boundary: explicit failure, sanitized detail
                metrics["llmProviderFailureCount"] += 1
                limitations.append(
                    f"LLM provider request failed for candidate {candidate.candidate_id!r} ({type(exc).__name__}); deterministic analysis continued."
                )
                continue

            metrics["llmExecuted"] = True
            metrics["llmSuccessfulRequestCount"] += 1
            provider_records.append(
                {
                    "provider": result.provider,
                    "mode": result.mode,
                    **_safe_provider_metadata(result.metadata),
                }
            )
            if result.limitations:
                limitations.append(
                    f"LLM provider reported {len(result.limitations)} limitation(s) for candidate {candidate.candidate_id!r}."
                )

            for hypothesis in result.hypotheses:
                if not _hypothesis_is_scoped(hypothesis, candidate):
                    metrics["llmOutOfScopeHypothesisCount"] += 1
                    limitations.append(
                        f"LLM hypothesis {hypothesis.hypothesis_id!r} was outside the requested executable field region/type and was ignored."
                    )
                    continue
                if hypothesis.hypothesis_id in deterministic_ids or hypothesis.hypothesis_id in generated_ids:
                    metrics["llmOutOfScopeHypothesisCount"] += 1
                    limitations.append(
                        f"LLM hypothesis {hypothesis.hypothesis_id!r} reused an existing hypothesis id and was ignored."
                    )
                    continue

                llm_evidence_id = f"llm-evidence:{hypothesis.hypothesis_id}"
                generated_evidence.append(
                    Evidence(
                        evidence_id=llm_evidence_id,
                        source_component="track-c-llm-provider",
                        method=result.provider,
                        feature_family=hypothesis.semantic_type,
                        score=float(hypothesis.model_confidence),
                        observation={
                            "hypothesisId": hypothesis.hypothesis_id,
                            "provider": result.provider,
                            "mode": result.mode,
                            "offset": hypothesis.offset,
                            "size": hypothesis.size,
                            "semanticType": hypothesis.semantic_type,
                            "interpretation": hypothesis.interpretation,
                            "parameters": _json_copy(hypothesis.parameters),
                            "modelConfidence": float(hypothesis.model_confidence),
                            "stance": "support",
                        },
                        parent_evidence_ids=(candidate_evidence_id,),
                        independence_group=independence_group,
                        sample_ids=sample_ids,
                    )
                )
                hypothesis.supporting_evidence_ids = tuple(
                    sorted({candidate_evidence_id, llm_evidence_id})
                )
                llm_candidate = replace(
                    candidate,
                    candidate_id=f"llm-derived:{candidate.candidate_id}:{hypothesis.hypothesis_id}",
                    evidence_ids=tuple(
                        sorted({*candidate.evidence_ids, candidate_evidence_id, llm_evidence_id})
                    ),
                    attributes={
                        **dict(candidate.attributes),
                        "semanticOrigin": "llm-provider",
                        "sourceCandidateId": candidate.candidate_id,
                    },
                )
                generated_entries.append(
                    (
                        llm_candidate,
                        hypothesis,
                        samples,
                        sample_ids,
                        independence_group,
                    )
                )
                generated_ids.add(hypothesis.hypothesis_id)

        metrics["llmHypothesisCount"] = len(generated_entries)
        metrics["llmProviderMetadata"] = _deduplicate_metadata(provider_records)
        return _LLMRun(
            entries=generated_entries,
            evidence=generated_evidence,
            hypothesis_ids=generated_ids,
            limitations=limitations,
            metrics=metrics,
        )


def _structural_context(
    candidate: FieldCandidate,
    samples: tuple[bytes, ...],
    sample_ids: tuple[str, ...],
) -> dict[str, Any]:
    included = min(len(samples), _MAX_CONTEXT_SAMPLES)
    summaries: list[dict[str, Any]] = []
    for index in range(included):
        payload = samples[index]
        sample_id = sample_ids[index] if index < len(sample_ids) else f"sample-{index}"
        start = candidate.offset
        end = start + (candidate.size or 0)
        field = payload[start:end] if candidate.size is not None and end <= len(payload) else b""
        displayed = field[:_MAX_CONTEXT_FIELD_BYTES]
        summary: dict[str, Any] = {
            "sampleId": sample_id,
            "messageLength": len(payload),
            "fieldAvailable": bool(field) and len(field) == (candidate.size or 0),
            "fieldByteCount": len(field),
            "fieldBytesHex": displayed.hex(),
            "fieldBytesTruncated": len(field) > len(displayed),
        }
        if field and len(field) <= _MAX_CONTEXT_FIELD_BYTES:
            summary["fieldUnsignedBigEndian"] = int.from_bytes(field, "big")
            summary["fieldUnsignedLittleEndian"] = int.from_bytes(field, "little")
        summaries.append(summary)

    return {
        "schemaVersion": "llm-structural-context-v1",
        "privacy": {
            "wholePayloadIncluded": False,
            "sampleLimit": _MAX_CONTEXT_SAMPLES,
            "fieldByteLimit": _MAX_CONTEXT_FIELD_BYTES,
        },
        "candidate": {
            "candidateId": candidate.candidate_id,
            "familyId": candidate.family_id,
            "offset": candidate.offset,
            "size": candidate.size,
            "candidateTypes": list(candidate.candidate_types),
            "declaredEndian": candidate.endian,
            "matchHint": candidate.attributes.get("match"),
        },
        "constraints": {
            "requiredOffset": candidate.offset,
            "requiredSize": candidate.size,
            "supportedSemanticTypes": sorted(_SUPPORTED_LLM_TYPES),
            "lengthParameters": {
                "endian": ["big", "little"],
                "target": ["full_message", "payload"],
            },
            "sequenceParameters": {
                "endian": ["big", "little"],
                "mode": ["increment", "strict", "wraparound"],
            },
        },
        "sampleCountTotal": len(samples),
        "sampleCountIncluded": included,
        "samples": summaries,
    }


def _hypothesis_is_scoped(hypothesis: ProtocolHypothesis, candidate: FieldCandidate) -> bool:
    if not isinstance(hypothesis, ProtocolHypothesis):
        return False
    if not hypothesis.hypothesis_id or hypothesis.semantic_type not in _SUPPORTED_LLM_TYPES:
        return False
    if hypothesis.offset != candidate.offset or hypothesis.size != candidate.size:
        return False
    if not isinstance(hypothesis.model_confidence, (int, float)) or isinstance(
        hypothesis.model_confidence, bool
    ):
        return False
    confidence = float(hypothesis.model_confidence)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return False
    try:
        _json_copy(hypothesis.parameters)
    except (TypeError, ValueError):
        return False
    return True


def _json_copy(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


def _safe_provider_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in _SAFE_PROVIDER_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, (str, bool)) or value is None:
            if value is not None:
                safe[key] = value
    usage = metadata.get("usage")
    if isinstance(usage, Mapping):
        numeric: dict[str, int | float] = {}
        for key, value in usage.items():
            if not isinstance(key, str) or isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                continue
            parsed = float(value)
            if math.isfinite(parsed) and parsed >= 0:
                numeric[key] = value
        if numeric:
            safe["usage"] = numeric
    return safe


def _deduplicate_metadata(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if encoded in seen:
            continue
        seen.add(encoded)
        deduplicated.append(record)
    return deduplicated
