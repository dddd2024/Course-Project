"""Chinese presentation helpers for analysis conclusions (Track D).

The frozen project-native DTOs keep English semantic labels because Track C's
verification pipeline matches on those exact strings. This module maps those
labels to Chinese for human-facing output only — it never changes the DTOs.
"""

from __future__ import annotations

from course_project.models import FieldCandidate

SEMANTIC_ZH = {
    "magic": "魔数",
    "constant": "常量",
    "enum": "枚举",
    "length": "长度",
    "sequence": "序号",
    "timestamp": "时间戳",
    "checksum": "校验和",
    "version": "版本",
    "payload": "载荷",
    "unknown": "未知",
}

BEHAVIOR_ZH = {
    "QUERY": "查询",
    "DOWNLOAD": "下载",
    "UPLOAD": "上传",
    "HEARTBEAT": "心跳",
    "STREAM": "流式",
    "UNKNOWN": "未知",
}

_FIELD_ORDER = (
    "magic",
    "constant",
    "enum",
    "length",
    "sequence",
    "timestamp",
    "checksum",
    "version",
    "payload",
    "unknown",
)


def semantic_zh(semantic: str) -> str:
    """Map an English semantic label to Chinese; passthrough if unknown."""
    return SEMANTIC_ZH.get(semantic, semantic)


def behavior_zh(label: str) -> str:
    """Map an English behavior label to Chinese; passthrough if unknown."""
    return BEHAVIOR_ZH.get(label, label)


def field_candidate_zh(candidate: FieldCandidate) -> str:
    """One-line Chinese description of a field candidate."""
    types = "、".join(semantic_zh(t) for t in candidate.candidate_types) or "未知"
    size = f"{candidate.size} 字节" if candidate.size is not None else "变长"
    if candidate.endian == "big":
        endian = "大端"
    elif candidate.endian == "little":
        endian = "小端"
    else:
        endian = ""
    parts = [f"偏移 {candidate.offset}", types, size]
    if endian:
        parts.append(endian)
    parts.append(f"置信度 {candidate.score:.2f}")
    return "，".join(parts)


def identified_fields_zh(candidates: list[FieldCandidate]) -> list[str]:
    """Distinct Chinese field-type labels present, in stable protocol order."""
    seen: set[str] = set()
    labels: list[tuple[int, str]] = []
    for candidate in candidates:
        for semantic in candidate.candidate_types:
            if semantic in seen:
                continue
            seen.add(semantic)
            order = (
                _FIELD_ORDER.index(semantic)
                if semantic in _FIELD_ORDER
                else len(_FIELD_ORDER)
            )
            labels.append((order, semantic_zh(semantic)))
    labels.sort()
    return [label for _, label in labels]
