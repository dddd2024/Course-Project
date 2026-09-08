"""Evidence registry and provenance graph for EvidenceGraph-PRE."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import asdict
from types import MappingProxyType

from course_project.models import Evidence


class EvidenceGraphError(ValueError):
    """Raised when evidence would make the provenance graph invalid."""


class EvidenceGraph:
    """Register project-native evidence and preserve its dependency graph.

    Parents must already be registered or be in the same register_many call.
    Batch registration is atomic, so invalid input cannot partially update
    the graph.
    """

    def __init__(self) -> None:
        self._evidence: dict[str, Evidence] = {}
        self._children: dict[str, set[str]] = defaultdict(set)

    @property
    def evidences(self) -> Mapping[str, Evidence]:
        """Return a read-only view of registered evidence by ID."""

        return MappingProxyType(self._evidence)

    def __len__(self) -> int:
        return len(self._evidence)

    def __contains__(self, evidence_id: object) -> bool:
        return evidence_id in self._evidence

    def register_evidence(self, evidence: Evidence) -> Evidence:
        """Register one evidence record and return it."""

        return self.register_many((evidence,))[0]

    def register_many(self, evidence_records: Iterable[Evidence]) -> tuple[Evidence, ...]:
        """Atomically register evidence records after validating the graph."""

        records = tuple(evidence_records)
        batch: dict[str, Evidence] = {}
        for evidence in records:
            if not isinstance(evidence, Evidence):
                raise TypeError("evidence records must use course_project.models.Evidence")
            if not evidence.evidence_id:
                raise EvidenceGraphError("evidence_id must not be empty")
            if evidence.evidence_id in self._evidence or evidence.evidence_id in batch:
                raise EvidenceGraphError(f"duplicate evidence_id: {evidence.evidence_id}")
            if not 0.0 <= evidence.score <= 1.0:
                raise EvidenceGraphError(
                    f"evidence score must be in [0, 1]: {evidence.evidence_id}"
                )
            batch[evidence.evidence_id] = deepcopy(evidence)

        available_ids = self._evidence.keys() | batch.keys()
        for evidence in records:
            for parent_id in evidence.parent_evidence_ids:
                if parent_id not in available_ids:
                    raise EvidenceGraphError(
                        f"unknown parent evidence_id {parent_id!r} "
                        f"for {evidence.evidence_id!r}"
                    )

        candidate = {**self._evidence, **batch}
        self._assert_acyclic(candidate)

        self._evidence.update(batch)
        for evidence in records:
            self._children.setdefault(evidence.evidence_id, set())
            for parent_id in evidence.parent_evidence_ids:
                self._children[parent_id].add(evidence.evidence_id)
        return tuple(self._evidence[evidence.evidence_id] for evidence in records)

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        """Return one evidence record, or None when it is unknown."""

        return self._evidence.get(evidence_id)

    def trace_provenance(self, evidence_id: str) -> tuple[Evidence, ...]:
        """Return all ancestors followed by the target in topological order."""

        self._require_evidence(evidence_id)
        ordered_ids: list[str] = []
        visited: set[str] = set()

        def visit(current_id: str) -> None:
            if current_id in visited:
                return
            for parent_id in sorted(self._evidence[current_id].parent_evidence_ids):
                visit(parent_id)
            visited.add(current_id)
            ordered_ids.append(current_id)

        visit(evidence_id)
        return tuple(self._evidence[current_id] for current_id in ordered_ids)

    def root_evidence_ids(self, evidence_id: str) -> tuple[str, ...]:
        """Return the direct-observation roots supporting an evidence record."""

        roots = tuple(
            evidence.evidence_id
            for evidence in self.trace_provenance(evidence_id)
            if not evidence.parent_evidence_ids
        )
        return tuple(sorted(roots))

    def descendants(self, evidence_id: str) -> tuple[Evidence, ...]:
        """Return all transitively derived evidence in deterministic order."""

        self._require_evidence(evidence_id)
        pending = sorted(self._children[evidence_id])
        visited: set[str] = set()
        while pending:
            current_id = pending.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            pending.extend(sorted(self._children[current_id] - visited))
        return tuple(self._evidence[current_id] for current_id in sorted(visited))

    def independence_groups(
        self, evidence_ids: Iterable[str]
    ) -> dict[str, tuple[str, ...]]:
        """Group requested evidence by independent root observations.

        Derived evidence inherits its roots' groups. Its own label therefore
        cannot turn a restatement of upstream evidence into a new independent
        vote. Evidence without an explicit group gets a stable per-root group.
        """

        grouped: dict[str, set[str]] = defaultdict(set)
        for evidence_id in evidence_ids:
            self._require_evidence(evidence_id)
            for root_id in self.root_evidence_ids(evidence_id):
                root = self._evidence[root_id]
                group_id = root.independence_group or f"evidence:{root_id}"
                grouped[group_id].add(evidence_id)
        return {
            group_id: tuple(sorted(member_ids))
            for group_id, member_ids in sorted(grouped.items())
        }

    def export(self) -> dict[str, object]:
        """Export deterministic JSON-compatible nodes and dependency edges."""

        evidence = [asdict(self._evidence[evidence_id]) for evidence_id in sorted(self._evidence)]
        edges = [
            {"parentEvidenceId": parent_id, "childEvidenceId": child_id}
            for parent_id in sorted(self._children)
            for child_id in sorted(self._children[parent_id])
        ]
        return {"evidence": evidence, "edges": edges}

    def _require_evidence(self, evidence_id: str) -> Evidence:
        evidence = self._evidence.get(evidence_id)
        if evidence is None:
            raise KeyError(f"unknown evidence_id: {evidence_id}")
        return evidence

    @staticmethod
    def _assert_acyclic(evidence: Mapping[str, Evidence]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(evidence_id: str) -> None:
            if evidence_id in visiting:
                raise EvidenceGraphError(f"evidence dependency cycle includes {evidence_id!r}")
            if evidence_id in visited:
                return
            visiting.add(evidence_id)
            for parent_id in evidence[evidence_id].parent_evidence_ids:
                visit(parent_id)
            visiting.remove(evidence_id)
            visited.add(evidence_id)

        for evidence_id in sorted(evidence):
            visit(evidence_id)
