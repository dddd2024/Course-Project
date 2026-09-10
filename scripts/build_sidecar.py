from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path
from typing import IO, Any

PYINSTALLER_VERSION = "6.22.2"
DPKT_VERSION = "1.9.8"
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


def _installed_distribution_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def _bootstrap_packaging_environment() -> None:
    root = _repo_root()
    requirement = f"{root}[package]"
    print(
        "The Sidecar packaging environment is incomplete; installing the repository "
        f"packaging extra with {sys.executable}",
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
            "Could not install the pinned packaging/runtime dependencies automatically. "
            f"Run {sys.executable} -m pip install -e \"{requirement}\" and retry."
        ) from exc


def _load_pyinstaller() -> Any:
    installed_pyinstaller = _installed_distribution_version("pyinstaller")
    installed_dpkt = _installed_distribution_version("dpkt")
    if installed_pyinstaller != PYINSTALLER_VERSION or installed_dpkt != DPKT_VERSION:
        _bootstrap_packaging_environment()
        installed_pyinstaller = _installed_distribution_version("pyinstaller")
        installed_dpkt = _installed_distribution_version("dpkt")

    try:
        import PyInstaller  # type: ignore[import-not-found]
        import PyInstaller.__main__  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PyInstaller could not be imported after installing the repository packaging extra"
        ) from exc

    if installed_pyinstaller != PYINSTALLER_VERSION or PyInstaller.__version__ != PYINSTALLER_VERSION:
        raise RuntimeError(
            f"PyInstaller {PYINSTALLER_VERSION} is required, found {PyInstaller.__version__}"
        )
    if installed_dpkt != DPKT_VERSION:
        raise RuntimeError(
            f"dpkt {DPKT_VERSION} is required for packaged PCAP support, found {installed_dpkt!r}"
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


def _await_result_ref(stream: IO[str]) -> str:
    for _ in range(32):
        response = _read_response(stream)
        result_ref = response.get("resultRef")
        if isinstance(result_ref, str) and result_ref.startswith("tasks/"):
            return result_ref
    raise RuntimeError("packaged sidecar analyze did not return a controlled resultRef")


def _dtls_pcap_fixture() -> bytes:
    """Return a minimal classic-PCAP Ethernet/IPv4/UDP/DTLS fixture."""
    dtls = b"\x17\xfe\xfd\x00\x01" + b"\x00" * 6 + b"\x00\x04test"
    udp = struct.pack("!HHHH", 50000, 443, 8 + len(dtls), 0) + dtls
    ipv4 = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(udp),
        0,
        0,
        64,
        17,
        0,
        b"\x0a\x00\x00\x01",
        b"\x0a\x00\x00\x02",
    ) + udp
    ethernet = b"\x00" * 6 + b"\x01" * 6 + b"\x08\x00" + ipv4
    global_header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    packet_header = struct.pack("<IIII", 1, 0, len(ethernet), len(ethernet))
    return global_header + packet_header + ethernet


def smoke_sidecar(executable: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="course-project-sidecar-smoke-") as temp:
        temp_root = Path(temp)
        state_dir = temp_root / "state"
        sample = temp_root / "sample.dat"
        sample.write_bytes(b"header\x00payload")
        capture = temp_root / "dtls-capture.dat"
        capture.write_bytes(_dtls_pcap_fixture())
        child_environment = dict(os.environ)
        child_environment.pop("PYTHONHOME", None)
        child_environment.pop("PYTHONPATH", None)
        child_environment["PATH"] = str(
            Path(child_environment.get("SystemRoot", r"C:\Windows")) / "System32"
        )
        process = subprocess.Popen(
            [str(executable), "--state-dir", str(state_dir)],
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
            result_ref = _await_result_ref(process.stdout)
            _write_request(process.stdin, "get_result", {"taskId": task_id}, "package-smoke-result")
            result = _read_response(process.stdout)
            if result.get("resultRef") != result_ref:
                raise RuntimeError("packaged sidecar get_result did not return the analysis result")

            _write_request(
                process.stdin,
                "register_input",
                {"sourceRef": capture.as_posix()},
                "package-pcap-register",
            )
            pcap_registered = _read_response(process.stdout)
            pcap_input_ref = pcap_registered["data"]["inputRef"]
            pcap_task_id = "package-pcap-dtls-analysis"
            _write_request(
                process.stdin,
                "analyze",
                {
                    "inputRef": pcap_input_ref,
                    "mode": "baseline",
                    "stages": ["inspect", "features"],
                    "llmEnabled": False,
                    "verificationEnabled": False,
                    "behaviorEnabled": False,
                    "timeoutSeconds": 30,
                    "optionalDependencyPolicy": "fail",
                },
                pcap_task_id,
            )
            pcap_result_ref = _await_result_ref(process.stdout)
            pcap_result_path = state_dir / pcap_result_ref
            pcap_result = json.loads(pcap_result_path.read_text(encoding="utf-8"))
            metrics = pcap_result.get("metrics", {})
            expected = {
                "preprocessContainer": "pcap",
                "protocolHint": "dtls",
                "genericInferenceGated": True,
                "fieldCandidateCount": 0,
            }
            for key, value in expected.items():
                if metrics.get(key) != value:
                    raise RuntimeError(
                        "packaged Sidecar PCAP/DTLS smoke failed: "
                        f"expected metrics[{key!r}]={value!r}, got {metrics.get(key)!r}"
                    )

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
        help="exercise raw and PCAP/DTLS analysis using the packaged executable",
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
