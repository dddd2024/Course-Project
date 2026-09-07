from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_codeowners_is_not_used_as_merge_routing() -> None:
    assert not (ROOT / ".github/CODEOWNERS").exists()


def test_authoritative_merge_policy_is_ci_only() -> None:
    agents = _read("AGENTS.md")
    pr_template = _read(".github/pull_request_template.md")
    settings = _read("docs/repository-settings.md")

    assert "## 7. Merge governance — CI only" in agents
    assert "no required human review" in agents.lower()
    assert "merge promptly" in agents.lower()
    assert "## Merge Gate — CI Only" in pr_template
    assert "human approval" in pr_template.lower()
    assert "not merge requirements" in pr_template.lower()
    assert "required approving reviews: 0" in settings
    assert "review-thread resolution: disabled" in settings
    assert "Code Owner review: disabled" in settings
    assert "merge promptly" in settings.lower()


def test_old_review_gates_do_not_reappear_in_authoritative_docs() -> None:
    paths = (
        "AGENTS.md",
        ".github/pull_request_template.md",
        "docs/repository-settings.md",
        "docs/architecture.md",
        "docs/day0-contract-freeze.md",
        "docs/team-division.md",
        "CONTRIBUTING.md",
    )
    forbidden = (
        "require at least one approving review",
        "required reviews / conversations are satisfied",
        "request track a review plus at least one",
        "track a + affected",
        "one valid human approval",
    )

    for path in paths:
        content = _read(path).lower()
        for phrase in forbidden:
            assert phrase not in content, f"obsolete review gate found in {path}: {phrase}"


def test_ci_keeps_all_blocking_jobs_and_aggregate_gate() -> None:
    workflow = _read(".github/workflows/ci.yml")

    assert 'python-version: ["3.10", "3.11"]' in workflow
    assert "windows-integration:" in workflow
    assert "merge-gate:" in workflow
    assert "needs:\n      - test\n      - windows-integration" in workflow
    assert 'TEST_RESULT: ${{ needs.test.result }}' in workflow
    assert 'WINDOWS_RESULT: ${{ needs.windows-integration.result }}' in workflow
    assert '"$TEST_RESULT" != "success"' in workflow
    assert '"$WINDOWS_RESULT" != "success"' in workflow
