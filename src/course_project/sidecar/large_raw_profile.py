"""Bounded-memory structural and cryptographic profiling for large raw captures."""

from __future__ import annotations

import math
import zlib
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

_SAMPLE_WINDOW_BYTES = 128 * 1024
_SCAN_CHUNK_BYTES = 4 * 1024 * 1024
_MAX_MARKER_CANDIDATES = 16
_MAX_OCCURRENCES_PER_MARKER = 50_000
_MAX_RECORD_SAMPLES = 512
_MAX_PAYLOAD_SAMPLE_BYTES = 4 * 1024 * 1024
_ETHERNET_LENGTHS = frozenset({64, 1514, 1518})


def profile_large_raw_file(path: Path, *, size_bytes: int) -> dict[str, Any]:
    """Scan a large raw file in bounded chunks and return evidence-led inferences."""
    candidates, sampled_offsets = _discover_markers(path, size_bytes)
    occurrences = _scan_occurrences(path, candidates)
    marker, offsets = _select_marker(occurrences)
    profile: dict[str, Any] = {
        "schemaVersion": "large-raw-profile-v1",
        "bytesScanned": size_bytes,
        "sampleWindowOffsets": sampled_offsets,
        "candidateMarkerCount": len(candidates),
        "markerHex": marker.hex() if marker is not None else None,
        "markerOccurrenceCount": len(offsets),
        "conclusions": [],
    }
    if marker is None or len(offsets) < 3:
        profile["summary"] = (
            "已分块扫描完整文件，但没有找到足够稳定的重复 4 字节记录标志；"
            "当前只能对分析窗口做通用边界推断。"
        )
        return profile

    gaps = [right - left for left, right in pairwise(offsets) if right > left]
    header_bytes, length_evidence = _infer_header_size(gaps)
    samples = _read_record_samples(path, offsets, gaps, header_bytes)
    header_evidence = _header_evidence(samples, len(marker), header_bytes)
    payload_evidence = _payload_evidence(samples, header_bytes)
    common_lengths = [
        {"length": length, "count": count}
        for length, count in Counter(gaps).most_common(12)
    ]
    profile.update(
        {
            "recordCount": len(gaps),
            "commonRecordLengths": common_lengths,
            "inferredHeaderBytes": header_bytes,
            "lengthEvidence": length_evidence,
            "headerEvidence": header_evidence,
            "payloadEvidence": payload_evidence,
        }
    )
    conclusions = _build_conclusions(
        marker=marker,
        header_bytes=header_bytes,
        length_evidence=length_evidence,
        header_evidence=header_evidence,
        payload_evidence=payload_evidence,
    )
    profile["conclusions"] = conclusions
    profile["summary"] = "；".join(item["claim"] for item in conclusions[:4]) or (
        "已完成全文件分块统计，但证据不足以判断具体记录结构或加密模式。"
    )
    return profile


def _discover_markers(path: Path, size_bytes: int) -> tuple[list[bytes], list[int]]:
    offsets = sorted(
        {
            0,
            max(0, size_bytes // 2 - _SAMPLE_WINDOW_BYTES // 2),
            max(0, size_bytes - _SAMPLE_WINDOW_BYTES),
        }
    )
    counts: Counter[bytes] = Counter()
    with path.open("rb") as handle:
        for offset in offsets:
            handle.seek(offset)
            data = handle.read(_SAMPLE_WINDOW_BYTES)
            counts.update(data[index : index + 4] for index in range(max(0, len(data) - 3)))
    candidates = [
        value
        for value, count in counts.most_common()
        if count >= 3 and len(set(value)) > 1
    ][:_MAX_MARKER_CANDIDATES]
    return candidates, offsets


def _scan_occurrences(path: Path, candidates: list[bytes]) -> dict[bytes, list[int]]:
    found = {candidate: [] for candidate in candidates}
    last_seen = {candidate: -1 for candidate in candidates}
    carry = b""
    consumed = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_SCAN_CHUNK_BYTES):
            data = carry + chunk
            base = consumed - len(carry)
            for candidate in candidates:
                start = 0
                while len(found[candidate]) < _MAX_OCCURRENCES_PER_MARKER:
                    index = data.find(candidate, start)
                    if index < 0:
                        break
                    absolute = base + index
                    if absolute > last_seen[candidate]:
                        found[candidate].append(absolute)
                        last_seen[candidate] = absolute
                    start = index + 1
            consumed += len(chunk)
            carry = data[-3:]
    return found


