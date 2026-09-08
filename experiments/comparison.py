"""Canonical comparison and ablation execution for Track C experiments."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from experiments.runner import (
    ExperimentManifest,
    GroundTruth,
    RunObservation,
    evaluate_experiment,
)

FailurePolicy = Literal["record", "fail"]
FusionMode = Literal["none", "naive", "provenance"]
StructureSource = Literal["heuristic", "adapter"]


class ComparisonExecutionError(RuntimeError):
    """Raised when configured comparison execution cannot continue."""


@dataclass(frozen=True, slots=True)
class ExperimentVariant:
    name: str
    structure_source: StructureSource
    llm_enabled: bool
    verification_enabled: bool
    alignment_enabled: bool
    fusion_mode: FusionMode


CANONICAL_VARIANTS = (
    ExperimentVariant("heuristic", "heuristic", False, False, False, "none"),
    ExperimentVariant(
        "netzob_binaryinferno", "adapter", False, False, True, "none"
    ),
    ExperimentVariant("llm_only", "heuristic", True, False, False, "none"),
    ExperimentVariant(
        "llm_verification", "heuristic", True, True, False, "none"
    ),
    ExperimentVariant("naive_vote", "adapter", True, True, True, "naive"),
    ExperimentVariant(
        "evidencegraph_pre", "adapter", True, True, True, "provenance"
    ),
    ExperimentVariant(
        "without_verification", "adapter", True, False, True, "provenance"
    ),
    ExperimentVariant(
        "without_provenance", "adapter", True, True, True, "naive"
    ),
    ExperimentVariant(
        "without_llm", "adapter", False, True, True, "provenance"
    ),
    ExperimentVariant(
        "without_alignment", "heuristic", True, True, False, "provenance"
    ),
)


class ComparisonExecutor(Protocol):
    """Project-local execution boundary that intentionally excludes ground truth."""

    def execute(self, variant: ExperimentVariant) -> RunObservation:
        """Run one inference variant without access to evaluation labels."""


@dataclass(frozen=True, slots=True)
class ExecutionFailure:
    variant: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ComparisonSuiteResult:
    runs: tuple[RunObservation, ...]
    failures: tuple[ExecutionFailure, ...]


def execute_variants(
    executor: ComparisonExecutor,
    variants: Iterable[ExperimentVariant] = CANONICAL_VARIANTS,
    *,
    failure_policy: FailurePolicy = "record",
) -> ComparisonSuiteResult:
    """Execute a deterministic variant list and explicitly record failures."""

    if failure_policy not in {"record", "fail"}:
        raise ValueError("failure_policy must be record or fail")
    normalized = _variants(variants)
    runs: list[RunObservation] = []
    failures: list[ExecutionFailure] = []
    run_ids: set[str] = set()
    for variant in normalized:
        try:
            run = executor.execute(variant)
            if not isinstance(run, RunObservation):
                raise TypeError("executor must return RunObservation")
            if run.method != variant.name:
                raise ValueError(
                    f"executor method {run.method!r} does not match {variant.name!r}"
                )
            if run.run_id in run_ids:
                raise ValueError(f"executor returned duplicate run_id: {run.run_id}")
            run_ids.add(run.run_id)
            runs.append(run)
        except Exception as exc:
            failure = ExecutionFailure(
                variant=variant.name,
                error_type=type(exc).__name__,
                message=str(exc),
            )
            if failure_policy == "fail":
                raise ComparisonExecutionError(
                    f"variant {variant.name} failed: {exc}"
                ) from exc
            failures.append(failure)
    return ComparisonSuiteResult(tuple(runs), tuple(failures))


def build_comparison_report(
    manifest: ExperimentManifest,
    ground_truth: GroundTruth,
    executor: ComparisonExecutor,
    variants: Iterable[ExperimentVariant] = CANONICAL_VARIANTS,
    *,
    failure_policy: FailurePolicy = "record",
) -> dict[str, Any]:
    """Execute inference first, then evaluate outputs against isolated truth."""

    execution = execute_variants(
        executor, variants, failure_policy=failure_policy
    )
    if not execution.runs:
        raise ComparisonExecutionError("all experiment variants failed")
    report = evaluate_experiment(manifest, ground_truth, execution.runs)
    report["execution_failures"] = [
        asdict(failure) for failure in execution.failures
    ]
    report["executed_variants"] = [run.method for run in execution.runs]
    return report


def _variants(
    values: Iterable[ExperimentVariant],
) -> tuple[ExperimentVariant, ...]:
    normalized = tuple(values)
    if not normalized:
        raise ValueError("at least one experiment variant is required")
    names: set[str] = set()
    for variant in normalized:
        if not isinstance(variant, ExperimentVariant):
            raise TypeError("variants must contain ExperimentVariant records")
        if not isinstance(variant.name, str) or not variant.name:
            raise ValueError("variant name must not be empty")
        if variant.name in names:
            raise ValueError(f"duplicate experiment variant: {variant.name}")
        if variant.structure_source not in {"heuristic", "adapter"}:
            raise ValueError(
                f"invalid structure_source: {variant.structure_source!r}"
            )
        if variant.fusion_mode not in {"none", "naive", "provenance"}:
            raise ValueError(f"invalid fusion_mode: {variant.fusion_mode!r}")
        if any(
            not isinstance(value, bool)
            for value in (
                variant.llm_enabled,
                variant.verification_enabled,
                variant.alignment_enabled,
            )
        ):
            raise TypeError("variant feature flags must be booleans")
        names.add(variant.name)
    return normalized
