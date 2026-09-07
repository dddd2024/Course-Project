"""Deterministic rule-based flow behavior classification (Track D).

Five explainable V1 behavior classes — QUERY / DOWNLOAD / UPLOAD / HEARTBEAT /
STREAM — scored by fixed rule weights over the feature record, with UNKNOWN
fallback when no rule is confident. This is the V1 rule baseline; a
RandomForest baseline may replace it once labeled data exists
(see ``docs/design-v1.md`` section 5.9 and ``docs/testing-plan.md`` section 4).
"""

from __future__ import annotations

from typing import Any, Literal

from course_project.behavior.features import extract_behavior_features
from course_project.behavior.records import FlowPacket
from course_project.models import BehaviorPrediction

BehaviorLabel = Literal[
    "QUERY", "DOWNLOAD", "UPLOAD", "HEARTBEAT", "STREAM", "UNKNOWN"
]

_CONFIDENCE_FLOOR = 0.5


def predict_behavior(
    packets: list[FlowPacket], *, flow_id: str = "flow-0"
) -> BehaviorPrediction:
    """Extract frozen BehaviorFeatures and apply the deterministic rule classifier."""
    behavior_features = extract_behavior_features(packets, flow_id=flow_id)
    label, confidence = classify(behavior_features.values)
    return BehaviorPrediction(
        flow_id=flow_id,
        label=label,
        confidence=round(confidence, 6),
        features=dict(behavior_features.values),
    )


def classify(features: dict[str, Any]) -> tuple[BehaviorLabel, float]:
    """Score every rule and pick the strongest label.

    When no rule reaches 0.5 the flow is UNKNOWN with confidence ``1 - score``.
    """
    if features["packet_count"] == 0:
        return "UNKNOWN", 1.0
    best_label, scorer = max(_RULES.items(), key=lambda item: item[1](features))
    best_score = scorer(features)
    if best_score < _CONFIDENCE_FLOOR:
        return "UNKNOWN", 1.0 - best_score
    return best_label, best_score


def _heartbeat_score(f: dict[str, Any]) -> float:
    if f["size_mean"] is None or f["size_std"] is None:
        return 0.0
    regularity = 1.0 - min(f["size_std"] / max(f["size_mean"], 1.0), 1.0)
    small = _clamp01(1.0 - (f["size_mean"] - 32.0) / 128.0)
    if f["inter_arrival_mean"] is not None and f["inter_arrival_std"] is not None:
        timing = 1.0 - min(
            f["inter_arrival_std"] / max(f["inter_arrival_mean"], 1e-9), 1.0
        )
    else:
        timing = 0.5
    return 0.35 * regularity + 0.25 * small + 0.15 * timing + 0.25 * _balance(f)


def _download_score(f: dict[str, Any]) -> float:
    up = f["up_bytes"] or 0
    down = f["down_bytes"] or 0
    if down == 0:
        return 0.0
    dominance = min(down / max(up, 1.0), 4.0) / 4.0
    mean_down = down / f["down_count"] if f["down_count"] else 0.0
    large_payload = _clamp01(mean_down / 1024.0)
    activity = _clamp01(f["packet_count"] / 20.0)
    return 0.5 * dominance + 0.25 * large_payload + 0.25 * activity


def _upload_score(f: dict[str, Any]) -> float:
    up = f["up_bytes"] or 0
    down = f["down_bytes"] or 0
    if up == 0:
        return 0.0
    dominance = min(up / max(down, 1.0), 4.0) / 4.0
    mean_up = up / f["up_count"] if f["up_count"] else 0.0
    large_payload = _clamp01(mean_up / 1024.0)
    activity = _clamp01(f["packet_count"] / 20.0)
    return 0.5 * dominance + 0.25 * large_payload + 0.25 * activity


def _query_score(f: dict[str, Any]) -> float:
    if f["size_mean"] is None:
        return 0.0
    request_style = 1.0 - _clamp01(f["size_mean"] / 512.0)
    interactive = _clamp01(f["packet_count"] / 16.0)
    return 0.4 * request_style + 0.3 * interactive + 0.3 * _balance(f)


def _stream_score(f: dict[str, Any]) -> float:
    total = f["total_bytes"] or 0
    volume = _clamp01(total / 65536.0)
    duration = f["duration"]
    if duration is not None and duration > 0:
        duration_score = _clamp01(duration / 30.0)
        rate = _clamp01(total / duration / 8192.0)
    else:
        duration_score = 0.5
        rate = 0.0
    return 0.4 * volume + 0.3 * duration_score + 0.3 * rate


def _balance(f: dict[str, Any]) -> float:
    """1.0 for perfectly symmetric up/down bytes; 0.5 without direction info."""
    up = f["up_bytes"] or 0
    down = f["down_bytes"] or 0
    if up + down <= 0:
        return 0.5
    return 1.0 - min(abs(up - down) / (up + down), 1.0)


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


_RULES = {
    "HEARTBEAT": _heartbeat_score,
    "DOWNLOAD": _download_score,
    "UPLOAD": _upload_score,
    "QUERY": _query_score,
    "STREAM": _stream_score,
}
