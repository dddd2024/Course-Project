"""Deterministic flow-behavior feature extraction (Track D).

Produces the V1 feature record: packet size sequence, direction sequence,
up/down byte and packet counts, inter-arrival statistics, burst structure,
duration and flow statistics. No supervised labels are invented — the record
is evidence, classification happens in ``behavior.classify``.

See ``docs/design-v1.md`` section 5.9.
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise
from statistics import mean, pstdev
from typing import Any

from course_project.behavior.records import FlowPacket, normalize_direction
from course_project.models import PacketCandidate


def from_packet_candidates(packets: list[PacketCandidate]) -> list[FlowPacket]:
    """Convert boundary candidates into flow observations (size/direction/time)."""
    return [
        FlowPacket(
            size=packet.end_offset - packet.start_offset,
            direction=packet.direction,
            timestamp=packet.timestamp,
        )
        for packet in packets
    ]


def extract_features(
    packets: list[FlowPacket], *, flow_id: str = "flow-0"
) -> dict[str, Any]:
    """Deterministic V1 behavior-feature record for one flow.

    Directionless packets still contribute size/timing statistics; directional
    statistics (up/down bytes, bursts, switches) treat them as gaps.
    """
    sizes = [p.size for p in packets]
    directions = [normalize_direction(p.direction) for p in packets]
    timestamps = [p.timestamp for p in packets if p.timestamp is not None]

    up_bytes = sum(s for s, d in zip(sizes, directions) if d == "up")
    down_bytes = sum(s for s, d in zip(sizes, directions) if d == "down")
    up_count = sum(1 for d in directions if d == "up")
    down_count = sum(1 for d in directions if d == "down")

    iats = [b - a for a, b in pairwise(timestamps)] if len(timestamps) >= 2 else []
    bursts = _bursts(zip(sizes, directions))

    return {
        "flow_id": flow_id,
        "packet_count": len(packets),
        "total_bytes": sum(sizes),
        "up_bytes": up_bytes,
        "down_bytes": down_bytes,
        "up_count": up_count,
        "down_count": down_count,
        "up_down_ratio": up_bytes / down_bytes if down_bytes > 0 else None,
        "size_mean": mean(sizes) if sizes else None,
        "size_std": pstdev(sizes) if sizes else None,
        "size_min": min(sizes) if sizes else None,
        "size_max": max(sizes) if sizes else None,
        "direction_switches": _direction_switches(directions),
        "burst_count": len(bursts),
        "burst_lengths": [count for count, _ in bursts],
        "burst_sizes": [total for _, total in bursts],
        "inter_arrival_mean": mean(iats) if iats else None,
        "inter_arrival_std": pstdev(iats) if iats else None,
        "duration": (
            max(timestamps) - min(timestamps) if len(timestamps) >= 2 else None
        ),
        "sizes": sizes,
        "directions": directions,
    }


def _bursts(pairs: Iterable[tuple[int, str | None]]) -> list[tuple[int, int]]:
    """Consecutive same-direction runs as ``(packet_count, byte_count)``.

    Packets without a usable direction flush the current run and act as gaps.
    """
    bursts: list[tuple[int, int]] = []
    current: str | None = None
    count = 0
    total = 0
    for size, direction in pairs:
        if direction is None:
            if count:
                bursts.append((count, total))
                count = 0
                total = 0
            current = None
            continue
        if direction == current:
            count += 1
            total += size
        else:
            if count:
                bursts.append((count, total))
            current = direction
            count = 1
            total = size
    if count:
        bursts.append((count, total))
    return bursts


def _direction_switches(directions: list[str | None]) -> int:
    switches = 0
    previous: str | None = None
    for direction in directions:
        if direction is None:
            continue
        if previous is not None and direction != previous:
            switches += 1
        previous = direction
    return switches
