from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from course_project import doctor


def _write_baseline(root: Path) -> None:
    (root / "contracts").mkdir(parents=True)
    (root / "apps/desktop/src-tauri").mkdir(parents=True)
    (root / ".python-version").write_text("3.11\n", encoding="utf-8")
    (root / ".nvmrc").write_text("22\n", encoding="utf-8")
    (root / "rust-toolchain.toml").write_text(
        '[toolchain]\nchannel = "stable"\nprofile = "minimal"\n', encoding="utf-8"
    )
    (root / "contracts/sidecar-message.schema.json").write_text("{}\n", encoding="utf-8")
    (root / "apps/desktop/package-lock.json").write_text("{}\n", encoding="utf-8")
    (root / "apps/desktop/src-tauri/Cargo.lock").write_text("# lock\n", encoding="utf-8")


def _probe_ok(command: Sequence[str], _cwd: Path) -> tuple[int, str] | None:
    if command[1:] == ("-m", "course_project.sidecar", "--help"):
        return 0, "usage: course-project-sidecar"
    outputs = {
        "node": "v22.18.0",
        "npm": "10.9.3",
        "rustup": "stable-x86_64-pc-windows-msvc (overridden by rust-toolchain.toml)",
        "rustc": "rustc 1.89.0 (29483883e 2025-08-04)",
        "cargo": "cargo 1.89.0 (c24e10642 2025-06-23)",
    }
    output = outputs.get(command[0])
    return (0, output) if output is not None else None


def test_collect_checks_passes_matching_baseline(tmp_path: Path) -> None:
    _write_baseline(tmp_path)

    checks = doctor.collect_checks(tmp_path, python_version=(3, 11), probe=_probe_ok)

    assert not [check for check in checks if check.status == "fail"]
    assert next(check for check in checks if check.name == "node").actual == "v22.18.0"
    assert next(check for check in checks if check.name == "rust-toolchain").status == "pass"
    assert next(check for check in checks if check.name == "platform").status == "info"


def test_collect_checks_fails_on_node_major_mismatch(tmp_path: Path) -> None:
    _write_baseline(tmp_path)

    def probe(command: Sequence[str], cwd: Path) -> tuple[int, str] | None:
        if command[0] == "node":
            return 0, "v20.19.0"
        return _probe_ok(command, cwd)

    checks = doctor.collect_checks(tmp_path, python_version=(3, 11), probe=probe)
    node = next(check for check in checks if check.name == "node")

    assert node.status == "fail"
    assert node.expected == "major 22"
    assert "mismatch" in node.detail


def test_collect_checks_fails_on_wrong_active_rust_channel(tmp_path: Path) -> None:
    _write_baseline(tmp_path)

    def probe(command: Sequence[str], cwd: Path) -> tuple[int, str] | None:
        if command[0] == "rustup":
            return 0, "nightly-x86_64-pc-windows-msvc (default)"
        return _probe_ok(command, cwd)

    checks = doctor.collect_checks(tmp_path, python_version=(3, 11), probe=probe)
    toolchain = next(check for check in checks if check.name == "rust-toolchain")

    assert toolchain.status == "fail"
    assert toolchain.expected == "stable"
    assert "mismatch" in toolchain.detail


def test_collect_checks_fails_on_malformed_rust_toolchain(tmp_path: Path) -> None:
    _write_baseline(tmp_path)
    (tmp_path / "rust-toolchain.toml").write_text(
        '[toolchain]\nprofile = "minimal"\n', encoding="utf-8"
    )

    checks = doctor.collect_checks(tmp_path, python_version=(3, 11), probe=_probe_ok)
    toolchain = next(check for check in checks if check.name == "rust-toolchain")

    assert toolchain.status == "fail"
    assert toolchain.actual == "unparseable"


def test_collect_checks_fails_closed_when_baseline_file_is_missing(tmp_path: Path) -> None:
    _write_baseline(tmp_path)
    (tmp_path / "apps/desktop/src-tauri/Cargo.lock").unlink()

    checks = doctor.collect_checks(tmp_path, python_version=(3, 11), probe=_probe_ok)
    baseline = next(check for check in checks if check.name == "baseline-files")

    assert baseline.status == "fail"
    assert "Cargo.lock" in baseline.actual


def test_collect_checks_reports_missing_tool(tmp_path: Path) -> None:
    _write_baseline(tmp_path)

    def probe(command: Sequence[str], cwd: Path) -> tuple[int, str] | None:
        if command[0] == "cargo":
            return None
        return _probe_ok(command, cwd)

    checks = doctor.collect_checks(tmp_path, python_version=(3, 11), probe=probe)
    cargo = next(check for check in checks if check.name == "cargo")

    assert cargo.status == "fail"
    assert cargo.actual == "not found"


def test_main_json_returns_nonzero_for_invalid_environment(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_baseline(tmp_path)
    (tmp_path / ".nvmrc").write_text("99\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "_probe", _probe_ok)

    result = doctor.main(["--root", str(tmp_path), "--json"])
    output = capsys.readouterr().out

    assert result == 1
    assert '"ready": false' in output
    assert '"name": "node"' in output