def _select_marker(occurrences: dict[bytes, list[int]]) -> tuple[bytes | None, list[int]]:
    eligible = [(marker, offsets) for marker, offsets in occurrences.items() if len(offsets) >= 3]
    if not eligible:
        return None, []

    def score(item: tuple[bytes, list[int]]) -> tuple[float, int, int, bytes]:
        marker, offsets = item
        gaps = [b - a for a, b in pairwise(offsets) if b > a]
        _, evidence = _infer_header_size(gaps)
        return (
            float(evidence["ethernetExactRatio"]) * 8.0
            + float(evidence["ethernetRangeRatio"]) * 2.0
            + math.log2(len(offsets) + 1),
            len(offsets),
            -offsets[0],
            marker,
        )

    marker, offsets = max(eligible, key=score)
    return marker, offsets


def _infer_header_size(gaps: list[int]) -> tuple[int | None, dict[str, Any]]:
    usable = [gap for gap in gaps if 8 <= gap <= 65_536]
    best_header: int | None = None
    best_score = -1.0
    best_exact = 0
    best_range = 0
    for header in range(4, 33):
        payload_lengths = [gap - header for gap in usable if gap > header]
        if not payload_lengths:
            continue
        exact = sum(length in _ETHERNET_LENGTHS for length in payload_lengths)
        in_range = sum(64 <= length <= 1518 for length in payload_lengths)
        score = exact / len(payload_lengths) * 8.0 + in_range / len(payload_lengths)
        if score > best_score:
            best_score = score
            best_header = header
            best_exact = exact
            best_range = in_range
    total = len(usable)
    exact_ratio = best_exact / total if total else 0.0
    range_ratio = best_range / total if total else 0.0
    if best_exact < 2 or exact_ratio < 0.01:
        best_header = None
    return best_header, {
        "evaluatedRecordCount": total,
        "ethernetExactCount": best_exact,
        "ethernetExactRatio": round(exact_ratio, 6),
        "ethernetRangeCount": best_range,
        "ethernetRangeRatio": round(range_ratio, 6),
        "candidateEthernetPayloadLengths": sorted(_ETHERNET_LENGTHS),
    }


def _read_record_samples(
    path: Path,
    offsets: list[int],
    gaps: list[int],
    header_bytes: int | None,
) -> list[tuple[bytes, int]]:
    if not gaps:
        return []
    count = min(_MAX_RECORD_SAMPLES, len(gaps))
    head_count = (count + 1) // 2
    tail_count = count - head_count
    indexes = list(range(head_count))
    if tail_count:
        indexes.extend(range(len(gaps) - tail_count, len(gaps)))
    samples: list[tuple[bytes, int]] = []
    with path.open("rb") as handle:
        for index in indexes:
            length = gaps[index]
            if length <= 0 or length > 65_536:
                continue
            handle.seek(offsets[index])
            record = handle.read(length)
            if len(record) == length and (header_bytes is None or length > header_bytes):
                samples.append((record, length))
    return samples


