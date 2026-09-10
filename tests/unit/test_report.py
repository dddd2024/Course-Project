from __future__ import annotations

from course_project.models import FieldCandidate
from course_project.report import (
    behavior_zh,
    field_candidate_zh,
    identified_fields_zh,
    semantic_zh,
)


def test_semantic_zh_maps_known_and_passthrough() -> None:
    assert semantic_zh("length") == "长度"
    assert semantic_zh("magic") == "魔数"
    assert semantic_zh("payload") == "载荷"
    assert semantic_zh("bogus") == "bogus"


def test_behavior_zh() -> None:
    assert behavior_zh("DOWNLOAD") == "下载"
    assert behavior_zh("HEARTBEAT") == "心跳"
    assert behavior_zh("UNKNOWN") == "未知"


def test_identified_fields_zh_orders_and_dedupes() -> None:
    candidates = [
        FieldCandidate(candidate_id="a", family_id=None, offset=9, size=2, candidate_types=("length",), endian="big"),
        FieldCandidate(candidate_id="b", family_id=None, offset=0, size=4, candidate_types=("magic",)),
        FieldCandidate(candidate_id="c", family_id=None, offset=8, size=1, candidate_types=("sequence",)),
        FieldCandidate(candidate_id="d", family_id=None, offset=0, size=4, candidate_types=("magic",)),
    ]
    assert identified_fields_zh(candidates) == ["魔数", "长度", "序号"]


def test_field_candidate_zh_renders_chinese() -> None:
    candidate = FieldCandidate(
        candidate_id="x",
        family_id=None,
        offset=9,
        size=2,
        candidate_types=("length",),
        endian="big",
        score=1.0,
    )
    text = field_candidate_zh(candidate)
    assert "长度" in text
    assert "偏移 9" in text
    assert "大端" in text
    assert "2 字节" in text
