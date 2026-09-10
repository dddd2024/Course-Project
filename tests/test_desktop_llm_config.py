from __future__ import annotations

import pytest

from course_project.sidecar.desktop_llm_config import desktop_llm_enabled_from_environment


def test_desktop_llm_environment_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COURSE_PROJECT_LLM_ENABLED", raising=False)
    assert desktop_llm_enabled_from_environment() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
def test_desktop_llm_environment_accepts_true_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("COURSE_PROJECT_LLM_ENABLED", value)
    assert desktop_llm_enabled_from_environment() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", " no ", "off", ""])
def test_desktop_llm_environment_accepts_false_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("COURSE_PROJECT_LLM_ENABLED", value)
    assert desktop_llm_enabled_from_environment() is False


def test_desktop_llm_environment_rejects_ambiguous_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COURSE_PROJECT_LLM_ENABLED", "enabled-ish")
    with pytest.raises(ValueError, match="COURSE_PROJECT_LLM_ENABLED"):
        desktop_llm_enabled_from_environment()
