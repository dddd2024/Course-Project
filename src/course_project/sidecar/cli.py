from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TextIO

from course_project.sidecar.runtime import PROTOCOL_VERSION, SidecarRuntime
from course_project.sidecar.track_d_backend import TrackDBaselineBackend


def serve_stream(
    runtime: SidecarRuntime,
    instream: TextIO,
    outstream: TextIO,
    errstream: TextIO,
) -> int:
    """Serve newline-delimited JSON requests without mixing diagnostics into stdout."""

    for line_number, raw_line in enumerate(instream, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            decoded = json.loads(line)
            if not isinstance(decoded, dict):
                raise TypeError("top-level JSON value must be an object")
            responses = runtime.handle(decoded)
        except (json.JSONDecodeError, TypeError) as exc:
            print(f"sidecar input error on line {line_number}: {exc}", file=errstream)
            responses = [
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "id": f"invalid-line-{line_number}",
                    "error": {
                        "code": "invalid_input",
                        "message": "stdin line is not a valid sidecar JSON object",
                    },
                }
            ]

        for response in responses:
            outstream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
            outstream.write("\n")
        outstream.flush()

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Course Project Python sidecar")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.environ.get("COURSE_PROJECT_STATE_DIR", ".course-project-state")),
        help="directory used for controlled task results",
    )
    parser.add_argument(
        "--allow-root",
        action="append",
        default=None,
        type=Path,
        help="optional input root; may be supplied multiple times",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    roots = tuple(args.allow_root) if args.allow_root else None
    runtime = SidecarRuntime(
        state_dir=args.state_dir,
        backend=TrackDBaselineBackend(state_dir=args.state_dir),
        allowed_roots=roots,
    )
    return serve_stream(runtime, sys.stdin, sys.stdout, sys.stderr)


if __name__ == "__main__":  # pragma: no cover - exercised through module/script entrypoints
    raise SystemExit(main())