def _header_evidence(
    samples: list[tuple[bytes, int]], marker_size: int, header_bytes: int | None
) -> dict[str, Any]:
    if header_bytes is None or header_bytes < marker_size + 4 or not samples:
        return {"sampleCount": 0}
    counter_values: list[int] = []
    sessions: list[bytes] = []
    for record, _ in samples:
        if len(record) < header_bytes:
            continue
        counter_values.append(int.from_bytes(record[marker_size : marker_size + 4], "big"))
        sessions.append(record[marker_size + 4 : header_bytes])
    unique_ratio = len(set(counter_values)) / len(counter_values) if counter_values else 0.0
    grouped: dict[bytes, list[int]] = defaultdict(list)
    for session, counter in zip(sessions, counter_values):
        grouped[session].append(counter)
    increments = 0
    transitions = 0
    for values in grouped.values():
        for left, right in pairwise(values):
            transitions += 1
            increments += ((right - left) & 0xFFFFFFFF) == 1
    return {
        "sampleCount": len(counter_values),
        "counterOffset": marker_size,
        "counterSize": 4,
        "counterUniqueRatio": round(unique_ratio, 6),
        "counterIncrementByOneRatio": round(increments / transitions, 6) if transitions else None,
        "sessionOffset": marker_size + 4,
        "sessionSize": max(0, header_bytes - marker_size - 4),
        "sessionValueCount": len(set(sessions)),
        "topSessions": [
            {"hex": value.hex(), "count": count}
            for value, count in Counter(sessions).most_common(8)
        ],
    }


def _payload_evidence(
    samples: list[tuple[bytes, int]], header_bytes: int | None
) -> dict[str, Any]:
    if header_bytes is None:
        return {"sampleCount": 0}
    payloads: list[bytes] = []
    payload_entries: list[tuple[bytes, bytes]] = []
    total = 0
    for record, _ in samples:
        payload = record[header_bytes:]
        if not payload or total >= _MAX_PAYLOAD_SAMPLE_BYTES:
            continue
        retained = payload[: _MAX_PAYLOAD_SAMPLE_BYTES - total]
        payloads.append(retained)
        payload_entries.append((record[8:header_bytes], retained))
        total += len(retained)
    combined = b"".join(payloads)
    if not combined:
        return {"sampleCount": 0}
    counts = Counter(combined)
    entropy = -sum((count / len(combined)) * math.log2(count / len(combined)) for count in counts.values())
    compressed_ratio = len(zlib.compress(combined, 9)) / len(combined)
    block_counts: Counter[bytes] = Counter()
    for payload in payloads:
        block_counts.update(payload[index : index + 16] for index in range(0, len(payload) - 15, 16))
    repeated_blocks = sum(count - 1 for count in block_counts.values() if count > 1)
    aligned = sum(len(payload) % 16 == 0 for payload in payloads)
    xor_zeros, xor_bytes = _xor_zero_counts(payload_entries)
    ipv4_valid = sum(_count_valid_ipv4_headers(payload) for payload in payloads)
    signatures = (b"GET ", b"POST ", b"HTTP/", b"SSH-", b"\x16\x03\x01", b"\x16\x03\x03")
    signature_hits = sum(payload.count(signature) for payload in payloads for signature in signatures)
    return {
        "sampleCount": len(payloads),
        "sampledPayloadBytes": len(combined),
        "entropyBitsPerByte": round(entropy, 6),
        "zlibRatio": round(compressed_ratio, 6),
        "block16Count": sum(block_counts.values()),
        "repeatedBlock16Count": repeated_blocks,
        "blockAlignedPayloadRatio": round(aligned / len(payloads), 6),
        "xorZeroRatio": round(xor_zeros / xor_bytes, 6) if xor_bytes else None,
        "randomXorZeroBaseline": round(1 / 256, 6),
        "validatedIpv4HeaderCount": ipv4_valid,
        "obviousPlaintextSignatureCount": signature_hits,
    }


def _xor_zero_counts(payloads: list[tuple[bytes, bytes]]) -> tuple[int, int]:
    by_session_and_length: dict[tuple[bytes, int], list[bytes]] = defaultdict(list)
    for session, payload in payloads:
        by_session_and_length[(session, len(payload))].append(payload)
    zeros = 0
    compared = 0
    pairs = 0
    for group in by_session_and_length.values():
        for left, right in pairwise(group):
            zeros += sum(a == b for a, b in zip(left, right))
            compared += len(left)
            pairs += 1
            if pairs >= 64:
                return zeros, compared
    return zeros, compared


