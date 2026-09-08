"""Competing protocol-hypothesis management for EvidenceGraph-PRE."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import replace

from course_project.models import (
    DecisionStatus,
    ProtocolHypothesis,
    VerificationResult,
)


class HypothesisManagerError(ValueError):
    """Raised when a hypothesis operation would violate manager invariants."""


class HypothesisManager:
    """Store competing hypotheses without treating model confidence as proof."""

    def __init__(self) -> None:
        self._hypotheses: dict[str, ProtocolHypothesis] = {}
        self._statuses: dict[str, DecisionStatus] = {}
        self._verification_results: dict[str, VerificationResult] = {}

    def __len__(self) -> int:
        return len(self._hypotheses)

    def register(self, hypothesis: ProtocolHypothesis) -> ProtocolHypothesis:
        """Register one hypothesis with an initial uncertain decision."""

        if not isinstance(hypothesis, ProtocolHypothesis):
            raise TypeError(
                "hypotheses must use course_project.models.ProtocolHypothesis"
            )
        if not hypothesis.hypothesis_id:
            raise HypothesisManagerError("hypothesis_id must not be empty")
        if hypothesis.hypothesis_id in self._hypotheses:
            raise HypothesisManagerError(
                f"duplicate hypothesis_id: {hypothesis.hypothesis_id}"
            )
        if hypothesis.offset < 0:
            raise HypothesisManagerError("hypothesis offset must be non-negative")
        if hypothesis.size is not None and hypothesis.size <= 0:
            raise HypothesisManagerError("hypothesis size must be positive or None")
        if not 0.0 <= hypothesis.model_confidence <= 1.0:
            raise HypothesisManagerError("model_confidence must be in [0, 1]")
        if hypothesis.hypothesis_id in hypothesis.competing_hypothesis_ids:
            raise HypothesisManagerError("a hypothesis cannot compete with itself")

        stored = deepcopy(hypothesis)
        stored.competing_hypothesis_ids = ()
        self._hypotheses[stored.hypothesis_id] = stored
        self._statuses[stored.hypothesis_id] = "uncertain"
        return deepcopy(stored)

    def register_competing(
        self, hypotheses: Iterable[ProtocolHypothesis]
    ) -> tuple[ProtocolHypothesis, ...]:
        """Atomically register alternatives for one byte region.

        Every member competes with every other member. All hypotheses remain
        uncertain until a deterministic verification result is recorded.
        """

        candidates = tuple(hypotheses)
        if len(candidates) < 2:
            raise HypothesisManagerError(
                "a competing set requires at least two hypotheses"
            )
        region = (candidates[0].offset, candidates[0].size)
        if any((candidate.offset, candidate.size) != region for candidate in candidates):
            raise HypothesisManagerError(
                "competing hypotheses must describe the same byte region"
            )

        before_ids = set(self._hypotheses)
        try:
            registered = tuple(self.register(candidate) for candidate in candidates)
            for hypothesis in registered:
                competitor_ids = tuple(
                    candidate.hypothesis_id
                    for candidate in registered
                    if candidate.hypothesis_id != hypothesis.hypothesis_id
                )
                self._hypotheses[hypothesis.hypothesis_id] = replace(
                    self._hypotheses[hypothesis.hypothesis_id],
                    competing_hypothesis_ids=competitor_ids,
                )
        except (HypothesisManagerError, TypeError):
            added_ids = set(self._hypotheses) - before_ids
            for hypothesis_id in added_ids:
                self._hypotheses.pop(hypothesis_id, None)
                self._statuses.pop(hypothesis_id, None)
            raise

        return tuple(self.get(candidate.hypothesis_id) for candidate in candidates)

    def get(self, hypothesis_id: str) -> ProtocolHypothesis:
        """Return a defensive copy of a registered hypothesis."""

        hypothesis = self._hypotheses.get(hypothesis_id)
        if hypothesis is None:
            raise KeyError(f"unknown hypothesis_id: {hypothesis_id}")
        return deepcopy(hypothesis)

    def status(self, hypothesis_id: str) -> DecisionStatus:
        """Return the current three-way decision for a hypothesis."""

        if hypothesis_id not in self._statuses:
            raise KeyError(f"unknown hypothesis_id: {hypothesis_id}")
        return self._statuses[hypothesis_id]

    def competing_with(self, hypothesis_id: str) -> tuple[ProtocolHypothesis, ...]:
        """Return competing interpretations in deterministic order."""

        hypothesis = self.get(hypothesis_id)
        return tuple(
            self.get(competitor_id)
            for competitor_id in sorted(hypothesis.competing_hypothesis_ids)
        )

    def for_region(
        self, offset: int, size: int | None
    ) -> tuple[ProtocolHypothesis, ...]:
        """Return all hypotheses for an exact byte region."""

        return tuple(
            deepcopy(hypothesis)
            for hypothesis in sorted(
                self._hypotheses.values(), key=lambda item: item.hypothesis_id
            )
            if hypothesis.offset == offset and hypothesis.size == size
        )

    def record_verification(
        self, result: VerificationResult
    ) -> VerificationResult:
        """Record executable verification and update the hypothesis decision."""

        if not isinstance(result, VerificationResult):
            raise TypeError(
                "results must use course_project.models.VerificationResult"
            )
        self.get(result.hypothesis_id)
        if result.sample_count < 0 or result.support_count < 0:
            raise HypothesisManagerError("verification counts must be non-negative")
        if result.support_count > result.sample_count:
            raise HypothesisManagerError(
                "support_count cannot exceed sample_count"
            )
        if not 0.0 <= result.score <= 1.0:
            raise HypothesisManagerError("verification score must be in [0, 1]")
        if result.status == "accepted" and result.sample_count == 0:
            raise HypothesisManagerError(
                "a hypothesis cannot be accepted without eligible samples"
            )

        stored = deepcopy(result)
        self._verification_results[result.hypothesis_id] = stored
        self._statuses[result.hypothesis_id] = result.status
        return deepcopy(stored)

    def verification_result(
        self, hypothesis_id: str
    ) -> VerificationResult | None:
        """Return the latest verification result, if one exists."""

        self.get(hypothesis_id)
        result = self._verification_results.get(hypothesis_id)
        return deepcopy(result) if result is not None else None

    def accepted_hypotheses(self) -> tuple[ProtocolHypothesis, ...]:
        """Return only hypotheses accepted by executable verification."""

        return tuple(
            self.get(hypothesis_id)
            for hypothesis_id in sorted(self._hypotheses)
            if self._statuses[hypothesis_id] == "accepted"
        )

    def decision_snapshot(self) -> dict[str, dict[str, object]]:
        """Return a deterministic, JSON-compatible decision summary."""

        return {
            hypothesis_id: {
                "status": self._statuses[hypothesis_id],
                "verificationScore": (
                    self._verification_results[hypothesis_id].score
                    if hypothesis_id in self._verification_results
                    else None
                ),
                "competingHypothesisIds": list(
                    self._hypotheses[hypothesis_id].competing_hypothesis_ids
                ),
            }
            for hypothesis_id in sorted(self._hypotheses)
        }
