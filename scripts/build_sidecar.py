from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path
from typing import IO, Any

PYINSTALLER_VERSION = "6.22.2"
SIDECAR_NAME = "course-project-sidecar"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _target_triple(explicit: str | None) -> str:
    completed = subprocess.run(
        ["rustc", "--print", "host-tuple"],
        check=True,
        capture_output=True,
        text=True,
    )
    host = completed.stdout.strip()
    if not host:
        raise RuntimeError("rustc returned an empty host target triple")
    if explicit and explicit != host:
        raise RuntimeError(
            "PyInstaller does not cross-compile; the requested target must match the Rust host "
            f"({host})"
        )
    return explicit or host


def _require_windows_target(target: str) -> None:
    if platform.system() != "Windows" or "windows" not in target:
        raise RuntimeError(
            "D4 currently builds the Windows sidecar on Windows; "
            f"host={platform.system()!r}, target={target!r}"
        )


def _installed_pyinstaller_version() -> str | None:
    try:
        return metadata.version("pyinstaller")
    except metadata.PackageNotFoundError:
        return None


def _bootstrap_pyinstaller() -> None:
    root = _repo_root()
    requirement = f"{root}[package]"
    print(
        f"PyInstaller {PYINSTALLER_VERSION} is required; installing the repository packaging extra "
        f"with {sys.executable}",
        file=sys.stderr,
    )
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-e",
                requirement,
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Could not install the pinned packaging dependency automatically. "
            f"Run {sys.executable} -m pip install -e \"{requirement}\" and retry."
        ) from exc


def _load_pyinstaller() -> Any:
    installed = _installed_pyinstaller_version()
    if installed != PYINSTALLER_VERSION:
        _bootstrap_pyinstaller()
        installed = _installed_pyinstaller_version()

    try:
        import PyInstaller  # type: ignore[import-not-found]
        import PyInstaller.__main__  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PyInstaller could not be imported after installing the repository packaging extra"
        ) from exc

    if installed != PYINSTALLER_VERSION or PyInstaller.__version__ != PYINSTALLER_VERSION:
        raise RuntimeError(
            f"PyInstaller {PYINSTALLER_VERSION} is required, found "
            f"{PyInstaller.__version__}"
        )
    return PyInstaller.__main__


def build_sidecar(target: str) -> Path:
    _require_windows_target(target)
    pyinstaller_main = _load_pyinstaller()
    root = _repo_root()
    build_root = root / "build" / "pyinstaller-sidecar" / target
    dist_dir = build_root / "dist"
    work_dir = build_root / "work"
    spec_dir = build_root / "spec"
    output_dir = root / "apps" / "desktop" / "src-tauri" / "binaries"
    output_dir.mkdir(parents=True, exist_ok=True)

    pyinstaller_main.run(
        [
            "--onefile",
            "--console",
            "--clean",
            "--noconfirm",
            "--noupx",
            "--name",
            SIDECAR_NAME,
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(spec_dir),
            "--paths",
            str(root / "src"),
            str(root / "src" / "course_project" / "sidecar" / "__main__.py"),
        ]
    )

    built = dist_dir / f"{SIDECAR_NAME}.exe"
    if not built.is_file():
        raise RuntimeError(f"PyInstaller did not produce {built}")
    target_path = output_dir / f"{SIDECAR_NAME}-{target}.exe"
    shutil.copy2(built, target_path)
    return target_path


def _write_request(stream: IO[str], method: str, params: dict[str, Any], request_id: str) -> None:
    payload = {
        "protocolVersion": 1,
        "id": request_id,
        "method": method,
        "params": params,
    }
    stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
    stream.flush()


def _read_response(stream: IO[str]) -> dict[str, Any]:
    line = stream.readline()
    if not line:
        raise RuntimeError("packaged sidecar exited before returning a response")
    response = json.loads(line)
    if "error" in response:
        raise RuntimeError(f"packaged sidecar returned an error: {response['error']}")
    return response


def smoke_sidecar(executable: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="course-project-sidecar-smoke-") as temp:
        temp_root = Path(temp)
        sample = temp_root / "sample.dat"
        sample.write_bytes(b"header\x00payload")
        child_environment = dict(os.environ)
        child_environment.pop("PYTHONHOME", None)
        child_environment.pop("PYTHONPATH", None)
        child_environment["PATH"] = str(
            Path(child_environment.get("SystemRoot", r"C:\Windows")) / "System32"
        )
        process = subprocess.Popen(
            [str(executable), "--state-dir", str(temp_root / "state")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=child_environment,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        try:
            _write_request(
                process.stdin,
                "register_input",
                {"sourceRef": sample.as_posix()},
                "package-smoke-register",
            )
            registered = _read_response(process.stdout)
            input_ref = registered["data"]["inputRef"]
            _write_request(
                process.stdin,
                "read_range",
                {"inputRef": input_ref, "offset": 6, "length": 8},
                "package-smoke-range",
            )
            ranged = _read_response(process.stdout)
            if ranged["data"]["actualLength"] != 8:
                raise RuntimeError("packaged sidecar returned an unexpected range length")
            task_id = "package-smoke-analysis"
            _write_request(
                process.stdin,
                "analyze",
                {
                    "inputRef": input_ref,
                    "mode": "baseline",
                    "stages": ["inspect", "features"],
                    "llmEnabled": False,
                    "verificationEnabled": True,
                    "behaviorEnabled": False,
                    "timeoutSeconds": 30,
                    "optionalDependencyPolicy": "degrade",
                },
                task_id,
            )
            result_ref = None
            for _ in range(32):
                response = _read_response(process.stdout)
                if "resultRef" in response:
                    result_ref = response["resultRef"]
                    break
            if not isinstance(result_ref, str) or not result_ref.startswith("tasks/"):
                raise RuntimeError("packaged sidecar analyze did not return a controlled resultRef")
            _write_request(process.stdin, "get_result", {"taskId": task_id}, "package-smoke-result")
            result = _read_response(process.stdout)
            if result.get("resultRef") != result_ref:
                raise RuntimeError("packaged sidecar get_result did not return the analysis result")
            process.stdin.close()
            return_code = process.wait(timeout=15)
            if return_code != 0:
                raise RuntimeError(
                    f"packaged sidecar exited with {return_code}: {process.stderr.read().strip()}"
                )
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the Python analyzer as a target-suffixed Tauri sidecar"
    )
    parser.add_argument("--target", help="Rust target triple; defaults to rustc host-tuple")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="exercise register_input and read_range using the packaged executable",
    )
    parser.add_argument(
        "--smoke-executable",
        type=Path,
        help="smoke an existing packaged or installed Sidecar without rebuilding it",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.smoke_executable is not None:
        if args.smoke or args.target:
            parser.error("--smoke-executable cannot be combined with --smoke or --target")
        executable = args.smoke_executable.expanduser().resolve()
        if not executable.is_file():
            parser.error(f"Sidecar executable does not exist: {executable}")
        smoke_sidecar(executable)
        print(executable)
        return 0
    target = _target_triple(args.target)
    output = build_sidecar(target)
    if args.smoke:
        smoke_sidecar(output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())