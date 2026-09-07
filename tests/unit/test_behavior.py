from __future__ import annotations

import json

import pytest

from course_project.behavior import (
    FlowPacket,
    classify,
    extract_features,
    from_packet_candidates,
    normalize_direction,
    predict_behavior,
)
from course_project.models import PacketCandidate


def test_normalize_direction_aliases() -> None:
    assert normalize_direction("up") == "up"
    assert normalize_direction("c2s") == "up"
    assert normalize_direction("S2C") == "down"
    assert normalize_direction("server") == "down"
    assert normalize_direction("sideways") is None
    assert normalize_direction(None) is None


def test_flow_packet_rejects_negative_size() -> None:
    with pytest.raises(ValueError):
        FlowPacket(size=-1)


def test_from_packet_candidates() -> None:
    packets = [
        PacketCandidate(0, 100, 0.9, direction="c2s", timestamp=1.0),
        PacketCandidate(100, 240, 0.9, direction="s2c", timestamp=1.5),
    ]
    assert from_packet_candidates(packets) == [
        FlowPacket(size=100, direction="c2s", timestamp=1.0),
        FlowPacket(size=140, direction="s2c", timestamp=1.5),
    ]


def test_extract_features_directions_and_bursts() -> None:
    packets = [
        FlowPacket(100, "up", 0.0),
        FlowPacket(80, "up", 1.0),
        FlowPacket(1000, "down", 2.0),
        FlowPacket(1200, "down", 3.0),
        FlowPacket(900, "down", 4.0),
        FlowPacket(60, "up", 5.0),
    ]
    features = extract_features(packets, flow_id="flow-1")
    assert features["flow_id"] == "flow-1"
    assert features["packet_count"] == 6
    assert features["up_count"] == 3
    assert features["down_count"] == 3
    assert features["up_bytes"] == 240
    assert features["down_bytes"] == 3100
    assert features["up_down_ratio"] == pytest.approx(240 / 3100)
    assert features["direction_switches"] == 2
    assert features["burst_lengths"] == [2, 3, 1]
    assert features["burst_sizes"] == [180, 3100, 60]
    assert features["sizes"] == [100, 80, 1000, 1200, 900, 60]
    assert features["directions"] == ["up", "up", "down", "down", "down", "up"]
    assert features["inter_arrival_mean"] == pytest.approx(1.0)
    assert features["duration"] == pytest.approx(5.0)
    assert features["size_min"] == 60
    assert features["size_max"] == 1200


def test_extract_features_none_direction_breaks_bursts() -> None:
    packets = [
        FlowPacket(10, "up"),
        FlowPacket(20, None),
        FlowPacket(30, "up"),
    ]
    features = extract_features(packets)
    assert features["up_count"] == 2
    assert features["burst_lengths"] == [1, 1]


def test_extract_features_empty_flow() -> None:
    features = extract_features([], flow_id="f")
    assert features["packet_count"] == 0
    assert features["total_bytes"] == 0
    assert features["size_mean"] is None
    assert features["burst_count"] == 0
    assert features["duration"] is None


def test_classify_heartbeat() -> None:
    packets = [FlowPacket(32, "up" if i % 2 == 0 else "down") for i in range(6)]
    label, confidence = classify(extract_features(packets))
    assert label == "HEARTBEAT"
    assert confidence == pytest.approx(0.925)


def test_classify_download() -> None:
    packets = [FlowPacket(64, "up") for _ in range(2)] + [
        FlowPacket(1500, "down") for _ in range(20)
    ]
    assert classify(extract_features(packets))[0] == "DOWNLOAD"


def test_classify_upload() -> None:
    packets = [FlowPacket(64, "down") for _ in range(2)] + [
        FlowPacket(1500, "up") for _ in range(20)
    ]
    assert classify(extract_features(packets))[0] == "UPLOAD"


def test_classify_stream() -> None:
    packets = [
        FlowPacket(1500, "up" if i % 2 == 0 else "down", i * 0.6)
        for i in range(100)
    ]
    assert classify(extract_features(packets))[0] == "STREAM"


def test_classify_empty_is_unknown() -> None:
    label, confidence = classify(extract_features([]))
    assert label == "UNKNOWN"
    assert confidence == 1.0


def test_classify_unclear_is_unknown() -> None:
    packets = [FlowPacket(100), FlowPacket(5000)]
    assert classify(extract_features(packets))[0] == "UNKNOWN"


def test_predict_behavior_returns_prediction() -> None:
    packets = [FlowPacket(32, "up" if i % 2 == 0 else "down") for i in range(6)]
    prediction = predict_behavior(packets, flow_id="hb-1")
    assert prediction.flow_id == "hb-1"
    assert prediction.label == "HEARTBEAT"
    assert prediction.confidence == pytest.approx(0.925)
    assert prediction.features["packet_count"] == 6
    json.dumps(prediction.features)


def test_predict_behavior_is_deterministic() -> None:
    packets = [
        FlowPacket(1500, "up" if i % 2 == 0 else "down", i * 0.6)
        for i in range(100)
    ]
    assert predict_behavior(packets) == predict_behavior(packets)
