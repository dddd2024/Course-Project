"""Project-native evidence producers for the Track C semantic pipeline."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from course_project.models import (
    Evidence,
    ExecutableCheck,
    FieldCandidate,
    ProtocolHypothesis,
)


class EvidenceProductionError(ValueError):
    """Raised when an input cannot safely become provenance-tagged evidence."""


def evidence_from_field_candidate(
    candidate: FieldCandidate,
    *,
    sample_ids: Iterable[str] = (),
) -> Evidence:
    """Convert one deterministic/PRE field candidate into evidence."""

    if not isinstance(candidate, FieldCandidate):
        raise TypeError("candidate must use course_project.models.FieldCandidate")
    if not candidate.candidate_id:
        raise EvidenceProductionError("candidate_id must not be empty")
    _field(candidate.offset, candidate.size)
    score = _score(candidate.score, "candidate score")
    parents = _identifiers(candidate.evidence_ids, "candidate evidence_ids")
    samples = _identifiers(sample_ids, "sample_ids")
    backend = candidate.attributes.get("backend", "field_candidate")
    if not isinstance(backend, str) or not backend:
        raise EvidenceProductionError("candidate backend must be a non-empty string")
    if any(not isinstance(item, str) or not item for item in candidate.candidate_types):
        raise EvidenceProductionError(
            "candidate_types must contain non-empty strings"
        )

    observation = {
        "candidateId": candidate.candidate_id,
        "familyId": candidate.family_id,
        "offset": candidate.offset,
        "size": candidate.size,
        "candidateTypes": list(candidate.candidate_types),
        "endian": candidate.endian,
        "attributes": deepcopy(candidate.attributes),
    }
    _json_object(observation, "candidate observation")
    feature_family = (
        candidate.candidate_types[0]
        if len(candidate.candidate_types) == 1
        else "field_structure"
    )
    independence_group = None
    if not parents:
        scope = candidate.family_id or candidate.candidate_id
        independence_group = f"field-candidate:{backend}:{scope}"
    return _make_evidence(
        prefix="field",
        source_component="inference",
        method=backend,
        feature_family=feature_family,
        score=score,
        observation=observation,
        parent_evidence_ids=parents,
        independence_group=independence_group,
        sample_ids=samples,
    )


def evidence_from_llm_hypothesis(
    hypothesis: ProtocolHypothesis,
    *,
    provider: str,
    model: str | None = None,
) -> Evidence:
    """Record an LLM interpretation as evidence derived from trusted support."""

    if not isinstance(hypothesis, ProtocolHypothesis):
        raise TypeError(
            "hypothesis must use course_project.models.ProtocolHypothesis"
        )
    if not hypothesis.hypothesis_id:
        raise EvidenceProductionError("hypothesis_id must not be empty")
    _field(hypothesis.offset, hypothesis.size)
    score = _score(hypothesis.model_confidence, "model_confidence")
    parents = _required_parents(
        hypothesis.supporting_evidence_ids, "hypothesis supporting_evidence_ids"
    )
    if not isinstance(provider, str) or not provider:
        raise EvidenceProductionError("provider must be a non-empty string")
    if model is not None and (not isinstance(model, str) or not model):
        raise EvidenceProductionError("model must be a non-empty string or None")
    if not hypothesis.semantic_type or not hypothesis.interpretation:
        raise EvidenceProductionError(
            "hypothesis semantic_type and interpretation must not be empty"
        )

    observation = {
        "hypothesisId": hypothesis.hypothesis_id,
        "offset": hypothesis.offset,
        "size": hypothesis.size,
        "semanticType": hypothesis.semantic_type,
        "interpretation": hypothesis.interpretation,
        "parameters": deepcopy(hypothesis.parameters),
        "competingHypothesisIds": list(hypothesis.competing_hypothesis_ids),
        "provider": provider,
        "model": model,
    }
    _json_object(observation, "LLM observation")
    return _make_evidence(
        prefix="llm",
        source_component="llm",
        method=provider if model is None else f"{provider}:{model}",
        feature_family="semantic_hypothesis",
        score=score,
        observation=observation,
        parent_evidence_ids=parents,
        independence_group=None,
        sample_ids=(),
    )


def evidence_from_executable_check(check: ExecutableCheck) -> Evidence:
    """Record one deterministic check as derived verification evidence."""

    if not isinstance(check, ExecutableCheck):
        raise TypeError("check must use course_project.models.ExecutableCheck")
    if not check.check_id or not check.hypothesis_id or not check.check_type:
        raise EvidenceProductionError(
            "check_id, hypothesis_id, and check_type must not be empty"
        )
    score = _score(check.score, "verification score")
    parents = _required_parents(check.evidence_ids, "check evidence_ids")
    sample_count = _count(check.sample_count, "sample_count")
    support_count = _count(check.support_count, "support_count")
    violation_count = _count(check.violation_count, "violation_count")
    if support_count + violation_count != sample_count:
        raise EvidenceProductionError(
            "support_count and violation_count must sum to sample_count"
        )
    if check.result not in {"accepted", "rejected", "uncertain"}:
        raise EvidenceProductionError(f"invalid verification result: {check.result!r}")

    observation = {
        "checkId": check.check_id,
        "hypothesisId": check.hypothesis_id,
        "checkType": check.check_type,
        "sampleCount": sample_count,
        "supportCount": support_count,
        "violationCount": violation_count,
        "result": check.result,
    }
    return _make_evidence(
        prefix="verification",
        source_component="verification",
        method=check.check_type,
        feature_family=check.check_type,
        score=score,
        observation=observation,
        parent_evidence_ids=parents,
        independence_group=None,
        sample_ids=(),
    )


def _make_evidence(
    *,
    prefix: str,
    source_component: str,
    method: str,
    feature_family: str,
    score: float,
    observation: dict[str, Any],
    parent_evidence_ids: tuple[str, ...],
    independence_group: str | None,
    sample_ids: tuple[str, ...],
) -> Evidence:
    identity: Mapping[str, object] = {
        "source_component": source_component,
        "method": method,
        "feature_family": feature_family,
        "score": score,
        "observation": observation,
        "parent_evidence_ids": parent_evidence_ids,
        "sample_ids": sample_ids,
    }
    serialized = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]
    return Evidence(
        evidence_id=f"evidence-{prefix}-{digest}",
        source_component=source_component,
        method=method,
        feature_family=feature_family,
        score=score,
        observation=observation,
        parent_evidence_ids=parent_evidence_ids,
        independence_group=independence_group,
        sample_ids=sample_ids,
    )


def _field(offset: int, size: int | None) -> None:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise EvidenceProductionError("field offset must be a non-negative integer")
    if size is not None and (
        isinstance(size, bool) or not isinstance(size, int) or size <= 0
    ):
        raise EvidenceProductionError("field size must be positive or None")


def _score(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise EvidenceProductionError(f"{name} must be a finite number in [0, 1]")
    return float(value)


def _count(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceProductionError(f"{name} must be a non-negative integer")
    return value


def _identifiers(values: Iterable[str], name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not isinstance(value, str) or not value for value in normalized):
        raise EvidenceProductionError(f"{name} must contain non-empty strings")
    if len(set(normalized)) != len(normalized):
        raise EvidenceProductionError(f"{name} must not contain duplicates")
    return normalized


def _required_parents(values: Iterable[str], name: str) -> tuple[str, ...]:
    parents = _identifiers(values, name)
    if not parents:
        raise EvidenceProductionError(f"{name} must retain at least one parent")
    return parents


def _json_object(value: dict[str, Any], name: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EvidenceProductionError(
            f"{name} must contain only finite JSON values"
        ) from exc
