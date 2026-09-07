"""Message clustering into structural families (Track D).

V1 uses greedy, deterministic clustering: each message joins the first cluster
whose representative (its first message) has a similar header. Similarity is
the byte-match rate over the first ``header_len`` bytes; length is
intentionally excluded so variable-length payloads of one family do not split
it. Known limitation: families that differ only beyond the compared header
bytes are merged.

See ``docs/design-v1.md`` section 5.4.
"""

from __future__ import annotations


def message_similarity(a: bytes, b: bytes, *, header_len: int = 8) -> float:
    """Header byte-match rate in [0, 1]; 0.0 when no bytes are comparable."""
    h = min(header_len, len(a), len(b))
    if h <= 0:
        return 0.0
    return sum(1 for i in range(h) if a[i] == b[i]) / h


def cluster_messages(
    messages: list[bytes], *, header_len: int = 8, threshold: float = 0.9
) -> list[int]:
    """Greedy deterministic cluster labels, one per message in input order."""
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("threshold must be in [0, 1]")
    representatives: list[bytes] = []
    labels: list[int] = []
    for message in messages:
        label = -1
        for i, representative in enumerate(representatives):
            if (
                message_similarity(message, representative, header_len=header_len)
                >= threshold
            ):
                label = i
                break
        if label == -1:
            label = len(representatives)
            representatives.append(message)
        labels.append(label)
    return labels