def _count_valid_ipv4_headers(payload: bytes) -> int:
    valid = 0
    for offset in range(max(0, len(payload) - 19)):
        first = payload[offset]
        if first >> 4 != 4:
            continue
        header_length = (first & 0x0F) * 4
        if header_length < 20 or offset + header_length > len(payload):
            continue
        header = payload[offset : offset + header_length]
        total_length = int.from_bytes(header[2:4], "big")
        if total_length < header_length or total_length > len(payload) - offset:
            continue
        words = sum(int.from_bytes(header[index : index + 2], "big") for index in range(0, header_length, 2))
        words = (words & 0xFFFF) + (words >> 16)
        words = (words & 0xFFFF) + (words >> 16)
        if words == 0xFFFF:
            valid += 1
    return valid


def _build_conclusions(
    *,
    marker: bytes,
    header_bytes: int | None,
    length_evidence: dict[str, Any],
    header_evidence: dict[str, Any],
    payload_evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    conclusions: list[dict[str, Any]] = []
    occurrence_note = f"重复记录标志 {marker.hex(' ')} 已在全文件定位"
    if header_bytes is not None:
        conclusions.append(
            {
                "claim": f"文件更像逐包记录流，候选明文封装头约 {header_bytes} 字节",
                "confidence": "high" if length_evidence["ethernetExactRatio"] >= 0.1 else "medium",
                "basis": [occurrence_note, "记录间距减去候选头长后命中以太网经典帧长"],
            }
        )
    unique_ratio = float(header_evidence.get("counterUniqueRatio") or 0.0)
    increment_ratio = float(header_evidence.get("counterIncrementByOneRatio") or 0.0)
    if unique_ratio >= 0.98:
        conclusions.append(
            {
                "claim": "标志后的 4 字节字段具有包计数器或 IV 组成部分特征",
                "confidence": "high" if increment_ratio >= 0.8 else "medium",
                "basis": [
                    f"样本唯一率 {unique_ratio:.2%}",
                    f"同会话递增 1 比例 {increment_ratio:.2%}",
                ],
            }
        )
    entropy = float(payload_evidence.get("entropyBitsPerByte") or 0.0)
    zlib_ratio = float(payload_evidence.get("zlibRatio") or 0.0)
    if entropy >= 7.8 and zlib_ratio >= 0.98:
        conclusions.append(
            {
                "claim": "候选负载呈高熵且不可压缩，主体经过加密或强压缩的可能性很高",
                "confidence": "high",
                "basis": [f"熵 {entropy:.6f} bit/Byte", f"zlib 比率 {zlib_ratio:.6f}"],
            }
        )
    aligned_ratio = float(payload_evidence.get("blockAlignedPayloadRatio") or 0.0)
    repeated_blocks = int(payload_evidence.get("repeatedBlock16Count") or 0)
    xor_ratio = payload_evidence.get("xorZeroRatio")
    if entropy >= 7.8 and aligned_ratio < 0.5 and repeated_blocks == 0:
        basis = ["大量负载长度不按 16 字节对齐", "样本中未发现重复 16 字节密文块"]
        if isinstance(xor_ratio, float):
            basis.append(f"等长负载异或零比例 {xor_ratio:.4%}，接近随机基线 {1 / 256:.4%}")
        conclusions.append(
            {
                "claim": "更符合使用唯一 nonce/counter 的长度保持型流式加密；AES-CTR 是候选，但不能仅凭密文排除 ChaCha20",
                "confidence": "medium-high",
                "basis": basis,
            }
        )
    if (
        header_bytes is not None
        and float(length_evidence["ethernetExactRatio"]) >= 0.01
        and int(payload_evidence.get("validatedIpv4HeaderCount") or 0) == 0
    ):
        conclusions.append(
            {
                "claim": "原始内容可能是被整体加密的 Ethernet 帧，IP/TCP 等头部没有以明文保留",
                "confidence": "medium-high",
                "basis": [
                    "候选负载长度命中 64/1514/1518 字节",
                    "候选负载中没有通过校验的 IPv4 头",
                ],
            }
        )
    return conclusions



