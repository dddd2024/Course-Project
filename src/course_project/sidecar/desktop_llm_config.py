from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from course_project.models import (
    AlignmentResult,
    BehaviorFeatures,
    FieldCandidate,
    InputMetadata,
    MessageCandidate,
    MessageFamily,
    PacketCandidate,
)
from course_project.sidecar.semantic_bridge import SemanticAnalysis
from course_project.sidecar.track_c_llm_semantic_backend import DeterministicTrackCSemanticBackend

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


def desktop_llm_enabled_from_environment() -> bool:
    """Return whether the desktop Sidecar explicitly opted into live LLM use.

    The desktop Rust request remains offline-safe by default. Setting
    ``COURSE_PROJECT_LLM_ENABLED`` is an operator-level opt-in that upgrades the
    effective semantic configuration for the CLI/packaged Sidecar process.
    """

    raw = os.environ.get("COURSE_PROJECT_LLM_ENABLED", "0")
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(
        "COURSE_PROJECT_LLM_ENABLED must be one of 1/0, true/false, yes/no, or on/off"
    )


class DesktopConfiguredTrackCSemanticBackend(DeterministicTrackCSemanticBackend):
    """Track C backend that honors the explicit desktop process-level LLM opt-in."""

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
        large_raw_profile: Mapping[str, Any] | None,
        behavior: BehaviorFeatures | None,
        config: Mapping[str, Any],
    ) -> SemanticAnalysis:
        effective_config = dict(config)
        if desktop_llm_enabled_from_environment():
            effective_config["llmEnabled"] = True
        return super().analyze(
            input_metadata=input_metadata,
            input_path=input_path,
            packets=packets,
            messages=messages,
            families=families,
            alignments=alignments,
            field_candidates=field_candidates,
            large_raw_profile=large_raw_profile,
            behavior=behavior,
            config=effective_config,
        )
