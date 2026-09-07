"""Project-native flow observation records (Track D, ``behavior`` layer).

``FlowPacket`` is the minimal unit the behavior module consumes: a directional
packet size with an optional timestamp. Direction is normalized to ``up``
(client -> server) / ``down`` (server -> client); raw ``.dat`` streams without
metadata leave direction/timestamp ``None``.

See ``docs/design-v1.md`` section 5.9.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Direction = Literal["up", "down"]

_DIRECTION_ALIASES = {
    "up": "up",
    "c2s": "up",
    "client": "up",
    "request": "up",
    "upload": "up",
    "down": "down",
    "s2c": "down",
    "server": "down",
    "response": "down",
    "download": "down",
}


@dataclass(frozen=True, slots=True)
class FlowPacket:
    """One directional observation in a flow: size, direction, optional time."""

    size: int
    direction: str | None = None
    timestamp: float | None = None

    def __post_init__(self) -> None:
        if self.size < 0:
            raise ValueError("size must be >= 0")


def normalize_direction(direction: str | None) -> Direction | None:
    """Normalize common direction aliases to "up"/"down"; unknown -> None."""
    if direction is None:
        return None
    return _DIRECTION_ALIASES.get(direction.lower())
