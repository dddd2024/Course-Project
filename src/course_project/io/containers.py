"""Input container-format detection (Track D, ``io`` layer).

Detects the real on-disk container from leading magic bytes so a ``.dat`` that
is actually a PCAP/PCAPNG capture is not mistaken for an opaque raw stream.
No third-party dependencies — pure magic-byte sniffing.

See ``docs/design-v1.md`` section 5.1 (PCAP is a first-class input).
"""

from __future__ import annotations

from course_project.models import InputKind

_PCAP_MAGICS = (
    b"\xd4\xc3\xb2\xa1",  # pcap, little-endian microsecond
    b"\xa1\xb2\xc3\xd4",  # pcap, big-endian microsecond
    b"\x4d\x3c\xb2\xa1",  # pcap, little-endian nanosecond
    b"\xa1\xb2\x3c\x4d",  # pcap, big-endian nanosecond
)
_PCAPNG_MAGIC = b"\x0a\x0d\x0d\x0a"


def detect_container(data: bytes) -> InputKind:
    """Return the container kind from leading magic bytes.

    ``"pcap"`` and ``"pcapng"`` are recognized; anything else is ``"unknown"``
    (i.e. treat as a raw byte stream).
    """
    if len(data) < 4:
        return "unknown"
    head = data[:4]
    if head == _PCAPNG_MAGIC:
        return "pcapng"
    if head in _PCAP_MAGICS:
        return "pcap"
    return "unknown"
