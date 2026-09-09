"""Track C semantic workflow from field candidates to verified fields."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from course_project.evidence.fusion import (
    FusionError,
    FusionPolicy,
    FusionResult,
    provenance_aware_fusion,
)
from course_project.evidence.graph import EvidenceGraph, EvidenceGraphError
from course_project.evidence.producers import (
    EvidenceProductionError,
    evidence_from_executable_check,
    evidence_from_field_candidate,
    evidence_from_llm_hypothesis,
)
from course_project.llm import (
    HypothesisGenerationError,
    HypothesisGenerator,
)
from course_project.models import (
    Evidence,
    ExecutableCheck,
    FieldCandidate,
    ProtocolHypothesis,
    VerificationResult,
    VerifiedField,
)
from course_project.verification import (
    VerificationError,
    verification_result,
    verify_hypothesis,
)

BytesLike = bytes | bytearray | memoryview
FailurePolicy = Literal["degrade", "fail"]


class SemanticWorkflowError(RuntimeError):
    """Raised when fail-fast workflow execution cannot continue."""


@dataclass(frozen=True, slots=True)
class SemanticWorkflowResult:
    evidence: tuple[Evidence, ...]
    hypotheses: tuple[ProtocolHypothesis, ...]
    checks: tuple[ExecutableCheck, ...]
    verification_results: tuple[VerificationResult, ...]
    fusion_results: tuple[FusionResult, ...]
    verified_fields: tuple[VerifiedField, ...]
    limitations: tuple[str, ...]


class SemanticWorkflow:
    """Compose Track C components without depending on sidecar internals."""

    def __init__(
        self,
        generator: HypothesisGenerator | None = None,
        *,
        fusion_policy: FusionPolicy | None = None,
        provider_name: str = "mock",
        model_name: str | None = "deterministic-v1",
    ) -> None:
        if not isinstance(provider_name, str) or not provider_name:
            raise ValueError("provider_name must be a non-empty string")
        if model_name is not None and (
            not isinstance(model_name, str) or not model_name
        ):
            raise ValueError("model_name must be a non-empty string or None")
        self._generator = generator or HypothesisGenerator()
        self._fusion_policy = fusion_policy or FusionPolicy()
        self._provider_name = provider_name
        self._model_name = model_name

    def analyze(
        self,
        field_candidates: Iterable[FieldCandidate],
        messages_by_family: Mapping[str | None, Sequence[BytesLike]],
        *,
        upstream_evidence: Iterable[Evidence] = (),
        conflicting_evidence: Mapping[str, Iterable[str]] | None = None,
        session_ids_by_family: Mapping[str | None, Sequence[str]] | None = None,
        llm_enabled: bool = True,
        verification_enabled: bool = True,
        failure_policy: FailurePolicy = "degrade",
    ) -> SemanticWorkflowResult:
        """Run semantic inference with explicit degradation and abstention."""

        if not isinstance(llm_enabled, bool) or not isinstance(
            verification_enabled, bool
        ):
            raise TypeError("workflow feature flags must be booleans")
        if failure_policy not in {"degrade", "fail"}:
            raise ValueError("failure_policy must be degrade or fail")
        candidates = _candidates(field_candidates)
        graph = EvidenceGraph()
        try:
            graph.register_many(upstream_evidence)
        except (TypeError, EvidenceGraphError) as exc:
            raise SemanticWorkflowError("upstream evidence is invalid") from exc

        hypotheses: list[ProtocolHypothesis] = []
        checks: list[ExecutableCheck] = []
        verifications: list[VerificationResult] = []
        fusions: list[FusionResult] = []
        limitations: list[str] = []
        candidate_hypotheses: dict[str, list[int]] = {}

        for candidate in candidates:
            try:
                candidate_evidence = evidence_from_field_candidate(candidate)
                graph.register_evidence(candidate_evidence)
                if not llm_enabled:
                    limitations.append(
                        f"candidate {candidate.candidate_id}: LLM generation disabled"
                    )
                    continue
                trusted_candidate = replace(
                    candidate, evidence_ids=(candidate_evidence.evidence_id,)
                )
                generated = self._generator.generate(trusted_candidate)
                if not generated:
                    limitations.append(
                        f"candidate {candidate.candidate_id}: provider abstained"
                    )
                    continue
                messages = messages_by_family.get(candidate.family_id)
                if messages is None:
                    raise VerificationError(
                        f"no message corpus for family {candidate.family_id!r}"
                    )
                session_ids = (
                    session_ids_by_family.get(candidate.family_id)
                    if session_ids_by_family is not None
                    else None
                )

                for generated_hypothesis in generated:
                    llm_evidence = evidence_from_llm_hypothesis(
                        generated_hypothesis,
                        provider=self._provider_name,
                        model=self._model_name,
                    )
                    graph.register_evidence(llm_evidence)
                    support_ids = tuple(
                        dict.fromkeys(
                            (
                                *candidate.evidence_ids,
                                candidate_evidence.evidence_id,
                                llm_evidence.evidence_id,
                            )
                        )
                    )
                    enriched = replace(
                        generated_hypothesis,
                        supporting_evidence_ids=support_ids,
                    )
                    hypothesis_index = len(hypotheses)
                    hypotheses.append(enriched)
                    candidate_hypotheses.setdefault(candidate.candidate_id, []).append(
                        hypothesis_index
                    )

                    verification: VerificationResult | None = None
                    check_evidence_id: str | None = None
                    if verification_enabled:
                        executable = verify_hypothesis(
                            enriched, messages, session_ids=session_ids
                        )
                        checks.append(executable)
                        verification = verification_result(executable)
                        verifications.append(verification)
                        check_evidence = evidence_from_executable_check(executable)
                        graph.register_evidence(check_evidence)
                        check_evidence_id = check_evidence.evidence_id

                    conflict_ids = tuple(
                        (conflicting_evidence or {}).get(
                            enriched.hypothesis_id, ()
                        )
                    )
                    fused = provenance_aware_fusion(
                        enriched,
                        graph.evidences.values(),
                        conflicting_evidence_ids=conflict_ids,
                        verification=verification,
                        policy=self._fusion_policy,
                    )
                    if check_evidence_id is not None:
                        fused = replace(
                            fused,
                            supporting_evidence_ids=tuple(
                                dict.fromkeys(
                                    (*fused.supporting_evidence_ids, check_evidence_id)
                                )
                            ),
                        )
                    fusions.append(fused)
            except (
                EvidenceGraphError,
                EvidenceProductionError,
                FusionError,
                HypothesisGenerationError,
                VerificationError,
                TypeError,
                ValueError,
            ) as exc:
                message = f"candidate {candidate.candidate_id}: {exc}"
                if failure_policy == "fail":
                    raise SemanticWorkflowError(message) from exc
                limitations.append(message)

        _abstain_on_competing_acceptances(
            candidates, candidate_hypotheses, hypotheses, fusions, limitations
        )
        verified_fields = _verified_fields(hypotheses, verifications, fusions)
        return SemanticWorkflowResult(
            evidence=tuple(
                graph.evidences[evidence_id]
                for evidence_id in sorted(graph.evidences)
            ),
            hypotheses=tuple(hypotheses),
            checks=tuple(checks),
            verification_results=tuple(verifications),
            fusion_results=tuple(fusions),
            verified_fields=verified_fields,
            limitations=tuple(limitations),
        )


def _candidates(values: Iterable[FieldCandidate]) -> tuple[FieldCandidate, ...]:
    normalized = tuple(values)
    if any(not isinstance(item, FieldCandidate) for item in normalized):
        raise TypeError("field_candidates must contain FieldCandidate records")
    candidate_ids = [item.candidate_id for item in normalized]
    if any(not candidate_id for candidate_id in candidate_ids):
        raise ValueError("candidate_id must not be empty")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("field candidate IDs must be unique")
    return tuple(sorted(normalized, key=lambda item: item.candidate_id))


def _abstain_on_competing_acceptances(
    candidates: tuple[FieldCandidate, ...],
    candidate_hypotheses: Mapping[str, list[int]],
    hypotheses: list[ProtocolHypothesis],
    fusions: list[FusionResult],
    limitations: list[str],
) -> None:
    candidate_by_id = {item.candidate_id: item for item in candidates}
    fusion_by_hypothesis = {
        result.hypothesis_id: index for index, result in enumerate(fusions)
    }
    for candidate_id, hypothesis_indexes in candidate_hypotheses.items():
        accepted_ids = [
            hypotheses[index].hypothesis_id
            for index in hypothesis_indexes
            if (
                fusion_index := fusion_by_hypothesis.get(
                    hypotheses[index].hypothesis_id
                )
            )
            is not None
            and fusions[fusion_index].status == "accepted"
        ]
        if len(accepted_ids) <= 1:
            continue
        for hypothesis_id in accepted_ids:
            fusion_index = fusion_by_hypothesis[hypothesis_id]
            fusions[fusion_index] = replace(
                fusions[fusion_index], status="uncertain"
            )
        candidate = candidate_by_id[candidate_id]
        limitations.append(
            "candidate "
            f"{candidate_id}: {len(accepted_ids)} competing interpretations passed "
            f"for region ({candidate.offset}, {candidate.size}); abstained"
        )


def _verified_fields(
    hypotheses: Sequence[ProtocolHypothesis],
    verifications: Sequence[VerificationResult],
    fusions: Sequence[FusionResult],
) -> tuple[VerifiedField, ...]:
    verification_by_id = {item.hypothesis_id: item for item in verifications}
    fusion_by_id = {item.hypothesis_id: item for item in fusions}
    verified = []
    for hypothesis in hypotheses:
        verification = verification_by_id.get(hypothesis.hypothesis_id)
        fusion = fusion_by_id.get(hypothesis.hypothesis_id)
        if (
            verification is None
            or verification.status != "accepted"
            or fusion is None
            or fusion.status != "accepted"
        ):
            continue
        verified.append(
            VerifiedField(
                field_id=f"verified-{hypothesis.hypothesis_id}",
                offset=hypothesis.offset,
                size=hypothesis.size,
                semantic_type=hypothesis.semantic_type,
                interpretation=hypothesis.interpretation,
                verification_score=verification.score,
                evidence_ids=fusion.supporting_evidence_ids,
            )
        )
    return tuple(sorted(verified, key=lambda item: (item.offset, item.field_id)))
