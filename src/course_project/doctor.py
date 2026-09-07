from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    expected: str
    actual: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


Probe = Callable[[Sequence[str], Path], tuple[int, str] | None]

_REQUIRED_FILES = (
    ".python-version",
    ".nvmrc",
    "rust-toolchain.toml",
    "contracts/sidecar-message.schema.json",
    "apps/desktop/package-lock.json",
    "apps/desktop/src-tauri/Cargo.lock",
)


def _probe(command: Sequence[str], cwd: Path) -> tuple[int, str] | None:
    executable = command[0]
    resolved = executable if Path(executable).is_file() else shutil.which(executable)
    if resolved is None:
        return None
    try:
        completed = subprocess.run(
            [resolved, *command[1:]],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, f"{type(exc).__name__}: {exc}"
    output = completed.stdout.strip() or completed.stderr.strip()
    first_line = output.splitlines()[0] if output else ""
    return completed.returncode, first_line


def _read_marker(root: Path, relative: str) -> str | None:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _rust_channel(root: Path) -> str | None:
    content = _read_marker(root, "rust-toolchain.toml")
    if content is None:
        return None
    match = re.search(r'^\s*channel\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else None


def _major(version_output: str) -> str | None:
    match = re.search(r"(?:^|\s)v?(\d+)(?:\.|$)", version_output)
    return match.group(1) if match else None


def _active_toolchain_matches(output: str, expected_channel: str) -> bool:
    token = output.split(maxsplit=1)[0] if output else ""
    return token == expected_channel or token.startswith(f"{expected_channel}-")


def _command_check(
    *,
    name: str,
    command: Sequence[str],
    expected: str,
    root: Path,
    probe: Probe,
    validator: Callable[[str], bool] | None = None,
) -> CheckResult:
    result = probe(command, root)
    if result is None:
        return CheckResult(name, "fail", expected, "not found", "executable is not on PATH")
    returncode, output = result
    if returncode != 0:
        return CheckResult(name, "fail", expected, output or f"exit {returncode}", "command failed")
    if validator is not None and not validator(output):
        return CheckResult(name, "fail", expected, output, "version mismatch with baseline")
    return CheckResult(name, "pass", expected, output)


def collect_checks(
    root: Path,
    *,
    python_version: tuple[int, int] | None = None,
    probe: Probe | None = None,
) -> list[CheckResult]:
    root = root.resolve()
    probe = probe or _probe
    checks: list[CheckResult] = []

    missing = [relative for relative in _REQUIRED_FILES if not (root / relative).is_file()]
    checks.append(
        CheckResult(
            "baseline-files",
            "pass" if not missing else "fail",
            "all canonical markers and desktop lockfiles present",
            "present" if not missing else f"missing: {', '.join(missing)}",
        )
    )

    expected_python = _read_marker(root, ".python-version")
    actual_python_tuple = python_version or (sys.version_info.major, sys.version_info.minor)
    actual_python = f"{actual_python_tuple[0]}.{actual_python_tuple[1]}"
    if expected_python is None:
        checks.append(CheckResult("python", "fail", ".python-version", actual_python, "baseline missing"))
    else:
        checks.append(
            CheckResult(
                "python",
                "pass" if actual_python == expected_python else "fail",
                expected_python,
                actual_python,
                "" if actual_python == expected_python else "major/minor version mismatch",
            )
        )

    expected_node = _read_marker(root, ".nvmrc")
    if expected_node is None:
        checks.append(CheckResult("node", "fail", ".nvmrc", "unknown", "baseline missing"))
    else:
        checks.append(
            _command_check(
                name="node",
                command=("node", "--version"),
                expected=f"major {expected_node}",
                root=root,
                probe=probe,
                validator=lambda output: _major(output) == expected_node,
            )
        )

    checks.append(
        _command_check(
            name="npm",
            command=("npm", "--version"),
            expected="available (desktop lockfile is authoritative)",
            root=root,
            probe=probe,
        )
    )

    channel = _rust_channel(root)
    if channel is None:
        checks.append(
            CheckResult(
                "rust-toolchain",
                "fail",
                'a parseable channel in rust-toolchain.toml',
                "unparseable",
                "toolchain channel is missing or malformed",
            )
        )
    else:
        checks.append(
            _command_check(
                name="rust-toolchain",
                command=("rustup", "show", "active-toolchain"),
                expected=channel,
                root=root,
                probe=probe,
                validator=lambda output: _active_toolchain_matches(output, channel),
            )
        )

    checks.append(
        _command_check(
            name="rustc",
            command=("rustc", "--version"),
            expected="available",
            root=root,
            probe=probe,
        )
    )
    checks.append(
        _command_check(
            name="cargo",
            command=("cargo", "--version"),
            expected="available",
            root=root,
            probe=probe,
        )
    )

    checks.append(
        _command_check(
            name="sidecar-cli",
            command=(sys.executable, "-m", "course_project.sidecar", "--help"),
            expected="course_project.sidecar CLI starts successfully",
            root=root,
            probe=probe,
        )
    )

    checks.append(
        CheckResult(
            "platform",
            "info",
            "Windows 10/11 x64 for final rehearsal; development may use another OS",
            f"{platform.system()} {platform.machine()}",
        )
    )
    return checks


def _find_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "contracts").is_dir():
            return candidate
    return current


def _render_text(root: Path, checks: Sequence[CheckResult]) -> str:
    lines = [f"Course Project environment doctor — {root}"]
    for check in checks:
        label = check.status.upper()
        suffix = f" — {check.detail}" if check.detail else ""
        lines.append(f"[{label}] {check.name}: {check.actual} (expected: {check.expected}){suffix}")
    failed = sum(check.status == "fail" for check in checks)
    lines.append(f"Result: {'READY' if failed == 0 else 'NOT READY'} ({failed} failing check(s))")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the course-project reproducible environment baseline.")
    parser.add_argument("--root", help="repository root; defaults to auto-detection from cwd")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    root = _find_root(args.root)
    checks = collect_checks(root)
    failed = any(check.status == "fail" for check in checks)

    if args.json:
        print(
            json.dumps(
                {
                    "root": root.as_posix(),
                    "ready": not failed,
                    "checks": [check.to_dict() for check in checks],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(_render_text(root, checks))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
